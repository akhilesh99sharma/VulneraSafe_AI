"""Focused tests for the schema-validated artifact exporter (Task 5.1).

Covers:
* schema-validation failure raises before writing;
* manifest completeness (version, generated_at policy, checksums, row counts,
  module status/feasibility, sources);
* status-tag invariant — exactly one valid tag per displayed value (Property 7);
* deterministic output — repeated export is byte-identical in substance,
  independent of generated_at (Property 10);
* equity-test arithmetic (ratio/disparity/threshold, Req 16.9);
* no synthetic/real mixing — SIMULATED and OBSERVED/PREDICTED never share a
  record set (Property 9, Req 4.4).

Validates: Requirements 8.6, 14.3, 15.1, 15.5, 16.9; Properties 7, 9, 10.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.artifacts import exporter
from src.artifacts.exporter import (
    SchemaValidationError,
    build_all_artifacts,
    build_equity_test,
    export_all,
    resolve_generated_at,
    validate_payload,
)
from src.artifacts.schemas import ModelMetric, RiskMapFeature


# --------------------------------------------------------------------------- #
# Schema-validation failure
# --------------------------------------------------------------------------- #
def test_validate_payload_rejects_bad_scalar_and_names_artifact():
    bad = {
        "region": "AL",
        "pathogen": "Salmonella",
        "period": "2026-05",
        "risk": "high",  # should be float
        "uncertainty": 0.1,
        "status": "PREDICTED",
        "data_freshness": "2026-01-01",
    }
    with pytest.raises(SchemaValidationError) as ei:
        validate_payload(bad, RiskMapFeature, label="risk_map")
    msg = str(ei.value)
    assert "risk_map" in msg
    assert "risk" in msg


def test_validate_payload_rejects_bad_literal_status_tag():
    bad = {
        "region": "AL",
        "pathogen": "Salmonella",
        "period": "2026-05",
        "risk": 0.2,
        "uncertainty": 0.1,
        "status": "OBSERVED_PLUS",  # not a valid StatusTag
        "data_freshness": "2026-01-01",
    }
    with pytest.raises(SchemaValidationError):
        validate_payload(bad, RiskMapFeature, label="risk_map")


def test_validate_payload_rejects_missing_and_extra_keys():
    # missing 'ci_low' etc., and an unexpected key
    bad = {
        "pathogen": "STEC",
        "validation": "chronological",
        "metric": "pr_auc",
        "value": 0.4,
        "surprise": 1,
    }
    with pytest.raises(SchemaValidationError) as ei:
        validate_payload(bad, ModelMetric, label="model_metrics")
    msg = str(ei.value)
    assert "missing required key" in msg
    assert "unexpected key" in msg


def test_build_all_artifacts_validates_everything():
    # Should not raise: real pipeline outputs conform to the contract.
    payloads = build_all_artifacts()
    for name in (
        "feasibility_report",
        "risk_timeseries",
        "risk_map",
        "attention_queue",
        "model_metrics",
        "ablation_results",
        "provenance",
        "equity_test",
    ):
        assert name in payloads


# --------------------------------------------------------------------------- #
# Export + manifest completeness
# --------------------------------------------------------------------------- #
@pytest.fixture()
def exported(tmp_path: Path) -> dict:
    summary = export_all(web_data_dir=tmp_path, generated_at="2026-01-01T00:00:00Z")
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    return {"dir": tmp_path, "summary": summary, "manifest": manifest}


def test_manifest_is_complete(exported):
    m = exported["manifest"]
    assert m["artifact_version"] == exporter.ARTIFACT_VERSION
    assert m["generated_at"] == "2026-01-01T00:00:00Z"
    assert "generated_at_policy" in m and "Deterministic" in m["generated_at_policy"]
    # module status + feasibility factors present for all three pathogens
    assert set(m["pathogens"]) == {"Salmonella", "Listeria", "STEC"}
    for pathogen, ms in m["pathogens"].items():
        assert ms["status"] in {"predictive", "non_predictive"}
        assert ms["feasibility_factors"], f"{pathogen} missing factors"
    # per-artifact checksum + row count recorded
    for name, info in m["artifacts"].items():
        assert "checksum_sha256" in info and len(info["checksum_sha256"]) == 64
        assert "record_count" in info
    # sources/provenance summary present with checksums
    assert m["sources"], "manifest must list sources"
    for s in m["sources"]:
        assert s["checksum_sha256"]
    # the key artifacts the React views need all exist on disk
    for name in (
        "risk_timeseries",
        "risk_map",
        "attention_queue",
        "model_metrics",
        "calibration",
        "ablation_results",
        "provenance",
        "feasibility_report",
        "equity_test",
    ):
        assert (exported["dir"] / f"{name}.json").exists()


def test_scenario_and_regulatory_artifacts_preserved(exported):
    d = exported["dir"]
    # scenario comparison regenerated/preserved
    assert (d / "scenario_results.json").exists()
    assert (d / "scenario_results.csv").exists()
    scen = json.loads((d / "scenario_results.json").read_text(encoding="utf-8"))
    assert scen["status"] == "SIMULATED"
    assert exported["manifest"]["artifacts"]["scenario_results"]["preserved"] is True


# --------------------------------------------------------------------------- #
# Status-tag invariant (Property 7)
# --------------------------------------------------------------------------- #
VALID_TAGS = {"OBSERVED", "PREDICTED", "SIMULATED"}


def test_exactly_one_valid_status_tag_per_displayed_value(exported):
    d = exported["dir"]
    for name in ("risk_timeseries", "risk_map", "attention_queue"):
        rows = json.loads((d / f"{name}.json").read_text(encoding="utf-8"))
        assert rows
        for row in rows:
            assert row["status"] in VALID_TAGS
    # model values for future periods are PREDICTED
    rm = json.loads((d / "risk_map.json").read_text(encoding="utf-8"))
    assert all(r["status"] == "PREDICTED" for r in rm)


# --------------------------------------------------------------------------- #
# Determinism (Property 10)
# --------------------------------------------------------------------------- #
def test_repeated_export_is_byte_identical(tmp_path: Path):
    a = tmp_path / "run_a"
    b = tmp_path / "run_b"
    export_all(web_data_dir=a, generated_at="2026-01-01T00:00:00Z")
    export_all(web_data_dir=b, generated_at="2026-01-01T00:00:00Z")
    for f in sorted(a.glob("*.json")):
        assert f.read_text(encoding="utf-8") == (b / f.name).read_text(
            encoding="utf-8"
        ), f"{f.name} differs between identical runs"


def test_generated_at_does_not_affect_substantive_artifacts(tmp_path: Path):
    a = tmp_path / "run_a"
    b = tmp_path / "run_b"
    export_all(web_data_dir=a, generated_at="2026-01-01T00:00:00Z")
    export_all(web_data_dir=b, generated_at="2099-12-31T23:59:59Z")
    # every substantive artifact is identical regardless of the stamp
    for f in sorted(a.glob("*.json")):
        if f.name == "manifest.json":
            continue
        assert f.read_text(encoding="utf-8") == (b / f.name).read_text(encoding="utf-8")
    # the manifest's per-artifact checksums are also stamp-independent
    ma = json.loads((a / "manifest.json").read_text(encoding="utf-8"))
    mb = json.loads((b / "manifest.json").read_text(encoding="utf-8"))
    assert ma["artifacts"] == mb["artifacts"]
    assert ma["generated_at"] != mb["generated_at"]


def test_resolve_generated_at_env_override(monkeypatch):
    monkeypatch.setenv("VULNERASAFE_GENERATED_AT", "2030-06-15T00:00:00Z")
    assert resolve_generated_at() == "2030-06-15T00:00:00Z"
    monkeypatch.delenv("VULNERASAFE_GENERATED_AT", raising=False)
    assert resolve_generated_at() == exporter.DEFAULT_GENERATED_AT


# --------------------------------------------------------------------------- #
# Equity-test arithmetic (Req 16.9)
# --------------------------------------------------------------------------- #
def test_equity_test_arithmetic_and_shape():
    eq = build_equity_test()
    assert set(eq) == {"passed", "disparity", "threshold", "description"}
    assert isinstance(eq["passed"], bool)
    assert isinstance(eq["disparity"], float)
    assert eq["threshold"] == pytest.approx(0.25)
    # no invented observed-illness effect in the stated metric
    assert "illness" not in eq["description"].lower() or "no observed illness" in eq[
        "description"
    ].lower()


def test_equity_disparity_matches_responsible_definition():
    from src.responsible import equity_disparity

    # parity -> ratio 1, disparity 0, pass
    d = equity_disparity(1.0, 1.0)
    assert d["ratio"] == pytest.approx(1.0)
    assert d["disparity"] == pytest.approx(0.0)
    assert d["passed"] is True
    # below four-fifths -> fail
    d2 = equity_disparity(0.5, 1.0)
    assert d2["passed"] is False
    assert d2["disparity"] == pytest.approx(-0.5)


# --------------------------------------------------------------------------- #
# No synthetic/real mixing (Property 9, Req 4.4)
# --------------------------------------------------------------------------- #
def test_no_synthetic_real_mixing_within_a_record_set(exported):
    d = exported["dir"]
    # SIMULATED only in the scenario (operational) artifact
    scen = json.loads((d / "scenario_results.json").read_text(encoding="utf-8"))
    assert scen["status"] == "SIMULATED"

    # The real surveillance/model artifacts never carry SIMULATED on a value.
    for name in ("risk_timeseries", "risk_map", "attention_queue"):
        rows = json.loads((d / f"{name}.json").read_text(encoding="utf-8"))
        tags = {r["status"] for r in rows}
        assert "SIMULATED" not in tags, f"{name} must not mix SIMULATED with real values"
        assert tags <= {"OBSERVED", "PREDICTED"}

    # Conversely every per-policy metric in the operational artifact is SIMULATED.
    for s in scen["scenarios"]:
        for pol in s["policies"]:
            for metric in pol["metrics"]:
                assert metric["status"] == "SIMULATED"
