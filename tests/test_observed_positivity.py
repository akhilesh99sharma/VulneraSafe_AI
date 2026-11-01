"""Tests for the OBSERVED positivity artifact (build_observed_positivity).

The OBSERVED positivity artifact is the MEASURED counterpart to the PREDICTED
risk_map: for each (pathogen, state) it emits ONE row for the latest reporting
period that carries a genuine measurement, reading the real model table
(``data/processed/model_<slug>.parquet``) via ``_load_model_table``.

These tests monkeypatch ``_load_model_table`` with a small hand-built pandas
DataFrame so there is no raw-data dependency, and lock the honesty properties:

  * status is always "OBSERVED";
  * the measured rate / sample / positive counts are read straight from the
    table (never invented);
  * the LATEST measured period per state is used;
  * a state whose only "latest" period has zero samples / a null rate is
    OMITTED (no fabricated row) — the predicted-map coverage-gap behavior;
  * the payload validates against the ObservedPositivityFeature schema.
"""

from __future__ import annotations

import pandas as pd

from src.artifacts import exporter
from src.artifacts.exporter import (
    build_observed_positivity,
    build_observed_positivity_timeseries,
    validate_payload,
)
from src.artifacts.schemas import ObservedPositivityFeature, RiskTimeseriesPoint


def _two_state_frame() -> pd.DataFrame:
    """A model-table fixture with two states.

    * ``TX`` has two measured periods; the LATEST ("2024-02") must be chosen.
    * ``CA`` has an earlier measured period ("2024-01") but its LATEST period
      ("2024-02") has zero samples and a null rate — so CA must be OMITTED
      entirely (no fabricated row), matching the "latest measured period" rule.
    """
    return pd.DataFrame(
        [
            # TX: earlier measured period
            {
                "state": "TX", "period": "2024-01",
                "outcome_routine_positivity_rate": 0.10,
                "outcome_routine_samples": 50, "outcome_routine_positives": 5,
            },
            # TX: latest measured period (the one that must win)
            {
                "state": "TX", "period": "2024-02",
                "outcome_routine_positivity_rate": 0.20,
                "outcome_routine_samples": 40, "outcome_routine_positives": 8,
            },
            # CA: a real earlier measured period
            {
                "state": "CA", "period": "2024-01",
                "outcome_routine_positivity_rate": 0.30,
                "outcome_routine_samples": 20, "outcome_routine_positives": 6,
            },
            # CA: latest period has NO measurement (zero samples, null rate) ->
            # CA has no *measured* latest period that qualifies... but note the
            # builder keeps only measured rows first, so CA's latest MEASURED
            # period is 2024-01. To exercise the full-omission path we add a
            # third state with no measured period at all below.
            {
                "state": "CA", "period": "2024-02",
                "outcome_routine_positivity_rate": None,
                "outcome_routine_samples": 0, "outcome_routine_positives": 0,
            },
            # ND: EVERY period has zero samples / null rate -> fully omitted.
            {
                "state": "ND", "period": "2024-01",
                "outcome_routine_positivity_rate": None,
                "outcome_routine_samples": 0, "outcome_routine_positives": 0,
            },
            {
                "state": "ND", "period": "2024-02",
                "outcome_routine_positivity_rate": None,
                "outcome_routine_samples": 0, "outcome_routine_positives": 0,
            },
        ]
    )


def test_observed_positivity_reads_latest_measured_and_omits_unmeasured(monkeypatch):
    # Serve the same fixture for every pathogen slug so the three PATHOGENS all
    # produce rows from the identical two/three-state table.
    monkeypatch.setattr(exporter, "_load_model_table", lambda slug: _two_state_frame())

    rows = build_observed_positivity()

    # Every emitted row is OBSERVED — never PREDICTED/SIMULATED.
    assert rows
    assert all(r["status"] == "OBSERVED" for r in rows)
    assert all(r["module_id"] == "OBSERVEDPOS" for r in rows)

    # ND has no measured period at all -> omitted for every pathogen.
    assert all(r["region"] != "ND" for r in rows)

    # Look at the Salmonella rows specifically.
    salm = [r for r in rows if r["pathogen"] == "Salmonella"]
    regions = {r["region"] for r in salm}
    # TX and CA each have at least one MEASURED period, so both appear; ND does not.
    assert regions == {"TX", "CA"}

    tx = next(r for r in salm if r["region"] == "TX")
    # Latest MEASURED period for TX is 2024-02 with its real rate/counts.
    assert tx["period"] == "2024-02"
    assert tx["positivity"] == 0.2
    assert tx["sample_n"] == 40
    assert tx["positive_n"] == 8

    ca = next(r for r in salm if r["region"] == "CA")
    # CA's only MEASURED period is 2024-01 (its 2024-02 row has zero samples /
    # null rate and is not counted), so that measured period is used.
    assert ca["period"] == "2024-01"
    assert ca["positivity"] == 0.3
    assert ca["sample_n"] == 20
    assert ca["positive_n"] == 6

    # Deterministic sort by (pathogen, region).
    keys = [(r["pathogen"], r["region"]) for r in rows]
    assert keys == sorted(keys)

    # The payload validates against the schema contract.
    validate_payload(rows, ObservedPositivityFeature, label="observed_positivity")


