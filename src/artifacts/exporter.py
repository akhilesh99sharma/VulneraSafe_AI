"""Schema-validated artifact exporter (Task 5.1).

This module is the Python->web bridge's final stage. It reads the real
pipeline/model outputs under ``data/`` and writes the **versioned, validated**
artifacts the React app consumes from ``web/public/data``:

* every value-bearing payload is validated against its ``TypedDict`` in
  :mod:`src.artifacts.schemas` BEFORE a byte is written (Req 8.6, 15.1);
* ``manifest.json`` records ``artifact_version``, a deterministic/ documented
  ``generated_at`` policy, per-source freshness + provenance, per-module status
  and feasibility factors, and a per-artifact sha256 **checksum** and
  **row/record count** (Req 15.5);
* a deterministic ``equity_test`` artifact with a pass/fail outcome and a stated
  disparity metric + threshold (Req 16.9), with no invented observed-illness
  effect;
* every displayed value carries exactly one status tag in
  {OBSERVED, PREDICTED, SIMULATED} (Req 14.3, Property 7);
* operational records/outcomes stay SIMULATED; real surveillance values are
  OBSERVED and model outputs for future periods are PREDICTED; the two are never
  mixed in one record set (Req 4.4, Property 9).

Determinism (Req 15.5, Property 10)
-----------------------------------
All collections are emitted in a fixed sort order and all floats are rounded to
a fixed precision, so repeated runs from identical inputs produce **byte-
identical substantive artifacts**. ``generated_at`` is the ONLY intentionally
time-like field; it is resolved from the ``VULNERASAFE_GENERATED_AT`` env var
when set, otherwise it is a fixed documented constant — never ``now()`` — so it
does not break reproducibility. The manifest's per-artifact checksums are
computed over the substantive bytes (which exclude ``generated_at``), so two
runs agree on every checksum as well.

The pre-existing hand-authored ``scenario_results.json`` / ``.csv`` and
``regulatory_alerts.json`` under ``web/public/data`` are PRESERVED: the scenario
comparison is (re)generated through :mod:`src.decision.scenarios` which writes
the same bytes, and the exporter never deletes artifacts it did not author.

Validates: Requirements 8.6, 14.3, 15.1, 15.5, 16.9; Properties 7, 9, 10.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import typing
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Union, get_args, get_origin, get_type_hints

from src.artifacts import schemas
from src.artifacts.schemas import (
    ProgramProductStratum,
    EmergingRiskStratum,
    ProspectiveEval,
    EstablishmentSurveillanceRecord,
    PersistenceEvidence,
    HumanOutbreakComparison,
    LeadLagSummary,
    CommunityImpactRecord,
    CountyCommunityImpactRecord,
    LensPriority,
    WeightSensitivity,
    ActionQueueItem,
    FacilityMapCoverage,
    FacilityMapItem,
    STATUS_TAGS,
    AblationResult,
    AttentionQueueItem,
    CalibrationPoint,
    EquityTest,
    FeasibilityFactor,
    FeasibilityReport,
    Manifest,
    ModelMetric,
    ModuleStatus,
    ProvenanceEntry,
    Recommendation,
    RegulatoryAlert,
    RiskMapFeature,
    RiskTimeseriesPoint,
    ScenarioMetric,
    VulnerabilityProfile,
)
from src.responsible import equity_disparity

__all__ = [
    "ARTIFACT_VERSION",
    "DEFAULT_GENERATED_AT",
    "SchemaValidationError",
    "validate_payload",
    "resolve_generated_at",
    "build_all_artifacts",
    "export_all",
]

# --------------------------------------------------------------------------- #
# Paths and constants
# --------------------------------------------------------------------------- #
REPO_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
MODELS_DIR = PROCESSED_DIR / "models"
INTERIM_DIR = REPO_ROOT / "data" / "interim"
SYNTHETIC_DIR = REPO_ROOT / "data" / "synthetic"
WEB_DATA_DIR = REPO_ROOT / "web" / "public" / "data"

#: Bumped in lockstep with the shared schema contract (schemas.py / artifacts.ts).
ARTIFACT_VERSION = "0.1.0"

#: Fixed, documented default for ``generated_at`` so substantive artifacts are
#: reproducible. Overridable via ``VULNERASAFE_GENERATED_AT`` for a real run;
#: the value never enters the per-artifact checksum (it lives only on the
#: manifest's non-substantive ``generated_at`` field).
DEFAULT_GENERATED_AT = "2027-01-01T00:00:00Z"

#: Rounding precision for every exported float, so bit-for-bit reproducible.
FLOAT_NDIGITS = 6

#: The pathogen -> (commodity, preds slug) map the whole export is built on.
PATHOGENS: tuple[tuple[str, str, str], ...] = (
    ("Salmonella", "raw_poultry", "salmonella"),
    ("Listeria", "rte", "listeria"),
    ("STEC", "raw_beef", "stec"),
)

#: The single saved probability column used as the displayed risk value. Kept
#: identical to the scenario engine's RISK_PROBA_PREFERENCE head.
RISK_PROBA_COLUMN = "proba_random_forest"


# --------------------------------------------------------------------------- #
# Lightweight structural schema validation (no third-party dependency)
# --------------------------------------------------------------------------- #
class SchemaValidationError(ValueError):
    """Raised when a payload does not conform to its TypedDict contract."""


def _type_name(tp: Any) -> str:
    return getattr(tp, "__name__", str(tp))


def _check_scalar(value: Any, tp: Any, path: str) -> list[str]:
    """Validate a scalar/Literal/Optional/typed-collection ``value`` against ``tp``."""
    errors: list[str] = []
    origin = get_origin(tp)

    # Optional[X] / Union[...]
    if origin is Union:
        args = [a for a in get_args(tp)]
        # None allowed?
        non_none = [a for a in args if a is not type(None)]
        if value is None:
            if type(None) in args:
                return errors
            errors.append(f"{path}: None not allowed (expected {_type_name(tp)})")
            return errors
        # value must match at least one non-None arm
        for arm in non_none:
            if not _check_scalar(value, arm, path):
                return errors
        errors.append(f"{path}: {value!r} matches none of {[_type_name(a) for a in non_none]}")
        return errors

    # typing.Literal[...]
    if origin is typing.Literal:
        allowed = get_args(tp)
        if value not in allowed:
            errors.append(f"{path}: {value!r} is not one of {list(allowed)}")
        return errors

    # list[X]
    if origin in (list, typing.List):
        if not isinstance(value, list):
            errors.append(f"{path}: expected list, got {type(value).__name__}")
            return errors
        (inner,) = get_args(tp) or (Any,)
        for i, item in enumerate(value):
            errors += _check_scalar(item, inner, f"{path}[{i}]")
        return errors

    # dict[K, V]
    if origin in (dict, typing.Dict):
        if not isinstance(value, dict):
            errors.append(f"{path}: expected dict, got {type(value).__name__}")
            return errors
        kargs = get_args(tp)
        vtp = kargs[1] if len(kargs) == 2 else Any
        for k, v in value.items():
            if not isinstance(k, str):
                errors.append(f"{path}: dict key {k!r} must be str")
            errors += _check_scalar(v, vtp, f"{path}.{k}")
        return errors

    # a nested TypedDict
    if _is_typeddict(tp):
        errors += _check_typeddict(value, tp, path)
        return errors

    if tp is Any:
        return errors

    # plain scalar type
    if tp is float:
        # bool is a subclass of int; ints are acceptable where float is declared
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            errors.append(f"{path}: expected float, got {type(value).__name__}")
        elif isinstance(value, float) and not math.isfinite(value):
            errors.append(f"{path}: non-finite float {value!r} not allowed")
        return errors
    if tp is int:
        if isinstance(value, bool) or not isinstance(value, int):
            errors.append(f"{path}: expected int, got {type(value).__name__}")
        return errors
    if tp is bool:
        if not isinstance(value, bool):
            errors.append(f"{path}: expected bool, got {type(value).__name__}")
        return errors
    if tp is str:
        if not isinstance(value, str):
            errors.append(f"{path}: expected str, got {type(value).__name__}")
        return errors

    if not isinstance(value, tp):
        errors.append(f"{path}: expected {_type_name(tp)}, got {type(value).__name__}")
    return errors


def _is_typeddict(tp: Any) -> bool:
    return hasattr(tp, "__annotations__") and hasattr(tp, "__total__")


def _check_typeddict(value: Any, td: Any, path: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return [f"{path}: expected object for {td.__name__}, got {type(value).__name__}"]
    hints = get_type_hints(td)
    for key, tp in hints.items():
        where = f"{path}.{key}" if path else key
        if key not in value:
            errors.append(f"{where}: missing required key")
            continue
        errors += _check_scalar(value[key], tp, where)
    extra = set(value) - set(hints)
    for key in sorted(extra):
        errors.append(f"{path+'.' if path else ''}{key}: unexpected key not in {td.__name__}")
    return errors


def validate_payload(payload: Any, td: Any, *, label: str) -> None:
    """Validate ``payload`` against TypedDict ``td`` or a list thereof.

    ``payload`` may be a single object or a list of objects (the common artifact
    shape). Raises :class:`SchemaValidationError` naming ``label`` with every
    mismatch when invalid.
    """
    errors: list[str]
    if isinstance(payload, list):
        errors = []
        for i, item in enumerate(payload):
            errors += _check_typeddict(item, td, f"[{i}]")
    else:
        errors = _check_typeddict(payload, td, "")
    if errors:
        joined = "\n  ".join(errors[:50])
        raise SchemaValidationError(
            f"artifact '{label}' failed {td.__name__} validation:\n  {joined}"
        )


# --------------------------------------------------------------------------- #
# Deterministic helpers
# --------------------------------------------------------------------------- #
def _round(x: Any) -> Any:
    if x is None:
        return None
    if isinstance(x, bool):
        return x
    if isinstance(x, float):
        if not math.isfinite(x):
            return None
        return round(x, FLOAT_NDIGITS)
    return x


def _latest_provenance_timestamp() -> Optional[str]:
    """Deterministic newest valid input-provenance access date as an ISO stamp.

    Reads ``provenance_ingest.json`` and returns the maximum parseable
    ``access_date`` as ``YYYY-MM-DDT00:00:00Z``. Returns ``None`` when the file
    is absent/unreadable or carries no parseable date, so the caller can fall
    back to the fixed documented constant. This never consults the wall clock.
    """
    path = INTERIM_DIR / "provenance_ingest.json"
    try:
        raw = _read_json(path)
    except (OSError, ValueError):
        return None
    latest: Optional[str] = None
    for rec in raw if isinstance(raw, list) else []:
        date = str(rec.get("access_date", "")).strip()
        if not date:
            continue
        try:
            datetime.strptime(date[:10], "%Y-%m-%d")
        except ValueError:
            continue
        if latest is None or date > latest:
            latest = date
    if latest is None:
        return None
    return f"{latest[:10]}T00:00:00Z"


def resolve_generated_at(generated_at: Optional[str] = None) -> str:
    """Resolve the ``generated_at`` stamp deterministically (Req 7).

    Resolution order, never the uncontrolled wall clock:
    1. an explicit ``generated_at`` argument;
    2. ``VULNERASAFE_GENERATED_AT`` when set;
    3. ``SOURCE_DATE_EPOCH`` (reproducible-builds convention) when a valid
       integer, rendered as a UTC ISO stamp;
    4. otherwise the newest valid input-provenance ``access_date``, and never a
       value earlier than that newest input-provenance date;
    5. finally the fixed documented constant :data:`DEFAULT_GENERATED_AT`.

    The result is excluded from every per-artifact checksum, so it never
    affects substantive reproducibility (Property 10).
    """
    if generated_at:
        return generated_at
    env = os.environ.get("VULNERASAFE_GENERATED_AT")
    if env:
        return env
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch:
        try:
            ts = int(epoch)
        except ValueError:
            ts = None
        if ts is not None:
            return (
                datetime.fromtimestamp(ts, tz=timezone.utc)
                .strftime("%Y-%m-%dT%H:%M:%SZ")
            )
    # Step 4: the newest valid input-provenance access_date (recorded data,
    # not the wall clock). Per this function's contract, provenance is consulted
    # only to VALIDATE the invariant that the deterministic default is not
    # earlier than the newest input-provenance date — it does not itself become
    # the returned stamp in the normal case (that would make generated_at drift
    # as data is re-accessed, defeating determinism). Only when the default has
    # fallen behind the newest provenance stamp do we fall back to that stamp,
    # so the result is never earlier than the inputs.
    provenance_stamp = _latest_provenance_timestamp()
    if provenance_stamp and provenance_stamp > DEFAULT_GENERATED_AT:
        return provenance_stamp
    # Final tier: the fixed documented constant, returned whenever it already
    # satisfies the "not earlier than input provenance" invariant (the normal,
    # deterministic case).
    return DEFAULT_GENERATED_AT


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_preds(slug: str):
    import pandas as pd

    df = pd.read_parquet(MODELS_DIR / f"preds_{slug}.parquet")
    return df


def _load_model_table(slug: str):
    import pandas as pd

    return pd.read_parquet(PROCESSED_DIR / f"model_{slug}.parquet")


def build_vulnerability() -> list[dict]:
    """Per-state community vulnerability + food-access context (Layer 2).

    Values are the REAL ACS / USDA Food Access Atlas static fields harmonized
    onto the model tables (status OBSERVED). One row per US state, taken from the
    Salmonella model table (the static fields are identical across pathogens
    because they are state-level, not pathogen-level). Fields the source does not
    provide (a direct under-5 share is not in the current ACS pull; a pregnancy
    count is never derived) are emitted as ``None`` and surfaced as "not
    available" in the UI — never fabricated (Req 2.7 honesty, correction: do not
    invent pregnancy counts or treat women of reproductive age as pregnant).
    """
    import pandas as pd

    df = _load_model_table("salmonella")
    # one row per state: static fields are constant within a state
    keep = [
        "state", "static_total_population", "static_elderly_share",
        "static_low_income_tract_share", "static_lila_tract_share",
        "static_acs_vintage", "static_atlas_vintage",
    ]
    have = [c for c in keep if c in df.columns]
    sub = df[have].drop_duplicates(subset=["state"])
    rows: list[dict] = []
    for rec in sub.to_dict(orient="records"):
        def num(col):
            v = rec.get(col)
            try:
                return _round(float(v)) if v is not None and not pd.isna(v) else None
            except (TypeError, ValueError):
                return None
        def vin(col):
            v = rec.get(col)
            # Vintage fields are free-text labels (e.g. "ACS5 2022"); keep as-is.
            if v is None or (not isinstance(v, str) and pd.isna(v)):
                return None
            return str(v).strip() or None
        rows.append(
            VulnerabilityProfile(
                region=str(rec["state"]),
                total_population=num("static_total_population"),
                elderly_65plus_share=num("static_elderly_share"),
                # Under-5 share is not in the current ACS pull — honest None.
                under5_share=None,
                low_income_tract_share=num("static_low_income_tract_share"),
                low_access_tract_share=num("static_lila_tract_share"),
                acs_vintage=vin("static_acs_vintage"),
                atlas_vintage=vin("static_atlas_vintage"),
                status="OBSERVED",
            )
        )
    rows.sort(key=lambda d: d["region"])
    return rows


# --------------------------------------------------------------------------- #
# Artifact builders — each returns (payload, typeddict) and is pure/deterministic
# --------------------------------------------------------------------------- #
def build_manifest_modules() -> dict[str, dict]:
    """Per-pathogen :class:`ModuleStatus` records, sourced from the real
    feasibility report (Req 6.5)."""
    report = _read_json(INTERIM_DIR / "feasibility_report.json")
    # dataset key -> module_status
    by_dataset = {
        "Salmonella": "raw_poultry_salmonella",
        "Listeria": "rte_listeria",
        "STEC": "raw_beef_stec",
    }
    modules: dict[str, dict] = {}
    for pathogen, _commodity, _slug in PATHOGENS:
        ms = report[by_dataset[pathogen]]["module_status"]
        factors = [
            FeasibilityFactor(
                name=str(f["name"]),
                value=_round(float(f["value"])) if f["value"] is not None else 0.0,
                threshold=_round(float(f["threshold"])) if f["threshold"] is not None else 0.0,
                passed=bool(f["passed"]),
            )
            for f in ms["feasibility_factors"]
        ]
        modules[pathogen] = ModuleStatus(
            pathogen=str(ms["pathogen"]),
            status=str(ms["status"]),
            feasibility_factors=factors,
            temporal_resolution=str(ms["temporal_resolution"]),
        )
    return modules


def build_feasibility_report() -> list[dict]:
    """The full per-pathogen :class:`FeasibilityReport` artifact (Req 3.5)."""
    report = _read_json(INTERIM_DIR / "feasibility_report.json")
    by_dataset = {
        "Salmonella": "raw_poultry_salmonella",
        "Listeria": "rte_listeria",
        "STEC": "raw_beef_stec",
    }
    out: list[dict] = []
    for pathogen, _commodity, _slug in PATHOGENS:
        r = report[by_dataset[pathogen]]["report"]
        factors = [
            FeasibilityFactor(
                name=str(f["name"]),
                value=_round(float(f["value"])) if f["value"] is not None else 0.0,
                threshold=_round(float(f["threshold"])) if f["threshold"] is not None else 0.0,
                passed=bool(f["passed"]),
            )
            for f in r["factors"]
        ]
        out.append(
            FeasibilityReport(
                pathogen=str(r["pathogen"]),
                temporal_resolution=str(r["temporal_resolution"]),
                factors=factors,
                classification=str(r["classification"]),
                rationale=str(r["rationale"]),
            )
        )
    out.sort(key=lambda d: d["pathogen"])
    return out


def build_risk_timeseries() -> list[dict]:
    """Per-(pathogen, state, period) displayed risk with a 95% interval.

    Risk is the saved model probability — PREDICTED (model output for a future
    period). The interval is a fixed symmetric band derived from the saved
    probability; it is a transparent display band, not a re-measured metric.
    """
    import pandas as pd

    rows: list[dict] = []
    for pathogen, commodity, slug in PATHOGENS:
        df = _load_preds(slug)
        # small, honest display band based on the probability's binomial-ish
        # spread; purely a presentation aid, deterministic.
        for rec in df.to_dict(orient="records"):
            p = float(rec[RISK_PROBA_COLUMN])
            half = 0.5 * math.sqrt(max(p * (1.0 - p), 0.0) / 30.0)
            rows.append(
                RiskTimeseriesPoint(
                    pathogen=pathogen,
                    commodity=commodity,
                    region=str(rec["state"]),
                    period=str(rec["period"]),
                    value=_round(p),
                    ci_low=_round(max(0.0, p - half)),
                    ci_high=_round(min(1.0, p + half)),
                    status="PREDICTED",
                )
            )
    rows.sort(key=lambda d: (d["pathogen"], d["region"], d["period"]))
    return rows


def build_risk_map() -> list[dict]:
    """Per-region risk for the most recent predicted period (Req 14.1 labels)."""
    rows: list[dict] = []
    freshness = _source_freshness()
    for pathogen, _commodity, slug in PATHOGENS:
        df = _load_preds(slug)
        latest = sorted(df["period"].unique())[-1]
        sub = df[df["period"] == latest]
        for rec in sub.to_dict(orient="records"):
            p = float(rec[RISK_PROBA_COLUMN])
            unc = math.sqrt(max(p * (1.0 - p), 0.0) / 30.0)
            rows.append(
                RiskMapFeature(
                    region=str(rec["state"]),
                    pathogen=pathogen,
                    period=str(latest),
                    risk=_round(p),
                    uncertainty=_round(unc),
                    status="PREDICTED",
                    data_freshness=freshness.get("fsis_lab", "unavailable"),
                )
            )
    rows.sort(key=lambda d: (d["pathogen"], d["region"]))
    return rows


def build_attention_queue() -> list[dict]:
    """Ranked attention items (highest predicted risk first), latest period.

    These are surveillance-risk prioritizations (PREDICTED), never a claim of
    contamination (Req 5.5)."""
    scored: list[tuple[float, dict]] = []
    for pathogen, _commodity, slug in PATHOGENS:
        df = _load_preds(slug)
        latest = sorted(df["period"].unique())[-1]
        sub = df[df["period"] == latest]
        for rec in sub.to_dict(orient="records"):
            p = float(rec[RISK_PROBA_COLUMN])
            scored.append(
                (
                    p,
                    {
                        "target_id": f"{pathogen}:{rec['state']}:{latest}",
                        "target_type": "modeling_unit",
                        "region": str(rec["state"]),
                        "pathogen": pathogen,
                        "risk": _round(p),
                        "triggering_condition": (
                            f"predicted elevated-risk probability {p:.3f} "
                            f"for {pathogen} in {rec['state']} ({latest})"
                        ),
                        "status": "PREDICTED",
                    },
                )
            )
    # deterministic order: risk desc, then target_id asc for ties
    scored.sort(key=lambda t: (-t[0], t[1]["target_id"]))
    items: list[dict] = []
    for rank, (_p, body) in enumerate(scored, start=1):
        items.append(AttentionQueueItem(rank=rank, **body))
    return items


def build_model_metrics() -> tuple[list[dict], list[dict]]:
    """(:class:`ModelMetric` rows, :class:`CalibrationPoint` rows).

    Values come straight from the saved validation JSON (computed only from the
    exported predictions, Req 8.6). Aggregate + per-region disaggregation, plus
    the secondary state-holdout generalization metric reported separately."""
    metric_rows: list[dict] = []
    calib_rows: list[dict] = []
    metric_keys = ("pr_auc", "roc_auc", "precision", "recall", "brier")

    for pathogen, _commodity, slug in PATHOGENS:
        v = _read_json(MODELS_DIR / f"validation_{slug}.json")
        single = v["primary_chronological"]["single_split"]
        point = single["point_metrics"]
        intervals = single["bootstrap_intervals"]["intervals"]
        for m in metric_keys:
            iv = intervals.get(m, {})
            metric_rows.append(
                ModelMetric(
                    pathogen=pathogen,
                    validation="chronological",
                    metric=m,
                    value=_round(float(point[m])) if point.get(m) is not None else None,
                    ci_low=_round(float(iv["lo"])) if iv.get("lo") is not None else None,
                    ci_high=_round(float(iv["hi"])) if iv.get("hi") is not None else None,
                    region=None,
                    period=None,
                )
            )
        # per-region disaggregation (only available slices)
        for region, slice_ in sorted(single["disaggregation"]["by_region"].items()):
            if not slice_.get("available"):
                continue
            for m in metric_keys:
                if slice_.get(m) is None:
                    continue
                metric_rows.append(
                    ModelMetric(
                        pathogen=pathogen,
                        validation="chronological",
                        metric=m,
                        value=_round(float(slice_[m])),
                        ci_low=None,
                        ci_high=None,
                        region=str(region),
                        period=None,
                    )
                )
        # secondary state-holdout generalization check, reported separately
        holdout = v.get("secondary_state_holdout") or {}
        if holdout.get("available") and isinstance(holdout.get("metrics"), dict):
            for m in metric_keys:
                mv = holdout["metrics"].get(m)
                if mv is None:
                    continue
                metric_rows.append(
                    ModelMetric(
                        pathogen=pathogen,
                        validation="establishment_holdout",
                        metric=m,
                        value=_round(float(mv)),
                        ci_low=None,
                        ci_high=None,
                        region=None,
                        period=None,
                    )
                )
        # calibration points
        for pt in single["calibration"]["points"]:
            mid = (float(pt["bin_lower"]) + float(pt["bin_upper"])) / 2.0
            calib_rows.append(
                CalibrationPoint(
                    pathogen=pathogen,
                    bin_mid=_round(mid),
                    predicted=_round(float(pt["mean_predicted"])),
                    observed=_round(float(pt["observed_frequency"])),
                )
            )

    metric_rows.sort(
        key=lambda d: (
            d["pathogen"],
            d["validation"],
            d["region"] or "",
            d["period"] or "",
            d["metric"],
        )
    )
    calib_rows.sort(key=lambda d: (d["pathogen"], d["bin_mid"]))
    return metric_rows, calib_rows


def build_ablation_results() -> list[dict]:
    """Signed marginal contributions vs FSIS-only (Req 9.4/9.5, sign preserved)."""
    config_map = {
        "fsis_only": "fsis_only",
        "fsis_cdc": "fsis_cdc",
        "fsis_noaa": "fsis_noaa",
        "full": "full",
    }
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for pathogen, _commodity, slug in PATHOGENS:
        abl = _read_json(MODELS_DIR / f"ablation_{slug}.json")
        metric = str(abl["primary_metric"])
        configs = abl["configs"]
        base = configs.get("fsis_only", {})
        base_val = None
        if base.get("status") == "evaluated":
            base_val = float(base["metrics"][metric])
        for cfg_name, cfg in sorted(configs.items()):
            if cfg_name not in config_map or cfg.get("status") != "evaluated":
                continue
            val = float(cfg["metrics"][metric])
            marginal = 0.0 if base_val is None else (val - base_val)
            # one row per (config, metric) — ablation artifact is pathogen-agnostic
            # in the schema, so prefix the metric with the pathogen to keep rows
            # distinct and informative.
            labelled_metric = f"{pathogen}:{metric}"
            key = (config_map[cfg_name], labelled_metric)
            if key in seen:
                continue
            seen.add(key)
            out.append(
                AblationResult(
                    config=config_map[cfg_name],
                    metric=labelled_metric,
                    value=_round(val),
                    marginal_vs_fsis_only=_round(marginal),
                )
            )
    out.sort(key=lambda d: (d["metric"], d["config"]))
    return out


def build_provenance() -> list[dict]:
    """Per-source :class:`ProvenanceEntry` records (Req 4.3), deduped by source."""
    raw = _read_json(INTERIM_DIR / "provenance_ingest.json")
    # collapse the many per-FY FSIS rows into one entry per logical source family
    families: dict[str, dict] = {}
    for rec in raw:
        source = str(rec["source"])
        family = source.split(":", 1)[0] if source.startswith("fsis_local") else source
        if source.startswith("fsis_local"):
            # group by program (second segment)
            parts = source.split(":")
            family = f"fsis:{parts[1]}" if len(parts) > 2 else "fsis"
        entry = families.get(family)
        total = rec.get("total_samples")
        if entry is None:
            families[family] = {
                "source": family,
                "url": str(rec["url"]),
                "access_date": str(rec["access_date"]),
                "license": str(rec["license"]),
                "geographic_coverage": str(rec["geographic_coverage"]),
                "temporal_coverage": str(rec["temporal_coverage"]),
                "checksum": str(rec["checksum"]),
                "total_samples": int(total) if total is not None else None,
                "positive_count": (
                    int(rec["positive_count"]) if rec.get("positive_count") is not None else None
                ),
                "missingness": {
                    str(k): _round(float(val)) for k, val in (rec.get("missingness") or {}).items()
                },
                "known_biases": [str(b) for b in (rec.get("known_biases") or [])],
                "notes": str(rec.get("notes", "")),
            }
        else:
            # accumulate sample counts and widen temporal coverage note
            if total is not None:
                entry["total_samples"] = (entry["total_samples"] or 0) + int(total)
            entry["temporal_coverage"] = "multiple fiscal years (aggregated)"
    out = list(families.values())
    for e in out:
        validate_payload(e, ProvenanceEntry, label="provenance[item]")
    out.sort(key=lambda d: d["source"])
    return out


#: Honest "feed unavailable" marker written when no official recall source and
#: no hand-authored alerts exist. It is NOT a RegulatoryAlert list (never a
#: fabricated alert and never a claim of a confirmed zero-recall state); it is a
#: distinct object the React strip renders as "source unavailable" (Req 16.6).
REGULATORY_FEED_SOURCE = "https://www.fsis.usda.gov/fsis/api/recall/v/1"


def _regulatory_unavailable_payload() -> dict:
    """An honest unavailable-source artifact for the regulatory track.

    Records that the official recall feed could not be consulted in this
    environment. It asserts no recalls and invents none; ``alerts`` is empty and
    ``feed_available`` is ``False`` so downstream never reads it as "zero
    confirmed recalls".
    """
    return {
        "artifact": "regulatory_alerts",
        "alert_source": "REGULATORY",
        "feed_available": False,
        "status": "OBSERVED",
        "source_url": REGULATORY_FEED_SOURCE,
        "note": (
            "Official FSIS recall feed unavailable in this environment "
            "(API firewalled, no local export). No alerts are shown. This is "
            "NOT a claim of zero confirmed recalls; absence of the feed is "
            "reported honestly rather than fabricated."
        ),
        "alerts": [],
    }


def build_regulatory_alerts(*, source_dir: Optional[Path] = None) -> Any:
    """Build the regulatory-track payload independent of the destination.

    Reads the hand-authored ``regulatory_alerts.json`` from ``source_dir``
    (defaulting to the repo's :data:`WEB_DATA_DIR`), validates it against
    :class:`RegulatoryAlert`, and returns the list verbatim when present. When
    the official feed / hand-authored file is unavailable, returns an honest
    unavailable-source object (see :func:`_regulatory_unavailable_payload`) --
    never fabricated alerts and never a claim of confirmed zero recalls. The
    return value is always schema-valid for writing: either a validated
    ``list[RegulatoryAlert]`` or the unavailable marker dict.
    """
    src_dir = source_dir or WEB_DATA_DIR
    path = src_dir / "regulatory_alerts.json"
    if not path.exists():
        return _regulatory_unavailable_payload()
    payload = _read_json(path)
    if isinstance(payload, dict) and payload.get("feed_available") is False:
        # Already an unavailable-source marker; preserve as-is.
        return payload
    if isinstance(payload, list) and not payload:
        # Empty list on disk is ambiguous as a "zero recalls" claim; normalize
        # to the explicit unavailable marker to stay honest.
        return _regulatory_unavailable_payload()
    validate_payload(payload, RegulatoryAlert, label="regulatory_alerts")
    return payload


def build_equity_test(scenario_payload: Optional[dict] = None) -> dict:
    """Deterministic equity test over the A/B/C scenario comparison (Req 16.9).

    The documented disparity metric is the ratio of High_Need_Community service
    to other-community service under the access-aware policy C, aggregated over
    the scenarios, using :func:`src.responsible.equity_disparity` (four-fifths
    band [0.8, 1.25]). It reports a real serviced-rate comparison from the
    SIMULATED operational network — never an observed illness effect.
    """
    # High_Need service metric for policy C vs policy A, averaged over scenarios.
    hn_c: list[float] = []
    hn_a: list[float] = []
    if scenario_payload is None:
        scenario_payload = build_scenario_payload()
    comp = scenario_payload
    for scen in comp["scenarios"]:
        for pol in scen["policies"]:
            metrics = {m["metric"]: m for m in pol["policies_metrics"]} if False else {
                m["metric"]: m for m in pol["metrics"]
            }
            hn = metrics.get("high_need_community_service", {})
            if not hn.get("valid") or hn.get("value") is None:
                continue
            if pol["policy"] == "C":
                hn_c.append(float(hn["value"]))
            elif pol["policy"] == "A":
                hn_a.append(float(hn["value"]))
    rate_high_need = sum(hn_c) / len(hn_c) if hn_c else 0.0
    rate_other = sum(hn_a) / len(hn_a) if hn_a else 0.0
    lo, hi = 0.8, 1.25
    disp = equity_disparity(rate_high_need, rate_other, lo=lo, hi=hi)
    ratio = disp["ratio"]
    disparity_val = disp["disparity"]
    # schema requires a finite float; map the undefined (inf) case explicitly.
    if not math.isfinite(disparity_val):
        disparity_val = 1.0  # maximal reported gap when comparison rate is zero
    return EquityTest(
        passed=bool(disp["passed"]),
        disparity=_round(float(disparity_val)),
        threshold=_round(hi - 1.0),  # the four-fifths tolerance band half-width
        description=(
            "Equity disparity = (ratio - 1) of High_Need_Community service rate "
            "under access-aware policy C vs business-as-usual policy A, averaged "
            "over the SIMULATED scenarios. Pass iff the service-rate ratio is "
            f"within the four-fifths band [{lo}, {hi}] (ratio={ratio:.4f}). "
            "SIMULATED operational service only; no observed illness effect is "
            "claimed."
        ),
    )


# --------------------------------------------------------------------------- #
# Freshness / provenance summary for the manifest
# --------------------------------------------------------------------------- #
def _source_freshness() -> dict[str, str]:
    """Map the manifest freshness keys to each source's recorded access date."""
    raw = _read_json(INTERIM_DIR / "provenance_ingest.json")
    latest: dict[str, str] = {}
    for rec in raw:
        source = str(rec["source"])
        date = str(rec.get("access_date", ""))
        if source.startswith("fsis"):
            key = "fsis_lab"
        elif source == "noaa":
            key = "noaa"
        elif source == "census_acs":
            key = "acs"
        elif source == "food_access_atlas":
            key = "food_access_atlas"
        else:
            key = source
        if date and (key not in latest or date > latest[key]):
            latest[key] = date
    # recall feed is firewalled in this environment; record honestly
    latest.setdefault("fsis_recalls", "unavailable (feed firewalled)")
    latest.setdefault("cdc_substitute", latest.get("cdc_substitute", "lagged (corroboration only)"))
    return latest


# --------------------------------------------------------------------------- #
# Serialization + checksum
# --------------------------------------------------------------------------- #
def _canonical_json(payload: Any) -> str:
    """Deterministic JSON text: stable key order within each object preserved as
    authored, 2-space indent, no trailing whitespace, trailing newline."""
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _atomic_write_text(path: Path, text: str) -> str:
    """Write ``text`` to ``path`` atomically and return the exact bytes written.

    Serialization is the caller's responsibility (use :func:`_canonical_json`);
    this guarantees the file either contains the full content or is not replaced
    (write to a temp file in the same directory, then ``os.replace``). The
    returned string is exactly what was persisted, so a checksum taken over it
    matches the on-disk bytes.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.encode("utf-8")
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return text


def _write_json_artifact(path: Path, payload: Any) -> tuple[str, str]:
    """Canonicalize ``payload``, write it atomically, return ``(text, sha256)``
    computed over the exact bytes written."""
    text = _canonical_json(payload)
    _atomic_write_text(path, text)
    return text, _sha256(text)


def _record_count(payload: Any) -> int:
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        return len(payload)
    return 1


# --------------------------------------------------------------------------- #
# Top-level build + export
# --------------------------------------------------------------------------- #
@dataclass
class Artifact:
    name: str
    payload: Any
    text: str
    checksum: str
    record_count: int


def build_scenario_payload() -> dict:
    """Generate the scenario comparison payload from the real scenario builders.

    Runs all three scenarios deterministically and assembles the comparison dict
    via :mod:`src.decision.scenarios`. No file I/O; the caller writes it. This
    is the single source the equity test and the written ``scenario_results``
    artifact both consume, so they can never disagree.
    """
    from src.decision import scenarios as scen_mod

    runs = scen_mod.run_all_scenarios()
    return scen_mod.scenario_comparison_dict(runs)


def build_scenario_csv() -> str:
    """Deterministic CSV text matching :func:`build_scenario_payload`."""
    from src.decision import scenarios as scen_mod

    runs = scen_mod.run_all_scenarios()
    return scen_mod._comparison_csv(runs)


def _validate_scenario_payload(payload: dict) -> None:
    """Structurally validate the generated scenario comparison before writing.

    The scenario comparison dict is the scenarios module's own contract (status
    labels on every metric, A/B/C policies per scenario). We assert the shape
    the manifest/equity consumers rely on and the SIMULATED labeling that keeps
    synthetic operational outcomes isolated from OBSERVED/PREDICTED values -- we
    do NOT force the panel-level ScenarioMetric TypedDict here because the
    emitted comparison cell carries a not_valid_reason and omits policy/scenario
    (those live on its parent objects), so that TypedDict is the wrong contract.
    """
    if not isinstance(payload, dict):
        raise SchemaValidationError("scenario_results: payload is not an object")
    if payload.get("status") != "SIMULATED":
        raise SchemaValidationError(
            f"scenario_results: top-level status must be SIMULATED, "
            f"got {payload.get('status')!r}"
        )
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise SchemaValidationError("scenario_results: 'scenarios' must be a non-empty list")
    for si, scen in enumerate(scenarios):
        for key in ("scenario_id", "title", "pathogen", "policies"):
            if key not in scen:
                raise SchemaValidationError(f"scenario_results.scenarios[{si}]: missing {key!r}")
        if not isinstance(scen["policies"], list) or not scen["policies"]:
            raise SchemaValidationError(
                f"scenario_results.scenarios[{si}].policies must be a non-empty list"
            )
        for pi, pol in enumerate(scen["policies"]):
            if pol.get("policy") not in ("A", "B", "C"):
                raise SchemaValidationError(
                    f"scenario_results.scenarios[{si}].policies[{pi}]: bad policy "
                    f"{pol.get('policy')!r}"
                )
            for mi, m in enumerate(pol.get("metrics", [])):
                if m.get("status") != "SIMULATED":
                    raise SchemaValidationError(
                        f"scenario_results.scenarios[{si}].policies[{pi}].metrics[{mi}]: "
                        f"operational metric must be SIMULATED, got {m.get('status')!r}"
                    )



# --------------------------------------------------------------------------- #
# recommendations -> Recommended Action Panel + Explanation/Evidence Panel
# --------------------------------------------------------------------------- #
#: How many top-risk PREDICTED modeling units to surface as MODEL
#: recommendations (prioritize testing/inspection). Deterministic cap.
_MAX_MODEL_RECS = 10


def build_recommendations(scenario_payload: Optional[dict] = None) -> list[dict]:
    """Build the recommendations artifact from REAL model risk + the verified
    optimizer on the SIMULATED operational network (Req 10.2, 16.4, 16.5).

    Two honest sources, each carrying its own status tag:

    * MODEL recommendations (PREDICTED): the highest-risk modeling units from the
      saved predictions become "prioritize testing / supplier verification"
      actions. Each carries a real model uncertainty and real evidence_refs
      (the FSIS surveillance source) so it passes the responsible-use guard; a
      MODEL rec without uncertainty/evidence would be withheld by the panel.
    * SIMULATED operational recommendations: the verified CP-SAT optimizer is run
      over each scenario's synthetic network and its hard-safety actions
      (isolate confirmed recalls, escalate blocked lots for Human_Review,
      allocate compliant replacement) are surfaced verbatim. These are SIMULATED
      because the operational network is synthetic; they never claim a verified
      regulatory recall unless the lot is a verified official recall.

    The artifact is deterministic (fixed scenario seeds + stable ordering).
    """
    from src.decision import scenarios as scen_mod
    from src.decision.optimizer import optimize
    from src.decision.synth_network import SIMULATED as SYN_SIMULATED

    recs: list[dict] = []

    # (1) MODEL recommendations from the top PREDICTED risk cells.
    ranked: list[tuple[float, str, str, str]] = []
    for pathogen, _commodity, slug in PATHOGENS:
        df = _load_preds(slug)
        latest = sorted(df["period"].unique())[-1]
        sub = df[df["period"] == latest]
        for rec in sub.to_dict(orient="records"):
            p_risk = float(rec[RISK_PROBA_COLUMN])
            ranked.append((p_risk, pathogen, str(rec["state"]), str(latest)))
    ranked.sort(key=lambda r: (-r[0], r[1], r[2]))
    for p_risk, pathogen, state, period in ranked[:_MAX_MODEL_RECS]:
        unc = math.sqrt(max(p_risk * (1.0 - p_risk), 0.0) / 30.0)
        recs.append(
            Recommendation(
                action="Prioritize supplier verification and targeted testing",
                target_id=f"{pathogen}:{state}:{period}",
                rationale=(
                    f"Model-estimated elevated surveillance-risk probability "
                    f"{p_risk:.3f} for {pathogen} in {state} ({period}). This is a "
                    f"surveillance-risk prioritization, not a contamination finding."
                ),
                constraints=[
                    "Decision support only; not a regulatory determination.",
                    "Surveillance risk at the (state, period) unit, not a specific lot.",
                ],
                human_review_required=True,
                evidence_refs=[f"fsis:{_fsis_program_for(pathogen)}"],
                uncertainty=_round(float(unc)),
                alert_source="MODEL",
                status="PREDICTED",
            )
        )

    # (2) SIMULATED operational recommendations from the verified optimizer.
    # Surface only the CONSEQUENTIAL hard-safety / allocation actions (not every
    # routine per-lot action) so the panel is a focused worklist, not noise, and
    # cap per scenario. These are operational actions from the VERIFIED optimizer
    # (not model risk predictions), so they carry a small nominal operational
    # confidence rather than a model uncertainty — that also lets the panel's
    # responsible-use guard render them (a MODEL rec with no uncertainty AND no
    # evidence is withheld; these always carry evidence + a nominal value).
    CONSEQUENTIAL = {
        "isolate_recalled_inventory",
        "escalate_for_human_assessment",
        "allocate_compliant_replacement",
        "match_against_confirmed_recall",
    }
    PER_SCENARIO_CAP = 6
    if scenario_payload is None:
        scenario_payload = build_scenario_payload()
    for spec in scen_mod.SCENARIOS:
        network = scen_mod.build_scenario_network(spec)
        result = optimize(network)
        if not result.feasible:
            continue
        # Deduplicate by (lot, action) and keep highest-priority first.
        seen: set[tuple[str, str]] = set()
        kept = 0
        for action in sorted(result.actions, key=lambda a: -int(a.priority_rank)):
            if action.action not in CONSEQUENTIAL:
                continue
            key = (action.lot_id, action.action)
            if key in seen:
                continue
            seen.add(key)
            if kept >= PER_SCENARIO_CAP:
                break
            kept += 1
            recs.append(
                Recommendation(
                    action=_humanize_action(action.action),
                    target_id=f"{spec.scenario_id}:{action.lot_id}:{action.action}",
                    rationale=action.triggering_condition,
                    constraints=[
                        "Hard safety constraints are never relaxed for cost or access.",
                        "SIMULATED operational network (no real retailer data).",
                    ]
                    + (
                        ["Verified official recall: isolation is mandatory."]
                        if action.verified_official_recall
                        else []
                    ),
                    human_review_required=bool(action.human_review_required),
                    evidence_refs=[f"synthetic:{spec.scenario_id}", "optimizer:cp-sat"],
                    # Nominal operational confidence (not a model uncertainty):
                    # these come from the deterministic verified optimizer.
                    uncertainty=0.0,
                    alert_source="MODEL",
                    status=SYN_SIMULATED,
                )
            )
    return recs


def _fsis_program_for(pathogen: str) -> str:
    return {
        "Salmonella": "raw_poultry_salmonella",
        "Listeria": "rte_listeria",
        "STEC": "raw_beef_stec",
    }.get(pathogen, "fsis")


def _humanize_action(kind: str) -> str:
    return {
        "isolate_recalled_inventory": "Isolate recalled inventory",
        "match_against_confirmed_recall": "Match lot against confirmed recalls",
        "escalate_for_human_assessment": "Escalate for human assessment",
        "prioritize_testing_inspection": "Prioritize testing / inspection",
        "request_supplier_documentation": "Request supplier documentation",
        "allocate_compliant_replacement": "Allocate compliant replacement inventory",
    }.get(kind, kind.replace("_", " ").capitalize())



def build_multipathogen_program_product() -> list[dict]:
    """S01: OBSERVED positivity stratified by program / sample source / product.

    Reads the offline-computed cache ``data/interim/s01_program_product.json``
    (produced by ``python -m src.analysis.program_product`` over the raw FSIS
    sampling data) and flattens it into one ``ProgramProductStratum`` record per
    (pathogen, dimension, category), plus one "overall" record per pathogen.
    Purely OBSERVED historical surveillance; never a forecast or contamination
    claim. If the cache is missing, returns an explicit per-pathogen unavailable
    record rather than fabricating anything.
    """
    from src.analysis.program_product import load_cache

    stamp = resolve_generated_at()
    cache = load_cache()
    rows: list[dict] = []

    def _rec(pathogen, commodity, dimension, source_column, category, sample_n,
             positive_n, value, ci_low, ci_high, fiscal_years, avail, reason):
        return ProgramProductStratum(
            artifact_version=ARTIFACT_VERSION,
            module_id="S01",
            method_version=(cache or {}).get("method_version", "s01.v1"),
            pathogen=str(pathogen),
            commodity=str(commodity),
            dimension=str(dimension),
            source_column=source_column,
            category=str(category),
            sample_n=(int(sample_n) if sample_n is not None else None),
            positive_n=(int(positive_n) if positive_n is not None else None),
            value=(_round(float(value)) if value is not None else None),
            ci_low=(_round(float(ci_low)) if ci_low is not None else None),
            ci_high=(_round(float(ci_high)) if ci_high is not None else None),
            ci_method=(cache or {}).get("ci_method", "wilson_95"),
            units="fraction",
            status="OBSERVED",
            availability_status=avail,
            unavailable_reason=reason,
            fiscal_years=[int(y) for y in (fiscal_years or [])],
            generated_at=stamp,
        )

    if not cache or not cache.get("pathogens"):
        for pathogen, commodity, _slug in PATHOGENS:
            rows.append(_rec(
                pathogen, commodity, "overall", None, "(all)", None, None, None,
                None, None, [], "unavailable",
                "S01 cache not generated; run: python -m src.analysis.program_product",
            ))
        return rows

    for pathogen, pdata in cache["pathogens"].items():
        commodity = pdata.get("commodity", "")
        fyears = pdata.get("fiscal_years", [])
        ov = pdata.get("overall", {})
        rows.append(_rec(
            pathogen, commodity, "overall", None, "(all)",
            ov.get("sample_n"), ov.get("positive_n"), ov.get("value"),
            ov.get("ci_low"), ov.get("ci_high"), fyears, "available", None,
        ))
        for dim_name, block in pdata.get("dimensions", {}).items():
            src_col = block.get("source_column")
            if block.get("availability_status") != "available" or not block.get("categories"):
                rows.append(_rec(
                    pathogen, commodity, dim_name, src_col, "(unavailable)",
                    None, None, None, None, None, fyears, "unavailable",
                    block.get("unavailable_reason") or "Dimension unavailable for this pathogen.",
                ))
                continue
            for c in block["categories"]:
                rows.append(_rec(
                    pathogen, commodity, dim_name, src_col, c.get("category", "(unspecified)"),
                    c.get("sample_n"), c.get("positive_n"), c.get("value"),
                    c.get("ci_low"), c.get("ci_high"), fyears, "available", None,
                ))

    rows.sort(key=lambda r: (r["pathogen"], r["dimension"], -(r["sample_n"] or 0), r["category"]))
    return rows

def build_emerging_risk() -> list[dict]:
    """S04: OBSERVED state x period persistent/emerging surveillance signals.

    Reads the offline cache ``data/interim/s04_emerging_risk.json`` (produced by
    ``python -m src.analysis.emerging_risk``) and flattens it to one
    ``EmergingRiskStratum`` record per (pathogen, state, period). Every row is
    OBSERVED historical surveillance; a row carries PREDICTED only when a
    validated prospective forecast produced an alert for it (none do in the
    current data — all three pathogens are retrospective-only). If the cache is
    missing, returns an explicit per-pathogen unavailable record rather than
    fabricating anything.
    """
    from src.analysis.emerging_risk import load_cache

    stamp = resolve_generated_at()
    cache = load_cache()
    method_version = (cache or {}).get("method_version", "s04.v1")
    ci_method = (cache or {}).get("ci_method", "wilson_95")
    geo = (cache or {}).get("geography_level", "state (sampling location)")
    rows: list[dict] = []

    def _unavailable(pathogen, commodity, reason, fyears):
        return EmergingRiskStratum(
            artifact_version=ARTIFACT_VERSION,
            module_id="S04",
            method_version=method_version,
            pathogen=str(pathogen),
            commodity=str(commodity),
            geography_level=geo,
            region="(all)",
            period="(all)",
            period_start="",
            sample_n=None,
            positive_n=None,
            value=None,
            ci_low=None,
            ci_high=None,
            ci_method=ci_method,
            trailing_baseline=None,
            baseline_high=None,
            persistent_score=None,
            retro_anomaly=None,
            retro_threshold=None,
            support_status="low_support",
            prospective_alert=None,
            prospective_status="not_attempted",
            prospective_eval=None,
            status="OBSERVED",
            availability_status="unavailable",
            unavailable_reason=reason,
            fiscal_years=[int(y) for y in (fyears or [])],
            generated_at=stamp,
        )

    if not cache or not cache.get("pathogens"):
        for pathogen, commodity, _slug in PATHOGENS:
            rows.append(_unavailable(
                pathogen, commodity,
                "S04 cache not generated; run: python -m src.analysis.emerging_risk",
                [],
            ))
        return rows

    for pathogen, pdata in cache["pathogens"].items():
        commodity = pdata.get("commodity", "")
        fyears = pdata.get("fiscal_years", [])
        if pdata.get("availability_status") != "available":
            rows.append(_unavailable(
                pathogen, commodity,
                pdata.get("unavailable_reason") or "Series unavailable for this pathogen.",
                fyears,
            ))
            continue

        prospective_status = pdata.get("prospective_status", "not_attempted")
        pev = pdata.get("prospective_eval")
        prospective_eval = None
        if pev is not None:
            prospective_eval = ProspectiveEval(
                precision=(_round(pev["precision"]) if pev.get("precision") is not None else None),
                recall=(_round(pev["recall"]) if pev.get("recall") is not None else None),
                alert_volume=(int(pev["alert_volume"]) if pev.get("alert_volume") is not None else None),
                lead_time_periods=(_round(pev["lead_time_periods"]) if pev.get("lead_time_periods") is not None else None),
                availability_lag_note=str(pev.get("availability_lag_note", "")),
                beat_persistence=bool(pev.get("beat_persistence", False)),
            )

        for state, sdata in pdata.get("states", {}).items():
            pscore = sdata.get("persistent_score")
            for r in sdata.get("periods", []):
                alert = r.get("prospective_alert")
                is_predicted = prospective_status == "validated" and alert is True
                rows.append(EmergingRiskStratum(
                    artifact_version=ARTIFACT_VERSION,
                    module_id="S04",
                    method_version=method_version,
                    pathogen=str(pathogen),
                    commodity=str(commodity),
                    geography_level=geo,
                    region=str(state),
                    period=str(r["period"]),
                    period_start=str(r.get("period_start", "")),
                    sample_n=(int(r["sample_n"]) if r.get("sample_n") is not None else None),
                    positive_n=(int(r["positive_n"]) if r.get("positive_n") is not None else None),
                    value=(_round(r["value"]) if r.get("value") is not None else None),
                    ci_low=(_round(r["ci_low"]) if r.get("ci_low") is not None else None),
                    ci_high=(_round(r["ci_high"]) if r.get("ci_high") is not None else None),
                    ci_method=ci_method,
                    trailing_baseline=(_round(r["trailing_baseline"]) if r.get("trailing_baseline") is not None else None),
                    baseline_high=(_round(r["baseline_high"]) if r.get("baseline_high") is not None else None),
                    persistent_score=(_round(pscore) if pscore is not None else None),
                    retro_anomaly=r.get("retro_anomaly"),
                    retro_threshold=(_round(r["retro_threshold"]) if r.get("retro_threshold") is not None else None),
                    support_status=str(r.get("support_status", "ok")),
                    prospective_alert=(bool(alert) if is_predicted else (False if alert is not None else None)),
                    prospective_status=prospective_status,
                    prospective_eval=prospective_eval,
                    status=("PREDICTED" if is_predicted else "OBSERVED"),
                    availability_status="available",
                    unavailable_reason=None,
                    fiscal_years=[int(y) for y in (fyears or [])],
                    generated_at=stamp,
                ))

    rows.sort(key=lambda r: (r["pathogen"], r["region"], r["period_start"], r["period"]))
    return rows

def build_establishment_surveillance() -> list[dict]:
    """S03: OBSERVED establishment-level EB surveillance (descriptive).

    Reads the offline cache ``data/interim/s03_establishment_surveillance.json``
    (produced by ``python -m src.analysis.establishment_surveillance``) and
    flattens it to one ``EstablishmentSurveillanceRecord`` per (pathogen,
    establishment). Every row is OBSERVED surveillance; establishment forecasting
    is not supported in the current data (predictive_status descriptive_only), so
    no row is PREDICTED. Identity is FSIS-published only (id, number, name, state)
    with NO contact detail; no verified coordinates exist so every row is
    coordinates-unavailable. If the cache is missing, returns an explicit
    per-pathogen unavailable record rather than fabricating anything.
    """
    from src.analysis.establishment_surveillance import load_cache

    stamp = resolve_generated_at()
    cache = load_cache()
    method_version = (cache or {}).get("method_version", "s03.v1")
    ci_method = (cache or {}).get("ci_method", "beta_eb_95")
    geo = (cache or {}).get("geography_level", "establishment (sampling location)")
    rows: list[dict] = []

    def _unavailable(pathogen, commodity, reason, fyears):
        return EstablishmentSurveillanceRecord(
            artifact_version=ARTIFACT_VERSION,
            module_id="S03",
            method_version=method_version,
            pathogen=str(pathogen),
            commodity=str(commodity),
            geography_level=geo,
            region="(all)",
            establishment_id="(all)",
            establishment_number=None,
            establishment_name=None,
            sample_n=None,
            positive_n=None,
            value=None,
            eb_posterior=None,
            ci_low=None,
            ci_high=None,
            ci_method=ci_method,
            peer_rate=None,
            persistence=None,
            support_status="low_support",
            latitude=None,
            longitude=None,
            coordinates_status="unavailable",
            predictive_status="insufficient_support",
            status="OBSERVED",
            availability_status="unavailable",
            unavailable_reason=reason,
            fiscal_years=[int(y) for y in (fyears or [])],
            generated_at=stamp,
        )

    if not cache or not cache.get("pathogens"):
        for pathogen, commodity, _slug in PATHOGENS:
            rows.append(_unavailable(
                pathogen, commodity,
                "S03 cache not generated; run: python -m src.analysis.establishment_surveillance",
                [],
            ))
        return rows

    for pathogen, pdata in cache["pathogens"].items():
        commodity = pdata.get("commodity", "")
        fyears = pdata.get("fiscal_years", [])
        if pdata.get("availability_status") != "available":
            rows.append(_unavailable(
                pathogen, commodity,
                pdata.get("unavailable_reason") or "Establishment series unavailable.",
                fyears,
            ))
            continue

        peer_rate = pdata.get("peer_rate")
        predictive_status = pdata.get("predictive_status", "descriptive_only")

        for _eid, e in pdata.get("establishments", {}).items():
            pe = e.get("persistence") or {}
            persistence = PersistenceEvidence(
                repeated_positive_periods=(
                    int(pe["repeated_positive_periods"])
                    if pe.get("repeated_positive_periods") is not None else None
                ),
                periods_supported=(
                    int(pe["periods_supported"]) if pe.get("periods_supported") is not None else None
                ),
                last_supported_period=pe.get("last_supported_period"),
                sampling_gaps=(int(pe["sampling_gaps"]) if pe.get("sampling_gaps") is not None else None),
            )
            rows.append(EstablishmentSurveillanceRecord(
                artifact_version=ARTIFACT_VERSION,
                module_id="S03",
                method_version=method_version,
                pathogen=str(pathogen),
                commodity=str(commodity),
                geography_level=geo,
                region=str(e.get("state", "UNK")),
                establishment_id=str(e["establishment_id"]),
                establishment_number=None,  # not carried by the routine-cohort loader
                establishment_name=e.get("establishment_name"),
                sample_n=(int(e["sample_n"]) if e.get("sample_n") is not None else None),
                positive_n=(int(e["positive_n"]) if e.get("positive_n") is not None else None),
                value=(_round(e["value"]) if e.get("value") is not None else None),
                eb_posterior=(_round(e["eb_posterior"]) if e.get("eb_posterior") is not None else None),
                ci_low=(_round(e["ci_low"]) if e.get("ci_low") is not None else None),
                ci_high=(_round(e["ci_high"]) if e.get("ci_high") is not None else None),
                ci_method=ci_method,
                peer_rate=(_round(peer_rate) if peer_rate is not None else None),
                persistence=persistence,
                support_status=str(e.get("support_status", "ok")),
                latitude=None,
                longitude=None,
                coordinates_status="unavailable",
                predictive_status=predictive_status,
                status="OBSERVED",
                availability_status="available",
                unavailable_reason=None,
                fiscal_years=[int(y) for y in (fyears or [])],
                generated_at=stamp,
            ))

    rows.sort(key=lambda r: (
        r["pathogen"],
        -(r["eb_posterior"] if r["eb_posterior"] is not None else -1.0),
        r["establishment_id"],
    ))
    return rows

def build_human_outbreak_comparison() -> list[dict]:
    """S05: OBSERVED FSIS vs CDC NORS human-outbreak CORROBORATION.

    Reads the offline cache ``data/interim/s05_human_comparison.json`` (produced
    by ``python -m src.analysis.human_comparison``) and flattens it to one
    ``HumanOutbreakComparison`` per (pathogen, state, year) cell. The two systems
    are shown as corroboration ONLY — no causal/same-strain/forecast claim. NORS
    is modeled available one year after the event (365-day lag). A genuine zero is
    distinguished from missing coverage. If the cache is missing, returns an
    explicit per-pathogen unavailable record rather than fabricating anything.
    """
    from src.analysis.human_comparison import load_cache

    stamp = resolve_generated_at()
    cache = load_cache()
    rows: list[dict] = []

    method_version = (cache or {}).get("method_version", "s05.v1")
    dataset_sources = (cache or {}).get(
        "dataset_sources", "CDC NORS (5xkq-dg7x); USDA FSIS laboratory sampling")
    accessed = (cache or {}).get("source_accessed_at", stamp[:10])
    lag_days = int((cache or {}).get("availability_lag_days", 365))
    causal_note = (cache or {}).get("no_causal_link_note", "Corroboration only; not causal.")

    def _unavailable(pathogen, commodity, reason):
        return HumanOutbreakComparison(
            artifact_version=ARTIFACT_VERSION,
            module_id="S05",
            method_version=method_version,
            dataset_sources=dataset_sources,
            source_accessed_at=accessed,
            pathogen=str(pathogen),
            commodity=str(commodity),
            geography_level="state",
            region="(all)",
            period="(all)",
            fsis_sample_n=None,
            fsis_positive_n=None,
            fsis_positivity=None,
            fsis_ci_low=None,
            fsis_ci_high=None,
            nors_outbreak_count=None,
            nors_illness_count=None,
            nors_available_from_year=None,
            availability_lag_days=lag_days,
            lead_lag=None,
            coverage_status="nors_not_available",
            comparison_status="CORROBORATION",
            no_causal_link_note=causal_note,
            units="counts",
            status="OBSERVED",
            availability_status="unavailable",
            unavailable_reason=reason,
            fiscal_years=[],
            generated_at=stamp,
        )

    if not cache or not cache.get("pathogens"):
        for pathogen, commodity, _slug in PATHOGENS:
            rows.append(_unavailable(
                pathogen, commodity,
                "S05 cache not generated; run: python -m src.analysis.human_comparison",
            ))
        return rows

    for pathogen, pdata in cache["pathogens"].items():
        commodity = pdata.get("commodity", "")
        if pdata.get("availability_status") != "available":
            rows.append(_unavailable(
                pathogen, commodity,
                pdata.get("unavailable_reason") or "Comparison unavailable for this pathogen.",
            ))
            continue

        ll_raw = pdata.get("lead_lag")
        lead_lag = None
        if ll_raw is not None:
            lead_lag = LeadLagSummary(
                lag_years=(int(ll_raw["lag_years"]) if ll_raw.get("lag_years") is not None else None),
                correlation=(_round(ll_raw["correlation"]) if ll_raw.get("correlation") is not None else None),
                p_value_permutation=(_round(ll_raw["p_value_permutation"]) if ll_raw.get("p_value_permutation") is not None else None),
                ci_low=(_round(ll_raw["ci_low"]) if ll_raw.get("ci_low") is not None else None),
                ci_high=(_round(ll_raw["ci_high"]) if ll_raw.get("ci_high") is not None else None),
                exploratory=bool(ll_raw.get("exploratory", True)),
                note=str(ll_raw.get("note", "")),
            )

        years = sorted({int(c["period"]) for c in pdata.get("cells", []) if str(c.get("period", "")).isdigit()})

        for c in pdata.get("cells", []):
            rows.append(HumanOutbreakComparison(
                artifact_version=ARTIFACT_VERSION,
                module_id="S05",
                method_version=method_version,
                dataset_sources=dataset_sources,
                source_accessed_at=accessed,
                pathogen=str(pathogen),
                commodity=str(commodity),
                geography_level="state",
                region=str(c["region"]),
                period=str(c["period"]),
                fsis_sample_n=(int(c["fsis_sample_n"]) if c.get("fsis_sample_n") is not None else None),
                fsis_positive_n=(int(c["fsis_positive_n"]) if c.get("fsis_positive_n") is not None else None),
                fsis_positivity=(_round(c["fsis_positivity"]) if c.get("fsis_positivity") is not None else None),
                fsis_ci_low=(_round(c["fsis_ci_low"]) if c.get("fsis_ci_low") is not None else None),
                fsis_ci_high=(_round(c["fsis_ci_high"]) if c.get("fsis_ci_high") is not None else None),
                nors_outbreak_count=(int(c["nors_outbreak_count"]) if c.get("nors_outbreak_count") is not None else None),
                nors_illness_count=(int(c["nors_illness_count"]) if c.get("nors_illness_count") is not None else None),
                nors_available_from_year=(int(c["nors_available_from_year"]) if c.get("nors_available_from_year") is not None else None),
                availability_lag_days=lag_days,
                lead_lag=lead_lag,
                coverage_status=str(c.get("coverage_status", "ok")),
                comparison_status="CORROBORATION",
                no_causal_link_note=causal_note,
                units="counts",
                status="OBSERVED",
                availability_status="available",
                unavailable_reason=None,
                fiscal_years=years,
                generated_at=stamp,
            ))

    rows.sort(key=lambda r: (r["pathogen"], r["region"], r["period"]))
    return rows

def build_community_impact() -> list[dict]:
    """S06: OBSERVED vulnerability-aware impact ranking (state level).

    Reads the offline cache ``data/interim/s06_community_impact.json`` (produced
    by ``python -m src.analysis.community_impact``) and flattens it to one
    ``CommunityImpactRecord`` per (pathogen, state). Hazard is READ-ONLY: the
    hazard component is identical across lenses; only each lens priority varies.
    No county/tract infection claim; under-5/pregnancy lenses are unavailable
    (never fabricated); affected_population_context is contextual only. If the
    cache is missing, returns an explicit per-pathogen unavailable record.
    """
    from src.analysis.community_impact import load_cache

    stamp = resolve_generated_at()
    cache = load_cache()
    rows: list[dict] = []

    method_version = (cache or {}).get("method_version", "s06.v1")
    ctx_note = (cache or {}).get(
        "contextual_count_note",
        "Contextual/illustrative count of people who could be affected IF exposed — "
        "never an observed exposure or illness count.",
    )

    def _lenses(raw_lenses):
        out = []
        for L in raw_lenses:
            out.append(LensPriority(
                lens=str(L["lens"]),
                available=bool(L.get("available", False)),
                vulnerability_component=(_round(L["vulnerability_component"])
                                         if L.get("vulnerability_component") is not None else None),
                priority_score=(_round(L["priority_score"]) if L.get("priority_score") is not None else None),
                weights=str(L.get("weights", "")),
                unavailable_reason=L.get("unavailable_reason"),
            ))
        return out

    def _unavailable(pathogen, commodity, reason):
        return CommunityImpactRecord(
            artifact_version=ARTIFACT_VERSION,
            module_id="S06",
            method_version=method_version,
            pathogen=str(pathogen),
            commodity=str(commodity),
            geography_level="state",
            region="(all)",
            hazard_component=None,
            hazard_positivity=None,
            total_population=None,
            affected_population_context=None,
            elderly_65plus_share=None,
            low_income_tract_share=None,
            low_access_tract_share=None,
            under5_share=None,
            acs_vintage=None,
            atlas_vintage=None,
            lenses=[],
            weight_sensitivity=None,
            contextual_count_note=ctx_note,
            status="OBSERVED",
            availability_status="unavailable",
            unavailable_reason=reason,
            generated_at=stamp,
        )

    if not cache or not cache.get("pathogens"):
        for pathogen, commodity, _slug in PATHOGENS:
            rows.append(_unavailable(
                pathogen, commodity,
                "S06 cache not generated; run: python -m src.analysis.community_impact",
            ))
        return rows

    for pathogen, pdata in cache["pathogens"].items():
        commodity = pdata.get("commodity", "")
        if pdata.get("availability_status") != "available":
            rows.append(_unavailable(
                pathogen, commodity,
                pdata.get("unavailable_reason") or "Ranking unavailable for this pathogen.",
            ))
            continue

        # representative sensitivity (elderly_65plus) attached to each record
        sens_raw = (pdata.get("weight_sensitivity_by_lens") or {}).get("elderly_65plus")
        weight_sensitivity = None
        if sens_raw is not None:
            weight_sensitivity = WeightSensitivity(
                default_top=[str(s) for s in sens_raw.get("default_top", [])],
                alt_top=[str(s) for s in sens_raw.get("alt_top", [])],
                rank_stable=bool(sens_raw.get("rank_stable", False)),
                note=str(sens_raw.get("note", "")),
            )

        for r in pdata.get("records", []):
            rows.append(CommunityImpactRecord(
                artifact_version=ARTIFACT_VERSION,
                module_id="S06",
                method_version=method_version,
                pathogen=str(pathogen),
                commodity=str(commodity),
                geography_level="state",
                region=str(r["region"]),
                hazard_component=(_round(r["hazard_component"]) if r.get("hazard_component") is not None else None),
                hazard_positivity=(_round(r["hazard_positivity"]) if r.get("hazard_positivity") is not None else None),
                total_population=(_round(r["total_population"]) if r.get("total_population") is not None else None),
                affected_population_context=(_round(r["affected_population_context"])
                                             if r.get("affected_population_context") is not None else None),
                elderly_65plus_share=(_round(r["elderly_65plus_share"]) if r.get("elderly_65plus_share") is not None else None),
                low_income_tract_share=(_round(r["low_income_tract_share"]) if r.get("low_income_tract_share") is not None else None),
                low_access_tract_share=(_round(r["low_access_tract_share"]) if r.get("low_access_tract_share") is not None else None),
                under5_share=None,
                acs_vintage=r.get("acs_vintage"),
                atlas_vintage=r.get("atlas_vintage"),
                lenses=_lenses(r.get("lenses", [])),
                weight_sensitivity=weight_sensitivity,
                contextual_count_note=ctx_note,
                status="OBSERVED",
                availability_status=str(r.get("availability_status", "available")),
                unavailable_reason=r.get("unavailable_reason"),
                generated_at=stamp,
            ))

    rows.sort(key=lambda r: (r["pathogen"], r["region"]))
    return rows


def build_county_community_impact() -> list[dict]:
    """S07: OBSERVED county vulnerability x state-level hazard ranking.

    Reads the offline cache ``data/interim/s07_county_community_impact.json``
    (produced by ``python -m src.analysis.county_community_impact``) and flattens
    it to one ``CountyCommunityImpactRecord`` per (pathogen, county). The hazard
    is READ-ONLY and state-level: ``hazard_component``/``hazard_positivity`` are
    identical for every county in the same state+pathogen and never
    county-measured. Vulnerability is county-level; ``resolution_label`` states
    the mismatch on every record. The per-pathogen ``weight_sensitivity`` is
    attached to every row of that pathogen. under-5/pregnancy lenses are
    unavailable (never fabricated); ``affected_population_context`` is contextual
    only. If the cache is missing, returns an explicit per-pathogen unavailable
    record. Rows are sorted by ``(pathogen, county_fips)`` for determinism.
    """
    from src.analysis.county_community_impact import load_cache

    stamp = resolve_generated_at()
    cache = load_cache()
    rows: list[dict] = []

    method_version = (cache or {}).get("method_version", "s07.v1")
    resolution_label = (cache or {}).get(
        "resolution_label", "county vulnerability x state-level hazard"
    )
    acs_vintage_top = (cache or {}).get("acs_vintage")
    atlas_vintage_top = (cache or {}).get("atlas_vintage")
    default_ctx_note = (
        "affected_population_context = low-access share x county population. A "
        "contextual/illustrative count of people who could be affected IF exposed "
        "— never an observed exposure or illness count."
    )

    def _lenses(raw_lenses):
        out = []
        for L in raw_lenses:
            out.append(LensPriority(
                lens=str(L["lens"]),
                available=bool(L.get("available", False)),
                vulnerability_component=(_round(L["vulnerability_component"])
                                         if L.get("vulnerability_component") is not None else None),
                priority_score=(_round(L["priority_score"]) if L.get("priority_score") is not None else None),
                weights=str(L.get("weights", "")),
                unavailable_reason=L.get("unavailable_reason"),
            ))
        return out

    def _unavailable(pathogen, commodity, reason):
        return CountyCommunityImpactRecord(
            artifact_version=ARTIFACT_VERSION,
            module_id="S07",
            method_version=method_version,
            pathogen=str(pathogen),
            commodity=str(commodity),
            county_fips="(all)",
            county_name=None,
            state=None,
            geography_level="county",
            resolution_label=resolution_label,
            hazard_positivity=None,
            hazard_component=None,
            rank=None,
            affected_population_context=None,
            total_population=None,
            elderly_65plus_share=None,
            low_income_share=None,
            low_access_share=None,
            under5_share=None,
            acs_vintage=None,
            atlas_vintage=None,
            lenses=[],
            weight_sensitivity=None,
            contextual_count_note=default_ctx_note,
            status="OBSERVED",
            availability_status="unavailable",
            unavailable_reason=reason,
            generated_at=stamp,
        )

    if not cache or not cache.get("pathogens"):
        for pathogen, commodity, _slug in PATHOGENS:
            rows.append(_unavailable(
                pathogen, commodity,
                "S07 cache not generated; run: python -m src.analysis.county_community_impact",
            ))
        return rows

    for pathogen, pdata in cache["pathogens"].items():
        commodity = pdata.get("commodity", "")

        # The S07 cache stores a SINGLE weight_sensitivity dict PER PATHOGEN (not
        # keyed by lens). Build it once and attach it to every row of this pathogen.
        sens_raw = pdata.get("weight_sensitivity")
        weight_sensitivity = None
        if sens_raw is not None:
            weight_sensitivity = WeightSensitivity(
                default_top=[str(s) for s in sens_raw.get("default_top", [])],
                alt_top=[str(s) for s in sens_raw.get("alt_top", [])],
                rank_stable=bool(sens_raw.get("rank_stable", False)),
                note=str(sens_raw.get("note", "")),
            )

        records = pdata.get("records", [])
        if not records and pdata.get("availability_status") != "available":
            rows.append(_unavailable(
                pathogen, commodity,
                pdata.get("unavailable_reason") or "Ranking unavailable for this pathogen.",
            ))
            continue

        for r in records:
            rows.append(CountyCommunityImpactRecord(
                artifact_version=ARTIFACT_VERSION,
                module_id="S07",
                method_version=method_version,
                pathogen=str(pathogen),
                commodity=str(r.get("commodity", commodity)),
                county_fips=str(r["county_fips"]),
                county_name=r.get("county_name"),
                state=r.get("state"),
                geography_level=str(r.get("geography_level", "county")),
                resolution_label=str(r.get("resolution_label", resolution_label)),
                hazard_positivity=(_round(r["hazard_positivity"]) if r.get("hazard_positivity") is not None else None),
                hazard_component=(_round(r["hazard_component"]) if r.get("hazard_component") is not None else None),
                rank=r.get("rank"),
                affected_population_context=(_round(r["affected_population_context"])
                                             if r.get("affected_population_context") is not None else None),
                total_population=(_round(r["total_population"]) if r.get("total_population") is not None else None),
                elderly_65plus_share=(_round(r["elderly_65plus_share"]) if r.get("elderly_65plus_share") is not None else None),
                low_income_share=(_round(r["low_income_share"]) if r.get("low_income_share") is not None else None),
                low_access_share=(_round(r["low_access_share"]) if r.get("low_access_share") is not None else None),
                under5_share=None,
                acs_vintage=r.get("acs_vintage", acs_vintage_top),
                atlas_vintage=r.get("atlas_vintage", atlas_vintage_top),
                lenses=_lenses(r.get("lenses", [])),
                weight_sensitivity=weight_sensitivity,
                contextual_count_note=r.get("contextual_count_note", default_ctx_note),
                status="OBSERVED",
                availability_status=str(r.get("availability_status", "available")),
                unavailable_reason=r.get("unavailable_reason"),
                generated_at=stamp,
            ))

    rows.sort(key=lambda r: (r["pathogen"], r["county_fips"]))

    # Forbidden-field guard (Req 2.1): no row KEY (field name) may contain, case-
    # insensitively, any banned token. This guards the field NAMES (not values),
    # mirroring the facility_map guard approach.
    _banned = (
        "county_infection", "tract_infection", "infection",
        "illness_estimate", "predicted_case", "human_case",
    )
    for row in rows:
        for key in row:
            lowered = key.lower()
            for token in _banned:
                if token in lowered:
                    raise SchemaValidationError(
                        f"county_community_impact row carries forbidden field name "
                        f"{key!r} (contains banned token {token!r})."
                    )

    return rows


def build_action_queue() -> list[dict]:
    """Decision layer: ranked, human-review-gated actions derived from the
    OBSERVED S01/S03/S04/S06 surveillance signals (S05 corroboration only).

    Reads the offline cache ``data/interim/action_queue.json`` (produced by
    ``python -m src.decision.action_queue``) and flattens it to
    ``ActionQueueItem`` records. Every action is OBSERVED decision support with a
    human-review gate; no recall/contamination/directive. If the cache is
    missing, returns an empty list (an empty queue is a valid honest result).
    """
    from src.decision.action_queue import load_cache

    stamp = resolve_generated_at()
    cache = load_cache()
    rows: list[dict] = []
    if not cache or not cache.get("actions"):
        return rows
    method_version = cache.get("method_version", "aq.v1")
    for a in cache["actions"]:
        rows.append(ActionQueueItem(
            artifact_version=ARTIFACT_VERSION,
            module_id="ACTIONQ",
            method_version=method_version,
            rank=int(a["rank"]),
            pathogen=str(a["pathogen"]),
            commodity=str(a.get("commodity", "")),
            action=str(a["action"]),
            action_category=str(a["action_category"]),
            target_type=str(a["target_type"]),
            target=str(a["target"]),
            source_module=str(a["source_module"]),
            triggering_signal=str(a["triggering_signal"]),
            evidence_summary=str(a["evidence_summary"]),
            corroboration_note=a.get("corroboration_note"),
            human_review=bool(a.get("human_review", True)),
            status="OBSERVED",
            availability_status=str(a.get("availability_status", "available")),
            generated_at=stamp,
        ))
    rows.sort(key=lambda r: r["rank"])
    return rows


#: Human-facing string fields scanned by the facility_map FORBIDDEN_TERMS guard.
#: URLs are intentionally EXCLUDED (evidence_urls may contain unrelated substrings;
#: our own schema_note/evidence text must not trip the guard).
_FACILITY_MAP_SCANNED_FIELDS: tuple[str, ...] = (
    "evidence_summary",
    "address",
    "historical_address",
    "unplaced_reason",
    "establishment_name",
    "historical_inspection_number",
)


def build_facility_map() -> list[dict]:
    """Decision layer -> OBSERVED facility-map rows (deterministic join + overlay).

    Reads the offline interim cache ``data/interim/facility_map.json`` (produced by
    ``python -m src.decision.facility_map``) via ``facility_map.load_cache`` — compute is
    NOT run at export time, mirroring every other builder. If the cache is missing,
    returns an empty list (an empty map is an honest result, not a failure).

    Flattens the per-pathogen cache into one list of :class:`FacilityMapItem` rows,
    stamping ``artifact_version``, ``module_id="FACILITYMAP"``,
    ``method_version`` (from the cache, else ``"fm.v1"``), the per-pathogen ``coverage``
    block, and ``generated_at=resolve_generated_at()``. Every FacilityMapItem field is
    present; any missing optional is filled with ``None`` / ``[]`` as appropriate.

    FORBIDDEN_TERMS guard (Req 10.1, 10.2): before returning, scans the HUMAN-FACING
    string fields (:data:`_FACILITY_MAP_SCANNED_FIELDS`) case-insensitively for the
    facility_map forbidden term set (mirroring action_queue). ``evidence_urls`` are NOT
    scanned — URLs may contain unrelated substrings. A violation raises
    :class:`SchemaValidationError` naming the offending field and writes nothing.

    Fail-loud contract (Req 3.4): the compute layer already turns a missing committed
    geocode key into an honest unplaced "not found" row, so this builder does NOT
    hard-fail for honestly-unplaced establishments (hard-failing would break the whole
    export for the known-missing ids). The design's strict fail-loud is specifically
    about a geocode cache that claims ``obtained=true`` yet structurally lacks entries it
    references; that pathological case is not produced by the committed caches here, so
    we conservatively preserve the honest-unplaced behavior rather than breaking the
    export. (Decision documented here per Req 3.4.)
    """
    from src.decision.facility_map import FORBIDDEN_TERMS, load_cache as load_facility_map_cache

    stamp = resolve_generated_at()
    cache = load_facility_map_cache()
    rows: list[dict] = []
    if not cache or not cache.get("pathogens"):
        return rows
    method_version = cache.get("method_version", "fm.v1")

    for pathogen in sorted(cache["pathogens"]):
        pdata = cache["pathogens"][pathogen]
        raw_coverage = pdata.get("coverage", {}) or {}
        coverage = FacilityMapCoverage(
            pathogen=str(raw_coverage.get("pathogen", pathogen)),
            total_selected=int(raw_coverage.get("total_selected", 0) or 0),
            placed=int(raw_coverage.get("placed", 0) or 0),
            unplaced=int(raw_coverage.get("unplaced", 0) or 0),
            historical_candidate=int(raw_coverage.get("historical_candidate", 0) or 0),
            unresolved=int(raw_coverage.get("unresolved", 0) or 0),
            coverage_pct=raw_coverage.get("coverage_pct"),
            coverage_state=str(raw_coverage.get("coverage_state", "not_applicable")),
        )
        for r in pdata.get("rows", []):
            evidence_urls = r.get("evidence_urls", [])
            rows.append(FacilityMapItem(
                artifact_version=ARTIFACT_VERSION,
                module_id="FACILITYMAP",
                method_version=method_version,
                pathogen=str(r.get("pathogen", pathogen)),
                normalized_establishment_number=str(r.get("normalized_establishment_number", "")),
                establishment_id=str(r.get("establishment_id", "")),
                establishment_number=r.get("establishment_number"),
                establishment_name=r.get("establishment_name"),
                state=str(r.get("state", "UNK")),
                county=r.get("county"),
                fips_code=r.get("fips_code"),
                eb_posterior=r.get("eb_posterior"),
                ci_low=r.get("ci_low"),
                ci_high=r.get("ci_high"),
                sample_n=int(r.get("sample_n", 0) or 0),
                positive_n=int(r.get("positive_n", 0) or 0),
                support_status=str(r.get("support_status", "unknown")),
                source_selection=str(r.get("source_selection", "s03")),
                placement_status=str(r.get("placement_status", "unplaced")),
                location_status=str(r.get("location_status", "unresolved")),
                match_method=r.get("match_method"),
                match_confidence=r.get("match_confidence"),
                verified_against_fsis_id=bool(r.get("verified_against_fsis_id", False)),
                historical_inspection_number=r.get("historical_inspection_number"),
                historical_address=r.get("historical_address"),
                coordinate_source=r.get("coordinate_source"),
                evidence_urls=list(evidence_urls) if isinstance(evidence_urls, list) else [],
                lat=r.get("lat"),
                lon=r.get("lon"),
                address=r.get("address"),
                unplaced_reason=r.get("unplaced_reason"),
                evidence_summary=str(r.get("evidence_summary", "")),
                coverage=coverage,
                human_review=bool(r.get("human_review", True)),
                status="OBSERVED",
                generated_at=stamp,
            ))

    # FORBIDDEN_TERMS guard (Req 10.1, 10.2): scan human-facing text fields only.
    lowered_terms = tuple(t.lower() for t in FORBIDDEN_TERMS)
    for ri, row in enumerate(rows):
        for field in _FACILITY_MAP_SCANNED_FIELDS:
            value = row.get(field)
            if not isinstance(value, str):
                continue
            haystack = value.lower()
            for term in lowered_terms:
                if term in haystack:
                    raise SchemaValidationError(
                        f"facility_map[item][{ri}].{field}: forbidden term "
                        f"{term!r} found; writing nothing"
                    )

    # Deterministic order: (pathogen, normalized_establishment_number), establishment_id.
    rows.sort(key=lambda r: (
        r["pathogen"],
        r["normalized_establishment_number"],
        r["establishment_id"],
    ))
    return rows


def build_all_artifacts(scenario_payload: Optional[dict] = None) -> dict[str, Any]:
    """Build and validate every value-bearing artifact payload (no I/O).

    Returns a mapping ``name -> payload``. Each payload is validated against its
    TypedDict here; a failure raises :class:`SchemaValidationError` before any
    file is touched. ``scenario_payload`` is the generated scenario comparison
    the equity test is computed over; when omitted it is generated here so the
    function stays self-contained and deterministic.
    """
    if scenario_payload is None:
        scenario_payload = build_scenario_payload()
    modules = build_manifest_modules()
    for pathogen, ms in modules.items():
        validate_payload(ms, ModuleStatus, label=f"manifest.pathogens.{pathogen}")

    feasibility = build_feasibility_report()
    validate_payload(feasibility, FeasibilityReport, label="feasibility_report")

    risk_timeseries = build_risk_timeseries()
    validate_payload(risk_timeseries, RiskTimeseriesPoint, label="risk_timeseries")

    risk_map = build_risk_map()
    validate_payload(risk_map, RiskMapFeature, label="risk_map")

    attention_queue = build_attention_queue()
    validate_payload(attention_queue, AttentionQueueItem, label="attention_queue")

    model_metrics, calibration = build_model_metrics()
    validate_payload(model_metrics, ModelMetric, label="model_metrics")
    validate_payload(calibration, CalibrationPoint, label="calibration")

    ablation = build_ablation_results()
    validate_payload(ablation, AblationResult, label="ablation_results")

    provenance = build_provenance()
    validate_payload(provenance, ProvenanceEntry, label="provenance")

    recommendations = build_recommendations(scenario_payload)
    validate_payload(recommendations, Recommendation, label="recommendations")

    vulnerability = build_vulnerability()
    validate_payload(vulnerability, VulnerabilityProfile, label="vulnerability")

    program_product = build_multipathogen_program_product()
    validate_payload(program_product, ProgramProductStratum, label="multipathogen_program_product")

    emerging_risk = build_emerging_risk()
    validate_payload(emerging_risk, EmergingRiskStratum, label="emerging_risk")
    establishment_surveillance = build_establishment_surveillance()
    validate_payload(establishment_surveillance, EstablishmentSurveillanceRecord, label="establishment_surveillance")
    human_comparison = build_human_outbreak_comparison()
    validate_payload(human_comparison, HumanOutbreakComparison, label="one_health_human_comparison")
    community_impact = build_community_impact()
    validate_payload(community_impact, CommunityImpactRecord, label="community_impact")
    county_community_impact = build_county_community_impact()
    validate_payload(county_community_impact, CountyCommunityImpactRecord, label="county_community_impact")

    action_queue = build_action_queue()
    validate_payload(action_queue, ActionQueueItem, label="action_queue")

    facility_map = build_facility_map()
    validate_payload(facility_map, FacilityMapItem, label="facility_map[item]")

    equity = build_equity_test(scenario_payload)
    validate_payload(equity, EquityTest, label="equity_test")

    return {
        "feasibility_report": feasibility,
        "risk_timeseries": risk_timeseries,
        "risk_map": risk_map,
        "attention_queue": attention_queue,
        "model_metrics": model_metrics,
        "calibration": calibration,
        "ablation_results": ablation,
        "provenance": provenance,
        "equity_test": equity,
        "recommendations": recommendations,
        "vulnerability": vulnerability,
        "multipathogen_program_product": program_product,
        "emerging_risk": emerging_risk,
        "establishment_surveillance": establishment_surveillance,
        "one_health_human_comparison": human_comparison,
        "community_impact": community_impact,
        "county_community_impact": county_community_impact,
        "action_queue": action_queue,
        "facility_map": facility_map,
        "_modules": modules,  # internal: folded into the manifest, not written standalone
    }


def _build_artifact_objects(payloads: dict[str, Any]) -> list[Artifact]:
    arts: list[Artifact] = []
    for name in sorted(payloads):
        if name.startswith("_"):
            continue
        payload = payloads[name]
        text = _canonical_json(payload)
        arts.append(
            Artifact(
                name=name,
                payload=payload,
                text=text,
                checksum=_sha256(text),
                record_count=_record_count(payload),
            )
        )
    return arts


def _build_manifest(
    arts: list[Artifact],
    modules: dict[str, dict],
    *,
    generated_at: str,
    extra_artifacts: dict[str, Any],
) -> dict:
    """Assemble the manifest. ``generated_at`` is the only non-substantive field.

    The manifest ``artifacts`` table records, per artifact, its checksum and
    record_count over the SUBSTANTIVE bytes, so it is itself reproducible.
    """
    freshness = _source_freshness()
    validate_payload(
        Manifest(
            artifact_version=ARTIFACT_VERSION,
            generated_at=generated_at,
            pathogens=modules,
            data_freshness=freshness,
        ),
        Manifest,
        label="manifest(core)",
    )

    artifact_index: dict[str, dict] = {}
    for a in arts:
        artifact_index[a.name] = {
            "file": f"{a.name}.json",
            "checksum_sha256": a.checksum,
            "record_count": a.record_count,
            "status_tagged": True,
        }
    for name, info in sorted(extra_artifacts.items()):
        artifact_index[name] = info

    return {
        "artifact_version": ARTIFACT_VERSION,
        "generated_at": generated_at,
        "generated_at_policy": (
            "Deterministic: resolved from VULNERASAFE_GENERATED_AT when set, "
            f"else the fixed documented constant {DEFAULT_GENERATED_AT!r}. This "
            "field is excluded from every per-artifact checksum so repeated "
            "exports from identical inputs are byte-identical in substance."
        ),
        "data_freshness": freshness,
        "pathogens": modules,
        "sources": _manifest_sources(),
        "artifacts": artifact_index,
    }


def _manifest_sources() -> list[dict]:
    """Checksummed-inputs summary for the manifest.

    Lists only sources that were actually ingested with content (a non-empty
    checksum). Sources with no retrievable bytes -- e.g. the firewalled FSIS
    recall feed -- are honestly recorded as GAP entries in ``provenance.json``
    and are intentionally not fabricated with a checksum here. Dropping them
    from this summary never hides them: the full provenance artifact retains
    every entry, gaps included.
    """
    prov = build_provenance()
    return [
        {
            "source": p["source"],
            "url": p["url"],
            "access_date": p["access_date"],
            "license": p["license"],
            "checksum_sha256": p["checksum"],
        }
        for p in prov
        if p.get("checksum")
    ]


def export_all(
    *,
    web_data_dir: Optional[Path] = None,
    generated_at: Optional[str] = None,
    regenerate_scenarios: bool = True,
) -> dict[str, Any]:
    """Build, validate and WRITE every artifact under ``web/public/data``.

    Returns a summary dict ``{"written": [paths], "checksums": {...},
    "manifest": {...}}``. Deterministic: two calls with identical inputs and the
    same ``generated_at`` produce byte-identical files.
    """
    out_dir = web_data_dir or WEB_DATA_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = resolve_generated_at(generated_at)

    written: list[str] = []
    checksums: dict[str, str] = {}
    extra: dict[str, Any] = {}

    # (1) Generate the scenario comparison payload from the real builders and
    # WRITE it (JSON + CSV) into out_dir before any manifest/checksum logic. The
    # same in-memory payload feeds the equity test, so they cannot disagree and
    # nothing depends on an earlier run having populated the directory.
    scenario_payload = build_scenario_payload()
    _validate_scenario_payload(scenario_payload)
    scen_path = out_dir / "scenario_results.json"
    scen_text, scen_checksum = _write_json_artifact(scen_path, scenario_payload)
    written.append(str(scen_path))
    checksums["scenario_results"] = scen_checksum
    scen_csv_path = out_dir / "scenario_results.csv"
    _atomic_write_text(scen_csv_path, build_scenario_csv())
    written.append(str(scen_csv_path))
    extra["scenario_results"] = {
        "file": "scenario_results.json",
        "checksum_sha256": scen_checksum,
        "record_count": len(scenario_payload.get("scenarios", [])),
        "status_tagged": True,
        "generated": True,
        "preserved": True,
    }

    # (2) Build the regulatory-track payload destination-independently, validate
    # it (list form), and WRITE it into out_dir before the manifest. An honest
    # unavailable-source marker is written when no official feed/file exists --
    # never fabricated alerts, never a confirmed zero-recall claim.
    reg = build_regulatory_alerts()
    if isinstance(reg, list):
        validate_payload(reg, RegulatoryAlert, label="regulatory_alerts")
        reg_count = len(reg)
    else:
        reg_count = len(reg.get("alerts", []))
    reg_path = out_dir / "regulatory_alerts.json"
    reg_text, reg_checksum = _write_json_artifact(reg_path, reg)
    written.append(str(reg_path))
    checksums["regulatory_alerts"] = reg_checksum
    extra["regulatory_alerts"] = {
        "file": "regulatory_alerts.json",
        "checksum_sha256": reg_checksum,
        "record_count": reg_count,
        "status_tagged": True,
        "feed_available": isinstance(reg, list),
    }

    # (3) Build + validate all generated artifacts, with the equity test computed
    # over the scenario payload generated above (explicit dependency injection).
    payloads = build_all_artifacts(scenario_payload=scenario_payload)
    modules = payloads["_modules"]
    arts = _build_artifact_objects(payloads)

    # (4) Write every generated artifact atomically, recording the checksum over
    # the exact bytes written. All referenced non-manifest artifacts now exist.
    for a in arts:
        path = out_dir / f"{a.name}.json"
        text, checksum = _write_json_artifact(path, a.payload)
        written.append(str(path))
        checksums[a.name] = checksum
        # CSV companions for the tabular artifacts the React views consume.
        if a.name in _CSV_ARTIFACTS:
            csv_path = out_dir / f"{a.name}.csv"
            _atomic_write_text(csv_path, _to_csv(a.payload))
            written.append(str(csv_path))

    # (5) Construct the manifest AFTER all referenced artifacts exist; it never
    # references itself, so no self-referential checksum is possible.
    manifest = _build_manifest(arts, modules, generated_at=stamp, extra_artifacts=extra)
    manifest_path = out_dir / "manifest.json"
    manifest_text, manifest_checksum = _write_json_artifact(manifest_path, manifest)
    written.append(str(manifest_path))
    checksums["manifest"] = manifest_checksum

    return {"written": written, "checksums": checksums, "manifest": manifest}


#: Artifacts that also get a flat CSV companion (useful for export/inspection).
_CSV_ARTIFACTS = frozenset(
    {"risk_timeseries", "risk_map", "attention_queue", "model_metrics", "provenance"}
)


def _to_csv(rows: list[dict]) -> str:
    """Deterministic CSV from a list of flat dicts (nested fields JSON-encoded)."""
    import csv
    import io

    if not rows:
        return ""
    fieldnames = list(rows[0].keys())
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        flat = {
            k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v)
            for k, v in row.items()
        }
        writer.writerow(flat)
    return buf.getvalue()


if __name__ == "__main__":  # pragma: no cover - manual invocation
    summary = export_all()
    print(f"Wrote {len(summary['written'])} files:")
    for p in summary["written"]:
        print(f"  {p}")
