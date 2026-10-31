"""Transparent baseline models per pathogen (Phase 2, Task 3.4; Req 7.1).

Requirement 7.1 asks the ``Risk_Model`` to build a ``Baseline_Model`` comprising
BOTH a historical/seasonal baseline AND a regularized logistic (statistical)
model, and to record each baseline's configuration and evaluation metrics for
comparison against the integrated models (Task 3.5). This module implements
exactly that, trained and evaluated with a STRICT CHRONOLOGICAL split so the
reported numbers are an honest "can a transparent reference do it?" floor that
the integrated models must beat.

Two baselines, per pathogen
---------------------------
1. **Seasonal / historical baseline** (``SeasonalNaiveBaseline``): a non-ML
   reference. Its probability-like score for a ``(state, period_of_year)`` cell
   is the *historical frequency of elevation* observed for that state-and-season
   on the TRAIN periods (with graceful back-off to the state rate, the seasonal
   rate, then the global train base rate when a cell is unseen). Its hard
   prediction is the seasonal-naive / persistence rule: predict ELEVATED when
   the last observed routine positivity (``routine_positivity_lag1``) exceeds
   its own trailing baseline (``routine_positivity_trailing12m_mean``). Because
   the score is a frequency in ``[0, 1]`` and the rule yields a 0/1 label,
   PR-AUC, ROC-AUC, Brier, precision and recall are all computable. This is the
   trivial-rule floor.

2. **Regularized logistic regression** (``LogisticBaseline``): sklearn
   ``LogisticRegression`` with L2 penalty, numeric features median-imputed and
   standardized, the small categoricals (``geo_state``, ``geo_region``,
   ``period_of_year``) one-hot encoded, and ``class_weight='balanced'`` for the
   rare-event pathogens. Fit ONLY on the training periods.

Both baselines consume the predictor set returned by
:func:`src.pipeline.target.feature_columns` (keys, raw outcomes, and label
columns excluded) and are evaluated only on the untouched, most-recent ~20% of
periods produced by :func:`src.models.splits.chronological_split`.

Reproducibility
---------------
A fixed ``RANDOM_STATE`` pins the logistic solver; the seasonal baseline is
deterministic by construction. Identical inputs therefore yield identical fitted
artifacts and identical metrics.

Outputs (written under ``data/processed/models/``)
--------------------------------------------------
* ``baseline_<slug>_seasonal.joblib`` and ``baseline_<slug>_logistic.joblib`` —
  the fitted baseline objects;
* ``baseline_metrics.json`` — per-pathogen, per-baseline configuration + the
  test-period metrics (PR-AUC, ROC-AUC, precision, recall, Brier, base rate)
  and the train/test period ranges and sizes.

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
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from src.pipeline.features import PATHOGEN_SLUG, PROCESSED_ROOT
from src.pipeline.target import feature_columns
from src.models.splits import DEFAULT_TEST_FRACTION, ChronoSplit, chronological_split

__all__ = [
    "RANDOM_STATE",
    "MODELS_ROOT",
    "PRIMARY_LABEL_COL",
    "PRIMARY_LABELABLE_COL",
    "SMALL_CATEGORICALS",
    "PERSISTENCE_LAG_COL",
    "PERSISTENCE_BASELINE_COL",
    "RARE_EVENT_PREVALENCE",
    "SeasonalNaiveBaseline",
    "LogisticBaseline",
    "labelable_frame",
    "split_labelable",
    "evaluate_scores",
    "train_baselines_for_pathogen",
    "run_baselines",
]

#: Fixed seed pinning the logistic solver for reproducibility (Req 7.1 spirit).
RANDOM_STATE: int = 42

#: Where fitted baseline artifacts + metrics are written.
MODELS_ROOT: Path = PROCESSED_ROOT / "models"

#: The small categorical predictors one-hot encoded in the logistic baseline.
SMALL_CATEGORICALS: tuple[str, ...] = ("geo_state", "geo_region", "period_of_year")

#: Columns used by the seasonal-naive / persistence hard rule (both are
#: leakage-safe, <= cutoff features already in the model table).
PERSISTENCE_LAG_COL: str = "routine_positivity_lag1"
PERSISTENCE_BASELINE_COL: str = "routine_positivity_trailing12m_mean"

#: Positive-class prevalence below which rare-event handling (class_weight=
#: 'balanced') is applied in the logistic baseline (design "Rare events").
RARE_EVENT_PREVALENCE: float = 0.10


# --------------------------------------------------------------------------- #
# Metric helper
# --------------------------------------------------------------------------- #

def evaluate_scores(
    y_true: np.ndarray,
    y_score: np.ndarray,
    y_pred: np.ndarray,
) -> dict[str, Optional[float]]:
    """Compute the Req-7/8 test-period metrics from labels + scores.

    ``y_score`` is a probability-like score in ``[0, 1]`` used for PR-AUC /
    ROC-AUC / Brier; ``y_pred`` is the hard 0/1 prediction used for precision /
    recall. Any metric that is undefined for the given test slice (e.g. ROC-AUC
    with a single class present) is recorded as ``None`` rather than fabricated.
    """
    y_true = np.asarray(y_true, dtype=float)
    y_score = np.asarray(y_score, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)

    n = int(len(y_true))
    n_pos = int(y_true.sum())
    base_rate = (n_pos / n) if n else None
    single_class = len(np.unique(y_true)) < 2

    def _safe(fn):
        try:
            return float(fn())
        except Exception:  # noqa: BLE001 - metric undefined on this slice
            return None

    pr_auc = None if single_class else _safe(lambda: average_precision_score(y_true, y_score))
    roc_auc = None if single_class else _safe(lambda: roc_auc_score(y_true, y_score))
    brier = _safe(lambda: brier_score_loss(y_true, y_score))
    precision = _safe(lambda: precision_score(y_true, y_pred, zero_division=0))
    recall = _safe(lambda: recall_score(y_true, y_pred, zero_division=0))

    return {
        "pr_auc": pr_auc,
        "roc_auc": roc_auc,
        "precision": precision,
        "recall": recall,
        "brier": brier,
        "base_rate": base_rate,
        "n": n,
        "n_positive": n_pos,
    }


# --------------------------------------------------------------------------- #
# Baseline 1: seasonal / historical (non-ML) baseline
# --------------------------------------------------------------------------- #

@dataclass
class SeasonalNaiveBaseline:
    """Non-ML seasonal/historical reference baseline (Req 7.1).

    * **Score** (``predict_proba``-like): the historical frequency of the
      elevated label for the row's ``(state, period_of_year)`` on the TRAIN
      data, with back-off ``(state, season) -> state -> season -> global`` so
      every test row gets a defined probability in ``[0, 1]``.
    * **Hard rule** (``predict``): seasonal-naive / persistence — predict 1 when
      the last observed routine positivity exceeds its trailing baseline
      (``routine_positivity_lag1 > routine_positivity_trailing12m_mean``). When
      either input is missing the rule falls back to ``score >= 0.5``.

    Deterministic by construction, so identical inputs give identical outputs.
    """

    season_col: str = "period_of_year"
    state_col: str = "state"
    lag_col: str = PERSISTENCE_LAG_COL
    baseline_col: str = PERSISTENCE_BASELINE_COL

    global_rate_: float = field(default=0.0, init=False)
    state_season_rate_: dict[tuple[Any, Any], float] = field(default_factory=dict, init=False)
    state_rate_: dict[Any, float] = field(default_factory=dict, init=False)
    season_rate_: dict[Any, float] = field(default_factory=dict, init=False)

    def fit(self, frame: pd.DataFrame, y: pd.Series) -> "SeasonalNaiveBaseline":
        y = pd.to_numeric(y, errors="coerce").astype(float)
        work = pd.DataFrame(
            {
                "state": frame[self.state_col].to_numpy(),
                "season": frame[self.season_col].to_numpy(),
                "y": y.to_numpy(),
            }
        )
        self.global_rate_ = float(work["y"].mean()) if len(work) else 0.0
        self.state_season_rate_ = (
            work.groupby(["state", "season"])["y"].mean().to_dict()
        )
        self.state_rate_ = work.groupby("state")["y"].mean().to_dict()
        self.season_rate_ = work.groupby("season")["y"].mean().to_dict()
        return self

    def predict_proba_pos(self, frame: pd.DataFrame) -> np.ndarray:
        states = frame[self.state_col].to_numpy()
        seasons = frame[self.season_col].to_numpy()
        out = np.empty(len(frame), dtype=float)
        for i, (st, se) in enumerate(zip(states, seasons)):
            if (st, se) in self.state_season_rate_:
                out[i] = self.state_season_rate_[(st, se)]
            elif st in self.state_rate_:
                out[i] = self.state_rate_[st]
            elif se in self.season_rate_:
                out[i] = self.season_rate_[se]
            else:
                out[i] = self.global_rate_
        return np.clip(out, 0.0, 1.0)

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        score = self.predict_proba_pos(frame)
        pred = np.where(score >= 0.5, 1.0, 0.0)
        if self.lag_col in frame.columns and self.baseline_col in frame.columns:
            lag = pd.to_numeric(frame[self.lag_col], errors="coerce").to_numpy()
            base = pd.to_numeric(frame[self.baseline_col], errors="coerce").to_numpy()
            rule_defined = ~(np.isnan(lag) | np.isnan(base))
            rule_pred = (lag > base).astype(float)
            pred = np.where(rule_defined, rule_pred, pred)
        return pred

    def config(self) -> dict[str, Any]:
        return {
            "type": "seasonal_naive_historical",
            "is_ml": False,
            "score_definition": (
                "historical frequency of y_elevated for the row's "
                "(state, period_of_year) on train, backing off state -> season "
                "-> global train base rate"
            ),
            "hard_rule": (
                f"persistence/seasonal-naive: predict 1 when {self.lag_col} > "
                f"{self.baseline_col}; else fall back to score >= 0.5"
            ),
            "season_col": self.season_col,
            "state_col": self.state_col,
            "deterministic": True,
        }


# --------------------------------------------------------------------------- #
# Baseline 2: regularized logistic regression
# --------------------------------------------------------------------------- #

@dataclass
class LogisticBaseline:
    """Regularized (L2) logistic-regression baseline (Req 7.1).

    Numeric features are median-imputed (weather is mostly NaN — expected) and
    standardized; the small categoricals are one-hot encoded; the classifier is
    ``LogisticRegression`` with an L2 penalty and, for rare-event pathogens,
    ``class_weight='balanced'``. The whole thing is a single sklearn
    ``Pipeline`` so it can be pickled as one artifact. Fit on train only.
    """

    feature_cols: list[str]
    categorical_cols: list[str]
    class_weight: Optional[str] = "balanced"
    C: float = 1.0
    random_state: int = RANDOM_STATE

    pipeline_: Optional[Pipeline] = field(default=None, init=False)
    numeric_cols_: list[str] = field(default_factory=list, init=False)
    categorical_cols_: list[str] = field(default_factory=list, init=False)

    def _build(self, frame: Optional[pd.DataFrame] = None) -> Pipeline:
        # Start from the explicitly-declared small categoricals, then add any
        # remaining non-numeric (object/string/categorical) feature column so a
        # stray string column (e.g. the ACS/atlas vintage tags) is one-hot
        # encoded rather than fed to the numeric median imputer.
        cats = [c for c in self.categorical_cols if c in self.feature_cols]
        if frame is not None:
            for c in self.feature_cols:
                if c in cats:
                    continue
                if not pd.api.types.is_numeric_dtype(frame[c]):
                    cats.append(c)
        nums = [c for c in self.feature_cols if c not in cats]
        self.categorical_cols_ = cats
        self.numeric_cols_ = nums

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
        # L2 is LogisticRegression's default penalty; we leave it at the
        # default rather than passing penalty='l2' explicitly (that keyword is
        # deprecated in recent sklearn) so the regularization is L2 without the
        # deprecation warning.
        clf = LogisticRegression(
            C=self.C,
            class_weight=self.class_weight,
            solver="liblinear",
            max_iter=2000,
            random_state=self.random_state,
        )
        return Pipeline(steps=[("pre", pre), ("clf", clf)])

    def fit(self, frame: pd.DataFrame, y: pd.Series) -> "LogisticBaseline":
        self.pipeline_ = self._build(frame)
        X = frame[self.feature_cols]
        y_arr = pd.to_numeric(y, errors="coerce").astype(int).to_numpy()
        self.pipeline_.fit(X, y_arr)
        return self

    def predict_proba_pos(self, frame: pd.DataFrame) -> np.ndarray:
        assert self.pipeline_ is not None, "fit() must be called first"
        X = frame[self.feature_cols]
        return self.pipeline_.predict_proba(X)[:, 1]

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        assert self.pipeline_ is not None, "fit() must be called first"
        return self.pipeline_.predict(frame[self.feature_cols]).astype(float)

    def config(self) -> dict[str, Any]:
        return {
            "type": "regularized_logistic_regression",
            "is_ml": True,
            "penalty": "l2 (sklearn default)",
            "C": self.C,
            "solver": "liblinear",
            "max_iter": 2000,
            "class_weight": self.class_weight,
            "random_state": self.random_state,
            "numeric_features": self.numeric_cols_,
            "categorical_features": self.categorical_cols_,
            "n_features_in": len(self.feature_cols),
            "preprocessing": "median-impute + standardize numeric; most-frequent-impute + one-hot categoricals",
        }


# --------------------------------------------------------------------------- #
# Data preparation
# --------------------------------------------------------------------------- #

#: The PRIMARY modeling label after the scientific target redesign. The old
#: ``y_elevated`` (v1) is retained in the model tables for an honest before/after
#: comparison, but models now train/evaluate on the denominator-aware tail label.
PRIMARY_LABEL_COL: str = "y_elevated_v2"
PRIMARY_LABELABLE_COL: str = "labelable_v2"


def labelable_frame(
    model: pd.DataFrame,
    *,
    label_col: str = PRIMARY_LABEL_COL,
) -> pd.DataFrame:
    """Return only the labelable rows with an integer label present.

    ``label_col`` selects which target to model. For the redesigned primary
    label (``y_elevated_v2``) the matching labelability flag is ``labelable_v2``;
    for the legacy ``y_elevated`` it is ``labelable``.
    """
    labelable_col = (
        PRIMARY_LABELABLE_COL if label_col == PRIMARY_LABEL_COL else "labelable"
    )
    mask = (model[labelable_col] == True) & model[label_col].notna()  # noqa: E712
    out = model.loc[mask].copy()
    out[label_col] = out[label_col].astype(int)
    # Expose a canonical ``y_elevated`` column holding the SELECTED label so the
    # downstream model code (which references y_elevated) stays agnostic.
    out["y_elevated"] = out[label_col].astype(int)
    return out


def split_labelable(
    model: pd.DataFrame,
    *,
    test_fraction: float = DEFAULT_TEST_FRACTION,
    label_col: str = PRIMARY_LABEL_COL,
) -> ChronoSplit:
    """Restrict to labelable rows, then chronologically split (shared helper)."""
    return chronological_split(
        labelable_frame(model, label_col=label_col), test_fraction=test_fraction
    )


# --------------------------------------------------------------------------- #
# Per-pathogen training + evaluation
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


def train_baselines_for_pathogen(
    pathogen: str,
    *,
    processed_root: Optional[Path] = None,
    models_root: Optional[Path] = None,
    test_fraction: float = DEFAULT_TEST_FRACTION,
    write_artifacts: bool = True,
    label_col: str = PRIMARY_LABEL_COL,
) -> dict[str, Any]:
    """Train + evaluate BOTH baselines for one pathogen on the untouched test.

    ``label_col`` selects the target: ``y_elevated_v2`` (the redesigned
    denominator-aware primary, default) or the legacy ``y_elevated`` (used to
    regenerate the v1 before/after metrics).

    Returns a result dict holding, per baseline, its configuration and the
    test-period metrics, plus the train/test period ranges and sizes. Fitted
    objects are saved to ``models_root`` when ``write_artifacts`` is True.
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

    train_prev = float(y_train.mean()) if len(y_train) else 0.0
    rare_event = train_prev < RARE_EVENT_PREVALENCE
    class_weight = "balanced" if rare_event else "balanced"
    # Rare-event pathogens REQUIRE balanced weighting; Salmonella (~45% train
    # prevalence) is not rare but 'balanced' is still a sensible transparent
    # default and is recorded in the config for full transparency.

    # --- seasonal/historical baseline -------------------------------------
    seasonal = SeasonalNaiveBaseline().fit(train, y_train)
    seas_score = seasonal.predict_proba_pos(test)
    seas_pred = seasonal.predict(test)
    seas_metrics = evaluate_scores(y_test.to_numpy(), seas_score, seas_pred)

    # --- regularized logistic baseline ------------------------------------
    logistic = LogisticBaseline(
        feature_cols=list(feats),
        categorical_cols=list(SMALL_CATEGORICALS),
        class_weight=class_weight,
        random_state=RANDOM_STATE,
    ).fit(train, y_train)
    log_score = logistic.predict_proba_pos(test)
    log_pred = logistic.predict(test)
    log_metrics = evaluate_scores(y_test.to_numpy(), log_score, log_pred)

    artifacts: dict[str, Optional[str]] = {"seasonal": None, "logistic": None}
    if write_artifacts:
        models_root.mkdir(parents=True, exist_ok=True)
        seas_path = models_root / f"baseline_{slug}_seasonal.joblib"
        log_path = models_root / f"baseline_{slug}_logistic.joblib"
        joblib.dump(seasonal, seas_path)
        joblib.dump(logistic, log_path)
        artifacts["seasonal"] = str(seas_path)
        artifacts["logistic"] = str(log_path)

    resolution = str(model["resolution"].iloc[0]) if not model.empty else "unknown"
    overall_base_rate = float(labelable["y_elevated"].mean()) if len(labelable) else None

    return {
        "pathogen": pathogen,
        "resolution": resolution,
        "label_col": label_col,
        "feature_column_count": len(feats),
        "test_fraction": test_fraction,
        "random_state": RANDOM_STATE,
        "rare_event_prevalence_threshold": RARE_EVENT_PREVALENCE,
        "train_prevalence": train_prev,
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
        "baselines": {
            "seasonal_naive": {
                "config": seasonal.config(),
                "metrics": seas_metrics,
            },
            "regularized_logistic": {
                "config": logistic.config(),
                "metrics": log_metrics,
            },
        },
        "artifacts": artifacts,
    }


