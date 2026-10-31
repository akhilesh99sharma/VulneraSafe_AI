"""Tests for data integrity and authenticity enforcement (Task 2.3).

Covers Requirements 4.2, 4.5, 4.6:

* ``verify_checksum`` returns True on a match and False after any mutation;
  ``enforce_checksum`` raises an IntegrityError naming the dataset on mismatch.
* ``assert_no_placeholder_in_empirical`` raises for an empirical dataframe that
  contains placeholder sentinels and passes when the dataset is SIMULATED.
* ``record_gap`` appends a structured gap entry that carries no numeric value
  for the missing field.

Validates: Requirements 4.2, 4.5, 4.6
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from src.pipeline import integrity


# --------------------------------------------------------------------------- #
# Req 4.2 — checksum verification + rejection
# --------------------------------------------------------------------------- #

def test_verify_checksum_true_on_match_bytes():
    data = b"authentic FSIS sampling bytes"
    recorded = integrity._sha256_of(data)
    assert integrity.verify_checksum(data, recorded) is True


def test_verify_checksum_false_on_mutation_bytes():
    data = b"authentic FSIS sampling bytes"
    recorded = integrity._sha256_of(data)
    mutated = data + b"!"  # one-byte tamper
    assert integrity.verify_checksum(mutated, recorded) is False


def test_verify_checksum_true_and_false_for_file(tmp_path):
    p = tmp_path / "dataset.csv"
    p.write_bytes(b"col\n1\n2\n")
    recorded = integrity._sha256_of(p)
    assert integrity.verify_checksum(p, recorded) is True

    p.write_bytes(b"col\n1\n2\n3\n")  # mutate the file in place
    assert integrity.verify_checksum(p, recorded) is False


def test_verify_checksum_blank_recorded_never_matches():
    assert integrity.verify_checksum(b"x", "") is False


def test_enforce_checksum_rejects_mismatch_naming_dataset():
    data = b"real data"
    recorded = integrity._sha256_of(data)
    tampered = b"tampered data"

    # Match: no exception.
    integrity.enforce_checksum(data, recorded, "fsis_raw_poultry_fy2023")

    # Mismatch: rejected, error names the dataset (Req 4.2).
    with pytest.raises(integrity.IntegrityError) as exc:
        integrity.enforce_checksum(tampered, recorded, "fsis_raw_poultry_fy2023")
    msg = str(exc.value)
    assert "fsis_raw_poultry_fy2023" in msg
    assert "downstream" in msg.lower()


# --------------------------------------------------------------------------- #
# Req 4.5 — no placeholders in empirical datasets
# --------------------------------------------------------------------------- #

def test_assert_no_placeholder_raises_for_empirical_string_sentinel():
    df = pd.DataFrame(
        {"establishment": ["E1", "PLACEHOLDER"], "result": ["Negative", "Positive"]}
    )
    with pytest.raises(integrity.PlaceholderError) as exc:
        integrity.assert_no_placeholder_in_empirical(df, "fsis_raw_beef")
    assert "fsis_raw_beef" in str(exc.value)


def test_assert_no_placeholder_raises_for_empirical_numeric_sentinel():
    df = pd.DataFrame({"mpn": [1.2, 9999, 0.0]})
    with pytest.raises(integrity.PlaceholderError):
        integrity.assert_no_placeholder_in_empirical(df, "fsis_raw_beef")


def test_assert_no_placeholder_raises_for_negative_numeric_sentinel():
    df = pd.DataFrame({"mpn": [1.2, -9999.0]})
    with pytest.raises(integrity.PlaceholderError):
        integrity.assert_no_placeholder_in_empirical(df, "noaa_weather")


def test_assert_no_placeholder_passes_for_synthetic_label():
    df = pd.DataFrame(
        {"lot": ["PLACEHOLDER", "FIXME"], "qty": [9999, -9999]}
    )
    # Synthetic/SIMULATED datasets may use placeholders freely (Req 4.4/4.5).
    integrity.assert_no_placeholder_in_empirical(df, "SIMULATED")
    integrity.assert_no_placeholder_in_empirical(df, "synthetic_operational_network")


def test_assert_no_placeholder_passes_for_clean_empirical():
    df = pd.DataFrame(
        {"establishment": ["E1", "E2"], "mpn": [0.3, 12.0], "result": ["Neg", "Pos"]}
    )
    integrity.assert_no_placeholder_in_empirical(df, "fsis_raw_poultry")


def test_assert_no_placeholder_handles_none_and_empty():
    integrity.assert_no_placeholder_in_empirical(None, "fsis_raw_poultry")
    integrity.assert_no_placeholder_in_empirical(pd.DataFrame(), "fsis_raw_poultry")


# --------------------------------------------------------------------------- #
# Req 4.6 — structured gap with no fabricated number
# --------------------------------------------------------------------------- #

def test_record_gap_emits_no_numeric_value():
    gaps: list[dict] = []
    entry = integrity.record_gap(
        gaps, "positive_count", "program denominator unavailable",
        dataset="fsis_rte_fy2026",
    )

    assert len(gaps) == 1 and gaps[0] is entry
    assert entry["field"] == "positive_count"
    assert entry["reason"] == "program denominator unavailable"
    assert entry["value_available"] is False
    assert entry["dataset"] == "fsis_rte_fy2026"

    # No numeric value may be present anywhere in the gap entry (Req 4.6).
    # ``value_available`` is an explicit boolean flag, not a numeric value for
    # the missing field; bool is a subclass of int so it is excluded here.
    for key, value in entry.items():
        if isinstance(value, bool):
            assert key == "value_available"
            continue
        assert not isinstance(value, (int, float)), (
            f"gap entry must not emit a numeric value, found {key}={value!r}"
        )


def test_record_gap_appends_multiple_without_values():
    gaps: list[dict] = []
    integrity.record_gap(gaps, "collection_date", "field absent in source")
    integrity.record_gap(gaps, "positive_count", "denominator missing")
    assert len(gaps) == 2
    assert all(g["value_available"] is False for g in gaps)
    assert all(
        not isinstance(v, (int, float))
        for g in gaps for k, v in g.items()
        if k != "value_available" and not isinstance(v, bool)
    )


# --------------------------------------------------------------------------- #
# Checksum manifest persistence
# --------------------------------------------------------------------------- #

def test_write_checksum_manifest_roundtrip(tmp_path):
    mapping = {"b_dataset": "bbb", "a_dataset": "aaa"}
    out = integrity.write_checksum_manifest(mapping, tmp_path / "sub" / "checksums.json")
    assert out.exists()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded == mapping
    # Keys are sorted on write for stable diffs.
    assert list(loaded.keys()) == ["a_dataset", "b_dataset"]
