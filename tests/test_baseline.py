"""Tests for the transparent baseline models (Task 3.4, Req 7.1).

Covers the four required cases:

(a) the shared chronological split has ALL train timestamps strictly before ALL
    test timestamps and reserves ~20% of the distinct periods for test;
(b) both baselines fit on train and predict on test using ONLY the predictor
    columns returned by ``src.pipeline.target.feature_columns`` — never the
    label / outcome / key columns;
(c) every reported metric is in its valid range ([0, 1] for the AUCs, Brier,
    precision, recall, base rate);
(d) the seasonal-naive baseline is reproducible (same seed / same inputs ->
    identical metrics), and so is the logistic baseline (fixed random_state).

Unit tests run on a small deterministic synthetic model table so the logic is
verified fast and independently of the real-data run; a data-backed smoke check
runs against the already-emitted model tables when they are present.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.pipeline import target as tg
from src.pipeline.target import feature_columns, KEY_COLS, OUTCOME_COLS, LABEL_COLS
from src.models.splits import chronological_split, DEFAULT_TEST_FRACTION
from src.models import baseline as bl
from src.models.baseline import (
    LogisticBaseline,
    SeasonalNaiveBaseline,
    SMALL_CATEGORICALS,
    evaluate_scores,
    labelable_frame,
    train_baselines_for_pathogen,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
PROCESSED = REPO_ROOT / "data" / "processed"

METRIC_KEYS = ("pr_auc", "roc_auc", "precision", "recall", "brier", "base_rate")


# --------------------------------------------------------------------------- #
# Synthetic model-table builder (mirrors the real model_* schema)
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


def _make_model_table(n_periods: int = 40, states=("AA", "BB", "CC")) -> pd.DataFrame:
    """Build a deterministic synthetic labelable model table.

    Every row is labelable with a defined ``y_elevated``. The label is driven by
    a reproducible rule on the numeric features so the logistic model has real
    signal to learn, while the categoricals and persistence columns required by
    the baselines are present.
    """
    rng = np.random.default_rng(7)
    periods = _monthly_periods(n_periods)
    regions = {"AA": "South", "BB": "West", "CC": "Midwest"}
    rows: list[dict] = []
    for state in states:
        for i, period in enumerate(periods):
            lag1 = float(rng.uniform(0.0, 0.3))
            trailing = float(rng.uniform(0.0, 0.3))
            season_sin = np.sin(2 * np.pi * (i % 12) / 12)
            season_cos = np.cos(2 * np.pi * (i % 12) / 12)
            # deterministic-ish label with signal from lag vs trailing + noise
            prob = 1.0 / (1.0 + np.exp(-(6.0 * (lag1 - trailing))))
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
                    # features
                    "routine_positivity_lag1": lag1,
                    "routine_positivity_trailing12m_mean": trailing,
                    "routine_samples_lag1": float(rng.integers(50, 150)),
                    "season_sin": season_sin,
                    "season_cos": season_cos,
                    "period_of_year": (i % 12) + 1,
                    "weather_tmax_mean_lag1": np.nan,  # weather mostly NaN (ok)
                    "geo_state": state,
                    "geo_region": regions[state],
                    # label/target bookkeeping
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


# --------------------------------------------------------------------------- #
# (a) Chronological split: train strictly before test, ~20% reserved
# --------------------------------------------------------------------------- #

def test_chronological_split_orders_train_before_test():
    df = _make_model_table(n_periods=40)
    split = chronological_split(df, test_fraction=DEFAULT_TEST_FRACTION)

    max_train = pd.to_datetime(split.train["period_start"]).max()
    min_test = pd.to_datetime(split.test["period_start"]).min()
    # STRICT ordering: every train timestamp earlier than every test timestamp
    assert max_train < min_test

    # period sets are disjoint
    assert not (set(split.train_periods) & set(split.test_periods))

    # ~20% of the 40 distinct periods reserved for test (8 periods)
    n_total = len(split.train_periods) + len(split.test_periods)
    assert n_total == 40
    assert len(split.test_periods) == pytest.approx(8, abs=1)
    frac = len(split.test_periods) / n_total
    assert abs(frac - DEFAULT_TEST_FRACTION) <= 0.05


def test_split_requires_two_periods():
    one_period = _make_model_table(n_periods=1, states=("AA",))
    with pytest.raises(ValueError):
        chronological_split(one_period)


# --------------------------------------------------------------------------- #
# (b) Baselines fit/predict using ONLY the feature columns (no label leakage)
# --------------------------------------------------------------------------- #

def test_feature_columns_exclude_label_and_outcome():
    df = _make_model_table()
    feats = set(feature_columns(df))
    assert not (feats & set(KEY_COLS))
    assert not (feats & set(OUTCOME_COLS))
    assert not (feats & set(LABEL_COLS))


def test_logistic_baseline_uses_only_feature_columns():
    df = labelable_frame(_make_model_table())
    split = chronological_split(df)
    feats = feature_columns(df)

    model = LogisticBaseline(
        feature_cols=list(feats),
        categorical_cols=list(SMALL_CATEGORICALS),
    ).fit(split.train, split.train["y_elevated"].astype(int))

    # the configured feature set must never include a label/outcome/key column
    assert "y_elevated" not in model.feature_cols
    for col in OUTCOME_COLS + LABEL_COLS + KEY_COLS:
        assert col not in model.feature_cols

    # drop the label entirely from the test frame: prediction must still work,
    # proving the model consumes only features
    test_no_label = split.test.drop(columns=["y_elevated"])
    proba = model.predict_proba_pos(test_no_label)
    preds = model.predict(test_no_label)
    assert proba.shape == (len(split.test),)
    assert set(np.unique(preds)).issubset({0.0, 1.0})
    assert np.all((proba >= 0.0) & (proba <= 1.0))


def test_seasonal_baseline_fits_and_predicts_on_test():
    df = labelable_frame(_make_model_table())
    split = chronological_split(df)
    seasonal = SeasonalNaiveBaseline().fit(split.train, split.train["y_elevated"].astype(int))
    score = seasonal.predict_proba_pos(split.test)
    pred = seasonal.predict(split.test)
    assert np.all((score >= 0.0) & (score <= 1.0))
    assert set(np.unique(pred)).issubset({0.0, 1.0})


# --------------------------------------------------------------------------- #
# (c) Metrics are in valid ranges
# --------------------------------------------------------------------------- #

def _assert_metrics_valid(metrics: dict):
    for key in METRIC_KEYS:
        assert key in metrics
        val = metrics[key]
        if val is None:
            continue  # undefined on this slice is allowed (recorded, not faked)
        assert 0.0 <= val <= 1.0, f"{key}={val} out of [0, 1]"


def test_metrics_in_valid_ranges_synthetic():
    df = _make_model_table(n_periods=48)
    # Evaluate directly on the synthetic table (no real-file dependency).
    labelable = labelable_frame(df)
    split = chronological_split(labelable)
    feats = feature_columns(labelable)

    seasonal = SeasonalNaiveBaseline().fit(split.train, split.train["y_elevated"].astype(int))
    seas_m = evaluate_scores(
        split.test["y_elevated"].astype(int).to_numpy(),
        seasonal.predict_proba_pos(split.test),
        seasonal.predict(split.test),
    )
    _assert_metrics_valid(seas_m)

    logistic = LogisticBaseline(
        feature_cols=list(feats), categorical_cols=list(SMALL_CATEGORICALS)
    ).fit(split.train, split.train["y_elevated"].astype(int))
    log_m = evaluate_scores(
        split.test["y_elevated"].astype(int).to_numpy(),
        logistic.predict_proba_pos(split.test),
        logistic.predict(split.test),
    )
    _assert_metrics_valid(log_m)


def test_evaluate_scores_single_class_records_none():
    # all-positive test slice -> PR/ROC-AUC undefined, recorded as None
    y = np.ones(10)
    score = np.linspace(0.1, 0.9, 10)
    pred = np.ones(10)
    m = evaluate_scores(y, score, pred)
    assert m["roc_auc"] is None
    assert m["pr_auc"] is None
    assert m["base_rate"] == pytest.approx(1.0)
    # Brier / precision / recall are still defined
    assert 0.0 <= m["brier"] <= 1.0


# --------------------------------------------------------------------------- #
# (d) Reproducibility: same seed -> identical metrics
# --------------------------------------------------------------------------- #

def _metrics_tuple(metrics: dict) -> tuple:
    return tuple(metrics[k] for k in METRIC_KEYS)


def test_seasonal_baseline_reproducible():
    df = labelable_frame(_make_model_table())
    split = chronological_split(df)
    y = split.train["y_elevated"].astype(int)

    m1 = evaluate_scores(
        split.test["y_elevated"].astype(int).to_numpy(),
        SeasonalNaiveBaseline().fit(split.train, y).predict_proba_pos(split.test),
        SeasonalNaiveBaseline().fit(split.train, y).predict(split.test),
    )
    m2 = evaluate_scores(
        split.test["y_elevated"].astype(int).to_numpy(),
        SeasonalNaiveBaseline().fit(split.train, y).predict_proba_pos(split.test),
        SeasonalNaiveBaseline().fit(split.train, y).predict(split.test),
    )
    assert _metrics_tuple(m1) == _metrics_tuple(m2)


def test_logistic_baseline_reproducible_fixed_seed():
    df = labelable_frame(_make_model_table())
    split = chronological_split(df)
    feats = feature_columns(df)
    y = split.train["y_elevated"].astype(int)

    def _run():
        m = LogisticBaseline(
            feature_cols=list(feats), categorical_cols=list(SMALL_CATEGORICALS)
        ).fit(split.train, y)
        return evaluate_scores(
            split.test["y_elevated"].astype(int).to_numpy(),
            m.predict_proba_pos(split.test),
            m.predict(split.test),
        )

    assert _metrics_tuple(_run()) == _metrics_tuple(_run())


# --------------------------------------------------------------------------- #
# Data-backed smoke check against the real model tables (when present)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("pathogen", ["Salmonella", "Listeria", "STEC"])
def test_real_table_baselines_smoke(pathogen):
    slug = {"Salmonella": "salmonella", "Listeria": "listeria", "STEC": "stec"}[pathogen]
    if not (PROCESSED / f"model_{slug}.parquet").exists() and not (
        PROCESSED / f"model_{slug}.csv"
    ).exists():
        pytest.skip(f"model table for {pathogen} not present")

    res = train_baselines_for_pathogen(pathogen, write_artifacts=False)
    # strict chronological ordering is reflected in the recorded split
    assert res["split"]["n_test_periods"] >= 1
    assert res["split"]["n_train_periods"] >= 1
    for name in ("seasonal_naive", "regularized_logistic"):
        _assert_metrics_valid(res["baselines"][name]["metrics"])
