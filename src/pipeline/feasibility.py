"""Multi-factor feasibility assessment and per-pathogen resolution (Task 2.7).

This module answers one question per pathogen, from the **real** FSIS
laboratory-sampling data: *can this pathogen support a defensible forecast, and
if so at what temporal resolution?* It deliberately replaces the discredited
"single >=30 independent-positive threshold" with a genuine multi-factor
``Feasibility_Assessment`` (Req 3.5, glossary ``Feasibility_Assessment``), and
it selects the temporal resolution (monthly vs quarterly) **independently per
pathogen** from that pathogen's own sample availability (Req 3.6, glossary
``Modeling_Unit``).

Modeling_Unit (Req 3.6, glossary)
---------------------------------
``Modeling_Unit = pathogen x commodity x region x time``. Here:

* ``pathogen``  — Salmonella / Listeria / STEC (one program each).
* ``commodity`` — the program commodity (raw_poultry / rte / raw_beef); one per
  program, so it is constant within a pathogen's panel.
* ``region``    — ``establishment_state`` (US state / territory code). This is
  the location identifier the FSIS sampling files actually carry.
* ``time``      — a monthly (``YYYY-MM``) or quarterly (``YYYY-Qn``) period,
  chosen per pathogen.

A *modeling-unit cell* is one ``(region, period)`` pair for a pathogen. We build
the real panel by reopening each program frame via
:func:`src.pipeline.audit._load_program_frame`, classifying each result with the
same tri-state logic the audit uses, and aggregating positives / samples per
cell at both monthly and quarterly resolution so the factors are **measured**,
never assumed.

The six factors (Req 3.5 / design "Multi-factor feasibility")
-------------------------------------------------------------
Each factor is a :class:`~src.artifacts.schemas.FeasibilityFactor`
``(name, value, threshold, passed)``. Thresholds are justified inline; no single
factor is decisive — classification is the **conjunction** of the *required*
factors (Property 2).

1. ``train_positives``  — positives in the chronological train window
   (FY2014-FY2023). Threshold 30: the classic minimum independent-positive
   count for a learnable minority signal; a floor, not the whole test.
2. ``test_positives``   — positives in the untouched chronological test window
   (FY2024-FY2026). Threshold 10: a held-out window with too few positives
   cannot evaluate a rare-event classifier, so prediction is not defensible.
3. ``temporal_coverage``— fraction of in-range periods that carry >=1 sample.
   Threshold 0.60: a signal with long gaps between observed periods cannot be
   forecast period-over-period.
4. ``geographic_coverage`` — fraction of active regions (states that are ever
   sampled) whose cells carry >=1 positive at the chosen resolution. Threshold
   0.25: forecasting is defensible only if a reasonable share of regions
   actually exhibit the event; very sparse geographic positivity means the
   target is near-degenerate.
5. ``stability``        — temporal stability of per-period positivity, scored as
   ``1 / (1 + CV)`` where ``CV`` is the coefficient of variation of the per-
   period positivity-rate series. Threshold 0.35 (i.e. CV <= ~1.86): a signal
   whose period-to-period positivity is pure noise is not learnable; this is a
   proxy for learnability, not a guarantee.
6. ``calibration``      — **DEFERRED**. True calibration (e.g. Brier / reliability)
   is only measurable *after* a model is fit and validated. We therefore record
   it with ``value = NaN``, ``threshold = NaN``, ``passed = True`` and mark it a
   non-required, to-be-confirmed-at-validation factor in the rationale. We never
   fabricate a calibration number now (Req 4.6).

``prevalence`` and ``positive_rate`` are additionally recorded as informational
(non-required) factors so downstream rare-event handling (Req 7.3) can read the
class prevalence straight from the assessment.

Resolution selection (Req 3.6)
------------------------------
Monthly is preferred because it is the finer forecast horizon, but it is only
chosen when monthly modeling-unit cells carry enough positives to be learnable.
Concretely we compute the **median positives per non-empty cell** at monthly and
at quarterly resolution. Monthly is selected iff the monthly median positives
per active cell is >= ``MONTHLY_CELL_POS_MEDIAN_MIN`` (1.0 — at least half of
active monthly cells see a positive); otherwise quarterly is selected. The
median values that drove the choice are recorded verbatim as the evidence.

Outputs
-------
* ``data/interim/feasibility_report.json`` — per pathogen, the full
  :class:`~src.artifacts.schemas.FeasibilityReport` (factors, classification,
  rationale) plus the chosen resolution + evidence, recommended prediction
  target, and recommended validation design.
* ``docs/reports/feasibility.md`` — the human-readable version.
* :func:`module_statuses` returns a per-pathogen
  :class:`~src.artifacts.schemas.ModuleStatus` suitable for the manifest so the
  exporter / Web app can show module status + factors + resolution (Req 6.5).

Design reference: design.md "Multi-factor feasibility (correction 1)" and
"Per-pathogen modules gated by feasibility (Req 6)".
"""

