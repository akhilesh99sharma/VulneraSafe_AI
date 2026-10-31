"""Tests for time-aware validation and uncertainty (Task 3.7, Req 8.1-8.7).

Covers the five required cases:

(a) rolling-origin produces >= 3 origins, each with its train window ending
    STRICTLY before its evaluation block begins (Req 8.1);
(b) bootstrap 95% intervals bracket the point estimate (lo <= point <= hi,
    Req 8.3);
(c) calibration bins lie within [0, 1] and the bin edges are monotone (Req 8.3);
(d) top-K selects exactly K (or all when K > n) and recall@K is <= 1 (Req 8.5);
(e) a slice with too few positives is marked unavailable, never fabricated
    (Req 8.4 / 8.7).

Unit tests run on a small deterministic synthetic model table / prediction
frame so the logic is verified fast and independently of the real data run; a
data-backed smoke check runs against the exported predictions when present.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.pipeline import target as tg
from src.pipeline.target import feature_columns
from src.models.baseline import labelable_frame
from src.models.integrated import INTEGRATED_MODEL_NAMES
from src.models import validation as val
from src.models.validation import (
    ROLLING_ORIGINS,
    bootstrap_intervals,
    calibration_curve_points,
    disaggregate,
    fp_fn_analysis,
    point_metrics,
    rolling_origin_validation,
    state_holdout_validation,
    top_k_budget,
    validate_pathogen,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
PROCESSED = REPO_ROOT / "data" / "processed"
MODELS = PROCESSED / "models"


# --------------------------------------------------------------------------- #
# Synthetic builders
# --------------------------------------------------------------------------- #

def _monthly_periods(n: int, start_year: int = 2015) -> list[str]:
    out: list[str] = []
    y, m = start_year, 1
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def _make_model_table(
    n_periods: int = 48,
    states=("AA", "BB", "CC", "DD"),
    *,
    positive_target: float = 0.5,
    seed: int = 7,
) -> pd.DataFrame:
    """Deterministic labelable (state, period) model table with real signal."""
    rng = np.random.default_rng(seed)
    periods = _monthly_periods(n_periods)
    regions = {"AA": "South", "BB": "West", "CC": "Midwest", "DD": "Northeast"}
    bias = float(np.log(positive_target / (1.0 - positive_target)))
    rows: list[dict] = []
    for state in states:
        for i, period in enumerate(periods):
            lag1 = float(rng.uniform(0.0, 0.3))
            trailing = float(rng.uniform(0.0, 0.3))
            prob = 1.0 / (1.0 + np.exp(-(bias + 6.0 * (lag1 - trailing))))
            y = int(rng.uniform() < prob)
            rows.append(
                {
                    "pathogen": "Test",
                    "state": state,
                    "period": period,
                    "period_start": tg.period_start(period),
                    "cutoff": tg.period_start(period),
                    "resolution": "monthly",
                    "outcome_routine_samples": 100.0,
                    "outcome_routine_positives": 10.0,
                    "outcome_routine_positivity_rate": 0.1,
                    "routine_positivity_lag1": lag1,
                    "routine_positivity_trailing12m_mean": trailing,
                    "routine_samples_lag1": float(rng.integers(50, 150)),
                    "season_sin": np.sin(2 * np.pi * (i % 12) / 12),
                    "season_cos": np.cos(2 * np.pi * (i % 12) / 12),
                    "period_of_year": (i % 12) + 1,
                    "geo_state": state,
                    "geo_region": regions[state],
                    "baseline": trailing,
                    "y_next_positivity": 0.1,
                    "next_routine_samples": 100.0,
                    "next_period": period,
                    "labelable": True,
                    "exclusion_reason": "",
                    "y_elevated": pd.array([y], dtype="Int64")[0],
                    # v2 label/target bookkeeping (mirrors real model_* schema)
                    "labelable_v2": True,
                    "y_elevated_v2": pd.array([y], dtype="Int64")[0],
                    "smoothed_next_positivity": 0.1,
                    "next_routine_positives": 10.0,
                    "v2_threshold": 0.2,
                    "exclusion_reason_v2": "",
                }
            )
    df = pd.DataFrame(rows)
    df["y_elevated"] = df["y_elevated"].astype("Int64")
    df["y_elevated_v2"] = df["y_elevated_v2"].astype("Int64")
    return df


def _make_preds(n: int = 400, *, seed: int = 3) -> pd.DataFrame:
    """A deterministic exported-style prediction frame."""
    rng = np.random.default_rng(seed)
    states = np.array(["AA", "BB", "CC", "DD"])
    periods = np.array(_monthly_periods(20))
    y = rng.integers(0, 2, size=n)
    # a score that is correlated with y so metrics aren't degenerate
    score = np.clip(0.3 * rng.random(n) + 0.4 * y + 0.15, 0.0, 1.0)
    return pd.DataFrame(
        {
            "pathogen": "Test",
            "state": rng.choice(states, size=n),
            "period": rng.choice(periods, size=n),
            "y_true": y,
            "proba_random_forest": score,
        }
    )


# --------------------------------------------------------------------------- #
# (a) Rolling-origin: >= 3 origins, train strictly before eval block
# --------------------------------------------------------------------------- #

def test_rolling_origin_produces_at_least_three_ordered_origins():
    df = labelable_frame(_make_model_table(n_periods=48))
    feats = feature_columns(df)
    res = rolling_origin_validation(df, "random_forest", feats, n_origins=ROLLING_ORIGINS)

    assert res["n_origins_produced"] >= 3
    # period -> calendar start lookup
    start_of = {
        p: s
        for p, s in zip(df["period"].to_numpy(), pd.to_datetime(df["period_start"]).to_numpy())
    }
    for origin in res["origins"]:
        train_end = origin["train_end"]
        eval_start = origin["eval_start"]
        # every training period ends strictly before the eval block begins
        assert start_of[train_end] < start_of[eval_start]


# --------------------------------------------------------------------------- #
# (b) Bootstrap intervals bracket the point estimate
# --------------------------------------------------------------------------- #

def test_bootstrap_intervals_bracket_point_estimate():
    preds = _make_preds(n=400)
    y = preds["y_true"].to_numpy()
    s = preds["proba_random_forest"].to_numpy()
    boot = bootstrap_intervals(y, s, n_draws=200)

    saw_available = False
    for metric, iv in boot["intervals"].items():
        if not iv["available"]:
            continue
        saw_available = True
        assert iv["lo"] <= iv["point"] <= iv["hi"], f"{metric}: {iv}"
    assert saw_available, "expected at least one metric with an available interval"


def test_bootstrap_unavailable_recorded_not_fabricated_on_single_class():
    # A single-class slice cannot yield PR-AUC / ROC-AUC -> recorded unavailable.
    y = np.ones(50)
    s = np.linspace(0.1, 0.9, 50)
    boot = bootstrap_intervals(y, s, n_draws=100)
    for metric in ("pr_auc", "roc_auc"):
        iv = boot["intervals"][metric]
        assert iv["available"] is False
        assert iv["lo"] is None and iv["hi"] is None


# --------------------------------------------------------------------------- #
# (c) Calibration bins within [0, 1] and monotone edges
# --------------------------------------------------------------------------- #

def test_calibration_bins_in_unit_range_and_monotone_edges():
    preds = _make_preds(n=400)
    cal = calibration_curve_points(
        preds["y_true"].to_numpy(), preds["proba_random_forest"].to_numpy()
    )
    edges = cal["bin_edges"]
    # edges strictly increasing and spanning [0, 1]
    assert edges[0] == 0.0 and edges[-1] == 1.0
    assert all(edges[i] < edges[i + 1] for i in range(len(edges) - 1))
    for pt in cal["points"]:
        assert 0.0 <= pt["bin_lower"] < pt["bin_upper"] <= 1.0
        if pt["count"]:
            assert 0.0 <= pt["mean_predicted"] <= 1.0
            assert 0.0 <= pt["observed_frequency"] <= 1.0


# --------------------------------------------------------------------------- #
# (d) top-K selects exactly K (or all if K > n) and recall@K <= 1
# --------------------------------------------------------------------------- #

def test_top_k_selects_exactly_k_and_recall_bounded():
    preds = _make_preds(n=200)
    y = preds["y_true"].to_numpy()
    s = preds["proba_random_forest"].to_numpy()

    tk = top_k_budget(y, s, k=25)
    assert tk["k"] == 25
    assert tk["positives_captured"] <= tk["k"]
    assert 0.0 <= tk["precision_at_k"] <= 1.0
    if tk["recall_at_k"] is not None:
        assert 0.0 <= tk["recall_at_k"] <= 1.0

    # K greater than n clamps to all units
    tk_all = top_k_budget(y, s, k=10_000)
    assert tk_all["k"] == len(y)
    assert tk_all["positives_captured"] == int(y.sum())
    if tk_all["recall_at_k"] is not None:
        assert tk_all["recall_at_k"] == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# (e) Too-few-positives slice marked unavailable, not fabricated
# --------------------------------------------------------------------------- #

def test_disaggregation_marks_thin_slice_unavailable():
    # Build a frame where one state ("ZZ") has only negatives -> single class ->
    # its slice must be marked unavailable (not fabricated).
    base = _make_preds(n=200)
    zz = pd.DataFrame(
        {
            "pathogen": "Test",
            "state": "ZZ",
            "period": "2015-01",
            "y_true": np.zeros(8, dtype=int),
            "proba_random_forest": np.linspace(0.1, 0.4, 8),
        }
    )
    preds = pd.concat([base, zz], ignore_index=True)
    dis = disaggregate(preds, "proba_random_forest")

    assert dis["by_region"]["ZZ"]["available"] is False
    assert "reason" in dis["by_region"]["ZZ"]
    # the unavailable slice carries no fabricated metric values
    assert "pr_auc" not in dis["by_region"]["ZZ"]
    assert dis["n_regions_unavailable"] >= 1


def test_point_metrics_single_class_returns_none_not_fabricated():
    y = np.zeros(20)
    s = np.linspace(0.0, 1.0, 20)
    m = point_metrics(y, s)
    assert m["pr_auc"] is None
    assert m["roc_auc"] is None


# --------------------------------------------------------------------------- #
# FP/FN sanity + state-holdout limitation documented
# --------------------------------------------------------------------------- #

def test_fp_fn_counts_consistent():
    y = np.array([1, 1, 0, 0, 1, 0])
    s = np.array([0.9, 0.2, 0.8, 0.1, 0.6, 0.4])
    r = fp_fn_analysis(y, s, threshold=0.5)
    assert r["tp"] + r["fn"] == r["actual_positives"]
    assert r["tn"] + r["fp"] == r["actual_negatives"]
    assert r["tp"] + r["fp"] + r["tn"] + r["fn"] == len(y)


def test_state_holdout_documents_limitation():
    df = labelable_frame(_make_model_table(n_periods=36))
    feats = feature_columns(df)
    res = state_holdout_validation(df, "random_forest", feats)
    assert "limitation" in res
    assert "geographic-holdout proxy" in res["limitation"]
    if res.get("available"):
        assert res["kind"] == "state_level_geographic_holdout_proxy"
        assert len(res["held_out_states"]) >= 1


# --------------------------------------------------------------------------- #
# Data-backed smoke check against the exported predictions (when present)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("pathogen", ["Salmonella", "Listeria", "STEC"])
def test_real_predictions_validation_smoke(pathogen):
    slug = {"Salmonella": "salmonella", "Listeria": "listeria", "STEC": "stec"}[pathogen]
    if not (MODELS / f"preds_{slug}.parquet").exists() and not (
        MODELS / f"preds_{slug}.csv"
    ).exists():
        pytest.skip(f"exported predictions for {pathogen} not present")

    res = validate_pathogen(pathogen, write_artifacts=False, n_bootstrap=100)
    assert res["best_model"] in res["models_available"]
    roll = res["primary_chronological"]["rolling_origin"]
    assert roll["n_origins_produced"] >= 3
    # intervals, where available, bracket their point estimate
    iv = res["primary_chronological"]["single_split"]["bootstrap_intervals"]["intervals"]
    for metric, record in iv.items():
        if record["available"]:
            assert record["lo"] <= record["point"] <= record["hi"]
    # secondary holdout is reported separately and documents its limitation
    assert "secondary_state_holdout" in res
    assert "limitation" in res["secondary_state_holdout"]