def run_baselines(
    *,
    pathogens: Optional[tuple[str, ...]] = None,
    processed_root: Optional[Path] = None,
    models_root: Optional[Path] = None,
    test_fraction: float = DEFAULT_TEST_FRACTION,
    write_metrics: bool = True,
    write_artifacts: bool = True,
    label_col: str = PRIMARY_LABEL_COL,
    metrics_filename: str = "baseline_metrics.json",
) -> dict[str, Any]:
    """Train + evaluate baselines for every pathogen; write the metrics JSON.

    Salmonella is processed first (the primary module), then Listeria and STEC.
    Writes ``data/processed/models/<metrics_filename>`` and returns the full
    results dict. ``label_col`` selects the target (``y_elevated_v2`` primary by
    default; pass ``y_elevated`` + ``metrics_filename='baseline_metrics_v1.json'``
    to regenerate the legacy before/after numbers).
    """
    processed_root = processed_root or PROCESSED_ROOT
    models_root = models_root or MODELS_ROOT
    order = pathogens or ("Salmonella", "Listeria", "STEC")

    results: dict[str, Any] = {
        "task": "3.4 Implement baseline models",
        "requirements": ["7.1"],
        "label_col": label_col,
        "random_state": RANDOM_STATE,
        "test_fraction": test_fraction,
        "split_strategy": (
            "strict chronological: most-recent ~20% of distinct periods held "
            "untouched; all train period_starts < all test period_starts "
            "(src.models.splits.chronological_split)"
        ),
        "per_pathogen": {},
    }
    for pathogen in order:
        results["per_pathogen"][pathogen] = train_baselines_for_pathogen(
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

    pprint.pprint(run_baselines())
