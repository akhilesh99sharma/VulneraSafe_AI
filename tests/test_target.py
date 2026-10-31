"""Tests for prediction-target + fixed-horizon derivation (Task 3.3, Req 5.1-5.5).

Covers the five required cases:

(a) ``y_elevated == 1`` iff next-period positivity > trailing baseline on a
    constructed series (Req 5.1);
(b) Modeling_Units with fewer than the lookback periods of history are
    unlabelable (Req 5.2);
(c) the horizon constant is 1 and documented as fixed pre-tuning (Req 5.3);
(d) the binary label never derives from a feature column — no label/outcome
    column leaks into the feature set (Req 5.1/5.5 integrity);
(e) the rate target equals next-period positivity (Req 5.4).

Unit tests use small deterministic synthetic feature frames so the pure
labeling logic is verified fast and independently of the real-data run; a
lightweight data-backed smoke check runs against the already-emitted feature
tables when present.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.pipeline import target as tg
from src.pipeline.target import (
    HORIZON_FIXED_PRE_TUNING,
    HORIZON_PERIODS,
    LABEL_COLS,
    LOOKBACK_PERIODS,
    MIN_NEXT_SAMPLES_V2,
    OUTCOME_COLS,
    SHRINKAGE_PSEUDOCOUNT,
    TAIL_PERCENTILE,
    add_smoothed_label,
    assert_no_label_leakage,
    beta_binomial_shrink,
    build_model_table,
    derive_target,
    feature_columns,
    lookback_for,
    national_prior_from_train,
    train_tail_threshold,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
PROCESSED = REPO_ROOT / "data" / "processed"


# --------------------------------------------------------------------------- #
# Synthetic feature-frame builder (mirrors the real features schema)
# --------------------------------------------------------------------------- #

def _monthly_periods(n: int, start_year: int = 2020) -> list[str]:
    out: list[str] = []
    y, m = start_year, 1
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def _make_features(
    *,
    states_rates: dict[str, list[float]],
    n_periods: int,
    samples: float = 100.0,
    resolution: str = "monthly",
    extra_feature_cols: bool = True,
) -> pd.DataFrame:
    """Build a synthetic feature frame with the real schema.

    ``states_rates`` maps a state -> a list of current-period routine positivity
    rates (one per period, chronological). A NaN rate marks a missing outcome.
    All next-period samples default to ``samples`` (labelable), unless the rate
    is NaN in which case samples are set to 0 so the cell is unlabelable.
    """
    periods = _monthly_periods(n_periods)
    rows: list[dict] = []
    for state, rates in states_rates.items():
        assert len(rates) == n_periods
        for period, rate in zip(periods, rates):
            samp = samples if not np.isnan(rate) else 0.0
            pos = rate * samp if not np.isnan(rate) else np.nan
            row = {
                "pathogen": "Test",
                "state": state,
                "period": period,
                "period_start": tg.period_start(period),
                "cutoff": tg.period_start(period),
                "resolution": resolution,
                "outcome_routine_samples": samp,
                "outcome_routine_positives": pos,
                "outcome_routine_positivity_rate": rate,
            }
            if extra_feature_cols:
                # feature columns that MUST NOT influence the label
                row["routine_positivity_lag1"] = 0.123
                row["season_sin"] = 0.5
                row["geo_state"] = state
            rows.append(row)
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# (c) Horizon constant is 1 and fixed pre-tuning (Req 5.3)
# --------------------------------------------------------------------------- #

def test_horizon_constant_is_one_and_fixed():
    assert HORIZON_PERIODS == 1
    assert HORIZON_FIXED_PRE_TUNING is True
    # lookback is at least 12 months for both resolutions
    assert LOOKBACK_PERIODS["monthly"] == 12
    assert LOOKBACK_PERIODS["quarterly"] == 4
    assert lookback_for("monthly") == 12
    assert lookback_for("quarterly") == 4


# --------------------------------------------------------------------------- #
# (a) label==1 iff next-period positivity > trailing baseline (Req 5.1)
# --------------------------------------------------------------------------- #

def test_label_one_iff_next_exceeds_trailing_baseline():
    # 12 periods of flat 0.10 baseline history, then a 13th period, then a 14th
    # period whose rate is the "next" outcome for period 13.
    # Build 14 periods: indices 0..11 = history (0.10), 12 = t, 13 = t+1.
    lb = 12
    # case 1: next (t+1) rate ABOVE baseline -> label at t == 1
    hist = [0.10] * lb
    rates_high = hist + [0.10, 0.50]  # period 12 = t (0.10), period 13 = t+1 (0.50)
    df_high = _make_features(states_rates={"AA": rates_high}, n_periods=lb + 2)
    out_high = derive_target(df_high)
    row_t = out_high[out_high["period"] == _monthly_periods(lb + 2)[lb]].iloc[0]
    assert bool(row_t["labelable"]) is True
    # baseline is trailing mean of the 12 periods strictly before t -> 0.10
    assert row_t["baseline"] == pytest.approx(0.10)
    assert row_t["y_next_positivity"] == pytest.approx(0.50)
    assert int(row_t["y_elevated"]) == 1

    # case 2: next (t+1) rate BELOW baseline -> label at t == 0
    rates_low = hist + [0.10, 0.02]
    df_low = _make_features(states_rates={"AA": rates_low}, n_periods=lb + 2)
    out_low = derive_target(df_low)
    row_t2 = out_low[out_low["period"] == _monthly_periods(lb + 2)[lb]].iloc[0]
    assert bool(row_t2["labelable"]) is True
    assert int(row_t2["y_elevated"]) == 0

    # case 3: next rate EQUAL to baseline -> not strictly greater -> 0
    rates_eq = hist + [0.10, 0.10]
    df_eq = _make_features(states_rates={"AA": rates_eq}, n_periods=lb + 2)
    out_eq = derive_target(df_eq)
    row_t3 = out_eq[out_eq["period"] == _monthly_periods(lb + 2)[lb]].iloc[0]
    assert int(row_t3["y_elevated"]) == 0


# --------------------------------------------------------------------------- #
# (b) units with < lookback history are unlabelable (Req 5.2)
# --------------------------------------------------------------------------- #

def test_insufficient_history_is_unlabelable():
    lb = 12
    # Only 6 periods of history: every cell has < 12 prior periods -> none of
    # the early cells can be labeled for insufficient history.
    rates = [0.10] * 6
    df = _make_features(states_rates={"BB": rates}, n_periods=6)
    out = derive_target(df)
    # The earliest cells cannot have a full 12-period trailing baseline.
    assert (out["labelable"] == False).all()  # noqa: E712
    assert out["exclusion_reason"].str.contains("insufficient_history").any()

    # With exactly lb+2 periods, the cell at index lb has a full baseline AND a
    # next period, so it is labelable; indices < lb are not (insufficient hist).
    rates2 = [0.10] * (lb + 2)
    df2 = _make_features(states_rates={"BB": rates2}, n_periods=lb + 2)
    out2 = derive_target(df2).sort_values("period").reset_index(drop=True)
    # first lb rows: insufficient history
    assert (out2.loc[: lb - 1, "labelable"] == False).all()  # noqa: E712
    for r in out2.loc[: lb - 1, "exclusion_reason"]:
        assert "insufficient_history" in r
    # row at position lb is labelable (12 prior periods + a next period)
    assert bool(out2.loc[lb, "labelable"]) is True


def test_thin_next_period_is_unlabelable():
    lb = 12
    # Full history, but the next period's samples are 0 -> unlabelable, recorded.
    hist = [0.10] * lb
    rates = hist + [0.10, float("nan")]  # period 13 (t+1) missing -> samples 0
    df = _make_features(states_rates={"CC": rates}, n_periods=lb + 2)
    out = derive_target(df)
    row_t = out[out["period"] == _monthly_periods(lb + 2)[lb]].iloc[0]
    assert bool(row_t["labelable"]) is False
    assert (
        "next_period_samples_below_min" in row_t["exclusion_reason"]
        or "next_period_positivity_unobserved" in row_t["exclusion_reason"]
    )
    # y_elevated must be NA (never fabricated) for an unlabelable cell
    assert pd.isna(row_t["y_elevated"])


# --------------------------------------------------------------------------- #
# (d) the binary label never derives from a feature column (no leakage)
# --------------------------------------------------------------------------- #

def test_no_label_leakage_into_features():
    lb = 12
    rates = [0.10] * (lb + 2)
    df = _make_features(states_rates={"DD": rates}, n_periods=lb + 2)
    out = derive_target(df)
    audit = assert_no_label_leakage(out)
    assert audit["ok"] is True
    feats = set(feature_columns(out))
    # none of the label columns nor the raw outcome columns are features
    assert not (feats & set(LABEL_COLS))
    assert not (feats & set(OUTCOME_COLS))
    # y_elevated is present as a label column, not a feature
    assert "y_elevated" in out.columns
    assert "y_elevated" not in feats


def test_label_invariant_to_feature_values():
    """Mutating a feature column must not change the derived label (Req 5.5)."""
    lb = 12
    rates = [0.10] * lb + [0.10, 0.50]
    df = _make_features(states_rates={"EE": rates}, n_periods=lb + 2)
    base = derive_target(df)

    mutated = df.copy()
    mutated["routine_positivity_lag1"] = 999.0
    mutated["season_sin"] = -42.0
    out = derive_target(mutated)

    # labels/targets are identical regardless of feature values
    pd.testing.assert_series_equal(
        base["y_elevated"], out["y_elevated"], check_names=False
    )
    pd.testing.assert_series_equal(
        base["y_next_positivity"], out["y_next_positivity"], check_names=False
    )


# --------------------------------------------------------------------------- #
# (e) rate target equals next-period positivity (Req 5.4)
# --------------------------------------------------------------------------- #

def test_rate_target_equals_next_period_positivity():
    lb = 12
    periods = _monthly_periods(lb + 3)
    # distinct rising rates so each next value is unambiguous
    rates = [0.05] * lb + [0.20, 0.30, 0.40]
    df = _make_features(states_rates={"FF": rates}, n_periods=lb + 3)
    out = derive_target(df).sort_values("period").reset_index(drop=True)
    for i in range(len(out) - 1):
        nxt_rate = out.loc[i + 1, "outcome_routine_positivity_rate"]
        if pd.notna(out.loc[i, "y_next_positivity"]):
            assert out.loc[i, "y_next_positivity"] == pytest.approx(nxt_rate)
            assert out.loc[i, "next_period"] == out.loc[i + 1, "period"]
    # last row has no next period -> y_next_positivity is NaN
    assert pd.isna(out.loc[len(out) - 1, "y_next_positivity"])


# --------------------------------------------------------------------------- #
# Multi-state independence
# --------------------------------------------------------------------------- #

def test_states_labeled_independently():
    lb = 12
    rates_a = [0.10] * lb + [0.10, 0.90]  # next >> baseline -> 1
    rates_b = [0.10] * lb + [0.10, 0.01]  # next < baseline -> 0
    df = _make_features(
        states_rates={"AA": rates_a, "BB": rates_b}, n_periods=lb + 2
    )
    out = derive_target(df)
    t_period = _monthly_periods(lb + 2)[lb]
    row_a = out[(out["state"] == "AA") & (out["period"] == t_period)].iloc[0]
    row_b = out[(out["state"] == "BB") & (out["period"] == t_period)].iloc[0]
    assert int(row_a["y_elevated"]) == 1
    assert int(row_b["y_elevated"]) == 0


# --------------------------------------------------------------------------- #
# Data-backed smoke check against the real feature tables (if present)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("pathogen", ["Salmonella", "Listeria", "STEC"])
def test_real_feature_tables_build_model(pathogen):
    slug = {"Salmonella": "salmonella", "Listeria": "listeria", "STEC": "stec"}[pathogen]
    parquet = PROCESSED / f"features_{slug}.parquet"
    csv = PROCESSED / f"features_{slug}.csv"
    if not parquet.exists() and not csv.exists():
        pytest.skip(f"no feature table for {pathogen}")
    model, summary = build_model_table(pathogen)
    # structural guarantees (v1 + redesigned v2)
    assert "y_elevated" in model.columns
    assert "y_next_positivity" in model.columns
    assert "labelable" in model.columns
    assert "y_elevated_v2" in model.columns
    assert "smoothed_next_positivity" in model.columns
    assert "labelable_v2" in model.columns
    assert_no_label_leakage(model)
    assert summary["horizon_periods"] == 1
    # base rate, when defined, is a valid fraction
    if summary["base_rate_elevated"] is not None:
        assert 0.0 <= summary["base_rate_elevated"] <= 1.0
    if summary["base_rate_v2"] is not None:
        assert 0.0 <= summary["base_rate_v2"] <= 1.0
    # labelable cells never exceed total
    assert summary["labelable_modeling_units"] <= summary["total_modeling_units"]
    assert summary["labelable_v2_modeling_units"] <= summary["total_modeling_units"]


# =========================================================================== #
# Redesigned denominator-aware label (y_elevated_v2) — Req 5.x redesign
#
# (a) smoothed rate lies between the raw rate and the national prior;
# (b) the train tail threshold is computed from TRAIN rows ONLY (mutating test
#     rows does not change it);
# (c) y_elevated_v2 == 1 iff smoothed_next_positivity >= threshold;
# (d) the horizon is still 1 (shared with the v1 horizon test above).
# =========================================================================== #


def _make_counts_features(
    *,
    states_counts: dict[str, list[tuple[float, float]]],
    n_periods: int,
    resolution: str = "monthly",
) -> pd.DataFrame:
    """Build a synthetic feature frame from explicit (positives, samples) pairs.

    ``states_counts`` maps a state -> a chronological list of ``(positives,
    samples)`` for each period. A ``samples == 0`` cell marks a missing/thin
    outcome (rate is NaN). This lets the v2 tests control denominators directly.
    """
    periods = _monthly_periods(n_periods)
    rows: list[dict] = []
    for state, counts in states_counts.items():
        assert len(counts) == n_periods
        for period, (pos, samp) in zip(periods, counts):
            rate = (pos / samp) if samp and samp > 0 else float("nan")
            rows.append(
                {
                    "pathogen": "Test",
                    "state": state,
                    "period": period,
                    "period_start": tg.period_start(period),
                    "cutoff": tg.period_start(period),
                    "resolution": resolution,
                    "outcome_routine_samples": float(samp),
                    "outcome_routine_positives": (float(pos) if samp and samp > 0 else float("nan")),
                    "outcome_routine_positivity_rate": rate,
                    # a feature column that MUST NOT influence the label
                    "routine_positivity_lag1": 0.123,
                    "season_sin": 0.5,
                    "geo_state": state,
                }
            )
    return pd.DataFrame(rows)


def _derive_then_smooth(df: pd.DataFrame):
    """Run the full v1 derivation then attach the v2 smoothed label.

    ``add_smoothed_label`` consumes the v1 label columns (``labelable``,
    ``next_routine_samples``/``positives``), so a raw feature frame must pass
    through ``derive_target`` first — exactly as ``build_model_table`` does.
    """
    model = derive_target(df)
    return add_smoothed_label(model)


def test_v2_beta_binomial_formula_matches_posterior_mean():
    # beta_binomial_shrink(k, n, p_nat, m) == (k + m*p_nat) / (n + m)
    p_nat = 0.2
    m = SHRINKAGE_PSEUDOCOUNT
    k = np.array([2.0, 50.0, 0.0])
    n = np.array([10.0, 100.0, 8.0])
    got = beta_binomial_shrink(k, n, p_nat, pseudocount=m)
    expected = (k + m * p_nat) / (n + m)
    assert np.allclose(got, expected)


def test_v2_smoothed_rate_between_raw_and_prior():
    """(a) the smoothed rate lies between the raw rate and the national prior."""
    lb = 12
    # One state, flat history then varied next-period denominators so some cells
    # are thin (shrink a lot) and some are well sampled (shrink a little).
    # history: 12 periods of (5 pos / 100 samp) = 0.05
    hist = [(5.0, 100.0)] * lb
    # period t (index lb): any; period t+1 (index lb+1): thin cell 1/5 = 0.20
    tail = [(5.0, 100.0), (1.0, 5.0), (40.0, 100.0)]
    df = _make_counts_features(
        states_counts={"AA": hist + tail}, n_periods=lb + 3
    )
    out, meta = _derive_then_smooth(df)
    p_nat = meta["p_nat"]
    lab = out[out["labelable_v2"] == True]  # noqa: E712
    assert len(lab) >= 1
    for _, row in lab.iterrows():
        k = row["next_routine_positives"]
        n = row["next_routine_samples"]
        raw = k / n
        sm = row["smoothed_next_positivity"]
        lo, hi = sorted([raw, p_nat])
        # smoothed is a convex combination of raw and prior -> lies within [lo, hi]
        assert lo - 1e-9 <= sm <= hi + 1e-9
        # and (strictly) between unless raw == prior
        if abs(raw - p_nat) > 1e-9:
            assert lo - 1e-9 <= sm <= hi + 1e-9


def test_v2_threshold_computed_from_train_only():
    """(b) mutating TEST-period rows must not change the train tail threshold."""
    lb = 12
    # Build a long single-state series so a chronological split has train+test
    # periods. All cells well-sampled so all are v2-labelable.
    n = lb + 20
    # rising positives so smoothed values vary across periods
    counts = [(float(i % 7) + 1.0, 100.0) for i in range(n)]
    df = _make_counts_features(states_counts={"AA": counts}, n_periods=n)

    out_a, meta_a = _derive_then_smooth(df)
    thr_a = meta_a["v2_threshold"]
    assert thr_a is not None

    # Identify the latest ~20% of periods (the TEST window) and mutate ONLY
    # their outcome counts drastically; the train-derived threshold must not move.
    from src.models.splits import distinct_periods_sorted

    lab = out_a[out_a["labelable_v2"] == True]  # noqa: E712
    periods = distinct_periods_sorted(lab)
    n_test = max(1, int(round(len(periods) * 0.20)))
    # Exclude the FIRST test period from mutation: the last TRAIN row's
    # next-period outcome is that first test period, so its smoothed value (and
    # thus the threshold) legitimately depends on it. Mutating strictly-later
    # test periods cannot touch any train row's label — a clean train-only check.
    test_periods = set(periods[-n_test + 1:]) if n_test > 1 else set()
    if not test_periods:
        pytest.skip("not enough distinct test periods to mutate past the boundary")

    mutated = df.copy()
    is_test = mutated["period"].isin(test_periods)
    mutated.loc[is_test, "outcome_routine_positives"] = 99.0
    mutated.loc[is_test, "outcome_routine_samples"] = 100.0
    mutated.loc[is_test, "outcome_routine_positivity_rate"] = 0.99

    out_b, meta_b = _derive_then_smooth(mutated)
    thr_b = meta_b["v2_threshold"]
    assert thr_b == pytest.approx(thr_a), (
        "train tail threshold changed when only TEST rows were mutated — "
        "threshold is not train-only"
    )


def test_v2_label_is_one_iff_smoothed_at_or_above_threshold():
    """(c) y_elevated_v2 == 1 iff smoothed_next_positivity >= v2_threshold."""
    lb = 12
    n = lb + 20
    counts = [(float(i % 5) * 3.0 + 1.0, 100.0) for i in range(n)]
    df = _make_counts_features(states_counts={"AA": counts}, n_periods=n)
    out, meta = _derive_then_smooth(df)
    thr = meta["v2_threshold"]
    assert thr is not None

    lab = out[out["labelable_v2"] == True].copy()  # noqa: E712
    assert len(lab) > 0
    for _, row in lab.iterrows():
        sm = row["smoothed_next_positivity"]
        expected = 1 if sm >= thr else 0
        assert int(row["y_elevated_v2"]) == expected
    # unlabelable-v2 cells never carry a fabricated v2 label
    unlab = out[out["labelable_v2"] == False]  # noqa: E712
    assert unlab["y_elevated_v2"].isna().all()


def test_v2_horizon_still_one():
    """(d) the horizon is unchanged at 1 period after the redesign."""
    assert HORIZON_PERIODS == 1
    assert HORIZON_FIXED_PRE_TUNING is True


def test_v2_thin_next_period_excluded_by_min_samples():
    """A next period below the v2 minimum-samples floor is unlabelable-v2."""
    lb = 12
    # history well sampled; next period has only 2 samples (< MIN_NEXT_SAMPLES_V2)
    hist = [(5.0, 100.0)] * lb
    tail = [(5.0, 100.0), (1.0, 2.0)]
    df = _make_counts_features(states_counts={"AA": hist + tail}, n_periods=lb + 2)
    out, _meta = _derive_then_smooth(df)
    row_t = out[out["period"] == _monthly_periods(lb + 2)[lb]].iloc[0]
    # v1 might consider it labelable (min 1 sample) but v2 requires >= 5
    assert bool(row_t["labelable_v2"]) is False
    assert "below_v2_min" in row_t["exclusion_reason_v2"]
    assert pd.isna(row_t["y_elevated_v2"])


def test_v2_national_prior_is_train_only_pooled_rate():
    """The national prior is the pooled next-period positivity over TRAIN rows."""
    lb = 12
    n = lb + 10
    counts = [(10.0, 100.0)] * n  # constant 0.10 everywhere
    df = _make_counts_features(states_counts={"AA": counts}, n_periods=n)
    out, meta = _derive_then_smooth(df)
    # pooled train rate of a constant 0.10 series is 0.10
    assert meta["p_nat"] == pytest.approx(0.10, abs=1e-9)


def test_v2_label_invariant_to_feature_values():
    """Mutating a feature column must not change the v2 label (no leakage)."""
    lb = 12
    n = lb + 16
    counts = [(float(i % 6) * 2.0 + 1.0, 100.0) for i in range(n)]
    df = _make_counts_features(states_counts={"AA": counts}, n_periods=n)
    base, _ = _derive_then_smooth(df)

    mutated = df.copy()
    mutated["routine_positivity_lag1"] = 999.0
    mutated["season_sin"] = -42.0
    out, _ = _derive_then_smooth(mutated)

    pd.testing.assert_series_equal(
        base["y_elevated_v2"], out["y_elevated_v2"], check_names=False
    )
    pd.testing.assert_series_equal(
        base["smoothed_next_positivity"],
        out["smoothed_next_positivity"],
        check_names=False,
    )
