"""Tests for the dataset audit module (Task 2.4).

Covers both unit tests on small synthetic frames and a property test for the
positivity-rate / tri-state math.

* (a) property: positivity_rate == positives / denominator AND
      pos + neg + other == observations (Property 3, Req 3.1).
* (b) a known small synthetic frame audits to expected tri-state counts.
* (c) schema diff detects an added and a removed column.
* (d) the duplicate detector finds an injected duplicate.
* (e) an uncomputable field (missing publication date / result column) is
      marked incomplete, not fabricated (Req 3.2, 4.6).

Validates: Requirements 3.1, 3.2, 3.3, 3.4
"""

from __future__ import annotations

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from src.pipeline import audit


# --------------------------------------------------------------------------- #
# Shared builders
# --------------------------------------------------------------------------- #

def _frame(results: list[str], *, program: str = "raw_poultry_salmonella") -> pd.DataFrame:
    """Build a minimal but realistic FSIS-shaped frame with given result values."""
    n = len(results)
    return pd.DataFrame(
        {
            "sample_number": list(range(1, n + 1)),
            "establishment_id": [100 + (i % 3) for i in range(n)],
            "establishment_state": ["GA" if i % 2 else "TX" for i in range(n)],
            "project_code": ["HC01" if i % 2 else "HC02" for i in range(n)],
            "project_name": ["Program One" if i % 2 else "Program Two" for i in range(n)],
            "collection_date": [f"2023-0{(i % 9) + 1}-15" for i in range(n)],
            "product_type": ["chicken" for _ in range(n)],
            "salmonella_sp_analysis": results,
        }
    )


_PATHOGEN_META = audit.PROGRAM_META["raw_poultry_salmonella"]


def _audit(df: pd.DataFrame, **kw):
    return audit.audit_dataframe(
        df,
        program="raw_poultry_salmonella",
        pathogen=_PATHOGEN_META["pathogen"],
        commodity=_PATHOGEN_META["commodity"],
        result_column=_PATHOGEN_META["result_column"],
        **kw,
    )


# --------------------------------------------------------------------------- #
# (a) Property: positivity math + tri-state partition (Property 3, Req 3.1)
# --------------------------------------------------------------------------- #

_RESULT_VALUES = st.sampled_from(
    [
        "Positive",
        "Negative",
        "Confirmed Negative of a Previous Presumptive",
        "NULL",
        "",
        "26 Lab closed",
        None,
    ]
)


@settings(max_examples=200, deadline=None)
@given(results=st.lists(_RESULT_VALUES, min_size=1, max_size=60))
def test_positivity_math_and_tristate_partition(results):
    """pos+neg+other == observations and positivity == pos/denominator."""
    report = _audit(_frame(results))

    obs = report["observation_count"]
    pos = report["positive_count"]
    neg = report["negative_count"]
    other = report["other_count"]

    # tri-state partition: the three buckets exactly cover every observation.
    assert pos + neg + other == obs

    denom = report["program_denominator"]
    assert denom == pos + neg

    if denom == 0:
        assert report["positivity_rate"] is None
    else:
        assert abs(report["positivity_rate"] - pos / denom) < 1e-12
        # positivity is a proper fraction in [0, 1].
        assert 0.0 <= report["positivity_rate"] <= 1.0

    # per-program breakdown never silently pools: sums match the totals.
    assert sum(p["positives"] for p in report["positivity_by_program"]) == pos
    assert sum(p["negatives"] for p in report["positivity_by_program"]) == neg
    assert sum(p["observations"] for p in report["positivity_by_program"]) == obs


# --------------------------------------------------------------------------- #
# (b) Known small frame -> expected tri-state counts
# --------------------------------------------------------------------------- #

