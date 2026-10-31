"""Smoke tests for the per-source ingestion module (Task 2.1).

Covers:
* NOAA token-free NCEI Access path returns ``ok`` with a non-empty DataFrame
  and a valid ProvenanceEntry carrying a checksum (hits the live service; the
  test skips only on a genuine network/connection error so CI stays green).
* ``ingest_fsis_local`` against an empty FSIS directory returns gracefully with
  a recorded gap and never crashes (Req 2.3, 3.7).
* ``run_ingestion`` writes both the provenance and the report JSON files.
* ``classify_fsis_dataframe`` recognises the four FSIS dataset families.

Validates: Requirements 2.1, 2.2, 2.3, 2.4, 3.7, 4.1, 4.3
"""

from __future__ import annotations

import json
import re

import pandas as pd
import pytest
import requests

from src.artifacts.schemas import ProvenanceEntry
from src.pipeline import ingest


_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _assert_valid_provenance(entry: dict) -> None:
    """Assert a provenance dict has every ProvenanceEntry key with sane types."""
    for key in ProvenanceEntry.__annotations__:
        assert key in entry, f"provenance missing key: {key}"
    assert _ISO_DATE.match(entry["access_date"]), "access_date must be ISO YYYY-MM-DD"
    assert isinstance(entry["missingness"], dict)
    assert isinstance(entry["known_biases"], list)


# --------------------------------------------------------------------------- #
# (a) Live NOAA token-free path
# --------------------------------------------------------------------------- #

def test_ingest_noaa_live_ok():
    """ingest_noaa hits the token-free NCEI Access service and returns data."""
    try:
        res = ingest.ingest_noaa(
            stations=["USW00094728"],  # NYC Central Park (GHCND)
            start="2023-01-01",
            end="2023-01-05",
            data_types=["TMAX", "TMIN", "PRCP"],
        )
    except requests.exceptions.RequestException as exc:  # pragma: no cover
        pytest.skip(f"network unavailable for live NOAA test: {exc}")

    # If the environment has no network at all, the function returns a graceful
    # failure rather than raising; skip in that case so CI is not flaky.
    if res.status == "failed" and (
        res.error and ("request failed" in res.error or "empty" in res.error)
    ):  # pragma: no cover
        pytest.skip(f"NOAA network path unavailable: {res.error}")

    assert res.status == "ok", f"expected ok, got {res.status}: {res.error}"
    assert isinstance(res.data, pd.DataFrame)
    assert not res.data.empty
    assert len(res.provenance) == 1
    prov = res.provenance[0]
    _assert_valid_provenance(prov)
    assert prov["source"] == "noaa"
    assert prov["checksum"] and len(prov["checksum"]) == 64  # SHA-256 hex
    assert prov["total_samples"] == len(res.data)


# --------------------------------------------------------------------------- #
# (b) FSIS local importer against an empty directory
# --------------------------------------------------------------------------- #

def test_ingest_fsis_local_empty_dir_graceful(tmp_path):
    """An empty FSIS dir yields a recorded gap, no crash (Req 2.3, 3.7)."""
    empty_dir = tmp_path / "fsis"
    res = ingest.ingest_fsis_local(fsis_dir=empty_dir)

    assert res.status == "failed"
    assert res.data is None  # nothing fabricated (Req 4.6)
    assert res.manual_instructions and "data/raw/fsis" in res.manual_instructions
    assert len(res.provenance) == 1
    prov = res.provenance[0]
    _assert_valid_provenance(prov)
    assert "GAP" in prov["notes"]


# --------------------------------------------------------------------------- #
# (c) run_ingestion writes provenance + report files
# --------------------------------------------------------------------------- #

def test_run_ingestion_writes_reports():
    """run_ingestion writes both JSON reports and returns per-source results."""
    outcome = ingest.run_ingestion()

    prov_path = outcome["provenance_path"]
    report_path = outcome["report_path"]
    assert prov_path.exists(), "provenance_ingest.json not written"
    assert report_path.exists(), "ingest_report.json not written"

    provenance = json.loads(prov_path.read_text(encoding="utf-8"))
    assert isinstance(provenance, list) and len(provenance) >= 1
    for entry in provenance:
        _assert_valid_provenance(entry)

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert "sources" in report and "summary" in report
    # Every source that ran must land in exactly one summary bucket.
    buckets = (
        set(report["summary"]["ok"])
        | set(report["summary"]["skipped_no_key"])
        | set(report["summary"]["failed"])
    )
    assert buckets == set(report["sources"].keys())


# --------------------------------------------------------------------------- #
# (d) FSIS classification of the four known families
# --------------------------------------------------------------------------- #

def test_classify_fsis_dataframe_families():
    raw_poultry = pd.DataFrame(
        {"EstablishmentID": [1], "Salmonella_Result": ["Negative"],
         "Campylobacter_Result": ["Negative"]}
    )
    assert ingest.classify_fsis_dataframe(raw_poultry, "poultry.csv") == "raw_poultry_salmonella"

    rte = pd.DataFrame(
        {"RTEPROD_RAND": [1], "Lm_Result": ["Negative"], "Salmonella_Result": ["Negative"]}
    )
    assert ingest.classify_fsis_dataframe(rte, "rte.csv") == "rte_listeria"

    beef = pd.DataFrame({"EstablishmentID": [1], "STEC_O157_Result": ["Negative"]})
    assert ingest.classify_fsis_dataframe(beef, "beef_n60.csv") == "raw_beef_stec"

    recalls = pd.DataFrame(
        {"recall_number": ["001-2024"], "product": ["x"], "classification": ["Class I"]}
    )
    assert ingest.classify_fsis_dataframe(recalls, "recalls.csv") == "recalls"

    unknown = pd.DataFrame({"foo": [1], "bar": [2]})
    assert ingest.classify_fsis_dataframe(unknown, "mystery.csv") == "unknown"