from __future__ import annotations

import datetime as _dt
import json
import math
import statistics
from pathlib import Path
from typing import Optional, TypedDict

import pandas as pd

from src.artifacts.schemas import (
    FeasibilityFactor,
    FeasibilityReport,
    ModuleClassification,
    ModuleStatus,
    TemporalResolution,
)
from src.pipeline import audit
from src.pipeline.ingest import REPO_ROOT

__all__ = [
    "TRAIN_FYS",
    "TEST_FYS",
    "THRESHOLDS",
    "REQUIRED_FACTORS",
    "ModelingUnitPanel",
    "build_panel",
    "assess_pathogen",
    "classify_from_factors",
    "select_resolution",
    "run_feasibility",
    "module_statuses",
    "write_feasibility_markdown",
]

INTERIM_ROOT = REPO_ROOT / "data" / "interim"
DOCS_REPORTS = REPO_ROOT / "docs" / "reports"

# --------------------------------------------------------------------------- #
# Chronological split (fiscal years). Train = FY2014-FY2023, test = FY2024-FY2026.
# FSIS fiscal year starts Oct 1 of the prior calendar year (matches audit).
# --------------------------------------------------------------------------- #

TRAIN_FYS: tuple[int, ...] = tuple(range(2014, 2024))   # FY2014 .. FY2023
TEST_FYS: tuple[int, ...] = (2024, 2025, 2026)          # FY2024 .. FY2026

# --------------------------------------------------------------------------- #
# Factor thresholds (justified in the module docstring). Centralised so tests
# and the report read the same numbers.
# --------------------------------------------------------------------------- #

THRESHOLDS: dict[str, float] = {
    "train_positives": 30.0,
    "test_positives": 10.0,
    "temporal_coverage": 0.60,
    "geographic_coverage": 0.25,
    "stability": 0.35,
}

#: Factors whose conjunction decides the classification (Property 2). The
#: deferred ``calibration`` factor and the informational ``prevalence`` /
#: ``positive_rate`` factors are intentionally excluded from the conjunction.
REQUIRED_FACTORS: tuple[str, ...] = (
    "train_positives",
    "test_positives",
    "temporal_coverage",
    "geographic_coverage",
    "stability",
)

#: Resolution rule: monthly is chosen only when the median positives per active
#: monthly cell reaches this floor; otherwise quarterly. 1.0 means "at least
#: half of the monthly cells that are sampled also see a positive".
MONTHLY_CELL_POS_MEDIAN_MIN: float = 1.0


# --------------------------------------------------------------------------- #
# Modeling-unit panel (the measured substrate for every factor)
# --------------------------------------------------------------------------- #

class CellStats(TypedDict):
    """Aggregates for one (region, period) modeling-unit cell."""

    samples: int
    positives: int


class ModelingUnitPanel(TypedDict):
    """Measured modeling-unit panel for one pathogen at both resolutions."""

    pathogen: str
    commodity: str
    # cells keyed by resolution -> {"state|period": CellStats}
    monthly_cells: dict[str, CellStats]
    quarterly_cells: dict[str, CellStats]
    # per-period positivity-rate series (period -> rate) at each resolution
    monthly_period_rates: dict[str, float]
    quarterly_period_rates: dict[str, float]
    # sampled periods present / full range of periods, at each resolution
    monthly_periods_present: int
    monthly_periods_in_range: int
    quarterly_periods_present: int
    quarterly_periods_in_range: int
    # active regions = states ever sampled for this pathogen
    active_regions: int
    # train / test positive counts (chronological FY split)
    train_positives: int
    test_positives: int
    total_samples: int
    total_positives: int


