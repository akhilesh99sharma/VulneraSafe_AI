"""Tests for the integrated models with rare-event handling (Task 3.5, Req 7.2, 7.3).

Covers the five required cases:

(a) the integrated models fit on the chronological TRAIN split and predict on
    the untouched TEST split using ONLY the feature columns (the label dropped
    from the test frame entirely);
(b) rare-event / class-imbalance handling is applied IFF the MEASURED train
    prevalence is below the threshold (Req 7.3) — it fires on a synthetic rare
    table and does NOT fire on a balanced one;
(c) every reported metric is in its valid range ([0, 1] or None);
(d) a fixed seed is reproducible: same inputs + same seed -> identical metrics;
(e) the exported predictions file has exactly one row per test modeling unit
    with ``y_true``, a per-model probability, and the ``(state, period)`` keys.

Unit tests run on a small deterministic synthetic model table so the logic is
verified fast and independently of the real data run; a data-backed smoke check
runs against the already-emitted model tables when present.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.pipeline import target as tg
from src.pipeline.target import feature_columns, KEY_COLS, OUTCOME_COLS, LABEL_COLS
from src.models.splits import chronological_split, DEFAULT_TEST_FRACTION
from src.models.baseline import SMALL_CATEGORICALS, evaluate_scores, labelable_frame
from src.models import integrated as it
from src.models.integrated import (
    INTEGRATED_MODEL_NAMES,
    IntegratedModel,
    RARE_EVENT_PREVALENCE,
    measure_train_prevalence,
    rare_event_triggered,
    train_integrated_for_pathogen,
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


def _make_model_table(
    n_periods: int = 40,
    states=("AA", "BB", "CC"),
    *,
    positive_target: float = 0.5,
    seed: int = 7,
) -> pd.DataFrame:
    """Build a deterministic synthetic labelable model table.

    ``positive_target`` tunes the overall positive-class prevalence (a bias on
    the label logit) so a near-balanced (~0.5) table and a rare (~0.05) table
    can both be produced for the rare-event trigger test. Every row is labelable
    with a defined ``y_elevated`` and carries real signal in the numeric
    features so the tree learners can fit.
    """
    rng = np.random.default_rng(seed)
    periods = _monthly_periods(n_periods)
    regions = {"AA": "South", "BB": "West", "CC": "Midwest"}
    # logit bias chosen so mean(prob) ~ positive_target
    bias = float(np.log(positive_target / (1.0 - positive_target)))
    rows: list[dict] = []
    for state in states:
        for i, period in enumerate(periods):
            lag1 = float(rng.uniform(0.0, 0.3))
            trailing = float(rng.uniform(0.0, 0.3))
            season_sin = np.sin(2 * np.pi * (i % 12) / 12)
            season_cos = np.cos(2 * np.pi * (i % 12) / 12)
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
                    # features
                    "routine_positivity_lag1": lag1,
                    "routine_positivity_trailing12m_mean": trailing,
                    "routine_samples_lag1": float(rng.integers(50, 150)),
                    "season_sin": season_sin,
                    "season_cos": season_cos,
                    "period_of_year": (i % 12) + 1,
                    "weather_tmax_mean_lag1": np.nan,
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
# (a) Integrated models fit on train, predict on untouched test, features only
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", list(INTEGRATED_MODEL_NAMES))
def test_integrated_model_uses_only_feature_columns(name):
    df = labelable_frame(_make_model_table())
    split = chronological_split(df)
    feats = feature_columns(df)

    model = IntegratedModel(
        name=name,
        feature_cols=list(feats),
        categorical_cols=list(SMALL_CATEGORICALS),
    ).fit(split.train, split.train["y_elevated"].astype(int))

    # the configured feature set must never include a label/outcome/key column
    for col in OUTCOME_COLS + LABEL_COLS + KEY_COLS:
        assert col not in model.feature_cols

    # drop the label entirely from the test frame: prediction must still work,
    # proving the model consumes only features (never peeks at the label)
    test_no_label = split.test.drop(columns=["y_elevated"])
    proba = model.predict_proba_pos(test_no_label)
    preds = model.predict(test_no_label)
    assert proba.shape == (len(split.test),)
    assert np.all((proba >= 0.0) & (proba <= 1.0))
    assert set(np.unique(preds)).issubset({0.0, 1.0})


def test_train_strictly_before_test_in_integrated_split():
    # The integrated models reuse the SAME chronological split as the baselines.
    df = labelable_frame(_make_model_table(n_periods=40))
    split = chronological_split(df, test_fraction=DEFAULT_TEST_FRACTION)
    max_train = pd.to_datetime(split.train["period_start"]).max()
    min_test = pd.to_datetime(split.test["period_start"]).min()
    assert max_train < min_test
    assert not (set(split.train_periods) & set(split.test_periods))


# --------------------------------------------------------------------------- #
# (b) Rare-event handling applied IFF measured train prevalence < threshold
# --------------------------------------------------------------------------- #

def test_rare_event_trigger_matches_measured_prevalence():
    assert rare_event_triggered(0.05) is True
    assert rare_event_triggered(0.09999) is True
    assert rare_event_triggered(0.10) is False  # strict <
    assert rare_event_triggered(0.45) is False


def test_rare_event_handling_fires_on_rare_table_only():
    # Balanced table -> prevalence ~0.5 -> NO rare-event handling.
    balanced = labelable_frame(_make_model_table(positive_target=0.5, seed=1))
    bal_split = chronological_split(balanced)
    bal_prev = measure_train_prevalence(bal_split.train["y_elevated"].astype(int))
    assert bal_prev >= RARE_EVENT_PREVALENCE
    assert rare_event_triggered(bal_prev) is False

    # Rare table -> prevalence < 10% -> rare-event handling fires.
    rare = labelable_frame(
        _make_model_table(n_periods=60, positive_target=0.04, seed=3)
    )
    rare_split = chronological_split(rare)
    rare_prev = measure_train_prevalence(rare_split.train["y_elevated"].astype(int))
    assert rare_prev < RARE_EVENT_PREVALENCE
    assert rare_event_triggered(rare_prev) is True

    # And the model config reflects the trigger per learner.
    feats = feature_columns(rare)
    for name in INTEGRATED_MODEL_NAMES:
        on = IntegratedModel(
            name=name,
            feature_cols=list(feats),
            categorical_cols=list(SMALL_CATEGORICALS),
            rare_event=True,
            scale_pos_weight=5.0,
        ).fit(rare_split.train, rare_split.train["y_elevated"].astype(int))
        assert on.config()["rare_event_handling_applied"] is True

        off = IntegratedModel(
            name=name,
            feature_cols=list(feats),
            categorical_cols=list(SMALL_CATEGORICALS),
            rare_event=False,
        ).fit(bal_split.train, bal_split.train["y_elevated"].astype(int))
        assert off.config()["rare_event_handling_applied"] is False
    # XGBoost explicitly carries the neg/pos weight only when triggered.
    on_xgb = IntegratedModel(
        name="xgboost",
        feature_cols=list(feats),
        categorical_cols=list(SMALL_CATEGORICALS),
        rare_event=True,
        scale_pos_weight=5.0,
    ).fit(rare_split.train, rare_split.train["y_elevated"].astype(int))
    assert on_xgb.classifier_params_["scale_pos_weight"] == pytest.approx(5.0)
    off_xgb = IntegratedModel(
        name="xgboost",
        feature_cols=list(feats),
        categorical_cols=list(SMALL_CATEGORICALS),
        rare_event=False,
        scale_pos_weight=5.0,
    ).fit(bal_split.train, bal_split.train["y_elevated"].astype(int))
    assert off_xgb.classifier_params_["scale_pos_weight"] == 1.0


# --------------------------------------------------------------------------- #
# (c) Metrics are in valid ranges
# --------------------------------------------------------------------------- #

def _assert_metrics_valid(metrics: dict):
    for key in METRIC_KEYS:
        assert key in metrics
        val = metrics[key]
        if val is None:
            continue
        assert 0.0 <= val <= 1.0, f"{key}={val} out of [0, 1]"


@pytest.mark.parametrize("name", list(INTEGRATED_MODEL_NAMES))
def test_metrics_in_valid_ranges_synthetic(name):
    df = labelable_frame(_make_model_table(n_periods=48))
    split = chronological_split(df)
    feats = feature_columns(df)
    model = IntegratedModel(
        name=name,
        feature_cols=list(feats),
        categorical_cols=list(SMALL_CATEGORICALS),
    ).fit(split.train, split.train["y_elevated"].astype(int))
    m = evaluate_scores(
        split.test["y_elevated"].astype(int).to_numpy(),
        model.predict_proba_pos(split.test),
        model.predict(split.test),
    )
    _assert_metrics_valid(m)


# --------------------------------------------------------------------------- #
# (d) Reproducibility: same seed -> identical metrics
# --------------------------------------------------------------------------- #

def _metrics_tuple(metrics: dict) -> tuple:
    return tuple(metrics[k] for k in METRIC_KEYS)


@pytest.mark.parametrize("name", list(INTEGRATED_MODEL_NAMES))
def test_integrated_reproducible_fixed_seed(name):
    df = labelable_frame(_make_model_table())
    split = chronological_split(df)
    feats = feature_columns(df)
    y = split.train["y_elevated"].astype(int)

    def _run():
        m = IntegratedModel(
            name=name,
            feature_cols=list(feats),
            categorical_cols=list(SMALL_CATEGORICALS),
        ).fit(split.train, y)
        return evaluate_scores(
            split.test["y_elevated"].astype(int).to_numpy(),
            m.predict_proba_pos(split.test),
            m.predict(split.test),
        )

    assert _metrics_tuple(_run()) == _metrics_tuple(_run())


# --------------------------------------------------------------------------- #
# (e) Exported predictions: one row per test unit with y_true, proba, keys
# --------------------------------------------------------------------------- #

def test_exported_predictions_shape_and_keys(tmp_path):
    # Write a synthetic model table and run the per-pathogen trainer against it,
    # redirecting both the processed root and the models root into tmp_path so
    # the real artifacts are untouched.
    processed = tmp_path / "processed"
    models = processed / "models"
    processed.mkdir(parents=True, exist_ok=True)

    df = _make_model_table(n_periods=48)
    slug = it.PATHOGEN_SLUG["Salmonella"]
    try:
        df.to_parquet(processed / f"model_{slug}.parquet", index=False)
    except Exception:
        df.to_csv(processed / f"model_{slug}.csv", index=False)

    res = train_integrated_for_pathogen(
        "Salmonella",
        processed_root=processed,
        models_root=models,
        write_artifacts=True,
    )

    preds_path = Path(res["predictions_path"])
    assert preds_path.exists()
    preds = (
        pd.read_parquet(preds_path)
        if preds_path.suffix == ".parquet"
        else pd.read_csv(preds_path)
    )

    # one row per test modeling unit
    assert len(preds) == res["split"]["n_test_rows"]
    # required columns: keys + y_true + one probability per model
    for col in ("state", "period", "y_true"):
        assert col in preds.columns
    for name in INTEGRATED_MODEL_NAMES:
        assert f"proba_{name}" in preds.columns
        assert np.all((preds[f"proba_{name}"] >= 0.0) & (preds[f"proba_{name}"] <= 1.0))
    # y_true is binary and one row per (state, period) test unit (no duplicates)
    assert set(pd.unique(preds["y_true"])).issubset({0, 1})
    assert not preds.duplicated(subset=["state", "period"]).any()


def test_vs_logistic_comparison_line_present(tmp_path):
    processed = tmp_path / "processed"
    models = processed / "models"
    processed.mkdir(parents=True, exist_ok=True)
    df = _make_model_table(n_periods=48)
    slug = it.PATHOGEN_SLUG["Salmonella"]
    try:
        df.to_parquet(processed / f"model_{slug}.parquet", index=False)
    except Exception:
        df.to_csv(processed / f"model_{slug}.csv", index=False)

    res = train_integrated_for_pathogen(
        "Salmonella", processed_root=processed, models_root=models, write_artifacts=True
    )
    for name in INTEGRATED_MODEL_NAMES:
        assert "vs_logistic_baseline" in res["models"][name]


# --------------------------------------------------------------------------- #
# Data-backed smoke check against the real model tables (when present)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("pathogen", ["Salmonella", "Listeria", "STEC"])
def test_real_table_integrated_smoke(pathogen):
    slug = {"Salmonella": "salmonella", "Listeria": "listeria", "STEC": "stec"}[pathogen]
    if not (PROCESSED / f"model_{slug}.parquet").exists() and not (
        PROCESSED / f"model_{slug}.csv"
    ).exists():
        pytest.skip(f"model table for {pathogen} not present")

    res = train_integrated_for_pathogen(pathogen, write_artifacts=False)
    assert res["split"]["n_test_periods"] >= 1
    assert res["split"]["n_train_periods"] >= 1
    assert isinstance(res["rare_event_handling_applied"], bool)
    for name in INTEGRATED_MODEL_NAMES:
        _assert_metrics_valid(res["models"][name]["metrics"])
