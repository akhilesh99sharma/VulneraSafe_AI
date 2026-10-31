"""Tests for responsible-interpretation guardrails (Task 7.1).

Covers the four public surfaces of ``src.responsible``:

* ``withhold_unsupported_model_recommendation`` — withholds a MODEL rec lacking
  uncertainty OR evidence (attaching an explanatory indicator) and NEVER
  withholds a REGULATORY alert (Req 16.5, 16.6).
* ``label_performance`` — tags historical/prospective and clamps a reported
  benefit to the evaluation value (Req 16.7, 16.8).
* ``DISCLAIMERS`` — the responsible-use copy (Req 16.1, 16.2, 16.3).
* ``equity_disparity`` — the documented equity metric with pass band (Req 16.8).

Validates: Requirements 16.1, 16.2, 16.3, 16.4, 16.5, 16.6, 16.7, 16.8
"""

from __future__ import annotations

import math

import pytest

from src import responsible


def _model_rec(**overrides) -> dict:
    base = {
        "action": "Prioritize inspection of lot L1",
        "target_id": "L1",
        "rationale": "Elevated predicted Salmonella positivity.",
        "constraints": ["Never distribute a confirmed-recall lot"],
        "human_review_required": True,
        "evidence_refs": ["FSIS lab sampling FY2024"],
        "uncertainty": 0.12,
        "alert_source": "MODEL",
        "status": "PREDICTED",
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------- #
# Req 16.5, 16.6 — withholding
# --------------------------------------------------------------------------- #

def test_model_rec_with_uncertainty_and_evidence_is_returned():
    rec = _model_rec()
    result = responsible.withhold_unsupported_model_recommendation(rec)
    assert result is rec
    assert "withheld" not in rec


def test_model_rec_without_uncertainty_is_withheld():
    rec = _model_rec(uncertainty=None)
    result = responsible.withhold_unsupported_model_recommendation(rec)
    assert result is None
    assert rec["withheld"] is True
    assert "uncertainty" in rec["withheld_missing"]
    assert rec["withheld_reason"] == responsible.WITHHELD_INDICATOR


def test_model_rec_with_nan_uncertainty_is_withheld():
    rec = _model_rec(uncertainty=float("nan"))
    assert responsible.withhold_unsupported_model_recommendation(rec) is None
    assert "uncertainty" in rec["withheld_missing"]


def test_model_rec_without_evidence_is_withheld():
    rec = _model_rec(evidence_refs=[])
    result = responsible.withhold_unsupported_model_recommendation(rec)
    assert result is None
    assert "evidence" in rec["withheld_missing"]


def test_model_rec_with_blank_evidence_is_withheld():
    rec = _model_rec(evidence_refs=["", "   "])
    assert responsible.withhold_unsupported_model_recommendation(rec) is None


def test_model_rec_missing_both_lists_both():
    rec = _model_rec(uncertainty=None, evidence_refs=[])
    assert responsible.withhold_unsupported_model_recommendation(rec) is None
    assert set(rec["withheld_missing"]) == {"uncertainty", "evidence"}


def test_regulatory_alert_never_withheld_even_without_uncertainty():
    # A REGULATORY alert with no uncertainty and no evidence is still returned
    # unchanged — the regulatory track is independent of model uncertainty.
    rec = _model_rec(
        alert_source="REGULATORY", uncertainty=None, evidence_refs=[], status="OBSERVED"
    )
    result = responsible.withhold_unsupported_model_recommendation(rec)
    assert result is rec
    assert "withheld" not in rec


# --------------------------------------------------------------------------- #
# Req 16.7, 16.8 — performance labeling + clamping
# --------------------------------------------------------------------------- #

def test_label_performance_tags_kind():
    hist = responsible.label_performance(0.7, "historical")
    pros = responsible.label_performance(0.6, "prospective")
    assert hist["kind"] == "historical"
    assert pros["kind"] == "prospective"
    assert hist["clamped"] is False
    assert hist["evaluated_value"] is None


def test_label_performance_clamps_benefit_above_evaluated():
    res = responsible.label_performance(0.95, "prospective", evaluated_value=0.80)
    assert res["value"] == pytest.approx(0.80)
    assert res["clamped"] is True
    assert res["evaluated_value"] == pytest.approx(0.80)


def test_label_performance_does_not_change_value_within_eval():
    res = responsible.label_performance(0.70, "historical", evaluated_value=0.80)
    assert res["value"] == pytest.approx(0.70)
    assert res["clamped"] is False


def test_label_performance_equal_to_eval_not_clamped():
    res = responsible.label_performance(0.80, "prospective", evaluated_value=0.80)
    assert res["value"] == pytest.approx(0.80)
    assert res["clamped"] is False


def test_label_performance_rejects_bad_kind():
    with pytest.raises(ValueError):
        responsible.label_performance(0.5, "future")  # type: ignore[arg-type]


def test_label_performance_rejects_nan():
    with pytest.raises(ValueError):
        responsible.label_performance(float("nan"), "historical")


# --------------------------------------------------------------------------- #
# Req 16.1, 16.2, 16.3 — disclaimers
# --------------------------------------------------------------------------- #

def test_disclaimers_present_and_nonempty():
    required = {
        "decision_support",
        "no_contamination_from_model",
        "no_safe_unsafe_from_risk",
        "no_causal_outbreak_from_similarity",
        "no_individual_medical_status",
    }
    assert required.issubset(responsible.DISCLAIMERS.keys())
    for key in required:
        assert responsible.DISCLAIMERS[key].strip()


def test_disclaimer_decision_support_denies_determination():
    text = responsible.DISCLAIMERS["decision_support"].lower()
    assert "decision support" in text
    assert "regulatory determination" in text
    assert "outbreak declaration" in text


def test_disclaimer_denies_contamination_and_safety_claims():
    assert "contamination" in responsible.DISCLAIMERS["no_contamination_from_model"].lower()
    assert "safe" in responsible.DISCLAIMERS["no_safe_unsafe_from_risk"].lower()


# --------------------------------------------------------------------------- #
# Req 16.8 — equity disparity metric
# --------------------------------------------------------------------------- #

def test_equity_parity_passes():
    res = responsible.equity_disparity(1.0, 1.0)
    assert res["ratio"] == pytest.approx(1.0)
    assert res["passed"] is True
    assert res["disparity"] == pytest.approx(0.0)


def test_equity_within_band_passes():
    res = responsible.equity_disparity(0.9, 1.0)
    assert res["passed"] is True


def test_equity_below_band_fails():
    res = responsible.equity_disparity(0.5, 1.0)
    assert res["ratio"] == pytest.approx(0.5)
    assert res["passed"] is False
    assert res["disparity"] == pytest.approx(-0.5)


def test_equity_above_band_fails():
    res = responsible.equity_disparity(2.0, 1.0)
    assert res["passed"] is False
    assert res["disparity"] == pytest.approx(1.0)


def test_equity_boundaries_inclusive():
    assert responsible.equity_disparity(0.8, 1.0)["passed"] is True
    assert responsible.equity_disparity(1.25, 1.0)["passed"] is True


def test_equity_zero_other_rate_is_infinite_and_fails():
    res = responsible.equity_disparity(0.5, 0.0)
    assert math.isinf(res["ratio"])
    assert res["passed"] is False


def test_equity_rejects_negative_rate():
    with pytest.raises(ValueError):
        responsible.equity_disparity(-0.1, 1.0)