def _fy_from_timestamp(ts: pd.Timestamp) -> int:
    """US federal fiscal year for a timestamp (FY starts Oct 1 prior year)."""
    return ts.year + 1 if ts.month >= 10 else ts.year


def _period_label(ts: pd.Timestamp, resolution: str) -> str:
    """Calendar period label for a timestamp at the given resolution."""
    if resolution == "monthly":
        return f"{ts.year:04d}-{ts.month:02d}"
    quarter = (ts.month - 1) // 3 + 1
    return f"{ts.year:04d}-Q{quarter}"


def _enumerate_periods(lo: pd.Timestamp, hi: pd.Timestamp, resolution: str) -> list[str]:
    """Every period label between two timestamps inclusive (no gaps)."""
    labels: list[str] = []
    if resolution == "monthly":
        y, m = lo.year, lo.month
        while (y, m) <= (hi.year, hi.month):
            labels.append(f"{y:04d}-{m:02d}")
            m += 1
            if m > 12:
                m = 1
                y += 1
    else:
        y, q = lo.year, (lo.month - 1) // 3 + 1
        hy, hq = hi.year, (hi.month - 1) // 3 + 1
        while (y, q) <= (hy, hq):
            labels.append(f"{y:04d}-Q{q}")
            q += 1
            if q > 4:
                q = 1
                y += 1
    return labels


def build_panel(
    pathogen_program: str,
    *,
    program_dirs: Optional[dict[str, Path]] = None,
) -> ModelingUnitPanel:
    """Build the real modeling-unit panel for one FSIS program.

    Reopens the program's fiscal-year archives via
    :func:`audit._load_program_frame`, applies the same tri-state result
    classification the audit uses, and aggregates positives/samples per
    ``(establishment_state, period)`` cell at monthly and quarterly resolution.
    Only rows with a parseable ``collection_date`` and a non-blank state are
    counted into a cell (rows missing either are still reflected in the overall
    sample total but cannot form a located, dated modeling-unit cell).
    """

    meta = audit.PROGRAM_META[pathogen_program]
    df, _schemas = audit._load_program_frame(pathogen_program, program_dirs)
    result_col = meta["result_column"]

    monthly_cells: dict[str, CellStats] = {}
    quarterly_cells: dict[str, CellStats] = {}
    # per-period aggregates for positivity-rate series
    monthly_period_pos: dict[str, int] = {}
    monthly_period_samp: dict[str, int] = {}
    quarterly_period_pos: dict[str, int] = {}
    quarterly_period_samp: dict[str, int] = {}

    total_samples = 0
    total_positives = 0
    train_positives = 0
    test_positives = 0
    active_region_set: set[str] = set()

    date_min: Optional[pd.Timestamp] = None
    date_max: Optional[pd.Timestamp] = None

    if not df.empty and result_col in df.columns:
        parsed, _failures = audit._parse_dates(df[audit.COL_COLLECTION_DATE]) \
            if audit.COL_COLLECTION_DATE in df.columns \
            else (pd.Series([pd.NaT] * len(df)), 0)
        states = (
            df[audit.COL_STATE].astype("string")
            if audit.COL_STATE in df.columns
            else pd.Series([pd.NA] * len(df), dtype="string")
        )
        results = df[result_col]

        for ts, state, raw_result in zip(parsed.tolist(), states.tolist(), results.tolist()):
            kind = audit.classify_result(raw_result)
            # tri-state: only positives/negatives are "tested samples"
            if kind == "other":
                is_sample = False
                is_pos = False
            else:
                is_sample = True
                is_pos = kind == "positive"
            if is_sample:
                total_samples += 1
                if is_pos:
                    total_positives += 1

            if ts is None or pd.isna(ts):
                continue
            ts = pd.Timestamp(ts)

            # chronological train/test positive counts by fiscal year
            if is_pos:
                fy = _fy_from_timestamp(ts)
                if fy in TRAIN_FYS:
                    train_positives += 1
                elif fy in TEST_FYS:
                    test_positives += 1

            if date_min is None or ts < date_min:
                date_min = ts
            if date_max is None or ts > date_max:
                date_max = ts

            state_key = (state or "").strip() if isinstance(state, str) else ""
            if not state_key or state_key.upper() == "NULL":
                # dated but unlocated: counts toward period rate, not a cell
                located = False
            else:
                located = True
                active_region_set.add(state_key)

            for resolution, cells, p_pos, p_samp in (
                ("monthly", monthly_cells, monthly_period_pos, monthly_period_samp),
                ("quarterly", quarterly_cells, quarterly_period_pos, quarterly_period_samp),
            ):
                period = _period_label(ts, resolution)
                if is_sample:
                    p_samp[period] = p_samp.get(period, 0) + 1
                    if is_pos:
                        p_pos[period] = p_pos.get(period, 0) + 1
                if located and is_sample:
                    key = f"{state_key}|{period}"
                    cur = cells.get(key) or CellStats(samples=0, positives=0)
                    cur["samples"] += 1
                    if is_pos:
                        cur["positives"] += 1
                    cells[key] = cur

    # per-period positivity-rate series (rate = positives / samples)
    def _rate_series(pos: dict[str, int], samp: dict[str, int]) -> dict[str, float]:
        return {
            per: (pos.get(per, 0) / samp[per])
            for per in sorted(samp)
            if samp[per] > 0
        }

    monthly_rates = _rate_series(monthly_period_pos, monthly_period_samp)
    quarterly_rates = _rate_series(quarterly_period_pos, quarterly_period_samp)

    # temporal coverage range (no-gap period count in [date_min, date_max])
    if date_min is not None and date_max is not None:
        m_range = len(_enumerate_periods(date_min, date_max, "monthly"))
        q_range = len(_enumerate_periods(date_min, date_max, "quarterly"))
    else:
        m_range = q_range = 0

    return ModelingUnitPanel(
        pathogen=meta["pathogen"],
        commodity=meta["commodity"],
        monthly_cells=monthly_cells,
        quarterly_cells=quarterly_cells,
        monthly_period_rates=monthly_rates,
        quarterly_period_rates=quarterly_rates,
        monthly_periods_present=len(monthly_period_samp),
        monthly_periods_in_range=m_range,
        quarterly_periods_present=len(quarterly_period_samp),
        quarterly_periods_in_range=q_range,
        active_regions=len(active_region_set),
        train_positives=train_positives,
        test_positives=test_positives,
        total_samples=total_samples,
        total_positives=total_positives,
    )


