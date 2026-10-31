"""Contract conformance tests for src.artifacts.schemas.

These tests are deliberately dependency-light (no pydantic). They introspect
the TypedDicts with ``typing`` helpers and structurally validate the example
``web/public/data/manifest.json`` against the Manifest contract.

Covers Requirements 14.3 (status tagging), 15.1 (shared contract), 15.5
(reproducible/validated artifacts).
"""

from __future__ import annotations

import json
import typing
from pathlib import Path

import pytest

from src.artifacts import schemas
from src.artifacts.schemas import (
    STATUS_TAGS,
    AblationResult,
    AttentionQueueItem,
    CalibrationPoint,
    EquityTest,
    EvidenceGraphEdge,
    EvidenceGraphNode,
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
)

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "web" / "public" / "data" / "manifest.json"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _is_typed_dict(tp: object) -> bool:
    """True if ``tp`` is a TypedDict class."""
    return (
        isinstance(tp, type)
        and hasattr(tp, "__annotations__")
        and hasattr(tp, "__total__")
        and hasattr(tp, "__required_keys__")
    )


def _expected_keys(td: type) -> set[str]:
    """Return the full set of annotated keys for a TypedDict."""
    return set(typing.get_type_hints(td).keys())


def assert_required_keys(value: dict, td: type) -> None:
    """Assert every required key of ``td`` exists in ``value``.

    This is the shared helper requested by the task: given a dict and a
    TypedDict, check required keys exist. ``total=True`` TypedDicts (the
    default used throughout the contract) treat all keys as required.
    """
    assert isinstance(value, dict), f"expected dict for {td.__name__}, got {type(value)}"
    missing = td.__required_keys__ - value.keys()
    assert not missing, f"{td.__name__} missing required keys: {sorted(missing)}"


# All TypedDicts in the contract and the keys we expect on each.
CONTRACT_TYPED_DICTS: dict[type, set[str]] = {
    FeasibilityFactor: {"name", "value", "threshold", "passed"},
    ModuleStatus: {"pathogen", "status", "feasibility_factors", "temporal_resolution"},
    Manifest: {"artifact_version", "generated_at", "pathogens", "data_freshness"},
    RiskTimeseriesPoint: {
        "pathogen", "commodity", "region", "period", "value",
        "ci_low", "ci_high", "status",
    },
    RiskMapFeature: {
        "region", "pathogen", "period", "risk", "uncertainty",
        "status", "data_freshness",
    },
    AttentionQueueItem: {
        "rank", "target_id", "target_type", "region", "pathogen",
        "risk", "triggering_condition", "status",
    },
    Recommendation: {
        "action", "target_id", "rationale", "constraints",
        "human_review_required", "evidence_refs", "uncertainty",
        "alert_source", "status",
    },
    RegulatoryAlert: {
        "recall_id", "product", "lot_ids", "classification", "date",
        "source_url", "alert_source", "status",
    },
    ScenarioMetric: {
        "policy", "scenario", "metric", "value", "diff_vs_a",
        "ci_low", "ci_high", "valid", "status",
    },
    AblationResult: {"config", "metric", "value", "marginal_vs_fsis_only"},
    ModelMetric: {
        "pathogen", "validation", "metric", "value", "ci_low",
        "ci_high", "region", "period",
    },
    CalibrationPoint: {"pathogen", "bin_mid", "predicted", "observed"},
    EvidenceGraphNode: {"id", "kind", "label"},
    EvidenceGraphEdge: {"source", "target"},
    ProvenanceEntry: {
        "source", "url", "access_date", "license", "geographic_coverage",
        "temporal_coverage", "checksum", "total_samples", "positive_count",
        "missingness", "known_biases", "notes",
    },
    EquityTest: {"passed", "disparity", "threshold", "description"},
    FeasibilityReport: {
        "pathogen", "temporal_resolution", "factors",
        "classification", "rationale",
    },
}


# --------------------------------------------------------------------------- #
# (a) every TypedDict is a TypedDict with the expected keys
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("td, expected", CONTRACT_TYPED_DICTS.items(),
                         ids=lambda x: getattr(x, "__name__", str(x)))
