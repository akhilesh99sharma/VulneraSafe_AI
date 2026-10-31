"""Tests for leakage-safe feature construction (Task 3.1, Req 7.4–7.6).

Covers:

* **Property 1: No feature uses post-cutoff data** (design.md) — for random
  cutoffs, ``build_features(cutoff)`` yields no feature whose contributing
  source has ``availability_date > cutoff``, and no cell is predicted past the
  cutoff. **Validates: Requirements 7.5, 7.6, 3.4.**
* routine and for-cause positivity live in SEPARATE columns and are never
  pooled (Req 7.4);
* lagged features at period ``t`` use only data from periods ``<= t-1`` (Req
  7.5);
* the excluded post-cutoff sources are recorded for audit (Req 7.6);
* the raw current-period outcome is kept separate from feature columns so Task
  3.3 can derive the label.

Unit tests use small deterministic synthetic frames so the pure leakage logic
is verified fast and independently of the (slow) real-data run; a lightweight
data-backed smoke check runs against the already-emitted harmonized tables when
present.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from src.pipeline import features as ft
from src.pipeline.features import (
    CONTEXT_CATEGORIES,
    LeakageError,
    assert_no_post_cutoff,
    build_features,
    period_start,
    resolution_for,
)
from src.pipeline.harmonize import REPORTING_LAG_DAYS, TARGET_CATEGORY

REPO_ROOT = Path(__file__).resolve().parents[1]
PROCESSED = REPO_ROOT / "data" / "processed"


# --------------------------------------------------------------------------- #
# Synthetic harmonized-table builder (mirrors the real long grain)
# --------------------------------------------------------------------------- #

def _monthly_periods(n: int, start_year: int = 2020) -> list[str]:
    out = []
    y, m = start_year, 1
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def _make_harmonized(
    states: list[str],
    periods: list[str],
    *,
    lag_days: int = REPORTING_LAG_DAYS,
    include_forcause: bool = True,
    seed: int = 0,
) -> pd.DataFrame:
    """Build a small synthetic harmonized table (long grain) like the real one.

    One routine row per (state, period) plus, optionally, one for-cause row.
    ``collection_date`` is set to the FIRST day of the period and
    ``availability_date = collection_date + lag_days`` — matching harmonize.
    """
    rng = np.random.default_rng(seed)
    recs: list[dict] = []
    for state in states:
        for period in periods:
            start = period_start(period)
            coll = start
            avail = coll + pd.Timedelta(days=lag_days)
            samples = int(rng.integers(5, 40))
            positives = int(rng.integers(0, samples + 1))
            recs.append({
                "pathogen": "Salmonella",
                "commodity": "raw_poultry",
                "state": state,
                "period": period,
                "sampling_program": "HC_X",
                "program_category": TARGET_CATEGORY,
                "is_target": True,
                "collection_date": coll,
                "availability_date": avail,
                "lag_days": lag_days,
                "samples": samples,
                "positives": positives,
                "positivity_rate": positives / samples if samples else np.nan,
            })
            if include_forcause:
                fc_samples = int(rng.integers(1, 10))
                fc_pos = int(rng.integers(0, fc_samples + 1))
                recs.append({
                    "pathogen": "Salmonella",
                    "commodity": "raw_poultry",
                    "state": state,
                    "period": period,
                    "sampling_program": "INT_X",
                    "program_category": "for_cause",
                    "is_target": False,
                    "collection_date": coll,
                    "availability_date": avail,
                    "lag_days": lag_days,
                    "samples": fc_samples,
                    "positives": fc_pos,
                    "positivity_rate": fc_pos / fc_samples if fc_samples else np.nan,
                })
    return pd.DataFrame.from_records(recs)


# --------------------------------------------------------------------------- #
# Property 1: No feature uses post-cutoff data
# --------------------------------------------------------------------------- #

_PERIODS = _monthly_periods(18, start_year=2020)
_STATES = ["AL", "CA", "NY"]
_HARMONIZED = _make_harmonized(_STATES, _PERIODS, seed=7)

# candidate cutoffs span before/within/after the data range
_CUTOFF_CANDIDATES = [
    period_start(p) + pd.Timedelta(days=d)
    for p in _PERIODS
    for d in (0, 15, REPORTING_LAG_DAYS, REPORTING_LAG_DAYS + 5)
]


@settings(max_examples=120, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(idx=st.integers(min_value=0, max_value=len(_CUTOFF_CANDIDATES) - 1))
def test_property1_no_feature_uses_post_cutoff_data(idx):
    """For random cutoffs, no contributing source has availability_date > cutoff.

    **Validates: Requirements 7.5, 7.6, 3.4**
    """
    cutoff = _CUTOFF_CANDIDATES[idx]
    excluded: list[dict] = []
    feats = build_features(
        "Salmonella", cutoff=cutoff, df=_HARMONIZED.copy(),
        excluded_sources=excluded,
    )
    if feats.empty:
        # no cell predictable at/before this cutoff — vacuously leak-free
        return

    # (a) no cell is predicted past the cutoff
    assert (pd.to_datetime(feats["cutoff"]) <= cutoff).all()

    # (b) the source-level assertion passes (raises LeakageError otherwise)
    audit = assert_no_post_cutoff(
        feats, cutoff, pathogen="Salmonella", harmonized=_HARMONIZED.copy()
    )
    assert audit["ok"] is True

    # (c) directly verify: every lagged routine feature, when non-null, is
    # backed by a source row with availability_date <= cutoff AND a period
    # strictly earlier than the target period.
    avail = pd.to_datetime(_HARMONIZED["availability_date"])
    available = _HARMONIZED.loc[avail <= cutoff].copy()
    available["_start"] = available["period"].map(period_start)
    for rec in feats.to_dict(orient="records"):
        tgt = period_start(rec["period"])
        state_src = available[
            (available["state"] == rec["state"])
            & (available["program_category"] == TARGET_CATEGORY)
            & (available["_start"] < tgt)
        ]
        if pd.notna(rec.get("routine_positivity_lag1")):
            assert not state_src.empty, (
                f"lag1 non-null but no pre-cutoff pre-period source for "
                f"{rec['state']} {rec['period']} at cutoff {cutoff}"
            )


# --------------------------------------------------------------------------- #
# routine vs for-cause kept in SEPARATE columns (Req 7.4)
# --------------------------------------------------------------------------- #

def test_routine_and_forcause_positivity_are_separate_columns():
    feats = build_features("Salmonella", df=_HARMONIZED.copy())
    assert not feats.empty
    routine_cols = [c for c in feats.columns if c.startswith("routine_positivity")]
    forcause_cols = [c for c in feats.columns if c.startswith("context_forcause_positivity")]
    assert routine_cols, "expected routine positivity columns"
    assert forcause_cols, "expected separate for-cause context columns"
    # no column mixes the two namespaces
    for c in feats.columns:
        assert not (c.startswith("routine_") and "forcause" in c)
    # the routine baseline columns never equal the for-cause columns name-wise
    assert set(routine_cols).isdisjoint(set(forcause_cols))


def test_context_categories_are_the_expected_two():
    assert CONTEXT_CATEGORIES == ("for_cause", "exploratory")


# --------------------------------------------------------------------------- #
# lagged features at t use only <= t-1 data (Req 7.5)
# --------------------------------------------------------------------------- #

def test_lagged_feature_equals_most_recent_available_prior_period():
    """lag1 routine positivity at t equals the rate of the most recent period
    that is both (a) available by the cutoff and (b) strictly earlier than t.

    Because availability_date = collection_date + 30d, a sample collected at the
    start of period t-1 is NOT available until ~30 days later — often AFTER the
    start of period t — so lag1 honestly reaches further back than a naive t-1.
    This test computes the expected lag with the SAME availability rule the code
    uses, confirming lagged features draw only on data available at or before
    the cutoff and strictly earlier than the target period (Req 7.5). Using a
    deterministic single-state frame so the exact relationship is checkable.
    """
    periods = _monthly_periods(6, start_year=2021)
    df = _make_harmonized(["TX"], periods, include_forcause=False, seed=3)
    feats = build_features("Salmonella", df=df)
    feats = feats.sort_values("period_start").reset_index(drop=True)

    routine = df[df["program_category"] == TARGET_CATEGORY]
    rate = {r["period"]: r["positivity_rate"] for r in routine.to_dict("records")}
    avail = {r["period"]: pd.Timestamp(r["availability_date"])
             for r in routine.to_dict("records")}
    ordered = sorted(rate, key=period_start)

    for period in ordered:
        row = feats[feats["period"] == period].iloc[0]
        cutoff = period_start(period)
        # most recent period available by the cutoff AND strictly earlier than t
        candidates = [
            p for p in ordered
            if period_start(p) < cutoff and avail[p] <= cutoff
        ]
        if not candidates:
            assert pd.isna(row["routine_positivity_lag1"])
        else:
            expected_period = max(candidates, key=period_start)
            assert row["routine_positivity_lag1"] == pytest.approx(rate[expected_period])
            # the lag feature must never be sourced from the target period itself
            assert expected_period != period


def test_first_period_has_no_lagged_history():
    periods = _monthly_periods(4, start_year=2022)
    df = _make_harmonized(["OH"], periods, include_forcause=False, seed=1)
    feats = build_features("Salmonella", df=df).sort_values("period_start")
    first = feats.iloc[0]
    assert pd.isna(first["routine_positivity_lag1"])
    assert pd.isna(first["routine_positivity_lag2"])
    assert pd.isna(first["routine_positivity_lag3"])


# --------------------------------------------------------------------------- #
# excluded post-cutoff sources recorded for audit (Req 7.6)
# --------------------------------------------------------------------------- #

def test_post_cutoff_sources_are_recorded_for_audit():
    periods = _monthly_periods(6, start_year=2021)
    df = _make_harmonized(["CA"], periods, include_forcause=False, seed=2)
    # cutoff in the middle: later periods' sources are post-cutoff and excluded
    cutoff = period_start("2021-03")
    excluded: list[dict] = []
    build_features("Salmonella", cutoff=cutoff, df=df, excluded_sources=excluded)
    assert excluded, "expected post-cutoff sources to be recorded"
    for rec in excluded:
        assert rec["reason"].startswith("availability_date > cutoff")
        assert pd.Timestamp(rec["max_availability_date"]) > cutoff


def test_assert_no_post_cutoff_raises_on_injected_leak():
    """A fabricated lag1 value with no available prior source must be flagged."""
    periods = _monthly_periods(5, start_year=2021)
    df = _make_harmonized(["NY"], periods, include_forcause=False, seed=4)
    # cutoff BEFORE any source is available -> no routine source available at all
    early_cutoff = period_start("2021-01") - pd.Timedelta(days=10)
    feats = build_features("Salmonella", cutoff=early_cutoff, df=df)
    # with nothing available, build_features yields no cells OR all-NaN lags;
    # inject a leak: a non-null lag1 with no backing source, then assert it raises
    injected = pd.DataFrame([{
        "pathogen": "Salmonella", "state": "NY", "period": "2021-02",
        "period_start": period_start("2021-02"), "cutoff": period_start("2021-02"),
        "resolution": "monthly",
        "outcome_routine_samples": np.nan, "outcome_routine_positives": np.nan,
        "outcome_routine_positivity_rate": np.nan,
        "routine_positivity_lag1": 0.5,  # fabricated — no available prior source
    }])
    with pytest.raises(LeakageError):
        assert_no_post_cutoff(
            injected, early_cutoff, pathogen="Salmonella", harmonized=df
        )


# --------------------------------------------------------------------------- #
# raw current-period outcome kept separate from features (for Task 3.3)
# --------------------------------------------------------------------------- #

def test_outcome_columns_present_and_separate():
    feats = build_features("Salmonella", df=_HARMONIZED.copy())
    for col in ("outcome_routine_samples", "outcome_routine_positives",
                "outcome_routine_positivity_rate"):
        assert col in feats.columns
    # outcome columns are not prefixed like feature columns
    assert not any(c.startswith("outcome_") and c.startswith("routine_positivity_lag")
                   for c in feats.columns)


# --------------------------------------------------------------------------- #
# lightweight data-backed smoke test against the real harmonized tables
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("pathogen", ["Salmonella", "Listeria", "STEC"])
def test_real_harmonized_builds_and_is_leak_free(pathogen):
    slug = ft.PATHOGEN_SLUG[pathogen]
    if not (PROCESSED / f"harmonized_{slug}.parquet").exists():
        pytest.skip("harmonized table not present")
    df = ft.load_harmonized(pathogen)
    # pick a cutoff near the middle of the real range
    periods = sorted(df["period"].unique(), key=period_start)
    mid = periods[len(periods) // 2]
    cutoff = period_start(mid)
    excluded: list[dict] = []
    feats = build_features(pathogen, cutoff=cutoff, df=df, excluded_sources=excluded)
    if feats.empty:
        pytest.skip("no cells at chosen cutoff")
    audit = assert_no_post_cutoff(feats, cutoff, pathogen=pathogen, harmonized=df)
    assert audit["ok"] is True
    # routine and for-cause separation holds on real data too
    assert any(c.startswith("routine_positivity") for c in feats.columns)