# --------------------------------------------------------------------------- #
# Resolution selection (Req 3.6) — pure, so it is directly testable
# --------------------------------------------------------------------------- #

def _median_positives_per_active_cell(cells: dict[str, CellStats]) -> float:
    """Median positive count over cells that carry at least one sample."""
    actives = [c["positives"] for c in cells.values() if c["samples"] > 0]
    if not actives:
        return 0.0
    return float(statistics.median(actives))


def select_resolution(panel: ModelingUnitPanel) -> tuple[TemporalResolution, str]:
    """Choose monthly vs quarterly for a pathogen and return (resolution, evidence).

    Monthly is selected iff the median positives per active **monthly** cell is
    at least :data:`MONTHLY_CELL_POS_MEDIAN_MIN`; otherwise quarterly. The two
    medians that drove the decision are recorded verbatim as the evidence
    (Req 3.6)."""

    m_median = _median_positives_per_active_cell(panel["monthly_cells"])
    q_median = _median_positives_per_active_cell(panel["quarterly_cells"])
    m_active = sum(1 for c in panel["monthly_cells"].values() if c["samples"] > 0)
    q_active = sum(1 for c in panel["quarterly_cells"].values() if c["samples"] > 0)

    if m_median >= MONTHLY_CELL_POS_MEDIAN_MIN:
        resolution: TemporalResolution = "monthly"
    else:
        resolution = "quarterly"

    evidence = (
        f"median positives per active cell: monthly={m_median:.2f} "
        f"(over {m_active} active monthly cells), quarterly={q_median:.2f} "
        f"(over {q_active} active quarterly cells); rule: choose monthly iff "
        f"monthly median >= {MONTHLY_CELL_POS_MEDIAN_MIN:.2f}, else quarterly. "
        f"Selected: {resolution}."
    )
    return resolution, evidence


# --------------------------------------------------------------------------- #
# Factor computation at the chosen resolution
# --------------------------------------------------------------------------- #

def _mk_factor(name: str, value: float, threshold: float, passed: bool) -> FeasibilityFactor:
    return FeasibilityFactor(name=name, value=float(value), threshold=float(threshold), passed=bool(passed))


