"""Integrated models with rare-event handling (Phase 2, Task 3.5; Req 7.2, 7.3).

Requirement 7.2 asks the ``Risk_Model`` to build **at least one gradient-boosting
model** (XGBoost / LightGBM / CatBoost) AND **at least one RandomForest**, and to
record each integrated model's configuration and evaluation metrics so the
integrated lift over the transparent baselines (Task 3.4) is explicit. This
module builds THREE integrated learners per pathogen so the downstream
ablation / interpretation tasks (3.9) can choose:

1. **XGBoost** (``xgboost.XGBClassifier``);
2. **LightGBM** (``lightgbm.LGBMClassifier``);
3. **RandomForest** (``sklearn.ensemble.RandomForestClassifier``).

They are trained on the EXACT same strict-chronological train split and
evaluated on the EXACT same untouched ~20% test period as the baselines
(:func:`src.models.splits.chronological_split`), so their metrics are directly
comparable to ``baseline_metrics.json`` cell-for-cell.

Preprocessing (consistent + documented, Req 7.2)
------------------------------------------------
To be directly comparable to the ``LogisticBaseline``, all three integrated
models reuse the SAME :class:`sklearn.compose.ColumnTransformer` preprocessing
as the logistic baseline:

* numeric features: median-impute then standardize;
* small categoricals (``geo_state``, ``geo_region``, ``period_of_year`` plus any
  stray string column): most-frequent-impute then one-hot encode
  (``handle_unknown='ignore'``).

The tree learners do not strictly need scaling, but using one shared pipeline
keeps the feature space identical across every model so the baseline-vs-
integrated deltas reflect the learner, not a feature-handling difference. This
choice is recorded in each model's ``config()``.

Rare-event handling (Req 7.3)
-----------------------------
Req 7.3: WHERE positive-class prevalence < 10%, apply a rare-event / class-
imbalance method. The trigger is evaluated on the MEASURED TRAIN prevalence
(positives / rows on the training split only — never peeking at test). When it
fires:

* XGBoost  -> ``scale_pos_weight = n_neg / n_pos`` (train);
* LightGBM -> ``class_weight='balanced'`` (equivalently up-weights the minority);
* RandomForest -> ``class_weight='balanced'``.

When it does not fire, the models use their standard unweighted configuration
(``scale_pos_weight=1``, ``class_weight=None``). The measured train prevalence,
the boolean trigger and the threshold are recorded per pathogen so the honest
answer to "which pathogens got rare-event handling?" is auditable. On the
observed data Salmonella (~45% train prevalence) is NOT rare, and the rarer
quarterly pathogens (Listeria ~12%, STEC ~16%) are imbalanced but still sit
ABOVE the strict 10% threshold — so by Req 7.3's exact rule none trigger; the
JSON records this faithfully rather than forcing handling on.

Outputs (written under ``data/processed/models/``)
--------------------------------------------------
* ``integrated_<slug>_<model>.joblib`` — the three fitted model objects;
* ``integrated_metrics.json`` — per-pathogen, per-model configuration + the
  test-period metrics (PR-AUC, ROC-AUC, precision, recall, Brier, base rate),
  the train/test period ranges and sizes, the rare-event trigger, AND a
  ``vs_logistic_baseline`` comparison line (delta PR-AUC / delta ROC-AUC vs the
  ``regularized_logistic`` baseline from ``baseline_metrics.json``) so the
  integrated lift (or lack thereof) is explicit and reported honestly;
* ``preds_<slug>.parquet`` — the untouched-test predicted probabilities + the
  true labels + the ``(state, period)`` keys for every model, so validation
  (3.7), calibration, and the exporter reuse the EXACT predictions and report
  only from exported predictions (Req 8.6). CSV fallback when no parquet engine.

Reproducibility
---------------
A fixed ``RANDOM_STATE = 42`` pins every learner; identical inputs + seed
reproduce identical fitted artifacts and identical metrics.

Design reference: design.md "Models, features, rare events (Req 7)" and
"Validation (Req 8)".
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from src.pipeline.features import PATHOGEN_SLUG, PROCESSED_ROOT
from src.pipeline.target import feature_columns
from src.models.splits import DEFAULT_TEST_FRACTION, chronological_split
from src.models.baseline import (
    MODELS_ROOT,
    PRIMARY_LABEL_COL,
    RANDOM_STATE,
    RARE_EVENT_PREVALENCE,
    SMALL_CATEGORICALS,
    evaluate_scores,
    labelable_frame,
)

__all__ = [
    "RANDOM_STATE",
    "MODELS_ROOT",
    "RARE_EVENT_PREVALENCE",
    "INTEGRATED_MODEL_NAMES",
    "build_preprocessor",
    "measure_train_prevalence",
    "rare_event_triggered",
    "IntegratedModel",
    "train_integrated_for_pathogen",
    "run_integrated",
]

#: The three integrated learners built per pathogen (Req 7.2).
INTEGRATED_MODEL_NAMES: tuple[str, ...] = ("xgboost", "lightgbm", "random_forest")


# --------------------------------------------------------------------------- #
# Shared preprocessing (same ColumnTransformer as the logistic baseline)
# --------------------------------------------------------------------------- #

def build_preprocessor(
    frame: pd.DataFrame,
    feature_cols: list[str],
    categorical_cols: list[str],
) -> tuple[ColumnTransformer, list[str], list[str]]:
    """Build the shared median-impute+scale / one-hot preprocessing.

    Mirrors :meth:`src.models.baseline.LogisticBaseline._build` so the
    integrated models consume an identical feature space. Returns the fitted-
    able (unfitted) ColumnTransformer plus the resolved numeric / categorical
    column lists for the config record.
    """
    cats = [c for c in categorical_cols if c in feature_cols]
    for c in feature_cols:
        if c in cats:
            continue
        if not pd.api.types.is_numeric_dtype(frame[c]):
            cats.append(c)
    nums = [c for c in feature_cols if c not in cats]

    numeric = Pipeline(
        steps=[
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
        ]
    )
    categorical = Pipeline(
        steps=[
            ("impute", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore")),
        ]
    )
    pre = ColumnTransformer(
        transformers=[
            ("num", numeric, nums),
            ("cat", categorical, cats),
        ],
        remainder="drop",
    )
    return pre, nums, cats


# --------------------------------------------------------------------------- #
# Rare-event trigger (measured on TRAIN only — Req 7.3)
# --------------------------------------------------------------------------- #

def measure_train_prevalence(y_train: pd.Series | np.ndarray) -> float:
    """Measured positive-class prevalence on the TRAIN split (positives/rows)."""
    y = pd.to_numeric(pd.Series(y_train), errors="coerce").astype(float)
    return float(y.mean()) if len(y) else 0.0


def rare_event_triggered(
    train_prevalence: float,
    *,
    threshold: float = RARE_EVENT_PREVALENCE,
) -> bool:
    """True iff the measured train prevalence is strictly below ``threshold``.

    Req 7.3 defines the trigger as positive-class prevalence < 10%. This is the
    single source of truth used to decide whether class-imbalance handling is
    applied, so the model config and the test both key off the same function.
    """
    return bool(train_prevalence < threshold)


# --------------------------------------------------------------------------- #
# Integrated model wrapper (preprocessing pipeline + one classifier)
# --------------------------------------------------------------------------- #

@dataclass
class IntegratedModel:
    """An integrated learner = shared preprocessing + one tree/boosting classifier.

    ``name`` is one of :data:`INTEGRATED_MODEL_NAMES`. ``rare_event`` decides
    whether class-imbalance handling is wired into the underlying classifier.
    The whole thing is a single sklearn ``Pipeline`` so it pickles as one
    artifact and predicts from feature columns alone.
    """

    name: str
    feature_cols: list[str]
    categorical_cols: list[str]
    rare_event: bool = False
    scale_pos_weight: float = 1.0
    random_state: int = RANDOM_STATE

    pipeline_: Optional[Pipeline] = field(default=None, init=False)
    numeric_cols_: list[str] = field(default_factory=list, init=False)
    categorical_cols_: list[str] = field(default_factory=list, init=False)
    classifier_params_: dict[str, Any] = field(default_factory=dict, init=False)

    def _make_classifier(self):
        if self.name == "xgboost":
            from xgboost import XGBClassifier

            params: dict[str, Any] = {
                "n_estimators": 300,
                "max_depth": 4,
                "learning_rate": 0.05,
                "subsample": 0.8,
                "colsample_bytree": 0.8,
                "reg_lambda": 1.0,
                "objective": "binary:logistic",
                "eval_metric": "logloss",
                "n_jobs": 1,
                "random_state": self.random_state,
                # rare-event handling: up-weight the minority positive class
                "scale_pos_weight": (self.scale_pos_weight if self.rare_event else 1.0),
            }
            self.classifier_params_ = dict(params)
            return XGBClassifier(**params)

        if self.name == "lightgbm":
            from lightgbm import LGBMClassifier

            params = {
                "n_estimators": 300,
                "max_depth": -1,
                "num_leaves": 31,
                "learning_rate": 0.05,
                "subsample": 0.8,
                "colsample_bytree": 0.8,
                "reg_lambda": 1.0,
                "objective": "binary",
                "n_jobs": 1,
                "random_state": self.random_state,
                "verbose": -1,
                # rare-event handling: balanced class weights up-weight minority
                "class_weight": ("balanced" if self.rare_event else None),
            }
            self.classifier_params_ = dict(params)
            return LGBMClassifier(**params)

        if self.name == "random_forest":
            params = {
                "n_estimators": 400,
                "max_depth": None,
                "min_samples_leaf": 2,
                "n_jobs": 1,
                "random_state": self.random_state,
                "class_weight": ("balanced" if self.rare_event else None),
            }
            self.classifier_params_ = dict(params)
            return RandomForestClassifier(**params)

        raise ValueError(f"unknown integrated model name: {self.name!r}")

    def _build(self, frame: pd.DataFrame) -> Pipeline:
        pre, nums, cats = build_preprocessor(
            frame, self.feature_cols, self.categorical_cols
        )
        self.numeric_cols_ = nums
        self.categorical_cols_ = cats
        clf = self._make_classifier()
        return Pipeline(steps=[("pre", pre), ("clf", clf)])

    def fit(self, frame: pd.DataFrame, y: pd.Series) -> "IntegratedModel":
        self.pipeline_ = self._build(frame)
        X = frame[self.feature_cols]
        y_arr = pd.to_numeric(y, errors="coerce").astype(int).to_numpy()
        self.pipeline_.fit(X, y_arr)
        return self

    def predict_proba_pos(self, frame: pd.DataFrame) -> np.ndarray:
        assert self.pipeline_ is not None, "fit() must be called first"
        return self.pipeline_.predict_proba(frame[self.feature_cols])[:, 1]

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        assert self.pipeline_ is not None, "fit() must be called first"
        return self.pipeline_.predict(frame[self.feature_cols]).astype(float)

    def config(self) -> dict[str, Any]:
        type_map = {
            "xgboost": "gradient_boosting_xgboost",
            "lightgbm": "gradient_boosting_lightgbm",
            "random_forest": "random_forest",
        }
        imbalance = {
            "xgboost": f"scale_pos_weight={self.classifier_params_.get('scale_pos_weight')}",
            "lightgbm": f"class_weight={self.classifier_params_.get('class_weight')!r}",
            "random_forest": f"class_weight={self.classifier_params_.get('class_weight')!r}",
        }
        return {
            "name": self.name,
            "type": type_map[self.name],
            "is_ml": True,
            "rare_event_handling_applied": self.rare_event,
            "imbalance_handling": imbalance[self.name],
            "scale_pos_weight_value": self.scale_pos_weight,
            "classifier_params": self.classifier_params_,
            "random_state": self.random_state,
            "numeric_features": self.numeric_cols_,
            "categorical_features": self.categorical_cols_,
            "n_features_in": len(self.feature_cols),
            "preprocessing": (
                "median-impute + standardize numeric; most-frequent-impute + "
                "one-hot categoricals (SAME ColumnTransformer as LogisticBaseline "
                "for direct comparability)"
            ),
        }


# --------------------------------------------------------------------------- #
# Baseline floor lookup (for the vs-baseline comparison line)
# --------------------------------------------------------------------------- #

def _load_logistic_baseline_metrics(
    pathogen: str, models_root: Path
) -> Optional[dict[str, Any]]:
    """Return the logistic-baseline test metrics for ``pathogen`` if available."""
    path = models_root / "baseline_metrics.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return (
            data.get("per_pathogen", {})
            .get(pathogen, {})
            .get("baselines", {})
            .get("regularized_logistic", {})
            .get("metrics")
        )
    except Exception:  # noqa: BLE001 - absent/corrupt baseline file is non-fatal
        return None


def _delta(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None:
        return None
    return float(a - b)


def _vs_logistic(
    integrated_metrics: dict[str, Optional[float]],
    logistic_metrics: Optional[dict[str, Any]],
) -> dict[str, Any]:
    """Build the explicit integrated-vs-logistic comparison line (delta metrics)."""
    if not logistic_metrics:
        return {
            "logistic_baseline_available": False,
            "note": "baseline_metrics.json missing; run baselines (Task 3.4) first",
        }
    d_pr = _delta(integrated_metrics.get("pr_auc"), logistic_metrics.get("pr_auc"))
    d_roc = _delta(integrated_metrics.get("roc_auc"), logistic_metrics.get("roc_auc"))
    beat = None
    if d_pr is not None:
        beat = bool(d_pr > 0)
    return {
        "logistic_baseline_available": True,
        "logistic_pr_auc": logistic_metrics.get("pr_auc"),
        "logistic_roc_auc": logistic_metrics.get("roc_auc"),
        "delta_pr_auc": d_pr,
        "delta_roc_auc": d_roc,
        "beats_logistic_pr_auc": beat,
    }


# --------------------------------------------------------------------------- #
# Model-table loader (same convention as baseline._load_model_table)
# --------------------------------------------------------------------------- #

def _load_model_table(pathogen: str, processed_root: Path) -> pd.DataFrame:
    slug = PATHOGEN_SLUG[pathogen]
    parquet = processed_root / f"model_{slug}.parquet"
    csv = processed_root / f"model_{slug}.csv"
    if parquet.exists():
        return pd.read_parquet(parquet)
    if csv.exists():
        return pd.read_csv(csv)
    raise FileNotFoundError(
        f"no model table for {pathogen} at {parquet} (run target derivation first)"
    )


def _write_predictions(
    test: pd.DataFrame,
    y_test: np.ndarray,
    proba_by_model: dict[str, np.ndarray],
    *,
    pathogen: str,
    slug: str,
    models_root: Path,
) -> Optional[str]:
    """Persist the untouched-test predictions for reuse (Req 8.6).

    One row per test modeling unit with the ``(state, period)`` keys, the true
    label, and each model's predicted probability. This is the single source the
    validation / calibration / exporter steps read, so downstream numbers come
    only from the exported predictions.
    """
    preds = pd.DataFrame(
        {
            "pathogen": pathogen,
            "state": test["state"].to_numpy(),
            "period": test["period"].to_numpy(),
            "period_start": pd.to_datetime(test["period_start"]).to_numpy(),
            "y_true": np.asarray(y_test, dtype=int),
        }
    )
    for model_name, proba in proba_by_model.items():
        preds[f"proba_{model_name}"] = np.asarray(proba, dtype=float)

    out = models_root / f"preds_{slug}.parquet"
    try:
        preds.to_parquet(out, index=False)
        return str(out)
    except Exception as exc:  # noqa: BLE001 - CSV fallback when no parquet engine
        out = models_root / f"preds_{slug}.csv"
        preds.to_csv(out, index=False)
        print(f"[integrated] parquet unavailable for {pathogen}: {exc!r}; wrote CSV")
        return str(out)


# --------------------------------------------------------------------------- #
# Per-pathogen training + evaluation
# --------------------------------------------------------------------------- #

def train_integrated_for_pathogen(
    pathogen: str,
    *,
    processed_root: Optional[Path] = None,
    models_root: Optional[Path] = None,
    test_fraction: float = DEFAULT_TEST_FRACTION,
    write_artifacts: bool = True,
    rare_event_threshold: float = RARE_EVENT_PREVALENCE,
    label_col: str = PRIMARY_LABEL_COL,
) -> dict[str, Any]:
    """Train + evaluate the three integrated models for one pathogen.

    Fit ONLY on the chronological train split; evaluate on the untouched test
    with :func:`evaluate_scores`. Returns a result dict with each model's config,
    test metrics, and a vs-logistic-baseline comparison line, plus the measured
    train prevalence and rare-event trigger. Writes fitted artifacts and the
    shared predictions table when ``write_artifacts`` is True.
    """
    import joblib

    processed_root = processed_root or PROCESSED_ROOT
    models_root = models_root or MODELS_ROOT
    slug = PATHOGEN_SLUG[pathogen]

    model = _load_model_table(pathogen, processed_root)
    labelable = labelable_frame(model, label_col=label_col)
    feats = feature_columns(labelable)

    split = chronological_split(labelable, test_fraction=test_fraction)
    train, test = split.train, split.test

    y_train = train["y_elevated"].astype(int)
    y_test = test["y_elevated"].astype(int)

    # Rare-event trigger measured on TRAIN ONLY (Req 7.3).
    train_prev = measure_train_prevalence(y_train)
    rare_event = rare_event_triggered(train_prev, threshold=rare_event_threshold)
    n_pos = int(y_train.sum())
    n_neg = int(len(y_train) - n_pos)
    scale_pos_weight = (n_neg / n_pos) if n_pos else 1.0

    logistic_metrics = _load_logistic_baseline_metrics(pathogen, models_root)

    if write_artifacts:
        models_root.mkdir(parents=True, exist_ok=True)

    models_out: dict[str, Any] = {}
    proba_by_model: dict[str, np.ndarray] = {}
    for name in INTEGRATED_MODEL_NAMES:
        mdl = IntegratedModel(
            name=name,
            feature_cols=list(feats),
            categorical_cols=list(SMALL_CATEGORICALS),
            rare_event=rare_event,
            scale_pos_weight=scale_pos_weight,
            random_state=RANDOM_STATE,
        ).fit(train, y_train)

        score = mdl.predict_proba_pos(test)
        pred = mdl.predict(test)
        metrics = evaluate_scores(y_test.to_numpy(), score, pred)
        proba_by_model[name] = score

        artifact_path: Optional[str] = None
        if write_artifacts:
            artifact_path = str(models_root / f"integrated_{slug}_{name}.joblib")
            joblib.dump(mdl, artifact_path)

        models_out[name] = {
            "config": mdl.config(),
            "metrics": metrics,
            "vs_logistic_baseline": _vs_logistic(metrics, logistic_metrics),
            "artifact": artifact_path,
        }

    preds_path: Optional[str] = None
    if write_artifacts:
        preds_path = _write_predictions(
            test,
            y_test.to_numpy(),
            proba_by_model,
            pathogen=pathogen,
            slug=slug,
            models_root=models_root,
        )

    resolution = str(model["resolution"].iloc[0]) if not model.empty else "unknown"
    overall_base_rate = (
        float(labelable["y_elevated"].mean()) if len(labelable) else None
    )

    return {
        "pathogen": pathogen,
        "resolution": resolution,
        "label_col": label_col,
        "feature_column_count": len(feats),
        "test_fraction": test_fraction,
        "random_state": RANDOM_STATE,
        "rare_event_prevalence_threshold": rare_event_threshold,
        "train_prevalence": train_prev,
        "rare_event_handling_applied": rare_event,
        "rare_event_rationale": (
            f"measured TRAIN prevalence={train_prev:.4f}; "
            + (
                f"< {rare_event_threshold:g} threshold -> imbalance handling ON "
                f"(xgboost scale_pos_weight={scale_pos_weight:.3f}, lightgbm/RF "
                f"class_weight='balanced')"
                if rare_event
                else f">= {rare_event_threshold:g} threshold -> standard weighting "
                f"(not a rare event by Req 7.3's <10% rule)"
            )
        ),
        "train_positive_count": n_pos,
        "train_negative_count": n_neg,
        "scale_pos_weight_if_triggered": scale_pos_weight,
        "overall_base_rate": overall_base_rate,
        "split": {
            "train_periods": [split.train_period_range[0], split.train_period_range[1]],
            "test_periods": [split.test_period_range[0], split.test_period_range[1]],
            "n_train_periods": len(split.train_periods),
            "n_test_periods": len(split.test_periods),
            "n_train_rows": int(len(train)),
            "n_test_rows": int(len(test)),
            "boundary_period_start": str(split.boundary),
        },
        "models": models_out,
        "predictions_path": preds_path,
    }


def run_integrated(
    *,
    pathogens: Optional[tuple[str, ...]] = None,
    processed_root: Optional[Path] = None,
    models_root: Optional[Path] = None,
    test_fraction: float = DEFAULT_TEST_FRACTION,
    write_metrics: bool = True,
    write_artifacts: bool = True,
    label_col: str = PRIMARY_LABEL_COL,
    metrics_filename: str = "integrated_metrics.json",
) -> dict[str, Any]:
    """Train + evaluate integrated models for every pathogen; write metrics JSON.

    Salmonella is processed FIRST (the primary module), then Listeria and STEC.
    Writes ``data/processed/models/integrated_metrics.json`` + the per-pathogen
    ``preds_<slug>.parquet`` prediction tables, and returns the full results.
    """
    processed_root = processed_root or PROCESSED_ROOT
    models_root = models_root or MODELS_ROOT
    order = pathogens or ("Salmonella", "Listeria", "STEC")

    results: dict[str, Any] = {
        "task": "3.5 Implement integrated models with rare-event handling",
        "requirements": ["7.2", "7.3"],
        "label_col": label_col,
        "random_state": RANDOM_STATE,
        "test_fraction": test_fraction,
        "models_built": list(INTEGRATED_MODEL_NAMES),
        "rare_event_prevalence_threshold": RARE_EVENT_PREVALENCE,
        "split_strategy": (
            "strict chronological: most-recent ~20% of distinct periods held "
            "untouched; all train period_starts < all test period_starts "
            "(src.models.splits.chronological_split) — SAME split as the baselines"
        ),
        "preprocessing_note": (
            "all integrated models reuse the SAME ColumnTransformer as the "
            "logistic baseline (median-impute+scale numeric; one-hot small "
            "categoricals) so metrics are directly comparable"
        ),
        "rare_event_note": (
            "rare-event handling (xgboost scale_pos_weight=neg/pos; "
            "lightgbm/RF class_weight='balanced') is applied iff the MEASURED "
            "train prevalence is < 10% (Req 7.3). Salmonella (~45%) is not rare; "
            "the quarterly pathogens are imbalanced but above the 10% threshold "
            "on the observed data — recorded honestly per pathogen."
        ),
        "per_pathogen": {},
    }
    for pathogen in order:
        results["per_pathogen"][pathogen] = train_integrated_for_pathogen(
            pathogen,
            processed_root=processed_root,
            models_root=models_root,
            test_fraction=test_fraction,
            write_artifacts=write_artifacts,
            label_col=label_col,
        )

    if write_metrics:
        models_root.mkdir(parents=True, exist_ok=True)
        out = models_root / metrics_filename
        out.write_text(json.dumps(results, indent=2), encoding="utf-8")
        results["metrics_path"] = str(out)

    return results


if __name__ == "__main__":  # pragma: no cover - manual invocation
    import pprint

    pprint.pprint(run_integrated())