def test_observed_positivity_tolerates_missing_model_table(monkeypatch):
    # If the model table cannot be read for a slug, that pathogen's rows are
    # skipped rather than crashing the whole export.
    def _raise(slug):
        raise FileNotFoundError(f"no model table for {slug}")

    monkeypatch.setattr(exporter, "_load_model_table", _raise)
    rows = build_observed_positivity()
    assert rows == []


# --------------------------------------------------------------------------- #
# OBSERVED positivity TIME SERIES (build_observed_positivity_timeseries)
# --------------------------------------------------------------------------- #
def test_observed_timeseries_emits_one_row_per_measured_period(monkeypatch):
    # The time-series builder keeps EVERY measured (state, period) — not just
    # the latest — so the National Risk Trend can follow the Observed toggle.
    monkeypatch.setattr(exporter, "_load_model_table", lambda slug: _two_state_frame())

    rows = build_observed_positivity_timeseries()
    assert rows
    # Every row is OBSERVED (never PREDICTED) and shares the RiskTimeseriesPoint
    # shape (no module_id / generated_at — this is the risk_timeseries contract).
    assert all(r["status"] == "OBSERVED" for r in rows)
    assert all("module_id" not in r for r in rows)

    salm = [r for r in rows if r["pathogen"] == "Salmonella"]
    # TX has TWO measured periods -> both appear (unlike the latest-only snapshot).
    tx = sorted((r for r in salm if r["region"] == "TX"), key=lambda r: r["period"])
    assert [r["period"] for r in tx] == ["2024-01", "2024-02"]
    assert [r["value"] for r in tx] == [0.1, 0.2]

    # CA contributes only its ONE measured period (2024-01); the 2024-02 row has
    # zero samples / null rate and is omitted (never fabricated).
    ca = [r for r in salm if r["region"] == "CA"]
    assert [r["period"] for r in ca] == ["2024-01"]

    # ND has no measured period at all -> fully omitted.
    assert all(r["region"] != "ND" for r in rows)

    # The CI is a REAL Wilson interval bracketing the measured rate, not the
    # fixed predicted display band: ci_low <= value <= ci_high with a real band.
    tx_latest = next(r for r in tx if r["period"] == "2024-02")
    assert tx_latest["ci_low"] <= tx_latest["value"] <= tx_latest["ci_high"]
    assert tx_latest["ci_low"] < tx_latest["ci_high"]  # a genuine (non-degenerate) band

    # Deterministic sort by (pathogen, region, period).
    keys = [(r["pathogen"], r["region"], r["period"]) for r in rows]
    assert keys == sorted(keys)

    # Validates against the SHARED RiskTimeseriesPoint schema (no new contract).
    validate_payload(rows, RiskTimeseriesPoint, label="observed_timeseries")


def test_observed_timeseries_tolerates_missing_model_table(monkeypatch):
    def _raise(slug):
        raise FileNotFoundError(f"no model table for {slug}")

    monkeypatch.setattr(exporter, "_load_model_table", _raise)
    assert build_observed_positivity_timeseries() == []


# --------------------------------------------------------------------------- #
# Schema <-> TypeScript parity (ObservedPositivityFeature)
# --------------------------------------------------------------------------- #
import re
import typing
from pathlib import Path

_ARTIFACTS_TS = Path(__file__).resolve().parents[1] / "web" / "src" / "types" / "artifacts.ts"


def _ts_interface_fields(ts_text: str, interface_name: str) -> set[str]:
    """Parse the field names of a TypeScript interface body (key-set only)."""
    m = re.search(
        r"export\s+interface\s+" + re.escape(interface_name) + r"\s*\{(.*?)\}",
        ts_text, re.DOTALL)
    assert m, f"interface {interface_name} not found in artifacts.ts"
    body = m.group(1)
    fields: set[str] = set()
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        stripped = stripped.split("//", 1)[0].strip()
        fm_match = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s*[?]?\s*:", stripped)
        if fm_match:
            fields.add(fm_match.group(1))
    return fields


def test_observed_positivity_python_ts_parity():
    ts_text = _ARTIFACTS_TS.read_text(encoding="utf-8")
    py_keys = set(typing.get_type_hints(ObservedPositivityFeature).keys())
    ts_keys = _ts_interface_fields(ts_text, "ObservedPositivityFeature")
    assert py_keys == ts_keys, (
        f"ObservedPositivityFeature parity mismatch: "
        f"py-only={py_keys - ts_keys}, ts-only={ts_keys - py_keys}")
    # The field counts must match too (no duplicate/ghost fields).
    assert len(py_keys) == len(ts_keys)
