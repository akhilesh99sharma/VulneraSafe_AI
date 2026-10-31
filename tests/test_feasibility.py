"""Tests for the multi-factor feasibility assessment (Task 2.7).

**Property 2: Feasibility classification matches factor conjunction**
**Validates: Requirements 3.5, 6.2, 6.3, 6.4**

The classification is defined as the conjunction of the *required* factors: a
pathogen is ``predictive`` iff every required factor passes, and
``non_predictive`` otherwise. These tests pin that definition (both directions),
the per-pathogen resolution selector against its recorded evidence rule, and the
invariant that factor values are recorded for every classification.

Unit tests use hand-built factor lists and synthetic modeling-unit panels so the
pure decision logic is verified independently of the (slow) real-data run. A
Hypothesis property test exercises the conjunction over randomised factor sets.
"""

from __future__ import annotations

import math

from hypothesis import given, settings
from hypothesis import strategies as st

from src.artifacts.schemas import FeasibilityFactor
from src.pipeline import feasibility as fz
from src.pipeline.feasibility import (
    MONTHLY_CELL_POS_MEDIAN_MIN,
    REQUIRED_FACTORS,
    THRESHOLDS,
    CellStats,
    ModelingUnitPanel,
    classify_from_factors,
    compute_factors,
    select_resolution,
)


# --------------------------------------------------------------------------- #
# Helpers to build factor lists / panels
# --------------------------------------------------------------------------- #

def _factor(name: str, passed: bool) -> FeasibilityFactor:
    thr = THRESHOLDS.get(name, 0.0)
    # value on the passing or failing side of the threshold
    value = thr if passed else thr - 1.0
    return FeasibilityFactor(name=name, value=float(value), threshold=float(thr), passed=bool(passed))


def _all_required(passed: bool) -> list[FeasibilityFactor]:
    factors = [_factor(n, passed) for n in REQUIRED_FACTORS]
    # add the deferred + informational factors that the real code always emits
    factors.append(FeasibilityFactor(name="calibration", value=float("nan"), threshold=float("nan"), passed=True))
    factors.append(FeasibilityFactor(name="prevalence", value=0.05, threshold=0.0, passed=True))
    return factors


def _panel(
    monthly_cells: dict[str, CellStats],
    quarterly_cells: dict[str, CellStats],
) -> ModelingUnitPanel:
    return ModelingUnitPanel(
        pathogen="Test",
        commodity="test",
        monthly_cells=monthly_cells,
        quarterly_cells=quarterly_cells,
        monthly_period_rates={},
        quarterly_period_rates={},
        monthly_periods_present=0,
        monthly_periods_in_range=0,
        quarterly_periods_present=0,
        quarterly_periods_in_range=0,
        active_regions=0,
        train_positives=0,
        test_positives=0,
        total_samples=0,
        total_positives=0,
    )


# --------------------------------------------------------------------------- #
# Property 2 — classification is the conjunction of required factors
# --------------------------------------------------------------------------- #

def test_all_required_passing_is_predictive():
    assert classify_from_factors(_all_required(True)) == "predictive"


def test_any_required_failing_is_non_predictive():
    for i in range(len(REQUIRED_FACTORS)):
        factors = _all_required(True)
        # flip exactly one required factor to failing
        name = REQUIRED_FACTORS[i]
        for f in factors:
            if f["name"] == name:
                f["passed"] = False
        assert classify_from_factors(factors) == "non_predictive", (
            f"failing required factor {name} must yield non_predictive"
        )


def test_missing_required_factor_is_non_predictive():
    # drop a required factor entirely -> cannot form the conjunction -> non_predictive
    factors = [f for f in _all_required(True) if f["name"] != "stability"]
    assert classify_from_factors(factors) == "non_predictive"


def test_non_required_factor_failing_does_not_demote():
    # a failing NON-required factor must not change a predictive verdict
    factors = _all_required(True)
    factors.append(FeasibilityFactor(name="extra_info", value=0.0, threshold=1.0, passed=False))
    assert classify_from_factors(factors) == "predictive"


@settings(max_examples=200, deadline=None)
@given(
    passed_flags=st.lists(
        st.booleans(), min_size=len(REQUIRED_FACTORS), max_size=len(REQUIRED_FACTORS)
    )
)
def test_classification_equals_conjunction(passed_flags):
    """classify == AND(required factors passed), for any combination."""
    factors = [_factor(n, p) for n, p in zip(REQUIRED_FACTORS, passed_flags)]
    factors.append(FeasibilityFactor(name="prevalence", value=0.05, threshold=0.0, passed=True))
    expected = "predictive" if all(passed_flags) else "non_predictive"
    assert classify_from_factors(factors) == expected