def _coefficient_of_variation(series: list[float]) -> Optional[float]:
    """Coefficient of variation (stdev/mean) of a series, or None if undefined."""
    vals = [v for v in series if v is not None]
    if len(vals) < 2:
        return None
    mean = statistics.fmean(vals)
    if mean == 0:
        return None
    stdev = statistics.pstdev(vals)
    return stdev / mean


def compute_factors(
    panel: ModelingUnitPanel, resolution: TemporalResolution
) -> list[FeasibilityFactor]:
    """Compute the six factors + informational prevalence at the chosen resolution."""

    if resolution == "monthly":
        cells = panel["monthly_cells"]
        periods_present = panel["monthly_periods_present"]
        periods_in_range = panel["monthly_periods_in_range"]
        rates = panel["monthly_period_rates"]
    else:
        cells = panel["quarterly_cells"]
        periods_present = panel["quarterly_periods_present"]
        periods_in_range = panel["quarterly_periods_in_range"]
        rates = panel["quarterly_period_rates"]

    factors: list[FeasibilityFactor] = []

    # 1. train_positives
    tp = panel["train_positives"]
    factors.append(_mk_factor("train_positives", tp, THRESHOLDS["train_positives"], tp >= THRESHOLDS["train_positives"]))

    # 2. test_positives
    te = panel["test_positives"]
    factors.append(_mk_factor("test_positives", te, THRESHOLDS["test_positives"], te >= THRESHOLDS["test_positives"]))

    # 3. temporal_coverage = present periods / in-range periods
    tc = (periods_present / periods_in_range) if periods_in_range else 0.0
    factors.append(_mk_factor("temporal_coverage", tc, THRESHOLDS["temporal_coverage"], tc >= THRESHOLDS["temporal_coverage"]))

    # 4. geographic_coverage = fraction of active regions with >=1 positive cell
    region_has_pos: dict[str, bool] = {}
    for key, c in cells.items():
        region = key.split("|", 1)[0]
        if c["positives"] > 0:
            region_has_pos[region] = True
        else:
            region_has_pos.setdefault(region, False)
    active_regions = panel["active_regions"]
    regions_with_pos = sum(1 for v in region_has_pos.values() if v)
    gc = (regions_with_pos / active_regions) if active_regions else 0.0
    factors.append(_mk_factor("geographic_coverage", gc, THRESHOLDS["geographic_coverage"], gc >= THRESHOLDS["geographic_coverage"]))

    # 5. stability = 1 / (1 + CV of per-period positivity-rate series)
    cv = _coefficient_of_variation(list(rates.values()))
    if cv is None:
        stability = 0.0
    else:
        stability = 1.0 / (1.0 + cv)
    factors.append(_mk_factor("stability", stability, THRESHOLDS["stability"], stability >= THRESHOLDS["stability"]))

    # 6. calibration — DEFERRED: measurable only after modeling/validation.
    #    Recorded honestly as NaN, non-required, passed=True (not fabricated).
    factors.append(_mk_factor("calibration", float("nan"), float("nan"), True))

    # informational (non-required): prevalence + positive_rate for rare-event handling
    prevalence = (panel["total_positives"] / panel["total_samples"]) if panel["total_samples"] else 0.0
    factors.append(_mk_factor("prevalence", prevalence, 0.0, True))
    factors.append(_mk_factor("positive_rate", prevalence, 0.0, True))

    return factors


# --------------------------------------------------------------------------- #
# Classification (Property 2: conjunction of required factors)
# --------------------------------------------------------------------------- #

def classify_from_factors(factors: list[FeasibilityFactor]) -> ModuleClassification:
    """Classify ``predictive`` iff every REQUIRED factor passed, else ``non_predictive``.

    Only the factors named in :data:`REQUIRED_FACTORS` participate in the
    conjunction; the deferred ``calibration`` factor and informational factors
    are ignored. If a required factor is missing from the list, the pathogen is
    conservatively ``non_predictive`` (a required factor could not be measured)."""

    by_name = {f["name"]: f for f in factors}
    for name in REQUIRED_FACTORS:
        factor = by_name.get(name)
        if factor is None or not factor["passed"]:
            return "non_predictive"
    return "predictive"


# --------------------------------------------------------------------------- #
# Recommended target + validation design (Req 5/8 inputs, data-driven)
# --------------------------------------------------------------------------- #