def test_contract_typeddict_has_expected_keys(td: type, expected: set[str]) -> None:
    assert _is_typed_dict(td), f"{td!r} is not a TypedDict"
    assert _expected_keys(td) == expected, (
        f"{td.__name__} keys mismatch: "
        f"missing={expected - _expected_keys(td)}, "
        f"extra={_expected_keys(td) - expected}"
    )


def test_status_tags_set_matches_literal() -> None:
    assert STATUS_TAGS == frozenset({"OBSERVED", "PREDICTED", "SIMULATED"})


def test_alert_sources_set_matches_literal() -> None:
    assert schemas.ALERT_SOURCES == frozenset({"MODEL", "REGULATORY"})


# --------------------------------------------------------------------------- #
# (b) the example manifest.json structurally conforms to the Manifest contract
# --------------------------------------------------------------------------- #

def _load_manifest() -> dict:
    assert MANIFEST_PATH.exists(), f"manifest not found at {MANIFEST_PATH}"
    with MANIFEST_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def test_manifest_conforms_to_manifest_contract() -> None:
    manifest = _load_manifest()
    assert_required_keys(manifest, Manifest)

    assert isinstance(manifest["artifact_version"], str)
    assert isinstance(manifest["generated_at"], str)
    assert isinstance(manifest["data_freshness"], dict)
    assert all(isinstance(k, str) and isinstance(v, str)
               for k, v in manifest["data_freshness"].items())

    pathogens = manifest["pathogens"]
    assert isinstance(pathogens, dict) and pathogens, "pathogens must be a non-empty dict"

    # All three pathogens present.
    assert {"Salmonella", "Listeria", "STEC"} <= pathogens.keys()

    for name, module in pathogens.items():
        assert_required_keys(module, ModuleStatus)
        assert module["pathogen"] == name
        assert module["status"] in {"predictive", "non_predictive"}
        assert module["temporal_resolution"] in {"monthly", "quarterly"}
        assert isinstance(module["feasibility_factors"], list)
        for factor in module["feasibility_factors"]:
            assert_required_keys(factor, FeasibilityFactor)
            assert isinstance(factor["name"], str)
            assert isinstance(factor["value"], (int, float))
            assert isinstance(factor["threshold"], (int, float))
            assert isinstance(factor["passed"], bool)


def test_manifest_is_placeholder_version() -> None:
    manifest = _load_manifest()
    assert manifest["artifact_version"] == "0.1.0"


#: Keys whose string value is a provenance StatusTag (Req 14.3), as opposed to
#: the ``status`` key inside a ModuleStatus record, which is a module
#: *classification* (predictive | non_predictive). The manifest is the one
#: artifact where ``status`` is overloaded, so the StatusTag walker skips the
#: ``pathogens`` subtree and the module classification is checked separately.
_MODULE_CLASSIFICATIONS = frozenset({"predictive", "non_predictive"})


def _iter_statustag_values(obj: object, *, under_pathogens: bool = False):
    """Yield every value stored under a provenance ``status`` key, recursively.

    Values of the ``status`` key inside a ModuleStatus record (reached via the
    manifest ``pathogens`` map) are module classifications, not StatusTags, and
    are intentionally excluded."""
    if isinstance(obj, dict):
        for key, val in obj.items():
            if key == "status" and isinstance(val, str) and not under_pathogens:
                yield val
            else:
                yield from _iter_statustag_values(
                    val, under_pathogens=under_pathogens or key == "pathogens"
                )
    elif isinstance(obj, list):
        for item in obj:
            yield from _iter_statustag_values(item, under_pathogens=under_pathogens)


def test_manifest_statustag_values_are_valid() -> None:
    """Every provenance status value in the manifest is a valid StatusTag.

    The manifest carries no provenance status values (its only ``status`` keys
    are module classifications); if any appear they must be in the allowed set
    (Req 14.3)."""
    manifest = _load_manifest()
    for status in _iter_statustag_values(manifest):
        assert status in STATUS_TAGS, f"invalid status tag: {status!r}"


def test_manifest_module_status_values_are_classifications() -> None:
    """Each ModuleStatus ``status`` is a valid module classification."""
    manifest = _load_manifest()
    for module in manifest["pathogens"].values():
        assert module["status"] in _MODULE_CLASSIFICATIONS, (
            f"invalid module classification: {module['status']!r}"
        )
