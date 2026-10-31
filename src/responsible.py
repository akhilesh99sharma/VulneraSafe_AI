"""Responsible-interpretation guardrails for the analysis/decision layer.

Task 7.1 — enforce the responsible-use constraints (design.md
"Responsible-Use and Guardrails") in the Python layer so that the exported
artifacts can never carry an unsupported model claim. The web layer mirrors
these same rules so a withheld recommendation is never rendered.

What this module enforces:

* ``withhold_unsupported_model_recommendation`` — a MODEL-sourced
  recommendation lacking a quantified uncertainty OR supporting evidence is
  withheld (returns ``None``) with an explanatory indicator attached; a
  REGULATORY-sourced alert is NEVER withheld (Req 16.5, 16.6).
* ``label_performance`` — tags each reported performance measure as
  ``historical`` or ``prospective`` and clamps a reported benefit so it never
  exceeds the value computed on the evaluation data (Req 16.7/16.8).
* ``DISCLAIMERS`` — the responsible-use copy asserting decision support, not a
  regulatory determination or outbreak declaration (Req 16.1, 16.2, 16.3).
* ``equity_disparity`` — the documented equity metric: a pass iff the
  high-need-vs-other rate ratio sits inside ``[lo, hi]`` (Req 16.8/16.9).

Validates: Requirements 16.1, 16.2, 16.3, 16.4, 16.5, 16.6, 16.7, 16.8
"""

from __future__ import annotations

import math
from typing import Literal, Optional, TypedDict


# --------------------------------------------------------------------------- #
# Req 16.1, 16.2, 16.3, 16.7 — responsible-use copy
# --------------------------------------------------------------------------- #

#: Responsible-use disclaimer text, keyed by constraint. These strings are the
#: single source of truth for the copy shown in the web layer's responsible-use
#: banner and panel labels. Each asserts a specific thing the system must never
#: claim (Req 16.1-16.3, 16.7).
DISCLAIMERS: dict[str, str] = {
    "decision_support": (
        "VulneraSafe AI is decision support only. It is not a regulatory "
        "determination, an outbreak declaration, or a substitute for "
        "epidemiologic investigation. Consequential actions require human "
        "review."
    ),
    "no_contamination_from_model": (
        "A model alert does not establish contamination. Contamination is "
        "confirmed only by laboratory testing and official regulatory action, "
        "never by a predicted risk alone."
    ),
    "no_safe_unsafe_from_risk": (
        "Predicted risk never declares a product safe or unsafe. A low "
        "predicted risk is not a safety clearance and a high predicted risk is "
        "not a finding of contamination."
    ),
    "no_causal_outbreak_from_similarity": (
        "Genomic or temporal similarity alone does not establish a causal "
        "outbreak linkage. Causal attribution requires epidemiologic "
        "investigation."
    ),
    "no_individual_medical_status": (
        "Regional demographics describe populations, not individuals. The "
        "system never infers any individual's medical status from regional "
        "demographic data."
    ),
    "performance_scope": (
        "Each reported performance measure is labeled historical or "
        "prospective. A reported benefit never exceeds the value measured on "
        "the evaluation data."
    ),
}


# --------------------------------------------------------------------------- #
# Req 16.5, 16.6 — withhold unsupported MODEL recommendations
# --------------------------------------------------------------------------- #

#: Explanatory indicator attached to a withheld MODEL recommendation so the
#: reason is auditable and the web layer can surface it verbatim.
WITHHELD_INDICATOR: str = (
    "Withheld — insufficient evidence/uncertainty: this model-generated "
    "recommendation cannot be shown because required supporting evidence or a "
    "quantified uncertainty measure is unavailable."
)


def _has_quantified_uncertainty(value: object) -> bool:
    """True iff ``value`` is a usable, finite numeric uncertainty measure.

    ``None`` (not applicable / unavailable) and NaN are both treated as
    "no quantified uncertainty".
    """
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return not math.isnan(float(value))
    return False


def _has_supporting_evidence(rec: dict) -> bool:
    """True iff the recommendation carries at least one evidence reference."""
    refs = rec.get("evidence_refs")
    if not isinstance(refs, (list, tuple)):
        return False
    return any(str(r).strip() for r in refs)


def withhold_unsupported_model_recommendation(
    rec: dict,
) -> Optional[dict]:
    """Withhold a MODEL recommendation that lacks uncertainty or evidence.

    Rules (Req 16.5, 16.6):

    * A REGULATORY-sourced alert (``alert_source == "REGULATORY"``) is ALWAYS
      returned unchanged — it flows on the independent regulatory-evidence
      track and is never suppressed by a missing model uncertainty.
    * A MODEL-sourced recommendation lacking a quantified uncertainty measure
      OR supporting evidence is withheld: this returns ``None`` and attaches an
      explanatory ``withheld`` indicator to the passed-in dict (mutated in
      place and also returned via the dict) so the caller/exporter can record
      WHY it was dropped.
    * A MODEL-sourced recommendation that has both uncertainty and evidence is
      returned unchanged.

    Returning ``None`` is the withhold signal: the exporter drops the record so
    the web layer never renders it.
    """
    source = rec.get("alert_source")

    # Regulatory evidence is never withheld (Req 16.6).
    if source == "REGULATORY":
        return rec

    has_uncertainty = _has_quantified_uncertainty(rec.get("uncertainty"))
    has_evidence = _has_supporting_evidence(rec)

    if has_uncertainty and has_evidence:
        return rec

    # Withhold: annotate the reason for the audit trail, then signal with None.
    missing: list[str] = []
    if not has_uncertainty:
        missing.append("uncertainty")
    if not has_evidence:
        missing.append("evidence")
    rec["withheld"] = True
    rec["withheld_reason"] = WITHHELD_INDICATOR
    rec["withheld_missing"] = missing
    return None