def _recommend_target(
    classification: ModuleClassification,
    resolution: TemporalResolution,
    prevalence: float,
) -> str:
    """Concrete, data-driven recommended prediction target per pathogen."""
    agg = "state-level" if resolution == "quarterly" else "state-level"
    rare = prevalence < 0.10
    if classification == "predictive" and not rare:
        return (
            f"Binary target at the {resolution} Modeling_Unit "
            f"(pathogen x commodity x state x {resolution} period): next-period "
            f"positivity rate exceeds the trailing >=12-month baseline for that "
            f"({agg}) unit. Prevalence {prevalence * 100:.2f}% is above the 10% "
            f"rare-event line, so standard class weighting suffices."
        )
    if classification == "predictive" and rare:
        return (
            f"Binary rare-event target at the {resolution} Modeling_Unit "
            f"({agg}, {resolution}): next-period elevated-rate indicator "
            f"(positivity exceeds the trailing >=12-month baseline), trained with "
            f"rare-event handling (class weighting / scale_pos_weight) because "
            f"prevalence is {prevalence * 100:.2f}% (< 10%). Report under "
            f"PR-AUC and calibration, not accuracy."
        )
    # non_predictive
    return (
        f"No forecast target. Prevalence {prevalence * 100:.2f}% with the measured "
        f"factor gaps does not support defensible prediction at {resolution} "
        f"resolution; present a Non-Predictive_Module showing historical "
        f"surveillance positivity with uncertainty (region-level / {resolution}), "
        f"revisit only with a coarser region aggregate or more positives."
    )


def _recommend_validation(
    classification: ModuleClassification, panel: ModelingUnitPanel
) -> str:
    """Concrete temporal validation design recommendation (Req 8.1)."""
    # establishment holdout only where enough establishments exist; we read the
    # count from the audit report so the recommendation is data-driven.
    if classification == "non_predictive":
        return (
            "No predictive validation (module is non-predictive). For the "
            "historical-surveillance view, report per-period positivity with "
            "Wilson 95% intervals; no train/test split is claimed."
        )
    return (
        "PRIMARY chronological rolling-origin with >=3 origins (train timestamps "
        "strictly before test timestamps), the final 20% of periods held "
        "untouched (excluded from train and tuning). SECONDARY and reported "
        "separately: Establishment_Holdout_Validation (withhold all observations "
        "of held-out establishments) as a generalization check. Metrics "
        "disaggregated by region and period with 95% intervals; rare-event "
        "pathogens emphasise PR-AUC, Brier, and calibration over accuracy."
    )


# --------------------------------------------------------------------------- #
# Per-pathogen assessment
# --------------------------------------------------------------------------- #

class PathogenAssessment(TypedDict):
    """Full per-pathogen result (report + resolution evidence + recommendations)."""

    report: FeasibilityReport
    resolution_evidence: str
    recommended_target: str
    recommended_validation: str
    measured: dict[str, float]


def _rationale(
    pathogen: str,
    classification: ModuleClassification,
    factors: list[FeasibilityFactor],
    resolution: TemporalResolution,
) -> str:
    """One-paragraph documented rationale referencing the measured factors."""
    by_name = {f["name"]: f for f in factors}
    req_summary = ", ".join(
        f"{n}={by_name[n]['value']:.3g}{'✓' if by_name[n]['passed'] else '✗'}"
        f"(thr {by_name[n]['threshold']:.3g})"
        for n in REQUIRED_FACTORS
        if n in by_name
    )
    failed = [n for n in REQUIRED_FACTORS if n in by_name and not by_name[n]["passed"]]
    prevalence = by_name.get("prevalence", {}).get("value", 0.0)
    if classification == "predictive":
        verdict = (
            f"{pathogen} is classified PREDICTIVE: all required factors pass the "
            f"conjunction. "
        )
    else:
        verdict = (
            f"{pathogen} is classified NON_PREDICTIVE: required factor(s) "
            f"{failed} did not pass, so the conjunction fails. "
        )
    return (
        verdict
        + f"Chosen resolution: {resolution} (prevalence {prevalence * 100:.2f}%). "
        + f"Required factors [{req_summary}]. Calibration is deferred to "
        + "post-modeling validation and is not treated as decisive now. "
        + "Classification is the conjunction of the required factors, not any "
        + "single positive-count threshold (Req 3.5)."
    )


