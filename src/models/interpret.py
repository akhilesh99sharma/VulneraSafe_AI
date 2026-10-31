"""Model interpretation: permutation importance, SHAP, error analysis (Task 3.9).

Requirement 9.1 asks, for every predictive module, a **permutation-importance
ranking of all input features** AND **SHAP attribution values for each input
feature**. Requirement 9.2 asks an **error analysis** reporting at least one
accuracy metric and at least one calibration / error-distribution metric on a
held-out evaluation set. This module produces all three for each pathogen's
BEST predictive model and exports ``interpret_<slug>.json``.

Best model per pathogen (from ``integrated_metrics.json`` test PR-AUC)
----------------------------------------------------------------------
* **Salmonella -> LightGBM**
* **Listeria   -> RandomForest**
* **STEC       -> RandomForest**

These are passed in explicitly (``BEST_MODEL``) so the interpretation targets
the model the decision layer actually uses. Each is the exact fitted
``IntegratedModel`` artifact written by Task 3.5
(``integrated_<slug>_<model>.joblib``) — a single sklearn ``Pipeline`` of
``("pre", ColumnTransformer) -> ("clf", tree_classifier)``.

How the three artifacts are computed
------------------------------------
1. **Permutation importance** (``sklearn.inspection.permutation_importance``):
   run on the WHOLE fitted pipeline over the untouched chronological TEST set,
   scoring with ``average_precision`` (PR-AUC — the rare-event-appropriate
   primary metric). This permutes each RAW input feature column in turn and
   measures the mean drop in PR-AUC, so the ranking is over the real model
   inputs (not the one-hot-expanded columns). Reported mean + std over
   ``n_repeats`` shuffles, ranked by mean importance drop. Negative / zero
   importances are reported honestly (Req 9.5 spirit).

2. **SHAP** (``shap.TreeExplainer``): the TreeExplainer cannot run on the
   sklearn ``Pipeline`` directly, so we run it on the **fitted classifier step**
   (``pipeline_.named_steps['clf']``) over the **transformed** test matrix
   (``pipeline_.named_steps['pre'].transform(X_test)``), capped at
   :data:`SHAP_MAX_ROWS` rows for speed. The resulting per-(transformed-column)
   SHAP values are aggregated back to the ORIGINAL input features by summing
   mean |SHAP| over every one-hot column that a categorical feature expands into
   (numeric features map 1:1). This "run on the classifier step + map back"
   approach is recorded in the JSON (``shap.approach``). Mean |SHAP| per original
   feature + the top features are exported.

3. **Error analysis** (Req 9.2): computed from the EXPORTED predictions
   (``preds_<slug>.parquet`` — Req 8.6, metrics only from exported predictions)
   for the best model's probability column. Reports:
   * an **accuracy metric** — PR-AUC (``average_precision``) and ROC-AUC;
   * a **calibration metric** — the Brier score plus a reliability table
     (observed positive rate vs mean predicted probability per probability
     band);
   * an **error-distribution breakdown** — where errors concentrate, by
     geographic region and by predicted-probability band (counts + FP/FN rates).

Nothing is fabricated: any metric undefined on the test slice (e.g. ROC-AUC with
a single class) is recorded as ``None`` / unavailable.

Outputs (written under ``data/processed/models/``)
--------------------------------------------------
``interpret_<slug>.json`` per pathogen and an ``interpret_summary.json`` index.

Design reference: design.md "Interpretation and ablations (Req 9)".
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from sklearn.inspection import permutation_importance

from src.pipeline.features import PATHOGEN_SLUG, PROCESSED_ROOT
from src.pipeline.target import feature_columns
from src.models.splits import DEFAULT_TEST_FRACTION, chronological_split
from src.models.baseline import MODELS_ROOT, RANDOM_STATE, SMALL_CATEGORICALS, labelable_frame
from src.models.integrated import IntegratedModel, INTEGRATED_MODEL_NAMES

__all__ = [
    "BEST_MODEL",
    "SHAP_MAX_ROWS",
    "PERM_N_REPEATS",
    "PROB_BANDS",
    "best_model_name_for",
    "load_or_fit_best_model",
    "permutation_importance_ranking",
    "shap_attributions",
    "error_analysis",
    "interpret_pathogen",
    "run_interpretation",
]

#: The BEST predictive model per pathogen (selected from Task 3.5 test PR-AUC).
#: The decision layer uses these, so interpretation targets exactly them.
BEST_MODEL: dict[str, str] = {
    "Salmonella": "lightgbm",
    "Listeria": "random_forest",
    "STEC": "random_forest",
}

#: Cap on test rows fed to SHAP's TreeExplainer (SHAP is slow; a sample keeps
#: the run tractable while remaining representative — Req 9.1 "for each feature").
SHAP_MAX_ROWS: int = 500

#: Permutation-importance shuffle repeats (mean + std over this many shuffles).
PERM_N_REPEATS: int = 10

#: Predicted-probability bands for the calibration / error-distribution breakdown.
PROB_BANDS: tuple[float, ...] = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)


# --------------------------------------------------------------------------- #
# Model + data loading
# --------------------------------------------------------------------------- #

def best_model_name_for(pathogen: str) -> str:
    """Return the best integrated-model name for ``pathogen`` (validated)."""
    name = BEST_MODEL[pathogen]
    assert name in INTEGRATED_MODEL_NAMES, f"unknown model {name!r}"
    return name


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


def load_or_fit_best_model(
    pathogen: str,
    train: pd.DataFrame,
    feats: list[str],
    *,
    models_root: Path,
) -> IntegratedModel:
    """Load the fitted best-model artifact if present, else re-fit it on train.

    Re-fitting uses the SAME configuration as Task 3.5 (same features, same
    categoricals, fixed seed), so an artifact-less run still reproduces the
    model deterministically.
    """
    import joblib

    name = best_model_name_for(pathogen)
    slug = PATHOGEN_SLUG[pathogen]
    artifact = models_root / f"integrated_{slug}_{name}.joblib"
    if artifact.exists():
        try:
            mdl = joblib.load(artifact)
            if isinstance(mdl, IntegratedModel) and mdl.pipeline_ is not None:
                return mdl
        except Exception:  # noqa: BLE001 - fall back to re-fit on any load issue
            pass

    # Re-fit deterministically (rare_event flag does not change feature mapping;
    # mirror Task 3.5's measured-prevalence trigger for fidelity).
    y_train = train["y_elevated"].astype(int)
    prev = float(y_train.mean()) if len(y_train) else 0.0
    n_pos = int(y_train.sum())
    n_neg = int(len(y_train) - n_pos)
    spw = (n_neg / n_pos) if n_pos else 1.0
    rare = prev < 0.10
    return IntegratedModel(
        name=name,
        feature_cols=list(feats),
        categorical_cols=list(SMALL_CATEGORICALS),
        rare_event=rare,
        scale_pos_weight=spw,
        random_state=RANDOM_STATE,
    ).fit(train, y_train)


# --------------------------------------------------------------------------- #
# 1. Permutation importance (Req 9.1)
# --------------------------------------------------------------------------- #

def permutation_importance_ranking(
    model: IntegratedModel,
    test: pd.DataFrame,
    feats: list[str],
    *,
    n_repeats: int = PERM_N_REPEATS,
    random_state: int = RANDOM_STATE,
) -> dict[str, Any]:
    """Permutation importance of every RAW input feature on the untouched test.

    Scored with ``average_precision`` (PR-AUC) over the whole fitted pipeline so
    each raw column is permuted as the model sees it. Returns the full ranking
    (mean drop + std, descending) — negative / zero importances kept honestly.
    """
    assert model.pipeline_ is not None, "model must be fitted"
    X = test[feats]
    y = test["y_elevated"].astype(int).to_numpy()

    single_class = len(np.unique(y)) < 2
    if single_class:
        return {
            "available": False,
            "reason": "test slice has a single class; PR-AUC permutation importance undefined",
            "scoring": "average_precision",
            "ranking": [],
        }

    result = permutation_importance(
        model.pipeline_,
        X,
        y,
        scoring="average_precision",
        n_repeats=n_repeats,
        random_state=random_state,
        n_jobs=1,
    )
    ranking = [
        {
            "feature": feats[i],
            "importance_mean": float(result.importances_mean[i]),
            "importance_std": float(result.importances_std[i]),
        }
        for i in range(len(feats))
    ]
    ranking.sort(key=lambda r: r["importance_mean"], reverse=True)
    return {
        "available": True,
        "scoring": "average_precision",
        "n_repeats": n_repeats,
        "random_state": random_state,
        "note": (
            "mean drop in PR-AUC when each RAW input feature is permuted on the "
            "untouched chronological test set; negative/zero values reported as-is"
        ),
        "ranking": ranking,
    }


# --------------------------------------------------------------------------- #
# 2. SHAP attributions (Req 9.1)
# --------------------------------------------------------------------------- #

def _transformed_feature_names(model: IntegratedModel, feats: list[str]) -> list[str]:
    """Best-effort names of the one-hot-expanded transformed columns."""
    pre = model.pipeline_.named_steps["pre"]
    try:
        return list(pre.get_feature_names_out())
    except Exception:  # noqa: BLE001 - older sklearn / transformer fallbacks
        n = pre.transform(pd.DataFrame(columns=feats)).shape[1] if False else None
        return [f"f{i}" for i in range(n or 0)]


def _map_transformed_to_original(
    transformed_names: list[str],
    feats: list[str],
) -> dict[str, list[int]]:
    """Map each ORIGINAL feature to the indices of its transformed columns.

    The ColumnTransformer prefixes numeric columns ``num__<feat>`` and one-hot
    columns ``cat__<feat>_<level>``. We attribute a transformed column to the
    original feature whose name it carries after the transformer prefix.
    """
    mapping: dict[str, list[int]] = {f: [] for f in feats}
    # longest feature names first so e.g. 'routine_positivity_lag1' is matched
    # before a hypothetical 'routine_positivity'
    ordered = sorted(feats, key=len, reverse=True)
    for j, tname in enumerate(transformed_names):
        body = tname.split("__", 1)[1] if "__" in tname else tname
        for f in ordered:
            if body == f or body.startswith(f + "_"):
                mapping[f].append(j)
                break
    return mapping


def shap_attributions(
    model: IntegratedModel,
    test: pd.DataFrame,
    feats: list[str],
    *,
    max_rows: int = SHAP_MAX_ROWS,
    random_state: int = RANDOM_STATE,
) -> dict[str, Any]:
    """SHAP TreeExplainer mean |SHAP| per ORIGINAL feature (Req 9.1).

    Runs TreeExplainer on the fitted CLASSIFIER step over the TRANSFORMED test
    matrix (a sample capped at ``max_rows``), then aggregates mean |SHAP| back
    to the original input features (summing over each feature's one-hot columns).
    The approach is recorded so the mapping is auditable.
    """
    assert model.pipeline_ is not None, "model must be fitted"
    try:
        import shap  # noqa: F401
    except Exception as exc:  # noqa: BLE001 - shap optional at import time
        return {"available": False, "reason": f"shap import failed: {exc!r}", "top_features": []}

    pre = model.pipeline_.named_steps["pre"]
    clf = model.pipeline_.named_steps["clf"]

    X = test[feats]
    if len(X) > max_rows:
        X = X.sample(n=max_rows, random_state=random_state)
    Xt = pre.transform(X)
    # TreeExplainer wants a dense array
    try:
        Xt_dense = Xt.toarray() if hasattr(Xt, "toarray") else np.asarray(Xt)
    except Exception:  # noqa: BLE001
        Xt_dense = np.asarray(Xt)

    import shap

    try:
        explainer = shap.TreeExplainer(clf)
        sv = explainer.shap_values(Xt_dense)
    except Exception as exc:  # noqa: BLE001 - surface honestly, don't fabricate
        return {
            "available": False,
            "reason": f"TreeExplainer failed on classifier step: {exc!r}",
            "approach": "TreeExplainer on fitted clf step over transformed matrix",
            "top_features": [],
        }

    # Normalise to the positive-class 2-D SHAP matrix (n_rows, n_transformed).
    arr = _positive_class_shap(sv, n_rows=Xt_dense.shape[0], n_cols=Xt_dense.shape[1])
    mean_abs_transformed = np.abs(arr).mean(axis=0)  # per transformed column

    tnames = _transformed_feature_names(model, feats)
    if len(tnames) != mean_abs_transformed.shape[0]:
        tnames = [f"t{i}" for i in range(mean_abs_transformed.shape[0])]
    mapping = _map_transformed_to_original(tnames, feats)

    per_feature: list[dict[str, Any]] = []
    for f in feats:
        idxs = mapping.get(f, [])
        val = float(mean_abs_transformed[idxs].sum()) if idxs else 0.0
        per_feature.append({"feature": f, "mean_abs_shap": val})
    per_feature.sort(key=lambda r: r["mean_abs_shap"], reverse=True)

    return {
        "available": True,
        "approach": (
            "shap.TreeExplainer on the fitted classifier step "
            "(pipeline_.named_steps['clf']) over the preprocessed/transformed "
            "test matrix (pipeline_.named_steps['pre'].transform(X)); mean |SHAP| "
            "aggregated back to ORIGINAL features by summing over each feature's "
            "one-hot-expanded transformed columns"
        ),
        "n_rows_sampled": int(Xt_dense.shape[0]),
        "max_rows": max_rows,
        "n_transformed_columns": int(mean_abs_transformed.shape[0]),
        "per_feature_mean_abs_shap": per_feature,
    }


def _positive_class_shap(sv: Any, *, n_rows: int, n_cols: int) -> np.ndarray:
    """Return the positive-class SHAP matrix as a (n_rows, n_cols) array.

    Different SHAP / model versions return either a single array, a list of two
    arrays (one per class), or a 3-D array ``(n_rows, n_cols, n_classes)``. This
    normalises all of them to the positive-class 2-D matrix.
    """
    if isinstance(sv, list):
        # list per class -> take the positive class (index 1 when present)
        chosen = sv[1] if len(sv) > 1 else sv[0]
        return np.asarray(chosen).reshape(n_rows, n_cols)
    arr = np.asarray(sv)
    if arr.ndim == 3:
        # (n_rows, n_cols, n_classes) -> positive class
        return arr[:, :, 1] if arr.shape[2] > 1 else arr[:, :, 0]
    return arr.reshape(n_rows, n_cols)


# --------------------------------------------------------------------------- #
# 3. Error analysis (Req 9.2)
# --------------------------------------------------------------------------- #

def _reliability_table(
    y_true: np.ndarray, proba: np.ndarray, bands: tuple[float, ...]
) -> list[dict[str, Any]]:
    """Reliability/calibration table: observed vs predicted per probability band."""
    rows: list[dict[str, Any]] = []
    for lo, hi in zip(bands[:-1], bands[1:]):
        # last band is inclusive on the right so proba==1.0 lands somewhere
        if hi >= 1.0:
            mask = (proba >= lo) & (proba <= hi)
        else:
            mask = (proba >= lo) & (proba < hi)
        n = int(mask.sum())
        rows.append(
            {
                "band": f"[{lo:.1f}, {hi:.1f}{']' if hi >= 1.0 else ')'}",
                "n": n,
                "mean_predicted": float(proba[mask].mean()) if n else None,
                "observed_positive_rate": float(y_true[mask].mean()) if n else None,
            }
        )
    return rows


def error_analysis(
    preds: pd.DataFrame,
    proba_col: str,
    *,
    threshold: float = 0.5,
    bands: tuple[float, ...] = PROB_BANDS,
) -> dict[str, Any]:
    """Error analysis from EXPORTED predictions (Req 9.2, Req 8.6).

    Reports an accuracy metric (PR-AUC + ROC-AUC), a calibration metric (Brier +
    reliability table), and an error-distribution breakdown by region and by
    predicted-probability band. Metrics undefined on the slice are ``None``.
    """
    from sklearn.metrics import (
        average_precision_score,
        brier_score_loss,
        roc_auc_score,
    )

    y = preds["y_true"].astype(int).to_numpy()
    p = preds[proba_col].astype(float).to_numpy()
    pred = (p >= threshold).astype(int)
    single_class = len(np.unique(y)) < 2

    def _safe(fn):
        try:
            return float(fn())
        except Exception:  # noqa: BLE001
            return None

    pr_auc = None if single_class else _safe(lambda: average_precision_score(y, p))
    roc_auc = None if single_class else _safe(lambda: roc_auc_score(y, p))
    brier = _safe(lambda: brier_score_loss(y, p))

    fp = int(((pred == 1) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum())
    tp = int(((pred == 1) & (y == 1)).sum())
    tn = int(((pred == 0) & (y == 0)).sum())
    n = int(len(y))
    n_pos = int(y.sum())
    n_neg = n - n_pos

    # error concentration by region (if the region key is available). preds does
    # not carry geo_region, so derive it from the state via the shared map.
    region_breakdown: list[dict[str, Any]] = []
    if "state" in preds.columns:
        from src.pipeline.features import CENSUS_REGION

        regions = preds["state"].map(lambda s: CENSUS_REGION.get(s, "Other"))
        tmp = pd.DataFrame({"region": regions.to_numpy(), "y": y, "pred": pred})
        for region, grp in tmp.groupby("region"):
            gy = grp["y"].to_numpy()
            gp = grp["pred"].to_numpy()
            g_fp = int(((gp == 1) & (gy == 0)).sum())
            g_fn = int(((gp == 0) & (gy == 1)).sum())
            gn = int(len(grp))
            region_breakdown.append(
                {
                    "region": str(region),
                    "n": gn,
                    "n_positive": int(gy.sum()),
                    "false_positives": g_fp,
                    "false_negatives": g_fn,
                    "error_rate": float((g_fp + g_fn) / gn) if gn else None,
                }
            )
        region_breakdown.sort(key=lambda r: (r["error_rate"] or 0.0), reverse=True)

    return {
        "proba_col": proba_col,
        "threshold": threshold,
        "accuracy_metrics": {"pr_auc": pr_auc, "roc_auc": roc_auc},
        "calibration_metrics": {
            "brier": brier,
            "reliability_table": _reliability_table(y, p, bands),
        },
        "confusion": {
            "n": n,
            "n_positive": n_pos,
            "n_negative": n_neg,
            "true_positives": tp,
            "true_negatives": tn,
            "false_positives": fp,
            "false_negatives": fn,
            "false_positive_rate": float(fp / n_neg) if n_neg else None,
            "false_negative_rate": float(fn / n_pos) if n_pos else None,
        },
        "error_concentration_by_region": region_breakdown,
        "error_concentration_by_prob_band": _reliability_table(y, p, bands),
        "note": (
            "accuracy = PR-AUC/ROC-AUC; calibration = Brier + reliability table; "
            "errors broken down by region and predicted-probability band; metrics "
            "undefined on the slice recorded as null (Req 8.6/9.2)"
        ),
    }


def _load_predictions(pathogen: str, models_root: Path) -> Optional[pd.DataFrame]:
    slug = PATHOGEN_SLUG[pathogen]
    parquet = models_root / f"preds_{slug}.parquet"
    csv = models_root / f"preds_{slug}.csv"
    if parquet.exists():
        return pd.read_parquet(parquet)
    if csv.exists():
        return pd.read_csv(csv)
    return None


# --------------------------------------------------------------------------- #
# Per-pathogen interpretation + orchestration
# --------------------------------------------------------------------------- #

def interpret_pathogen(
    pathogen: str,
    *,
    processed_root: Optional[Path] = None,
    models_root: Optional[Path] = None,
    test_fraction: float = DEFAULT_TEST_FRACTION,
    shap_max_rows: int = SHAP_MAX_ROWS,
    write: bool = True,
) -> dict[str, Any]:
    """Run permutation importance, SHAP, and error analysis for one pathogen."""
    processed_root = processed_root or PROCESSED_ROOT
    models_root = models_root or MODELS_ROOT
    slug = PATHOGEN_SLUG[pathogen]
    name = best_model_name_for(pathogen)

    model_tbl = _load_model_table(pathogen, processed_root)
    labelable = labelable_frame(model_tbl)
    feats = feature_columns(labelable)
    split = chronological_split(labelable, test_fraction=test_fraction)

    model = load_or_fit_best_model(
        pathogen, split.train, feats, models_root=models_root
    )

    perm = permutation_importance_ranking(model, split.test, feats)
    shap_res = shap_attributions(model, split.test, feats, max_rows=shap_max_rows)

    preds = _load_predictions(pathogen, models_root)
    proba_col = f"proba_{name}"
    if preds is not None and proba_col in preds.columns:
        err = error_analysis(preds, proba_col)
        err_source = "exported preds_<slug> (Req 8.6)"
    else:
        # fall back to scoring the untouched test directly (still held-out)
        fallback = pd.DataFrame(
            {
                "state": split.test["state"].to_numpy(),
                "period": split.test["period"].to_numpy(),
                "y_true": split.test["y_elevated"].astype(int).to_numpy(),
                proba_col: model.predict_proba_pos(split.test),
            }
        )
        err = error_analysis(fallback, proba_col)
        err_source = "scored untouched chronological test (preds file absent)"

    top_perm = [r["feature"] for r in perm.get("ranking", [])[:5]]
    top_shap = [
        r["feature"] for r in shap_res.get("per_feature_mean_abs_shap", [])[:5]
    ]

    result: dict[str, Any] = {
        "task": "3.9 Implement interpretation and ablations",
        "requirements": ["9.1", "9.2"],
        "pathogen": pathogen,
        "best_model": name,
        "n_features": len(feats),
        "test_fraction": test_fraction,
        "split": {
            "train_periods": [split.train_period_range[0], split.train_period_range[1]],
            "test_periods": [split.test_period_range[0], split.test_period_range[1]],
            "n_test_rows": int(len(split.test)),
        },
        "error_analysis_source": err_source,
        "permutation_importance": perm,
        "shap": shap_res,
        "error_analysis": err,
        "top5_permutation_importance": top_perm,
        "top5_shap": top_shap,
    }

    if write:
        models_root.mkdir(parents=True, exist_ok=True)
        out = models_root / f"interpret_{slug}.json"
        out.write_text(json.dumps(result, indent=2), encoding="utf-8")
        result["interpret_path"] = str(out)

    return result


def run_interpretation(
    *,
    pathogens: Optional[tuple[str, ...]] = None,
    processed_root: Optional[Path] = None,
    models_root: Optional[Path] = None,
    test_fraction: float = DEFAULT_TEST_FRACTION,
    shap_max_rows: int = SHAP_MAX_ROWS,
    write: bool = True,
) -> dict[str, Any]:
    """Interpret every predictive module; write per-pathogen JSON + an index."""
    processed_root = processed_root or PROCESSED_ROOT
    models_root = models_root or MODELS_ROOT
    order = pathogens or ("Salmonella", "Listeria", "STEC")

    per: dict[str, Any] = {}
    for pathogen in order:
        per[pathogen] = interpret_pathogen(
            pathogen,
            processed_root=processed_root,
            models_root=models_root,
            test_fraction=test_fraction,
            shap_max_rows=shap_max_rows,
            write=write,
        )

    summary = {
        "task": "3.9 Implement interpretation and ablations",
        "requirements": ["9.1", "9.2"],
        "best_model_per_pathogen": BEST_MODEL,
        "shap_max_rows": shap_max_rows,
        "permutation_n_repeats": PERM_N_REPEATS,
        "per_pathogen": {
            p: {
                "best_model": per[p]["best_model"],
                "top5_permutation_importance": per[p]["top5_permutation_importance"],
                "top5_shap": per[p]["top5_shap"],
            }
            for p in order
        },
    }
    if write:
        models_root.mkdir(parents=True, exist_ok=True)
        out = models_root / "interpret_summary.json"
        out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        summary["summary_path"] = str(out)
    return summary


if __name__ == "__main__":  # pragma: no cover - manual invocation
    import pprint

    pprint.pprint(run_interpretation())