# --------------------------------------------------------------------------- #
# Req 16.7, 16.8 — historical vs prospective performance labeling
# --------------------------------------------------------------------------- #

class PerformanceLabel(TypedDict):
    """A tagged performance measure (Req 16.8).

    ``kind`` labels the measure historical or prospective. ``value`` is the
    reported benefit after clamping so it never exceeds ``evaluated_value``
    (the value computed on the evaluation data) when one is supplied.
    ``clamped`` records whether the reported value was reduced.
    """

    value: float
    kind: Literal["historical", "prospective"]
    evaluated_value: Optional[float]
    clamped: bool


def label_performance(
    value: float,
    kind: Literal["historical", "prospective"],
    evaluated_value: Optional[float] = None,
) -> PerformanceLabel:
    """Return a tagged performance measure, clamping an over-reported benefit.

    A reported benefit must never exceed the value computed on the evaluation
    data (Req 16.8). When ``evaluated_value`` is provided and ``value`` exceeds
    it, the reported value is clamped down to ``evaluated_value`` and the result
    is flagged ``clamped``. When no evaluation value is supplied, the value is
    returned as given.

    Raises:
        ValueError: if ``kind`` is not ``"historical"`` or ``"prospective"``,
            or if ``value`` / ``evaluated_value`` is NaN.
    """
    if kind not in ("historical", "prospective"):
        raise ValueError(
            f"kind must be 'historical' or 'prospective', got {kind!r}"
        )
    if value is None or (isinstance(value, float) and math.isnan(value)):
        raise ValueError("value must be a finite number")
    if evaluated_value is not None and (
        isinstance(evaluated_value, float) and math.isnan(evaluated_value)
    ):
        raise ValueError("evaluated_value must be a finite number or None")

    reported = float(value)
    clamped = False
    if evaluated_value is not None and reported > float(evaluated_value):
        reported = float(evaluated_value)
        clamped = True

    return PerformanceLabel(
        value=reported,
        kind=kind,
        evaluated_value=(
            None if evaluated_value is None else float(evaluated_value)
        ),
        clamped=clamped,
    )


# --------------------------------------------------------------------------- #
# Req 16.8 (16.9) — equity disparity metric
# --------------------------------------------------------------------------- #

class EquityDisparity(TypedDict):
    """Result of the equity disparity test (documented metric).

    ``ratio`` is the high-need rate divided by the other-population rate.
    ``passed`` is true iff the ratio sits inside the acceptable band
    ``[lo, hi]`` — i.e. recommendations do not systematically disadvantage a
    High_Need_Community. ``disparity`` is the signed distance of the ratio from
    parity (``ratio - 1.0``).
    """

    ratio: float
    passed: bool
    disparity: float


def equity_disparity(
    rate_high_need: float,
    rate_other: float,
    lo: float = 0.8,
    hi: float = 1.25,
) -> EquityDisparity:
    """Compute the high-need-vs-other service rate ratio and pass/fail.

    Metric definition (Req 16.8/16.9): ``ratio = rate_high_need / rate_other``.
    The test ``passed`` iff ``lo <= ratio <= hi``; the default band
    ``[0.8, 1.25]`` is the standard four-fifths / inverse four-fifths rule, so
    a High_Need_Community receiving substantially less service (ratio < 0.8) or
    substantially disproportionate burden (ratio > 1.25) fails. ``disparity``
    reports the signed gap from parity (``ratio - 1``), which is 0 at parity.

    When the comparison rate is zero the ratio is undefined; it is reported as
    ``inf`` and the test fails, since a defined disparity cannot be established.

    Raises:
        ValueError: on a negative rate or a NaN input.
    """
    for name, r in (("rate_high_need", rate_high_need), ("rate_other", rate_other)):
        if r is None or (isinstance(r, float) and math.isnan(r)):
            raise ValueError(f"{name} must be a finite number")
        if r < 0:
            raise ValueError(f"{name} must be non-negative, got {r}")

    if rate_other == 0:
        ratio = math.inf
        passed = False
        disparity = math.inf
    else:
        ratio = float(rate_high_need) / float(rate_other)
        passed = lo <= ratio <= hi
        disparity = ratio - 1.0

    return EquityDisparity(ratio=ratio, passed=passed, disparity=disparity)
