"""Tests for harmonization into analytic tables (Task 2.9).

Covers the four invariants required by the task:

(a) the reconciled 'other' categories sum to the audit ``other_count`` per
    pathogen (Req 1.3, 2.8);
(b) :func:`available_as_of` never returns a row whose
    ``collection_date + lag > cutoff`` (Req 1.5);
(c) program tagging leaves no observed project code untagged (Req 2.6, 2.7);
(d) the harmonized join keys are unique per
    ``(pathogen, scope, state, period)`` — with ``scope`` the sampling_program —
    and every row carries ``collection_date`` / ``availability_date`` / ``lag``
    (Req 1.1, 2.7).

Unit tests use small synthetic frames so the pure logic is verified fast and
independently of the (slow) real-data run; a couple of lightweight data-backed
checks run against the already-emitted audit report when it is present.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.pipeline import harmonize as hz
from src.pipeline.harmonize import (
    DECISION_ELEMENTS,
    PROGRAM_CATEGORIES,
    REPORTING_LAG_DAYS,
    TARGET_CATEGORY,
    DecisionStatementError,
    add_availability_columns,
    available_as_of,
    build_decision_statement,
    build_program_taxonomy,
    reconcile_other,
    state_from_fips,
    tag_program,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
INTERIM = REPO_ROOT / "data" / "interim"


# --------------------------------------------------------------------------- #
# (c) program tagging leaves no code untagged
# --------------------------------------------------------------------------- #

def test_tag_program_always_returns_a_known_category():
    """Every input — including junk — maps to one of the five categories."""
    samples = [
        ("HC_CPT_LBW01", "Sampling for Chicken Parts"),
        ("RTEPROD_RAND", "RTEPROD Sampling - Random RTE Products"),
        ("MT43", "Risk-based Sampling of Raw Ground Beef"),
        ("F_CH_CARC01", "Follow-up sampling of Chicken Carcasses"),
        ("EXP_CH_MSK01", "Exploratory Sampling for Mechanically Separated Chicken"),
        ("NRTE_EXP_CH", "NRTE Exploratory Sampling - Chickens"),
        ("INTCONT_LM_E", "For-Cause Sampling-Eastern Lab-Listeria"),
        ("RLMCONT", "LM Risk-based Verification Testing Program"),
        ("SPECPGM_02", "Intensifed Sampling - S. Heidelberg"),
        ("INTENV_SA_E", "For-Cause Sampling-Eastern Lab-Salmonella"),
        ("MT52_C", "Follow-up Sampling of Suppliers with Cloth"),
        ("", ""),
        ("ZZZ_UNKNOWN", "mystery program"),
    ]
    for code, name in samples:
        cat = tag_program(code, name)
        assert cat in PROGRAM_CATEGORIES


def test_tag_program_semantics():
    """Spot-check that the obvious codes land in the obvious categories."""
    assert tag_program("HC_CH_CARC01", "HACCP Verification") == "routine_surveillance"
    assert tag_program("RTEPROD_RAND", "Random RTE") == "routine_surveillance"
    assert tag_program("MT43", "Risk-based Sampling of Raw Ground Beef") == "routine_surveillance"
    assert tag_program("F_CPT_LBW01", "Follow-up sampling") == "follow_up"
    assert tag_program("MT53", "Follow-up Sampling") == "follow_up"
    assert tag_program("EXP_CPT_OT01", "Exploratory Sampling") == "exploratory"
    assert tag_program("NRTE_EXP_TU", "Exploratory Sampling - Turkeys") == "exploratory"
    assert tag_program("INTCONT_LM_E", "For-Cause") == "for_cause"
    assert tag_program("RLMENVC", "Risk-based Testing-Environmental") == "for_cause"
    assert tag_program("SPECPGM_06", "Stuffed Chicken Outbreak Sampling") == "special"


@pytest.mark.skipif(
    not (INTERIM / "audit_report.json").exists(),
    reason="audit_report.json not present",
)
def test_build_program_taxonomy_leaves_nothing_untagged():
    """Every observed project code in the real audit report is tagged (Req 2.7)."""
    out = INTERIM / "program_taxonomy.json"
    result = build_program_taxonomy(out_json=out)
    assert result["untagged"] == []
    assert result["total_codes_tagged"] > 0
    for tag in result["tags"]:
        assert tag["category"] in PROGRAM_CATEGORIES
    assert TARGET_CATEGORY in result["categories"]


# --------------------------------------------------------------------------- #
# (a) reconciled other-categories sum to audit other_count per pathogen
# --------------------------------------------------------------------------- #

@pytest.mark.skipif(
    not (INTERIM / "audit_report.json").exists(),
    reason="audit_report.json not present",
)
def test_reconcile_other_sums_to_audit_other_count():
    """Per-pathogen reconciled category counts equal the audit other_count."""
    audit_report = json.loads(
        (INTERIM / "audit_report.json").read_text(encoding="utf-8")
    )
    result = reconcile_other(audit_report=audit_report)
    assert result["all_reconcile"] is True
    for pathogen, entry in result["per_pathogen"].items():
        cat_sum = sum(c["count"] for c in entry["categories"].values())
        assert cat_sum == entry["audit_other_count"], (
            f"{pathogen}: categories sum {cat_sum} != "
            f"audit other_count {entry['audit_other_count']}"
        )
        assert entry["reconciled_total"] == entry["audit_other_count"]
        # every other-category is excluded from modeling labels
        assert entry["excluded_from_modeling_labels"] == entry["audit_other_count"]


@pytest.mark.skipif(
    not (INTERIM / "audit_report.json").exists(),
    reason="audit_report.json not present",
)
def test_reconcile_other_listeria_has_salmonella_only_programs():
    """The Lm panel reconciliation names the Salmonella-only INT*_SA_* programs."""
    result = reconcile_other()
    listeria = result["per_pathogen"]["Listeria"]
    assert "salmonella_only_program" in listeria["categories"], (
        "expected an INT*_SA_* Salmonella-only category in the Lm 'other' bucket"
    )
    assert listeria["categories"]["salmonella_only_program"]["count"] > 0


# --------------------------------------------------------------------------- #
# (b) available_as_of never returns a post-cutoff row
# --------------------------------------------------------------------------- #

def _availability_frame(dates: list[str], lag: int) -> pd.DataFrame:
    df = pd.DataFrame({"collection_date": dates})
    return add_availability_columns(df, lag_days=lag)


def test_add_availability_columns_math():
    df = _availability_frame(["2023-01-01", "2023-06-15"], lag=30)
    assert (df["lag_days"] == 30).all()
    assert df["availability_date"].iloc[0] == pd.Timestamp("2023-01-31")
    assert df["availability_date"].iloc[1] == pd.Timestamp("2023-07-15")


def test_available_as_of_excludes_post_cutoff_rows():
    df = _availability_frame(
        ["2023-01-01", "2023-02-01", "2023-03-01", "2023-04-01"], lag=30
    )
    cutoff = pd.Timestamp("2023-03-15")
    out = available_as_of(df, cutoff)
    # invariant: no returned row has collection_date + lag > cutoff
    for _, row in out.iterrows():
        assert row["collection_date"] + pd.Timedelta(days=30) <= cutoff
    # the Jan and Feb samples (available 01-31, 03-03) are in; Mar/Apr are out
    assert len(out) == 2


@settings(max_examples=200, deadline=None)
@given(
    base_days=st.lists(st.integers(min_value=0, max_value=4000), min_size=1, max_size=40),
    lag=st.integers(min_value=0, max_value=120),
    cutoff_days=st.integers(min_value=0, max_value=4200),
)
def test_available_as_of_invariant_property(base_days, lag, cutoff_days):
    """Property: every returned row satisfies collection_date + lag <= cutoff."""
    epoch = pd.Timestamp("2015-01-01")
    dates = [(epoch + pd.Timedelta(days=d)).date().isoformat() for d in base_days]
    df = _availability_frame(dates, lag=lag)
    cutoff = epoch + pd.Timedelta(days=cutoff_days)
    out = available_as_of(df, cutoff)
    lag_td = pd.Timedelta(days=lag)
    for _, row in out.iterrows():
        assert row["collection_date"] + lag_td <= cutoff
    # completeness: a row strictly satisfying the predicate is never dropped
    expected = sum(
        1 for d in base_days
        if (epoch + pd.Timedelta(days=d)) + lag_td <= cutoff
    )
    assert len(out) == expected


# --------------------------------------------------------------------------- #
# (d) harmonized join keys unique + carry availability columns
# --------------------------------------------------------------------------- #

def _fake_program_frame() -> pd.DataFrame:
    """A tiny FSIS-shaped frame with two states, two periods, two programs."""
    return pd.DataFrame({
        "establishment_state": ["NY", "NY", "NY", "TX", "TX", "NY"],
        "collection_date": [
            "2023-01-05", "2023-01-20", "2023-02-10",
            "2023-01-15", "2023-01-16", "2023-01-07",
        ],
        "project_code": [
            "HC_CH_CARC01", "HC_CH_CARC01", "HC_CH_CARC01",
            "F_CH_CARC01", "F_CH_CARC01", "EXP_CH_MSK01",
        ],
        "project_name": [
            "HACCP Verification", "HACCP Verification", "HACCP Verification",
            "Follow-up sampling", "Follow-up sampling", "Exploratory Sampling",
        ],
        "salmonella_sp_analysis": [
            "Positive", "Negative", "Negative", "Positive", "Negative", "NULL",
        ],
    })


def test_harmonize_pathogen_keys_unique_and_carry_availability(monkeypatch):
    """Harmonized rows are unique per (pathogen, program, state, period) and
    every row carries collection_date / availability_date / lag_days."""
    fake = _fake_program_frame()
    monkeypatch.setattr(hz.audit, "_load_program_frame", lambda *a, **k: (fake, {}))

    table = hz.harmonize_pathogen("Salmonella", "monthly")
    assert not table.empty

    # (d) uniqueness on the modeling-unit key incl. sampling_program (scope)
    key = ["pathogen", "sampling_program", "state", "period"]
    assert not table.duplicated(subset=key).any()

    # availability columns present on every row
    for col in ("collection_date", "availability_date", "lag_days"):
        assert col in table.columns
        assert table[col].notna().all()
    assert (table["lag_days"] == REPORTING_LAG_DAYS).all()

    # availability = collection + lag on every row
    for _, row in table.iterrows():
        assert row["availability_date"] == row["collection_date"] + pd.Timedelta(
            days=REPORTING_LAG_DAYS
        )

    # the "NULL" salmonella result (other) is excluded from labels
    # NY 2023-01 routine has 2 samples (pos+neg); the exploratory NULL dropped
    routine_ny_jan = table[
        (table["state"] == "NY")
        & (table["period"] == "2023-01")
        & (table["sampling_program"] == "HC_CH_CARC01")
    ]
    assert routine_ny_jan["samples"].iloc[0] == 2
    assert routine_ny_jan["positives"].iloc[0] == 1

    # (2) routine-only target flag never set for for-cause/exploratory rows
    assert table.loc[table["program_category"] != TARGET_CATEGORY, "is_target"].eq(
        False
    ).all()
    assert table.loc[table["program_category"] == TARGET_CATEGORY, "is_target"].eq(
        True
    ).all()


def test_harmonize_pathogen_target_is_routine_only(monkeypatch):
    """Only routine_surveillance rows feed the target baseline (Req 2.6)."""
    fake = _fake_program_frame()
    monkeypatch.setattr(hz.audit, "_load_program_frame", lambda *a, **k: (fake, {}))
    table = hz.harmonize_pathogen("Salmonella", "monthly")
    target = table[table["is_target"]]
    assert (target["program_category"] == TARGET_CATEGORY).all()
    # the follow-up + exploratory programs exist but are not targets
    assert set(table["program_category"]) >= {"routine_surveillance", "follow_up"}


# --------------------------------------------------------------------------- #
# decision statement (Req 1.2) + FIPS crosswalk
# --------------------------------------------------------------------------- #

def test_decision_statement_valid(tmp_path):
    out = tmp_path / "decision_statement.json"
    statement = build_decision_statement(out_json=out)
    assert statement["_valid"] is True
    for element in DECISION_ELEMENTS:
        assert str(statement[element]).strip()
    assert out.exists()


def test_decision_statement_rejects_missing_element(tmp_path):
    out = tmp_path / "decision_statement.json"
    with pytest.raises(DecisionStatementError):
        build_decision_statement({"horizon": ""}, out_json=out)


def test_state_from_fips_crosswalk():
    assert state_from_fips("36") == "NY"      # 2-digit state FIPS
    assert state_from_fips("36007") == "NY"   # county FIPS
    assert state_from_fips("48") == "TX"
    assert state_from_fips("1") == "AL"       # zero-pads short codes
    assert state_from_fips("") is None
    assert state_from_fips(None) is None