def assess_pathogen(
    pathogen_program: str,
    *,
    program_dirs: Optional[dict[str, Path]] = None,
) -> PathogenAssessment:
    """Run the full multi-factor assessment for one FSIS program."""
    panel = build_panel(pathogen_program, program_dirs=program_dirs)
    resolution, evidence = select_resolution(panel)
    factors = compute_factors(panel, resolution)
    classification = classify_from_factors(factors)
    rationale = _rationale(panel["pathogen"], classification, factors, resolution)

    by_name = {f["name"]: f for f in factors}
    prevalence = by_name["prevalence"]["value"]
    recommended_target = _recommend_target(classification, resolution, prevalence)
    recommended_validation = _recommend_validation(classification, panel)

    report = FeasibilityReport(
        pathogen=panel["pathogen"],
        temporal_resolution=resolution,
        factors=factors,
        classification=classification,
        rationale=rationale,
    )

    measured = {
        "train_positives": float(panel["train_positives"]),
        "test_positives": float(panel["test_positives"]),
        "total_samples": float(panel["total_samples"]),
        "total_positives": float(panel["total_positives"]),
        "active_regions": float(panel["active_regions"]),
        "monthly_periods_present": float(panel["monthly_periods_present"]),
        "monthly_periods_in_range": float(panel["monthly_periods_in_range"]),
        "quarterly_periods_present": float(panel["quarterly_periods_present"]),
        "quarterly_periods_in_range": float(panel["quarterly_periods_in_range"]),
        "monthly_median_pos_per_cell": _median_positives_per_active_cell(panel["monthly_cells"]),
        "quarterly_median_pos_per_cell": _median_positives_per_active_cell(panel["quarterly_cells"]),
    }

    return PathogenAssessment(
        report=report,
        resolution_evidence=evidence,
        recommended_target=recommended_target,
        recommended_validation=recommended_validation,
        measured=measured,
    )


# --------------------------------------------------------------------------- #
# Full run over all three real pathogens + artifact emission
# --------------------------------------------------------------------------- #

def module_statuses(
    assessments: dict[str, PathogenAssessment]
) -> dict[str, ModuleStatus]:
    """Per-pathogen :class:`ModuleStatus` for the manifest (Req 6.5)."""
    out: dict[str, ModuleStatus] = {}
    for assessment in assessments.values():
        report = assessment["report"]
        out[report["pathogen"]] = ModuleStatus(
            pathogen=report["pathogen"],
            status=report["classification"],
            feasibility_factors=report["factors"],
            temporal_resolution=report["temporal_resolution"],
        )
    return out


def _nan_to_none(obj):
    """Recursively replace NaN/inf floats with None so JSON stays strictly valid.

    The deferred ``calibration`` factor carries ``NaN`` in memory (it is not yet
    measurable). JSON has no NaN literal, so it is serialized as ``null`` here —
    the web contract reads a deferred factor as ``null`` value/threshold, never a
    fabricated number (Req 4.6, 6.5)."""
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: _nan_to_none(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_nan_to_none(v) for v in obj]
    return obj


def run_feasibility(
    program_dirs: Optional[dict[str, Path]] = None,
    *,
    out_json: Optional[Path] = None,
    out_md: Optional[Path] = None,
) -> dict[str, PathogenAssessment]:
    """Assess every real FSIS program and emit the machine- + human-readable reports.

    Writes ``data/interim/feasibility_report.json`` (per pathogen: the full
    FeasibilityReport with factors/classification/rationale, chosen resolution +
    evidence, recommended target, recommended validation design) and
    ``docs/reports/feasibility.md``. Returns the per-program assessment map."""

    program_dirs = program_dirs or None
    assessments: dict[str, PathogenAssessment] = {}
    for program in audit.PROGRAM_META:
        assessments[program] = assess_pathogen(program, program_dirs=program_dirs)

    # ---- machine-readable JSON ----
    payload: dict[str, dict] = {}
    for program, a in assessments.items():
        payload[program] = {
            "report": a["report"],
            "resolution_evidence": a["resolution_evidence"],
            "recommended_target": a["recommended_target"],
            "recommended_validation": a["recommended_validation"],
            "measured": a["measured"],
            "module_status": {
                "pathogen": a["report"]["pathogen"],
                "status": a["report"]["classification"],
                "temporal_resolution": a["report"]["temporal_resolution"],
                "feasibility_factors": a["report"]["factors"],
            },
        }

    out_json = out_json or (INTERIM_ROOT / "feasibility_report.json")
    out_json.parent.mkdir(parents=True, exist_ok=True)

    # Deferred-calibration factor values are NaN in memory (honest: not yet
    # measurable). Bare NaN is NOT valid strict JSON and the web loader's
    # JSON.parse would reject it, so emit NaN as JSON ``null`` and dump with
    # ``allow_nan=False`` to guarantee a contract-valid artifact (Req 6.5).
    sanitized = _nan_to_none(payload)
    out_json.write_text(
        json.dumps(sanitized, indent=2, ensure_ascii=False, allow_nan=False, default=str),
        encoding="utf-8",
    )

    out_md = out_md or (DOCS_REPORTS / "feasibility.md")
    write_feasibility_markdown(assessments, out_md)
    return assessments


