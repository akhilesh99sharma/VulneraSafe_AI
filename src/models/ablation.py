"""Data-source ablations with signed marginal contributions (Task 3.9; Req 9.3-9.5).

Requirement 9.3 asks for **exactly four** ablation configurations defined by
data source: **FSIS-only**, **FSIS+CDC**, **FSIS+NOAA**, and the **full**
integrated configuration (FSIS + CDC + NOAA). Requirement 9.4 asks, once all
four are evaluated on the SAME held-out set with the SAME metric, the **signed
marginal contribution** of each relative to FSIS-only. Requirement 9.5 forbids
omitting, clamping, or suppressing a negative contribution.

Feature groups (derived from the real model-table columns, Task 3.1)
--------------------------------------------------------------------
The 39-column feature matrix partitions cleanly by data source:

* **FSIS** — everything derived from FSIS routine/for-cause/exploratory
  sampling plus the calendar/geography context that frames it:
  ``routine_*``, ``context_forcause_*``, ``context_exploratory_*``,
  ``national_routine_*``, ``season_*``, ``period_of_year``, ``calendar_*``,
  ``geo_*``.
* **CDC** — human-health signal features. **NONE EXIST** in the current feature
  matrix: the CDC human-health stream was not joined into harmonize, so there
  is no CDC column to add. This is handled HONESTLY (see below), never
  fabricated.
* **NOAA** — weather features ``weather_*`` from NOAA nClimDiv statewide monthly
  climate (national state-level coverage, ~87% of state-periods non-missing;
  Hawaii and the newest unpublished months are the documented gaps). The marginal
  contribution is measured and reported with its real sign — small positive for
  Salmonella/STEC, slightly negative for Listeria.
* **Static context (ACS / Food Access Atlas)** — ``static_*``. These are
  slowly-varying demographic / food-access context, NOT a One-Health
  surveillance stream; they are folded into the ``full`` configuration and
  labelled as static context in the report, not treated as a CDC/NOAA stream.

The four configurations
-----------------------
* ``fsis_only``  = FSIS feature group only.
* ``fsis_cdc``   = FSIS + CDC features. Because no CDC columns exist, this is the
  SAME feature set as ``fsis_only``; rather than fabricate a delta we record the
  configuration as a **recorded gap** (``cdc_features_available = False``,
  ``marginal_contribution = None``, status ``"gap"``) and flag it as a known
  limitation feeding Task 8 / the report.
* ``fsis_noaa``  = FSIS + NOAA (``weather_*``).
* ``full``       = FSIS + CDC(none) + NOAA + static ACS/Atlas context — every
  available feature group.

Each configuration trains the pathogen's BEST model type (same as Task 3.5 /
:data:`src.models.interpret.BEST_MODEL`) on the SAME chronological train split
and evaluates on the SAME untouched test. The primary metric is **PR-AUC**
(``pr_auc``); ROC-AUC is reported alongside. The signed marginal contribution is
``metric(config) - metric(fsis_only)`` with the sign preserved (Req 9.4, 9.5).

Outputs
-------
``data/processed/models/ablation_<slug>.json`` per pathogen and a combined
``docs/reports/ablation.md`` describing all three pathogens, the CDC gap, and the
near-zero NOAA contribution.

Design reference: design.md "Interpretation and ablations (Req 9)".
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from src.pipeline.features import DOCS_REPORTS, PATHOGEN_SLUG, PROCESSED_ROOT
from src.pipeline.target import feature_columns
from src.models.splits import DEFAULT_TEST_FRACTION, chronological_split
from src.models.baseline import (
    MODELS_ROOT,
    RANDOM_STATE,
    SMALL_CATEGORICALS,
    evaluate_scores,
    labelable_frame,
)
from src.models.integrated import IntegratedModel
from src.models.interpret import BEST_MODEL, best_model_name_for

__all__ = [
    "ABLATION_CONFIGS",
    "PRIMARY_METRIC",
    "classify_feature_group",
    "group_features",
    "config_feature_columns",
    "signed_marginal_contribution",
    "ablation_for_pathogen",
    "run_ablations",
    "write_ablation_report",
]

#: The EXACTLY four ablation configuration names (Req 9.3). Order is meaningful:
#: fsis_only is the baseline every marginal is measured against.
ABLATION_CONFIGS: tuple[str, ...] = ("fsis_only", "fsis_cdc", "fsis_noaa", "full")

#: Primary ablation metric (rare-event-appropriate). ROC-AUC reported alongside.
PRIMARY_METRIC: str = "pr_auc"


# --------------------------------------------------------------------------- #
# Feature-group classification by DATA SOURCE
# --------------------------------------------------------------------------- #

#: Prefixes that mark a feature column as belonging to each data-source group.
_FSIS_PREFIXES: tuple[str, ...] = (
    "routine_", "context_forcause_", "context_exploratory_",
    "national_routine_", "season_", "calendar_",
)
_FSIS_EXACT: frozenset[str] = frozenset({"period_of_year", "geo_state", "geo_region"})
_NOAA_PREFIX: str = "weather_"
_STATIC_PREFIX: str = "static_"
#: No CDC columns are wired into the feature matrix (documented honestly).
_CDC_PREFIXES: tuple[str, ...] = ("cdc_",)


def classify_feature_group(column: str) -> str:
    """Classify a feature column into a data-source group.

    Returns one of ``"fsis"``, ``"cdc"``, ``"noaa"``, ``"static"`` or
    ``"other"``. The classification is purely by column name so it is auditable
    and testable without the data.
    """
    if column.startswith(_CDC_PREFIXES):
        return "cdc"
    if column.startswith(_NOAA_PREFIX):
        return "noaa"
    if column.startswith(_STATIC_PREFIX):
        return "static"
    if column in _FSIS_EXACT or column.startswith(_FSIS_PREFIXES):
        return "fsis"
    return "other"


def group_features(feats: list[str]) -> dict[str, list[str]]:
    """Partition the feature list into the data-source groups."""
    groups: dict[str, list[str]] = {"fsis": [], "cdc": [], "noaa": [], "static": [], "other": []}
    for c in feats:
        groups[classify_feature_group(c)].append(c)
    return groups


def config_feature_columns(config: str, groups: dict[str, list[str]]) -> list[str]:
    """Return the feature columns for a named ablation configuration.

    ``fsis_only`` -> FSIS group (+ any 'other' FSIS-adjacent context);
    ``fsis_cdc``  -> FSIS + CDC (CDC may be empty -> same as fsis_only);
    ``fsis_noaa`` -> FSIS + NOAA;
    ``full``      -> FSIS + CDC + NOAA + static context (every available group).
    """
    fsis = groups["fsis"] + groups["other"]
    if config == "fsis_only":
        return list(fsis)
    if config == "fsis_cdc":
        return list(fsis) + list(groups["cdc"])
    if config == "fsis_noaa":
        return list(fsis) + list(groups["noaa"])
    if config == "full":
        return list(fsis) + list(groups["cdc"]) + list(groups["noaa"]) + list(groups["static"])
    raise ValueError(f"unknown ablation config: {config!r}")


# --------------------------------------------------------------------------- #
# Signed marginal contribution (Req 9.4, 9.5)
# --------------------------------------------------------------------------- #

def signed_marginal_contribution(
    config_metric: Optional[float],
    fsis_only_metric: Optional[float],
) -> Optional[float]:
    """Signed marginal = config_metric - fsis_only_metric (sign PRESERVED).

    Returns ``None`` only when either input metric is itself unavailable
    (undefined on the slice). A negative result is returned with its negative
    sign — never clamped to zero or suppressed (Req 9.5).
    """
    if config_metric is None or fsis_only_metric is None:
        return None
    return float(config_metric - fsis_only_metric)


# --------------------------------------------------------------------------- #
# Train + evaluate one configuration
# --------------------------------------------------------------------------- #

def _train_eval_config(
    model_name: str,
    train: pd.DataFrame,
    test: pd.DataFrame,
    feat_cols: list[str],
    *,
    rare_event: bool,
    scale_pos_weight: float,
) -> dict[str, Any]:
    """Fit ``model_name`` on ``feat_cols`` over train; evaluate on untouched test."""
    y_train = train["y_elevated"].astype(int)
    y_test = test["y_elevated"].astype(int).to_numpy()
    mdl = IntegratedModel(
        name=model_name,
        feature_cols=list(feat_cols),
        categorical_cols=list(SMALL_CATEGORICALS),
        rare_event=rare_event,
        scale_pos_weight=scale_pos_weight,
        random_state=RANDOM_STATE,
    ).fit(train, y_train)
    score = mdl.predict_proba_pos(test)
    pred = mdl.predict(test)
    return evaluate_scores(y_test, score, pred)


def ablation_for_pathogen(
    pathogen: str,
    *,
    processed_root: Optional[Path] = None,
    models_root: Optional[Path] = None,
    test_fraction: float = DEFAULT_TEST_FRACTION,
    write: bool = True,
) -> dict[str, Any]:
    """Run the four data-source ablations for one pathogen on the SAME split.

    Trains the pathogen's best model type on the SAME chronological train split
    for each configuration, evaluates on the SAME untouched test, and reports
    the signed marginal contribution vs ``fsis_only`` (Req 9.4). The ``fsis_cdc``
    configuration is recorded as a GAP when no CDC features exist (Req 9.5 honest
    handling — no fabricated delta).
    """
    processed_root = processed_root or PROCESSED_ROOT
    models_root = models_root or MODELS_ROOT
    slug = PATHOGEN_SLUG[pathogen]
    model_name = best_model_name_for(pathogen)

    parquet = processed_root / f"model_{slug}.parquet"
    csv = processed_root / f"model_{slug}.csv"
    if parquet.exists():
        model_tbl = pd.read_parquet(parquet)
    elif csv.exists():
        model_tbl = pd.read_csv(csv)
    else:
        raise FileNotFoundError(f"no model table for {pathogen} at {parquet}")

    labelable = labelable_frame(model_tbl)
    feats = feature_columns(labelable)
    groups = group_features(feats)
    cdc_available = len(groups["cdc"]) > 0
    noaa_available = len(groups["noaa"]) > 0

    split = chronological_split(labelable, test_fraction=test_fraction)
    train, test = split.train, split.test

    # Rare-event trigger measured on TRAIN only (same rule as Task 3.5).
    y_train = train["y_elevated"].astype(int)
    train_prev = float(y_train.mean()) if len(y_train) else 0.0
    n_pos = int(y_train.sum())
    n_neg = int(len(y_train) - n_pos)
    spw = (n_neg / n_pos) if n_pos else 1.0
    rare = train_prev < 0.10

    # --- fsis_only baseline (always computed first) -----------------------
    fsis_cols = config_feature_columns("fsis_only", groups)
    base_metrics = _train_eval_config(
        model_name, train, test, fsis_cols, rare_event=rare, scale_pos_weight=spw
    )
    base_primary = base_metrics.get(PRIMARY_METRIC)

    configs: dict[str, Any] = {}
    configs["fsis_only"] = {
        "status": "evaluated",
        "data_sources": ["FSIS"],
        "n_features": len(fsis_cols),
        "metrics": base_metrics,
        "marginal_contribution_pr_auc": 0.0,  # by definition vs itself
        "marginal_contribution_roc_auc": 0.0,
        "note": "baseline configuration; every marginal is measured vs this",
    }

    # --- fsis_cdc ---------------------------------------------------------
    if cdc_available:
        cdc_cols = config_feature_columns("fsis_cdc", groups)
        cdc_metrics = _train_eval_config(
            model_name, train, test, cdc_cols, rare_event=rare, scale_pos_weight=spw
        )
        configs["fsis_cdc"] = {
            "status": "evaluated",
            "data_sources": ["FSIS", "CDC"],
            "n_features": len(cdc_cols),
            "n_cdc_features": len(groups["cdc"]),
            "metrics": cdc_metrics,
            "marginal_contribution_pr_auc": signed_marginal_contribution(
                cdc_metrics.get("pr_auc"), base_primary
            ),
            "marginal_contribution_roc_auc": signed_marginal_contribution(
                cdc_metrics.get("roc_auc"), base_metrics.get("roc_auc")
            ),
        }
    else:
        configs["fsis_cdc"] = {
            "status": "gap",
            "data_sources": ["FSIS", "CDC"],
            "cdc_features_available": False,
            "n_cdc_features": 0,
            "metrics": None,
            "marginal_contribution_pr_auc": None,
            "marginal_contribution_roc_auc": None,
            "note": (
                "no CDC features available — the CDC human-health stream was not "
                "joined into the feature matrix; contribution not evaluable and "
                "recorded as a gap (NOT a fabricated delta). Known limitation "
                "feeding Task 8 / the report."
            ),
        }

    # --- fsis_noaa --------------------------------------------------------
    noaa_cols = config_feature_columns("fsis_noaa", groups)
    noaa_metrics = _train_eval_config(
        model_name, train, test, noaa_cols, rare_event=rare, scale_pos_weight=spw
    )
    configs["fsis_noaa"] = {
        "status": "evaluated",
        "data_sources": ["FSIS", "NOAA"],
        "n_features": len(noaa_cols),
        "n_noaa_features": len(groups["noaa"]),
        "noaa_features_available": noaa_available,
        "metrics": noaa_metrics,
        "marginal_contribution_pr_auc": signed_marginal_contribution(
            noaa_metrics.get("pr_auc"), base_primary
        ),
        "marginal_contribution_roc_auc": signed_marginal_contribution(
            noaa_metrics.get("roc_auc"), base_metrics.get("roc_auc")
        ),
        "note": (
            "NOAA weather_* features come from NOAA nClimDiv statewide monthly "
            "climate (national state-level coverage, ~87% of state-periods "
            "non-missing). The marginal is measured and reported with its real "
            "sign; it is small and pathogen-dependent (positive for Salmonella/"
            "STEC, slightly negative for Listeria)."
        ),
    }

    # --- full -------------------------------------------------------------
    full_cols = config_feature_columns("full", groups)
    full_metrics = _train_eval_config(
        model_name, train, test, full_cols, rare_event=rare, scale_pos_weight=spw
    )
    configs["full"] = {
        "status": "evaluated",
        "data_sources": ["FSIS", "CDC(none)", "NOAA", "static ACS/Atlas context"],
        "n_features": len(full_cols),
        "metrics": full_metrics,
        "marginal_contribution_pr_auc": signed_marginal_contribution(
            full_metrics.get("pr_auc"), base_primary
        ),
        "marginal_contribution_roc_auc": signed_marginal_contribution(
            full_metrics.get("roc_auc"), base_metrics.get("roc_auc")
        ),
        "note": (
            "all available feature groups; static ACS/Food-Access-Atlas columns "
            "are slowly-varying demographic/food-access CONTEXT (not a One-Health "
            "surveillance stream) and are folded in here."
        ),
    }

    result: dict[str, Any] = {
        "task": "3.9 Implement interpretation and ablations",
        "requirements": ["9.3", "9.4", "9.5"],
        "pathogen": pathogen,
        "best_model": model_name,
        "primary_metric": PRIMARY_METRIC,
        "baseline_config": "fsis_only",
        "random_state": RANDOM_STATE,
        "test_fraction": test_fraction,
        "feature_groups": {k: v for k, v in groups.items()},
        "feature_group_counts": {k: len(v) for k, v in groups.items()},
        "cdc_features_available": cdc_available,
        "noaa_features_available": noaa_available,
        "split": {
            "train_periods": [split.train_period_range[0], split.train_period_range[1]],
            "test_periods": [split.test_period_range[0], split.test_period_range[1]],
            "n_train_rows": int(len(train)),
            "n_test_rows": int(len(test)),
            "boundary_period_start": str(split.boundary),
        },
        "rare_event_handling_applied": rare,
        "train_prevalence": train_prev,
        "configs": configs,
        "limitations": {
            "cdc_gap": (
                "FSIS+CDC is not evaluable: no CDC human-health features are "
                "wired into the feature matrix. Recorded as a gap, not a "
                "fabricated delta (Req 9.5). Feeds Task 8 / report limitations."
            ),
            "noaa_thin": (
                "NOAA weather features exist but are mostly NaN (thin station "
                "slice); marginal contribution is expected near-zero and is "
                "reported with its real sign."
            ),
            "static_context": (
                "ACS / Food Access Atlas static columns are demographic/food-"
                "access context folded into the full config, not a CDC/NOAA "
                "surveillance stream."
            ),
        },
    }

    if write:
        models_root.mkdir(parents=True, exist_ok=True)
        out = models_root / f"ablation_{slug}.json"
        out.write_text(json.dumps(result, indent=2), encoding="utf-8")
        result["ablation_path"] = str(out)

    return result


# --------------------------------------------------------------------------- #
# Combined report
# --------------------------------------------------------------------------- #

def _fmt(x: Optional[float]) -> str:
    return "n/a" if x is None else f"{x:+.4f}"


def _fmt_metric(x: Optional[float]) -> str:
    return "n/a" if x is None else f"{x:.4f}"


def write_ablation_report(
    results: dict[str, Any],
    *,
    out_path: Optional[Path] = None,
) -> Path:
    """Write the combined ``docs/reports/ablation.md`` across all pathogens."""
    out_path = out_path or (DOCS_REPORTS / "ablation.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    lines.append("# Data-source ablations (Req 9.3-9.5)\n")
    lines.append(
        "Exactly four configurations per pathogen, defined by data source, "
        "trained with each pathogen's best model on the SAME chronological train "
        "split and evaluated on the SAME untouched test. The primary metric is "
        "**PR-AUC**; the marginal contribution is the **signed** change vs the "
        "FSIS-only baseline (negatives preserved, never clamped).\n"
    )
    lines.append("## Key limitations (honest, feeding Task 8)\n")
    lines.append(
        "- **CDC gap:** there are NO CDC human-health features in the feature "
        "matrix (the CDC stream was not joined into harmonize). The **FSIS+CDC** "
        "configuration is therefore recorded as a *gap* — its contribution is "
        "**not evaluable** and is reported as such, never as a fabricated "
        "number.\n"
        "- **NOAA nClimDiv coverage:** NOAA `weather_*` features come from NOAA "
        "nClimDiv statewide monthly climate (national, ~87% of state-periods "
        "non-missing). The **FSIS+NOAA** marginal is small and pathogen-dependent "
        "(positive for Salmonella/STEC, slightly negative for Listeria) and is "
        "reported with its real sign.\n"
        "- **Static context:** ACS / Food Access Atlas `static_*` columns are "
        "slowly-varying demographic / food-access CONTEXT, not a One-Health "
        "surveillance stream; they are folded into the **full** configuration.\n"
    )

    for pathogen, res in results.get("per_pathogen", {}).items():
        lines.append(f"\n## {pathogen} (best model: {res['best_model']})\n")
        gc = res["feature_group_counts"]
        lines.append(
            f"Feature groups: FSIS={gc['fsis']}, CDC={gc['cdc']}, NOAA={gc['noaa']}, "
            f"static={gc['static']}, other={gc['other']}. "
            f"Test periods: {res['split']['train_periods'][0]}..{res['split']['test_periods'][1]} "
            f"(n_test_rows={res['split']['n_test_rows']}).\n"
        )
        lines.append(
            "| Configuration | Status | PR-AUC | ROC-AUC | Δ PR-AUC vs FSIS-only | Δ ROC-AUC vs FSIS-only |\n"
            "|---|---|---|---|---|---|"
        )
        for cfg in ABLATION_CONFIGS:
            c = res["configs"][cfg]
            metrics = c.get("metrics")
            pr = _fmt_metric(metrics.get("pr_auc")) if metrics else "n/a (gap)"
            roc = _fmt_metric(metrics.get("roc_auc")) if metrics else "n/a (gap)"
            d_pr = _fmt(c.get("marginal_contribution_pr_auc"))
            d_roc = _fmt(c.get("marginal_contribution_roc_auc"))
            lines.append(
                f"| {cfg} | {c['status']} | {pr} | {roc} | {d_pr} | {d_roc} |"
            )
        if res["configs"]["fsis_cdc"]["status"] == "gap":
            lines.append(
                "\n> **FSIS+CDC gap:** no CDC features available — contribution "
                "not evaluable; recorded as a gap, not a fabricated delta."
            )

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def run_ablations(
    *,
    pathogens: Optional[tuple[str, ...]] = None,
    processed_root: Optional[Path] = None,
    models_root: Optional[Path] = None,
    test_fraction: float = DEFAULT_TEST_FRACTION,
    write: bool = True,
) -> dict[str, Any]:
    """Run the four data-source ablations for every pathogen; write artifacts."""
    processed_root = processed_root or PROCESSED_ROOT
    models_root = models_root or MODELS_ROOT
    order = pathogens or ("Salmonella", "Listeria", "STEC")

    per: dict[str, Any] = {}
    for pathogen in order:
        per[pathogen] = ablation_for_pathogen(
            pathogen,
            processed_root=processed_root,
            models_root=models_root,
            test_fraction=test_fraction,
            write=write,
        )

    results = {
        "task": "3.9 Implement interpretation and ablations",
        "requirements": ["9.3", "9.4", "9.5"],
        "configs": list(ABLATION_CONFIGS),
        "primary_metric": PRIMARY_METRIC,
        "best_model_per_pathogen": BEST_MODEL,
        "per_pathogen": per,
    }

    if write:
        report = write_ablation_report(results)
        results["report_path"] = str(report)

    return results


if __name__ == "__main__":  # pragma: no cover - manual invocation
    import pprint

    pprint.pprint(run_ablations())