# --------------------------------------------------------------------------- #
# Factor values are recorded for every classification
# --------------------------------------------------------------------------- #

def test_factor_values_recorded_for_every_classification():
    # a dense panel -> whatever it classifies as, all six named factors exist
    monthly = {f"ST|2020-{m:02d}": CellStats(samples=10, positives=3) for m in range(1, 13)}
    quarterly = {f"ST|2020-Q{q}": CellStats(samples=30, positives=9) for q in range(1, 5)}
    panel = _panel(monthly, quarterly)
    panel["active_regions"] = 1
    panel["monthly_periods_present"] = 12
    panel["monthly_periods_in_range"] = 12
    panel["quarterly_periods_present"] = 4
    panel["quarterly_periods_in_range"] = 4
    panel["monthly_period_rates"] = {f"2020-{m:02d}": 0.3 for m in range(1, 13)}
    panel["quarterly_period_rates"] = {f"2020-Q{q}": 0.3 for q in range(1, 5)}
    panel["train_positives"] = 100
    panel["test_positives"] = 40
    panel["total_samples"] = 1000
    panel["total_positives"] = 300

    resolution, _ = select_resolution(panel)
    factors = compute_factors(panel, resolution)
    names = {f["name"] for f in factors}
    for required in REQUIRED_FACTORS:
        assert required in names, f"required factor {required} not recorded"
    assert "calibration" in names  # deferred factor always present
    # every factor carries a numeric value + threshold + bool passed
    for f in factors:
        assert isinstance(f["value"], float)
        assert isinstance(f["threshold"], float)
        assert isinstance(f["passed"], bool)


def test_calibration_is_deferred_not_fabricated():
    panel = _panel(
        {"ST|2020-01": CellStats(samples=5, positives=2)},
        {"ST|2020-Q1": CellStats(samples=5, positives=2)},
    )
    panel["monthly_period_rates"] = {"2020-01": 0.4}
    panel["quarterly_period_rates"] = {"2020-Q1": 0.4}
    factors = compute_factors(panel, "quarterly")
    calib = next(f for f in factors if f["name"] == "calibration")
    assert math.isnan(calib["value"]), "calibration value must be NaN (deferred, not fabricated)"
    assert calib["name"] not in REQUIRED_FACTORS, "calibration must not be a required factor"


# --------------------------------------------------------------------------- #
# Resolution selector follows the recorded evidence rule (Req 3.6)
# --------------------------------------------------------------------------- #

def test_selects_monthly_when_monthly_cells_dense():
    # monthly median positives per active cell >= MIN -> monthly
    monthly = {f"ST|2020-{m:02d}": CellStats(samples=10, positives=4) for m in range(1, 13)}
    quarterly = {f"ST|2020-Q{q}": CellStats(samples=30, positives=12) for q in range(1, 5)}
    panel = _panel(monthly, quarterly)
    resolution, evidence = select_resolution(panel)
    assert resolution == "monthly"
    assert "monthly=" in evidence and "quarterly=" in evidence
    assert f">= {MONTHLY_CELL_POS_MEDIAN_MIN:.2f}" in evidence


def test_selects_quarterly_when_monthly_cells_sparse():
    # monthly cells mostly zero positives -> monthly median < MIN -> quarterly
    monthly = {f"ST|2020-{m:02d}": CellStats(samples=4, positives=0) for m in range(1, 13)}
    # make quarterly cells carry the positives
    quarterly = {f"ST|2020-Q{q}": CellStats(samples=12, positives=3) for q in range(1, 5)}
    panel = _panel(monthly, quarterly)
    resolution, evidence = select_resolution(panel)
    assert resolution == "quarterly"
    assert "Selected: quarterly" in evidence


def test_resolution_evidence_reports_both_medians():
    monthly = {"ST|2020-01": CellStats(samples=2, positives=1)}
    quarterly = {"ST|2020-Q1": CellStats(samples=2, positives=1)}
    panel = _panel(monthly, quarterly)
    _resolution, evidence = select_resolution(panel)
    # evidence must record the medians that drove the decision
    assert "median positives per active cell" in evidence