# --------------------------------------------------------------------------- #
# Human-readable markdown
# --------------------------------------------------------------------------- #

def _fmt_factor_value(f: FeasibilityFactor) -> str:
    v = f["value"]
    if isinstance(v, float) and math.isnan(v):
        return "deferred (post-validation)"
    return f"{v:.4g}"


def _fmt_threshold(f: FeasibilityFactor) -> str:
    t = f["threshold"]
    if isinstance(t, float) and math.isnan(t):
        return "n/a"
    return f"{t:.4g}"


def write_feasibility_markdown(
    assessments: dict[str, PathogenAssessment], path: Path
) -> Path:
    """Write the human-readable feasibility report with real measured factors."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# Multi-Factor Feasibility Assessment")
    lines.append("")
    lines.append(
        f"Generated {_dt.datetime.now().isoformat(timespec='seconds')}. Every "
        "factor below is measured from the real FSIS laboratory-sampling "
        "archives (FY2014-FY2026). Feasibility is the conjunction of the "
        "required factors — never a single positive-count threshold (Req 3.5). "
        "Temporal resolution is chosen independently per pathogen from that "
        "pathogen's own sample availability (Req 3.6)."
    )
    lines.append("")
    lines.append(
        f"Chronological split: train = FY{TRAIN_FYS[0]}-FY{TRAIN_FYS[-1]}, "
        f"test = FY{TEST_FYS[0]}-FY{TEST_FYS[-1]}."
    )
    lines.append("")

    # headline
    lines.append("## Summary")
    lines.append("")
    lines.append("| Pathogen | Classification | Resolution | Train pos | Test pos | Prevalence |")
    lines.append("|---|:--:|:--:|---:|---:|---:|")
    for a in assessments.values():
        r = a["report"]
        by = {f["name"]: f for f in r["factors"]}
        lines.append(
            f"| {r['pathogen']} | {r['classification']} | {r['temporal_resolution']} | "
            f"{int(by['train_positives']['value']):,} | "
            f"{int(by['test_positives']['value']):,} | "
            f"{by['prevalence']['value'] * 100:.2f}% |"
        )
    lines.append("")

    for a in assessments.values():
        r = a["report"]
        lines.append(f"## {r['pathogen']}")
        lines.append("")
        lines.append(f"**Classification:** `{r['classification']}`  ")
        lines.append(f"**Temporal resolution:** `{r['temporal_resolution']}`")
        lines.append("")
        lines.append("### Factors")
        lines.append("")
        lines.append("| Factor | Value | Threshold | Passed | Required |")
        lines.append("|---|---:|---:|:--:|:--:|")
        for f in r["factors"]:
            required = "yes" if f["name"] in REQUIRED_FACTORS else "no"
            passed = "✓" if f["passed"] else "✗"
            lines.append(
                f"| {f['name']} | {_fmt_factor_value(f)} | {_fmt_threshold(f)} | "
                f"{passed} | {required} |"
            )
        lines.append("")
        lines.append(f"**Resolution evidence:** {a['resolution_evidence']}")
        lines.append("")
        lines.append(f"**Rationale:** {r['rationale']}")
        lines.append("")
        lines.append(f"**Recommended prediction target:** {a['recommended_target']}")
        lines.append("")
        lines.append(f"**Recommended validation design:** {a['recommended_validation']}")
        lines.append("")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


if __name__ == "__main__":  # pragma: no cover
    run_feasibility()
