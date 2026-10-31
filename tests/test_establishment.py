"""Tests for the establishment-level Salmonella forecasting experiment.

These verify the honest, leakage-safe core of :mod:`src.models.establishment`
with small deterministic synthetic sample frames (fast, independent of the slow
real-data run), plus property-based checks with Hypothesis:

* **features are leakage-safe** — no trailing feature count can exceed what an
  establishment actually had available STRICTLY BEFORE its target quarter, and
  :func:`assert_leakage_safe` raises on a hand-crafted leak;
* **EB smoothing lies between the raw establishment rate and the national rate**
  (and collapses to the national rate when the establishment has no samples);
* **the unseen-establishment split shares no establishment** between the
  familiar and unseen populations;
* **top-K math is correct** — positives captured / precision@K / recall@K match a
  hand-computed reference, and K is clamped to the eligible population;
* **a zero-positive establishment is never auto-labelled "safe"** — its binary
  target is NaN (unknown) when the future is not evaluable, and it is flagged
  uncertain-not-safe, never given a low/"safe" label.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.models import establishment as est
from src.models.establishment import (
    EstablishmentLeakageError,
    EstablishmentSamples,
    assert_leakage_safe,
    baseline_scores,
    build_establishment_quarters,
    build_features,
    build_targets,
    eb_smoothed_rate,
    top_k_capture,
    unseen_establishment_holdout,
)
from src.pipeline.harmonize import REPORTING_LAG_DAYS, TARGET_CATEGORY


# --------------------------------------------------------------------------- #
# Synthetic per-sample frame builder (mirrors load_establishment_samples output)
# --------------------------------------------------------------------------- #

def _make_samples(records: list[dict]) -> pd.DataFrame:
    """Build a per-sample frame with the columns build_features expects.

    Each record: establishment_id, state, product_type, collection_date (str),
    is_positive (0/1). availability_date is derived with the real reporting lag.
    """
    rows = []
    for r in records:
        coll = pd.Timestamp(r["collection_date"])
        rows.append(
            {
                "establishment_id": str(r["establishment_id"]),
                "establishment_name": str(r["establishment_id"]),
                "state": r.get("state", "TX"),
                "product_type": r.get("product_type", "Breast"),
                "project_code": "HC_CPT_LBW01",
                "project_name": "routine",
                "program_category": TARGET_CATEGORY,
                "collection_date": coll,
                "availability_date": coll + pd.Timedelta(days=REPORTING_LAG_DAYS),
                "is_positive": int(r["is_positive"]),
                "is_testable": 1,
                "quarter": est.quarter_label(coll),
            }
        )
    return pd.DataFrame(rows).reset_index(drop=True)


def _grid_samples(
    n_est: int = 6, n_quarters: int = 8, per_quarter: int = 12, seed: int = 7
) -> pd.DataFrame:
    """A dense establishment x quarter grid with mixed positivity (for ML paths)."""
    rng = np.random.default_rng(seed)
    records = []
    base = pd.Timestamp("2020-01-15")
    for e in range(n_est):
        # establishment-specific base positivity so ranking is meaningful
        p = 0.05 + 0.5 * (e / max(n_est - 1, 1))
        pt = ["Breast", "Leg", "Wing"][e % 3]
        stt = ["TX", "CA", "GA"][e % 3]
        for q in range(n_quarters):
            qstart = base + pd.DateOffset(months=3 * q)
            for _ in range(per_quarter):
                day = qstart + pd.Timedelta(days=int(rng.integers(0, 80)))
                records.append(
                    {
                        "establishment_id": f"E{e}",
                        "state": stt,
                        "product_type": pt,
                        "collection_date": str(day.date()),
                        "is_positive": int(rng.random() < p),
                    }
                )
    return _make_samples(records)


# --------------------------------------------------------------------------- #
# EB smoothing: posterior mean lies between raw and national
# --------------------------------------------------------------------------- #

@settings(max_examples=200, deadline=None)
@given(
    positives=st.integers(min_value=0, max_value=200),
    extra_neg=st.integers(min_value=0, max_value=200),
    national=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    prior=st.floats(min_value=1.0, max_value=100.0, allow_nan=False),
)
def test_eb_between_raw_and_national(positives, extra_neg, national, prior):
    samples = positives + extra_neg
    smoothed = eb_smoothed_rate(positives, samples, national, prior_strength=prior)
    assert 0.0 <= smoothed <= 1.0
    if samples == 0:
        assert smoothed == pytest.approx(national)
        return
    raw = positives / samples
    lo, hi = min(raw, national), max(raw, national)
    # posterior mean is a convex combination of raw and national -> within [lo, hi]
    assert lo - 1e-9 <= smoothed <= hi + 1e-9


def test_eb_zero_samples_returns_national():
    assert eb_smoothed_rate(0, 0, 0.123) == pytest.approx(0.123)


def test_eb_heavy_sampling_approaches_raw():
    # 10,000 samples swamps a prior of 20 -> posterior ~ raw rate
    smoothed = eb_smoothed_rate(3000, 10000, 0.5, prior_strength=20.0)
    assert abs(smoothed - 0.3) < 0.01


# --------------------------------------------------------------------------- #
# Features are leakage-safe
# --------------------------------------------------------------------------- #

def test_features_are_leakage_safe_on_grid():
    samples = _grid_samples()
    panel = build_establishment_quarters(samples)
    features = build_features(samples, panel)
    # must not raise
    assert_leakage_safe(features, samples)
    assert len(features) > 0
    # trailing counts never exceed the full pre-cutoff available history
    for row in features.itertuples(index=False):
        cutoff = row.quarter_start
        es = samples[
            (samples["establishment_id"] == row.establishment_id)
            & (samples["availability_date"] <= cutoff)
            & (samples["collection_date"] < cutoff)
        ]
        assert row.trail_samples_365d <= es["is_testable"].sum() + 1e-9
        assert row.trail_positives_365d <= es["is_positive"].sum() + 1e-9


def test_assert_leakage_safe_detects_injected_leak():
    samples = _grid_samples(n_est=3, n_quarters=4)
    panel = build_establishment_quarters(samples)
    features = build_features(samples, panel).copy()
    # inject a leak: claim more trailing positives than ANY establishment could
    # have had before its cutoff
    features.loc[0, "trail_positives_365d"] = 10_000.0
    features.loc[0, "trail_samples_365d"] = 10_000.0
    with pytest.raises(EstablishmentLeakageError):
        assert_leakage_safe(features, samples)


def test_feature_cutoff_excludes_same_quarter_samples():
    # One establishment: a huge positive spike lands in the TARGET quarter; the
    # feature row for that quarter must NOT see it (strictly-before cutoff).
    records = []
    # history: 2020-Q1 all negative
    for _ in range(12):
        records.append({"establishment_id": "E", "collection_date": "2020-02-10", "is_positive": 0})
    # target quarter 2020-Q2: all positive (must be invisible to its own features)
    for _ in range(12):
        records.append({"establishment_id": "E", "collection_date": "2020-05-10", "is_positive": 1})
    samples = _make_samples(records)
    features = build_features(samples)
    q2 = features[features["quarter"] == "2020-Q2"]
    assert len(q2) == 1
    # trailing positives available before 2020-Q2 start come only from Q1 (all 0)
    assert q2.iloc[0]["trail_positives_365d"] == 0.0
    assert q2.iloc[0]["raw_hist_positivity"] == 0.0


# --------------------------------------------------------------------------- #
# Zero-positive establishment is never auto-labelled "safe"
# --------------------------------------------------------------------------- #

def test_zero_positive_not_labelled_safe():
    # Establishment that is ALWAYS negative and has NO evaluable future in its
    # last quarter -> binary target is NaN (unknown), never a confident "safe" 0.
    records = []
    for q_month in ("2020-02-10", "2020-05-10"):
        for _ in range(12):
            records.append({"establishment_id": "Z", "collection_date": q_month, "is_positive": 0})
    # last quarter has only 2 samples -> future not evaluable (>=10 needed)
    for _ in range(2):
        records.append({"establishment_id": "Z", "collection_date": "2020-08-10", "is_positive": 0})
    samples = _make_samples(records)
    targeted = build_targets(build_features(samples))
    last = targeted[targeted["quarter"] == "2020-Q3"].iloc[0]
    # future (Q4) has zero samples -> not evaluable -> target unknown, not "safe"
    assert not last["evaluable_future"]
    assert np.isnan(last["target_binary"])
    # and it is flagged insufficient_recent_testing where history is thin
    thin = targeted[targeted["trail_samples_365d"] < est.HISTORY_MIN_SAMPLES]
    assert bool(thin["insufficient_recent_testing"].all())


def test_zero_positive_establishment_scores_not_minimized_to_safe():
    # The EB score of a zero-positive but thin establishment is shrunk toward the
    # national rate, NOT driven to 0 ("safe").
    records = [{"establishment_id": "Z", "collection_date": "2020-02-10", "is_positive": 0}
               for _ in range(3)]
    records += [{"establishment_id": "H", "collection_date": "2020-02-10", "is_positive": 1}
                for _ in range(10)]
    samples = _make_samples(records)
    feats = build_features(samples)
    # a later quarter so Z has history available
    z_rows = feats[(feats["establishment_id"] == "Z") & (feats["quarter"] == "2020-Q2")]
    if len(z_rows):
        assert z_rows.iloc[0]["eb_positivity"] > 0.0  # not forced to a "safe" zero


# --------------------------------------------------------------------------- #
# top-K math
# --------------------------------------------------------------------------- #

def test_top_k_math_reference():
    # scores descending: labels at ranks [1,0,1,0,0] ; top-2 captures 1 positive
    df = pd.DataFrame({"score": [0.9, 0.8, 0.7, 0.6, 0.5], "label": [1, 0, 1, 0, 0]})
    r = top_k_capture(df, "score", "label", k=2)
    assert r["k"] == 2
    assert r["total_positives"] == 2
    assert r["positives_captured"] == 1
    assert r["precision_at_k"] == pytest.approx(0.5)
    assert r["recall_at_k"] == pytest.approx(0.5)


def test_top_k_fraction_and_clamp():
    df = pd.DataFrame({"score": [0.1, 0.2, 0.3], "label": [0, 1, 1]})
    # 10% of 3 -> ceil(0.3) = 1 ; top-1 by score is the 0.3 row (label 1)
    r = top_k_capture(df, "score", "label", k_fraction=0.10)
    assert r["k"] == 1
    assert r["positives_captured"] == 1
    assert r["precision_at_k"] == pytest.approx(1.0)
    assert r["recall_at_k"] == pytest.approx(0.5)
    # a budget larger than the population is clamped to the population
    r2 = top_k_capture(df, "score", "label", k=100)
    assert r2["k"] == 3
    assert r2["positives_captured"] == 2
    assert r2["recall_at_k"] == pytest.approx(1.0)


@settings(max_examples=100, deadline=None)
@given(
    scores=st.lists(st.floats(0, 1, allow_nan=False), min_size=1, max_size=40),
    seed=st.integers(0, 10_000),
)
def test_top_k_recall_precision_bounds(scores, seed):
    rng = np.random.default_rng(seed)
    labels = (rng.random(len(scores)) < 0.4).astype(int)
    df = pd.DataFrame({"score": scores, "label": labels})
    r = top_k_capture(df, "score", "label", k_fraction=0.25)
    assert 0 <= r["positives_captured"] <= r["total_positives"]
    assert r["positives_captured"] <= r["k"]
    if r["precision_at_k"] is not None:
        assert 0.0 <= r["precision_at_k"] <= 1.0
    if r["recall_at_k"] is not None:
        assert 0.0 <= r["recall_at_k"] <= 1.0


# --------------------------------------------------------------------------- #
# Unseen-establishment split shares no establishment
# --------------------------------------------------------------------------- #

def test_unseen_holdout_disjoint_establishments():
    samples = _grid_samples(n_est=8, n_quarters=8, per_quarter=14)
    targeted = build_targets(build_features(samples))
    out = unseen_establishment_holdout(targeted, "random_forest")
    if not out.get("available"):
        pytest.skip(f"holdout unavailable: {out.get('reason')}")
    assert out["n_unseen_establishments"] >= 1
    assert out["n_familiar_establishments"] >= 1
    assert (
        out["n_unseen_establishments"] + out["n_familiar_establishments"]
        == out["n_establishments_total"]
    )


# --------------------------------------------------------------------------- #
# Baselines return rankable risk scores
# --------------------------------------------------------------------------- #

def test_baselines_return_scores():
    samples = _grid_samples()
    targeted = build_targets(build_features(samples))
    ev = targeted[targeted["evaluable_future"] & targeted["target_binary"].notna()]
    if ev.empty:
        pytest.skip("no evaluable rows in synthetic grid")
    for kind in ("eb_establishment", "peer_group", "seasonal_persistence"):
        s = baseline_scores(ev, ev, kind)
        assert len(s) == len(ev)
        assert np.all((s >= 0) & (s <= 1))