def test_known_frame_tristate_counts():
    """A hand-counted frame audits to exactly the expected tri-state counts."""
    results = [
        "Positive",
        "Positive",
        "Negative",
        "Negative",
        "Negative",
        "Confirmed Negative of a Previous Presumptive",  # negative
        "NULL",      # other
        "",          # other
        "26 Lab closed",  # other
    ]
    report = _audit(_frame(results))

    assert report["observation_count"] == 9
    assert report["positive_count"] == 2
    assert report["negative_count"] == 4  # 3 Negative + 1 confirmed-negative
    assert report["other_count"] == 3
    assert report["program_denominator"] == 6
    assert abs(report["positivity_rate"] - 2 / 6) < 1e-12
    # vocabulary detection picked up the real labels present.
    assert "Positive" in report["positive_labels"]
    assert "Negative" in report["negative_labels"]


# --------------------------------------------------------------------------- #
# (c) Schema diff detects added / removed columns
# --------------------------------------------------------------------------- #

def test_schema_diff_detects_added_and_removed_column():
    fy_schemas = {
        2014: {"a": "str", "b": "int64", "c": "str"},
        2015: {"a": "str", "b": "str", "d": "str"},  # +d, -c, b dtype changed
    }
    changes = audit.diff_schemas(fy_schemas)

    # baseline (first FY) + the 2014->2015 diff.
    by_to = {c["to_fy"]: c for c in changes}
    assert 2015 in by_to
    diff = by_to[2015]
    assert diff["from_fy"] == 2014
    assert "d" in diff["added_columns"]
    assert "c" in diff["removed_columns"]
    assert any("b:" in dc for dc in diff["dtype_changes"])


def test_schema_diff_no_change_when_stable():
    fy_schemas = {
        2014: {"a": "str", "b": "int64"},
        2015: {"a": "str", "b": "int64"},
    }
    changes = audit.diff_schemas(fy_schemas)
    # only the baseline entry; the second FY is identical so no diff emitted.
    assert [c["to_fy"] for c in changes] == [2014]


# --------------------------------------------------------------------------- #
# (d) Duplicate detector finds an injected duplicate
# --------------------------------------------------------------------------- #

def test_duplicate_detector_finds_injected_duplicate():
    df = _frame(["Positive", "Negative", "Negative"])
    # inject an exact duplicate of the first row.
    dup = pd.concat([df, df.iloc[[0]]], ignore_index=True)
    report = _audit(dup)

    assert report["duplicates"]["exact_duplicate_rows"] >= 1
    # the duplicated sample_number is also flagged.
    assert report["duplicates"]["duplicate_sample_numbers"] >= 1
    # likely-duplicate records key is populated and finds the repeat.
    assert report["duplicates"]["likely_duplicate_records"] >= 1


# --------------------------------------------------------------------------- #
# (e) Uncomputable field -> marked incomplete, not fabricated (Req 3.2, 4.6)
# --------------------------------------------------------------------------- #

def test_missing_publication_date_marks_incomplete_not_fabricated():
    report = _audit(_frame(["Positive", "Negative"]))
    # FSIS files carry no publication date: delay must be None (never invented).
    assert report["publication_date"] is None
    assert report["reporting_delay_days"] is None
    assert report["complete"] is False
    gap_fields = {g["field"] for g in report["gaps"]}
    assert "publication_date" in gap_fields
    assert "reporting_delay_days" in gap_fields


def test_missing_result_column_marks_incomplete():
    df = _frame(["Positive", "Negative"]).drop(columns=["salmonella_sp_analysis"])
    report = _audit(df)
    assert report["complete"] is False
    assert report["positivity_rate"] is None
    gap_fields = {g["field"] for g in report["gaps"]}
    assert "salmonella_sp_analysis" in gap_fields


def test_provided_publication_date_computes_delay():
    # When a publication date IS supplied, the delay is computed (not None).
    report = _audit(
        _frame(["Positive", "Negative", "Negative"]),
        publication_date="2023-12-31",
    )
    assert report["publication_date"] == "2023-12-31"
    assert report["reporting_delay_days"] is not None
    assert isinstance(report["reporting_delay_days"], int)
