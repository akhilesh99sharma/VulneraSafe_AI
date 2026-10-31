"""Harmonization into analytic tables (Phase 1, Task 2.9).

This module turns the audited FSIS laboratory-sampling programs plus the other
One Health sources (NOAA weather, Census ACS demographics, USDA Food Access
Research Atlas) into the per-pathogen **analytic tables** that modeling (Phase
2) consumes. It is the merge point where everything becomes one row per
``(pathogen, commodity, state, period)`` modeling unit, carrying a
``sampling_program`` dimension and explicit lag/availability columns.

It incorporates the five refinements required by Task 2.9. Each is implemented
by a clearly-named public function so it is independently testable and nothing
is hidden:

1. **Reconcile the "other" result bucket** (Req 1.3, 2.6, 2.8). The audit's
   tri-state classifier puts 2,146 records (Salmonella 200 + Listeria 1,930 +
   STEC 16) into ``other``. :func:`reconcile_other` re-loads the real program
   frames and enumerates the *actual* categories behind ``other`` per pathogen:

   * lab-problem codes — ``26 Lab closed``, ``25-* Lab problem ...``,
     ``13  Insufficient tissue or sample``, ``25-20  Other - ...`` — a sample
     that could not yield a valid test result, so it is **excluded** from
     modeling labels (it is neither a positive nor a negative detection);
   * blank / NULL result — no result recorded → **excluded** from labels;
   * for the Listeria (Lm) panel, the ``INT*_SA_*`` project codes are
     *Salmonella* for-cause programs that run in the RTE file but test a
     **different analyte** (Salmonella, not Lm), so their ``lm_listeria_analysis``
     is always blank; these are **excluded** from Lm labels because they do not
     test the Lm target at all.

   The reconciled per-category counts sum back to the audit ``other_count``
   totals exactly (enforced by :func:`reconcile_other` and a test). The result
   is written to ``data/interim/other_reconciliation.json`` and a transparent
   section is appended to ``docs/reports/data_audit.md``.

2. **Program-aware panels** (Req 2.6, 2.7). Every observed ``project_code`` is
   tagged with a :data:`ProgramCategory` from code/name semantics via
   :func:`tag_program`. The modeling target is built from **routine
   surveillance only**; for-cause / exploratory / follow-up / special programs
   are carried as separate context columns and are **never pooled into the
   baseline positivity** the forecast predicts. The mapping is written to
   ``data/interim/program_taxonomy.json`` and :func:`build_program_taxonomy`
   guarantees every observed code is tagged (none left untagged).

3. **Availability / lag logic** (Req 1.5, 2.6). FSIS sampling files carry a
   ``collection_date`` but **no publication date** (confirmed by the audit's
   recorded gap), so true release timing is unknown. We therefore derive
   ``availability_date = collection_date + REPORTING_LAG_DAYS`` with
   :data:`REPORTING_LAG_DAYS` a configurable constant (default 30) that is an
   **assumption, not an observed value**. :func:`available_as_of` returns only
   rows whose ``availability_date <= cutoff``. Harmonized rows carry
   ``collection_date``, ``availability_date`` and ``lag_days``. The platform
   must **not** claim true historical real-time forecasting: publication dates
   are unavailable, so the lag is a stated modeling assumption and a documented
   limitation (see :data:`AVAILABILITY_LIMITATION`).

4. **Harmonize the other One Health sources onto (state, period)** (Req 1.1,
   1.2, 2.7). :func:`harmonize_noaa`, :func:`harmonize_census_acs` and
   :func:`harmonize_food_access` aggregate each source to ``(state, period)``
   with an explicit lag so no post-cutoff information leaks, using a FIPS/state
   crosswalk (:data:`STATE_FIPS`, :data:`STATION_STATE`). Coverage is reported
   **honestly** — e.g. the ingested NOAA slice is a single representative
   station, so NOAA state coverage is documented as a known limitation rather
   than fabricated for every state.

5. **Data dictionary + decision statement** (Req 1.1, 1.2, 2.7, 2.8).
   :func:`write_data_dictionary` emits ``docs/data_dictionary.md`` with every
   column's name, type, units, source and lag. :func:`build_decision_statement`
   builds the five-element decision statement (Decision_Maker, decision,
   geography, commodity scope, horizon) and **rejects** it if any element is
   missing (Req 1.2), writing ``data/interim/decision_statement.json``.

The per-pathogen harmonized analytic table is written to ``data/processed/`` as
Parquet plus a small CSV sample, at the pathogen's feasibility resolution
(Salmonella monthly; Listeria / STEC quarterly) read from the feasibility
report.

Nothing in this module fabricates empirical values. Where a source cannot cover
a ``(state, period)`` cell, the predictor columns are left missing (NaN) and the
coverage limitation is recorded honestly.

Design reference: design.md "Harmonization and analytic tables" and the Task
2.9 refinements.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
from pathlib import Path
from typing import Any, Literal, Optional, TypedDict

import pandas as pd

from src.pipeline import audit
from src.pipeline.ingest import REPO_ROOT

__all__ = [
    "REPORTING_LAG_DAYS",
    "AVAILABILITY_LIMITATION",
    "ProgramCategory",
    "PROGRAM_CATEGORIES",
    "TARGET_CATEGORY",
    "LAB_PROBLEM_PATTERNS",
    "tag_program",
    "build_program_taxonomy",
    "reconcile_other",
    "add_availability_columns",
    "available_as_of",
    "STATE_FIPS",
    "FIPS_STATE",
    "STATION_STATE",
    "state_from_fips",
    "harmonize_noaa",
    "harmonize_nclimdiv",
    "harmonize_cdc_nors",
    "NCLIMDIV_AVAILABILITY_LAG_DAYS",
    "CDC_NORS_AVAILABILITY_LAG_DAYS",
    "CDC_NORS_LIMITATION",
    "harmonize_census_acs",
    "harmonize_food_access",
    "build_decision_statement",
    "DecisionStatementError",
    "harmonize_pathogen",
    "run_harmonization",
    "write_data_dictionary",
]

INTERIM_ROOT = REPO_ROOT / "data" / "interim"
PROCESSED_ROOT = REPO_ROOT / "data" / "processed"
RAW_ROOT = REPO_ROOT / "data" / "raw"
DOCS_ROOT = REPO_ROOT / "docs"
DOCS_REPORTS = DOCS_ROOT / "reports"


# --------------------------------------------------------------------------- #
# (3) Availability / reporting-lag ASSUMPTION (Req 1.5, 2.6)
# --------------------------------------------------------------------------- #

#: ASSUMED reporting lag in days between a sample's collection and the date its
#: result would realistically be *available* to a decision maker. FSIS lab
#: sampling files carry NO publication/release date (confirmed by the audit's
#: recorded ``publication_date`` gap), so this is a configurable modeling
#: ASSUMPTION, **not** an observed value. 30 days is a conservative default
#: covering lab turnaround + result posting; change it in one place here.
REPORTING_LAG_DAYS: int = 30

#: Honest limitation statement carried into code + docs (Req 1.5). The platform
#: must not claim true historical real-time forecasting because the real
#: publication dates are unavailable; availability is derived from an assumed
#: lag applied to the collection date.
AVAILABILITY_LIMITATION: str = (
    "LIMITATION: FSIS laboratory-sampling records carry a collection_date but "
    "no publication/release date (audit gap). availability_date is therefore "
    f"derived as collection_date + REPORTING_LAG_DAYS (assumed {REPORTING_LAG_DAYS} "
    "days), NOT an observed availability date. Consequently this platform must "
    "not claim true historical real-time forecasting: the lag is a stated "
    "assumption and a documented limitation. Backtests reflect assumed-"
    "availability timing, not verified real-time data releases."
)


# --------------------------------------------------------------------------- #
# (2) Program taxonomy (Req 2.6, 2.7) — tag every project code
# --------------------------------------------------------------------------- #

#: The five sampling-program categories. Only ``routine_surveillance`` feeds the
#: prediction target's baseline positivity; the others are context features.
ProgramCategory = Literal[
    "routine_surveillance",
    "for_cause",
    "exploratory",
    "follow_up",
    "special",
]

PROGRAM_CATEGORIES: tuple[ProgramCategory, ...] = (
    "routine_surveillance",
    "for_cause",
    "exploratory",
    "follow_up",
    "special",
)

#: The single category whose positivity defines the forecast baseline/target.
TARGET_CATEGORY: ProgramCategory = "routine_surveillance"


def tag_program(project_code: str, project_name: str = "") -> ProgramCategory:
    """Tag one FSIS ``project_code`` into a :data:`ProgramCategory`.

    The rules below are driven by the real FSIS project-code / project-name
    semantics observed in the audit report. They are applied in priority order
    so a code matches exactly one category, and the final fallback guarantees
    **every** observed code is tagged (none left untagged, Req 2.7):

    * ``special``            — ``SPECPGM_*`` (intensified/outbreak special
      programs) and project names mentioning "outbreak" / "intensified".
    * ``follow_up``          — ``F_*`` poultry follow-ups, beef ``MT52``-``MT55``
      and their ``_C`` / traceback (``MT44T``) variants, ``MT44`` follow-up, and
      any name beginning "follow-up".
    * ``for_cause``          — ``INT*`` / ``RLM*`` for-cause and risk-based
      verification Listeria programs and names mentioning "for-cause".
    * ``exploratory``        — ``EXP_*`` / ``EX_*`` / ``NRTE_EXP*`` exploratory
      programs and "exploratory" / "rehang" names.
    * ``routine_surveillance`` — ``HC_*`` HACCP verification, ``RTEPROD*``
      random/risk-based RTE, ``MT43``/``MT60``/``MT64``/``MT65`` beef routine,
      ``LO_*`` very-low-volume and ``RE_*`` religious-exempt routine sampling.

    Everything that still fails to match is tagged ``routine_surveillance`` only
    when its name clearly indicates routine/HACCP/random; otherwise it is tagged
    ``special`` so an unknown program is never silently pooled into the baseline
    (a conservative choice: unknown programs stay OUT of the target).
    """

    code = (project_code or "").strip().upper()
    name = (project_name or "").strip().lower()

    # --- special (outbreak / intensified special programs) ----------------
    if code.startswith("SPECPGM") or "outbreak" in name or "intensifed" in name \
            or "intensified" in name:
        return "special"

    # --- follow-up --------------------------------------------------------
    if code.startswith("F_") or name.startswith("follow-up") or "follow-up" in name:
        return "follow_up"
    # beef follow-up project codes MT52..MT55 (+ _C / traceback variants)
    if re.match(r"^MT5[2-5](_C|T|T_C)?$", code):
        return "follow_up"
    if code.startswith("MT44"):  # MT44, MT44T, MT44T_C — follow-up of positives
        return "follow_up"

    # --- exploratory ------------------------------------------------------
    if code.startswith("EXP_") or code.startswith("EX_") or "NRTE_EXP" in code \
            or "exploratory" in name or "rehang" in name:
        return "exploratory"

    # --- for-cause (intensified/for-cause + risk-based Lm verification) ----
    if code.startswith("INT") or code.startswith("RLM") or "for-cause" in name:
        return "for_cause"

    # --- routine surveillance --------------------------------------------
    if code.startswith("HC_") or code.startswith("RTEPROD") \
            or code.startswith("LO_") or code.startswith("RE_") \
            or code in {"MT43", "MT60", "MT60_C", "MT64", "MT65", "MT65_C"} \
            or "haccp" in name or "random" in name or "risk-based sampling" in name:
        return "routine_surveillance"

    # --- conservative fallback -------------------------------------------
    # A clearly-routine name still lands as routine; anything genuinely unknown
    # is parked in ``special`` so it never contaminates the routine baseline.
    if "verification" in name or "routine" in name:
        return "routine_surveillance"
    return "special"


class ProgramTag(TypedDict):
    """One tagged project code with its category and observed counts."""

    project_code: str
    project_name: str
    category: ProgramCategory
    pathogen: str
    observations: int
    positives: int
    negatives: int
    other: int


def _load_audit_report(path: Optional[Path] = None) -> dict[str, Any]:
    """Load the audit report JSON (the authoritative per-program breakdowns)."""
    path = path or (INTERIM_ROOT / "audit_report.json")
    return json.loads(path.read_text(encoding="utf-8"))


def build_program_taxonomy(
    audit_report: Optional[dict[str, Any]] = None,
    *,
    out_json: Optional[Path] = None,
) -> dict[str, Any]:
    """Tag every observed project code and write ``program_taxonomy.json`` (Req 2.6/2.7).

    Reads the per-program ``positivity_by_program`` breakdown straight from the
    audit report so the tagging covers exactly the codes present in the real
    data. Returns a dict with a flat ``tags`` list (one entry per
    ``(pathogen, project_code)``), per-pathogen ``by_category`` count roll-ups,
    and an ``untagged`` list that is guaranteed empty (every code is tagged).
    """

    audit_report = audit_report or _load_audit_report()

    tags: list[ProgramTag] = []
    by_category: dict[str, dict[str, dict[str, int]]] = {}
    untagged: list[str] = []

    for program, rep in audit_report.items():
        pathogen = rep["pathogen"]
        cat_counts: dict[str, dict[str, int]] = {
            c: {"codes": 0, "observations": 0, "positives": 0, "negatives": 0, "other": 0}
            for c in PROGRAM_CATEGORIES
        }
        for pp in rep.get("positivity_by_program", []):
            code = pp["project_code"]
            pname = pp.get("project_name", "")
            category = tag_program(code, pname)
            if category not in PROGRAM_CATEGORIES:  # defensive; never happens
                untagged.append(f"{pathogen}:{code}")
                continue
            tags.append(
                ProgramTag(
                    project_code=code,
                    project_name=pname,
                    category=category,
                    pathogen=pathogen,
                    observations=int(pp["observations"]),
                    positives=int(pp["positives"]),
                    negatives=int(pp["negatives"]),
                    other=int(pp["other"]),
                )
            )
            agg = cat_counts[category]
            agg["codes"] += 1
            agg["observations"] += int(pp["observations"])
            agg["positives"] += int(pp["positives"])
            agg["negatives"] += int(pp["negatives"])
            agg["other"] += int(pp["other"])
        by_category[pathogen] = cat_counts

    result = {
        "description": (
            "Every observed FSIS project_code tagged into one of five sampling-"
            "program categories. The prediction target is built from "
            f"'{TARGET_CATEGORY}' ONLY; for_cause / exploratory / follow_up / "
            "special programs are separate context features and are never pooled "
            "into the baseline positivity the forecast predicts (Req 2.6)."
        ),
        "target_category": TARGET_CATEGORY,
        "categories": list(PROGRAM_CATEGORIES),
        "tags": tags,
        "by_category": by_category,
        "untagged": untagged,
        "total_codes_tagged": len(tags),
    }

    out_json = out_json or (INTERIM_ROOT / "program_taxonomy.json")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return result


# --------------------------------------------------------------------------- #
# (1) Reconcile the "other" result bucket (Req 1.3, 2.6, 2.8)
# --------------------------------------------------------------------------- #

#: Regexes that identify FSIS lab-problem / insufficient-sample result codes
#: inside the ``other`` bucket. These are not valid test results.
LAB_PROBLEM_PATTERNS: tuple[tuple[str, str], ...] = (
    ("lab_closed", r"^(26\b.*lab closed|25-5\b.*lab closed|.*lab closed.*)$"),
    ("lab_problem", r"^25-\d+\b.*"),
    ("insufficient_sample", r"^13\b.*insufficient.*"),
)

#: Disposition strings used in the reconciliation output.
_DISP_LAB_PROBLEM = (
    "excluded_from_labels: lab problem / insufficient sample is not a valid "
    "test result (neither a positive nor a negative detection)"
)
_DISP_BLANK = (
    "excluded_from_labels: blank/NULL result — no result recorded, so the "
    "sample yields no label"
)
_DISP_SA_IN_LM = (
    "excluded_from_lm_labels: INT*_SA_* are Salmonella for-cause programs that "
    "run in the RTE/Listeria file but test a DIFFERENT analyte (Salmonella, not "
    "Lm); their lm_listeria_analysis is blank so they test nothing on the Lm "
    "target"
)


def _categorize_other_value(value: Any) -> str:
    """Categorize one ``other`` result cell into a lab-problem / blank bucket."""
    if value is None:
        return "blank_or_null"
    text = str(value).strip()
    if not text or text.upper() == "NULL":
        return "blank_or_null"
    low = text.lower()
    for label, pattern in LAB_PROBLEM_PATTERNS:
        if re.match(pattern, low):
            return label
    if "lab closed" in low or "lab problem" in low:
        return "lab_closed"
    if "insufficient" in low:
        return "insufficient_sample"
    if low.startswith("25-") or low.startswith("26"):
        return "lab_problem"
    # Any other non-empty, non-positive/negative token (e.g. "25-20 Other ...").
    return "other_coded"


def reconcile_other(
    *,
    program_dirs: Optional[dict[str, Path]] = None,
    audit_report: Optional[dict[str, Any]] = None,
    out_json: Optional[Path] = None,
) -> dict[str, Any]:
    """Enumerate the real categories behind the ``other`` bucket per pathogen.

    Re-loads each program frame, finds every row the audit classified as
    ``other`` (via :func:`audit.classify_result`), and splits those rows into
    categories: ``lab_closed`` / ``lab_problem`` / ``insufficient_sample`` /
    ``other_coded`` lab-problem families, ``blank_or_null`` missing results,
    and — for the Listeria panel only — ``salmonella_only_program`` for rows
    whose ``project_code`` matches ``INT*_SA_*`` (Salmonella for-cause programs
    that do not test the Lm target at all).

    Each category carries its count and an explicit **exclusion disposition**.
    The sum of category counts equals the audit ``other_count`` for the pathogen
    exactly; a ``reconciles`` boolean records that invariant per pathogen.

    Writes ``data/interim/other_reconciliation.json`` and returns the same dict.
    """

    program_dirs = program_dirs or audit.FSIS_PROGRAM_DIRS
    audit_report = audit_report or _load_audit_report()

    sa_only_re = re.compile(r"^INT.*_SA_[EMW]$", re.IGNORECASE)

    per_pathogen: dict[str, Any] = {}
    for program, meta in audit.PROGRAM_META.items():
        if program not in program_dirs:
            continue
        pathogen = meta["pathogen"]
        result_col = meta["result_column"]
        audit_other = int(audit_report[program]["other_count"])

        df, _schemas = audit._load_program_frame(program, program_dirs)

        categories: dict[str, dict[str, Any]] = {}

        def _bump(key: str, disposition: str) -> None:
            entry = categories.setdefault(
                key, {"count": 0, "disposition": disposition}
            )
            entry["count"] += 1

        counted = 0
        if not df.empty and result_col in df.columns:
            results = df[result_col].tolist()
            if audit.COL_PROJECT_CODE in df.columns:
                codes = df[audit.COL_PROJECT_CODE].astype("string").tolist()
            else:
                codes = [None] * len(results)

            for value, code in zip(results, codes):
                if audit.classify_result(value) != "other":
                    continue
                counted += 1
                code_str = (code or "").strip() if isinstance(code, str) else ""
                # Listeria-only special case: Salmonella-only programs.
                if pathogen == "Listeria" and sa_only_re.match(code_str):
                    _bump("salmonella_only_program", _DISP_SA_IN_LM)
                    continue
                bucket = _categorize_other_value(value)
                if bucket == "blank_or_null":
                    _bump("blank_or_null", _DISP_BLANK)
                else:
                    _bump(bucket, _DISP_LAB_PROBLEM)

        total = sum(c["count"] for c in categories.values())
        per_pathogen[pathogen] = {
            "program": program,
            "result_column": result_col,
            "audit_other_count": audit_other,
            "reconciled_total": total,
            "reconciles": bool(total == audit_other),
            "categories": dict(sorted(categories.items(), key=lambda kv: -kv[1]["count"])),
            "excluded_from_modeling_labels": total,  # every other-category is excluded
        }

    result = {
        "description": (
            "Reconciliation of the tri-state 'other' result bucket (Salmonella "
            "200 + Listeria 1,930 + STEC 16 = 2,146) into its real categories. "
            "Every category is a non-result (lab problem, insufficient sample, "
            "blank/NULL) or — in the Lm panel — a Salmonella-only program that "
            "tests a different analyte; ALL are excluded from modeling labels "
            "because none is a valid positive/negative detection of the "
            "pathogen target (Req 1.3)."
        ),
        "per_pathogen": per_pathogen,
        "grand_total_other": sum(p["reconciled_total"] for p in per_pathogen.values()),
        "all_reconcile": all(p["reconciles"] for p in per_pathogen.values()),
    }

    out_json = out_json or (INTERIM_ROOT / "other_reconciliation.json")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return result


# --------------------------------------------------------------------------- #
# (3) Availability columns + available_as_of (Req 1.5)
# --------------------------------------------------------------------------- #

def add_availability_columns(
    df: pd.DataFrame,
    *,
    collection_col: str = "collection_date",
    lag_days: int = REPORTING_LAG_DAYS,
) -> pd.DataFrame:
    """Add ``availability_date`` and ``lag_days`` from an assumed reporting lag.

    ``availability_date = collection_date + lag_days`` (an ASSUMPTION — see
    :data:`AVAILABILITY_LIMITATION`). The returned frame is a copy; the
    ``collection_date`` column is coerced to datetime. Rows with an unparseable
    collection date get ``NaT`` availability (never fabricated)."""

    out = df.copy()
    coll = pd.to_datetime(out[collection_col], errors="coerce")
    out[collection_col] = coll
    out["lag_days"] = int(lag_days)
    out["availability_date"] = coll + pd.to_timedelta(int(lag_days), unit="D")
    return out


def available_as_of(
    df: pd.DataFrame,
    cutoff: Any,
    *,
    availability_col: str = "availability_date",
) -> pd.DataFrame:
    """Return only rows available at ``cutoff`` (``availability_date <= cutoff``).

    This is the leakage guard for backtests: a row is visible only once its
    assumed availability date has passed. Rows with a missing availability date
    are treated as not-yet-available and excluded (never leaked). ``cutoff`` may
    be anything ``pandas.Timestamp`` accepts."""

    cutoff_ts = pd.Timestamp(cutoff)
    avail = pd.to_datetime(df[availability_col], errors="coerce")
    mask = avail.notna() & (avail <= cutoff_ts)
    return df.loc[mask].copy()


# --------------------------------------------------------------------------- #
# (4) FIPS / state crosswalk (Req 1.1, 2.7)
# --------------------------------------------------------------------------- #

#: State / territory FIPS code -> USPS two-letter abbreviation. Covers the 50
#: states, DC, PR and the territories that appear in Census output. This is the
#: crosswalk that maps county/tract FIPS (whose first two digits are the state
#: FIPS) and Census ``state`` columns to the FSIS ``establishment_state`` codes.
STATE_FIPS: dict[str, str] = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO",
    "09": "CT", "10": "DE", "11": "DC", "12": "FL", "13": "GA", "15": "HI",
    "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY",
    "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN",
    "28": "MS", "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
    "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH",
    "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD",
    "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA",
    "54": "WV", "55": "WI", "56": "WY", "60": "AS", "66": "GU", "69": "MP",
    "72": "PR", "78": "VI",
}

#: Reverse crosswalk USPS abbreviation -> FIPS.
FIPS_STATE: dict[str, str] = {v: k for k, v in STATE_FIPS.items()}

#: GHCND station id -> state. Only stations actually ingested are mapped; the
#: single demonstration station below lives in New York (NYC Central Park).
#: NOAA state coverage is therefore limited to the stations present — a
#: documented limitation, not a per-state fabrication (Req 2.7).
STATION_STATE: dict[str, str] = {
    "USW00094728": "NY",  # New York, NY (Central Park)
}


def state_from_fips(fips: Any) -> Optional[str]:
    """Map a 2-digit state FIPS (or a longer county/tract FIPS) to a USPS code."""
    if fips is None:
        return None
    text = str(fips).strip()
    if not text:
        return None
    # Zero-pad short codes, then take the first two digits as the state FIPS.
    digits = re.sub(r"\D", "", text)
    if not digits:
        return None
    state_fips = digits.zfill(2)[:2] if len(digits) <= 2 else digits.zfill(5)[:2]
    return STATE_FIPS.get(state_fips)


def _period_label(ts: pd.Timestamp, resolution: str) -> str:
    """Calendar period label for a timestamp at the given resolution."""
    if resolution == "monthly":
        return f"{ts.year:04d}-{ts.month:02d}"
    quarter = (ts.month - 1) // 3 + 1
    return f"{ts.year:04d}-Q{quarter}"


# --------------------------------------------------------------------------- #
# (4) NOAA -> (state, period) weather means + anomalies (Req 2.7)
# --------------------------------------------------------------------------- #

def _load_noaa_frame() -> pd.DataFrame:
    """Load + concatenate the ingested NOAA daily-summary JSON files."""
    noaa_dir = RAW_ROOT / "noaa"
    frames: list[pd.DataFrame] = []
    if noaa_dir.exists():
        for p in sorted(noaa_dir.glob("*.json")):
            try:
                recs = json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                continue
            if recs:
                frames.append(pd.DataFrame(recs))
    if not frames:
        return pd.DataFrame(columns=["DATE", "STATION", "TMAX", "TMIN", "PRCP"])
    df = pd.concat(frames, ignore_index=True, sort=False)
    return df.drop_duplicates(subset=["DATE", "STATION"], keep="last")


def harmonize_noaa(resolution: str, *, lag_days: int = REPORTING_LAG_DAYS) -> dict[str, Any]:
    """Aggregate daily NOAA station data to ``(state, period)`` means + anomalies.

    Daily records are mapped to a state via :data:`STATION_STATE`, grouped to
    ``(state, period)`` at ``resolution``, and summarised with mean TMAX/TMIN
    and total PRCP. Anomalies are each cell's value minus that state's long-run
    mean over all observed periods (a within-sample anomaly; honest given the
    short ingested window). An explicit ``availability_period`` lag column marks
    when the aggregate would be usable.

    Returns a dict with a ``table`` (list of row dicts keyed by ``state`` +
    ``period``) and a ``coverage`` note stating honestly how many stations /
    states / periods are actually covered — the ingested slice is a single
    demonstration station, so coverage is narrow and this is documented rather
    than fabricated for other states.
    """

    df = _load_noaa_frame()
    rows: list[dict[str, Any]] = []
    stations = sorted(df["STATION"].dropna().unique().tolist()) if not df.empty else []
    mapped_states = sorted({STATION_STATE[s] for s in stations if s in STATION_STATE})
    unmapped = [s for s in stations if s not in STATION_STATE]

    if not df.empty:
        work = df.copy()
        work["state"] = work["STATION"].map(STATION_STATE)
        work = work.dropna(subset=["state"])
        work["ts"] = pd.to_datetime(work["DATE"], errors="coerce")
        work = work.dropna(subset=["ts"])
        for col in ("TMAX", "TMIN", "PRCP"):
            work[col] = pd.to_numeric(work.get(col), errors="coerce")
        work["period"] = work["ts"].map(lambda t: _period_label(t, resolution))

        grouped = work.groupby(["state", "period"]).agg(
            tmax_mean=("TMAX", "mean"),
            tmin_mean=("TMIN", "mean"),
            prcp_total=("PRCP", "sum"),
            n_days=("DATE", "count"),
        ).reset_index()

        # anomalies vs each state's long-run mean across observed periods
        state_means = grouped.groupby("state").agg(
            tmax_ref=("tmax_mean", "mean"),
            tmin_ref=("tmin_mean", "mean"),
            prcp_ref=("prcp_total", "mean"),
        ).reset_index()
        grouped = grouped.merge(state_means, on="state", how="left")
        grouped["tmax_anomaly"] = grouped["tmax_mean"] - grouped["tmax_ref"]
        grouped["tmin_anomaly"] = grouped["tmin_mean"] - grouped["tmin_ref"]
        grouped["prcp_anomaly"] = grouped["prcp_total"] - grouped["prcp_ref"]
        grouped["noaa_lag_days"] = int(lag_days)

        rows = grouped.drop(columns=["tmax_ref", "tmin_ref", "prcp_ref"]).to_dict(
            orient="records"
        )

    periods = sorted({r["period"] for r in rows})
    coverage = {
        "stations_ingested": stations,
        "stations_mapped_to_state": [s for s in stations if s in STATION_STATE],
        "stations_unmapped": unmapped,
        "states_covered": mapped_states,
        "states_covered_count": len(mapped_states),
        "periods_covered": periods,
        "limitation": (
            "NOAA coverage is limited to the ingested station slice — a single "
            "representative demonstration station (NYC Central Park, NY) over a "
            "short January-2023 window. Weather predictors are therefore only "
            "non-missing for the covered state/periods; every other "
            "(state, period) weather cell is left MISSING (NaN), never "
            "fabricated. A production run would ingest one-or-more stations per "
            "state across the full temporal range."
        ),
    }
    return {"resolution": resolution, "table": rows, "coverage": coverage}


# --------------------------------------------------------------------------- #
# (4b) NOAA nClimDiv statewide -> (state, period) weather (PRIMARY source)
# --------------------------------------------------------------------------- #

#: Assumed nClimDiv publication lag. nClimDiv monthly statewide values are
#: released in the first week of the following month, so a month's data becomes
#: usable at ``end_of_month + NCLIMDIV_AVAILABILITY_LAG_DAYS``. This is a small,
#: documented, realistic lag (Req 1.5). It is deliberately applied at the END of
#: the weather month so leakage-safe features draw only on fully-published
#: months.
NCLIMDIV_AVAILABILITY_LAG_DAYS: int = 7

#: Weather months spanning the FSIS data range (and before). nClimDiv covers
#: 1895-present; we honour the ingested [start_year, end_year] slice in ingest.


def _f_to_c(series: pd.Series) -> pd.Series:
    """Convert Fahrenheit to Celsius (nClimDiv temperatures are °F)."""
    return (series - 32.0) * 5.0 / 9.0


def _inches_to_mm(series: pd.Series) -> pd.Series:
    """Convert inches to millimetres (nClimDiv precipitation is inches)."""
    return series * 25.4


def _load_nclimdiv_frame() -> pd.DataFrame:
    """Load + merge the ingested nClimDiv per-element raw files into one tidy frame.

    Re-parses the raw statewide files written by
    :func:`src.pipeline.ingest.ingest_nclimdiv` (``data/raw/noaa_nclimdiv/``)
    into a ``(state, year, month, tavg, tmax, tmin, pcpn)`` frame. Returns an
    empty frame (never fabricated) when no files are present."""
    from src.pipeline import ingest as _ing

    ndir = RAW_ROOT / "noaa_nclimdiv"
    if not ndir.exists():
        return pd.DataFrame(columns=["state", "year", "month"])
    # stem -> element
    stem_to_element = {v: k for k, v in _ing.NCLIMDIV_ELEMENTS.items()}
    frames: list[pd.DataFrame] = []
    for path in sorted(ndir.glob("climdiv-*")):
        element = None
        for stem, elem in stem_to_element.items():
            if path.name.startswith(stem):
                element = elem
                break
        if element is None:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        tidy = _ing._parse_climdiv_statewide(text, element)
        if not tidy.empty:
            frames.append(tidy)
    if not frames:
        return pd.DataFrame(columns=["state", "year", "month"])
    merged = frames[0]
    for extra in frames[1:]:
        merged = merged.merge(extra, on=["state", "year", "month"], how="outer")
    return merged.sort_values(["state", "year", "month"]).reset_index(drop=True)


def _month_end_plus_lag(year: int, month: int, lag_days: int) -> pd.Timestamp:
    """Availability date = last day of (year, month) + ``lag_days`` days."""
    first = pd.Timestamp(year=int(year), month=int(month), day=1)
    month_end = first + pd.offsets.MonthEnd(0)
    return month_end + pd.Timedelta(days=int(lag_days))


def harmonize_nclimdiv(
    resolution: str,
    *,
    lag_days: int = NCLIMDIV_AVAILABILITY_LAG_DAYS,
) -> dict[str, Any]:
    """Aggregate nClimDiv statewide monthly climate to ``(state, period)`` (PRIMARY).

    Builds the weather table features.py consumes, with the SAME column names as
    :func:`harmonize_noaa` so no downstream change is needed: ``tmax_mean`` /
    ``tmin_mean`` (°C, period means), ``prcp_total`` (mm, period total), and the
    three anomalies (value minus that state's long-run monthly mean over the
    ingested window), plus ``noaa_lag_days``.

    Each weather period carries an ``availability_date`` = the MAX over its
    constituent months of ``end_of_month + lag_days`` (a small, documented,
    realistic publication lag — Req 1.5), so the leakage guard in features.py
    draws only on fully-published months strictly before the target period.

    Coverage is REAL national state-level: the 48 contiguous states + Alaska for
    every month in range. Hawaii is absent (documented nClimDiv gap). Returns a
    dict with ``table`` (list of row dicts) + an honest ``coverage`` note.
    """
    df = _load_nclimdiv_frame()
    if df.empty:
        coverage = {
            "source": "noaa_nclimdiv",
            "states_covered_count": 0,
            "periods_covered": [],
            "limitation": (
                "nClimDiv raw files absent — run ingest_nclimdiv first. Weather "
                "cells left MISSING (NaN), never fabricated."
            ),
        }
        return {"resolution": resolution, "table": [], "coverage": coverage}

    work = df.copy()
    # Convert to the units features.py/doc expect (°C, mm).
    if "tmax" in work:
        work["tmax_c"] = _f_to_c(work["tmax"])
    else:
        work["tmax_c"] = _f_to_c(work.get("tavg"))
    if "tmin" in work:
        work["tmin_c"] = _f_to_c(work["tmin"])
    else:
        work["tmin_c"] = _f_to_c(work.get("tavg"))
    work["pcpn_mm"] = _inches_to_mm(work["pcpn"]) if "pcpn" in work else pd.NA

    # Monthly availability date (end of weather month + lag).
    work["avail"] = [
        _month_end_plus_lag(y, m, lag_days)
        for y, m in zip(work["year"].tolist(), work["month"].tolist())
    ]
    # Period label at the pathogen's resolution (uses month start for mapping).
    work["period"] = [
        _period_label(pd.Timestamp(year=int(y), month=int(m), day=1), resolution)
        for y, m in zip(work["year"].tolist(), work["month"].tolist())
    ]

    grouped = work.groupby(["state", "period"]).agg(
        tmax_mean=("tmax_c", "mean"),
        tmin_mean=("tmin_c", "mean"),
        prcp_total=("pcpn_mm", "sum"),
        availability_date=("avail", "max"),
        n_months=("month", "count"),
    ).reset_index()

    # Anomalies vs each state's long-run mean across the ingested window.
    state_ref = grouped.groupby("state").agg(
        tmax_ref=("tmax_mean", "mean"),
        tmin_ref=("tmin_mean", "mean"),
        prcp_ref=("prcp_total", "mean"),
    ).reset_index()
    grouped = grouped.merge(state_ref, on="state", how="left")
    grouped["tmax_anomaly"] = grouped["tmax_mean"] - grouped["tmax_ref"]
    grouped["tmin_anomaly"] = grouped["tmin_mean"] - grouped["tmin_ref"]
    grouped["prcp_anomaly"] = grouped["prcp_total"] - grouped["prcp_ref"]
    grouped["noaa_lag_days"] = int(lag_days)
    grouped = grouped.drop(columns=["tmax_ref", "tmin_ref", "prcp_ref"])

    rows = grouped.to_dict(orient="records")
    states = sorted(grouped["state"].unique().tolist())
    periods = sorted(grouped["period"].unique().tolist())
    coverage = {
        "source": "noaa_nclimdiv",
        "states_covered": states,
        "states_covered_count": len(states),
        "periods_covered_count": len(periods),
        "period_range": [periods[0], periods[-1]] if periods else [],
        "availability_lag_days": lag_days,
        "cells": int(len(grouped)),
        "units": {"temperature": "degrees Celsius", "precipitation": "mm"},
        "limitation": (
            "nClimDiv statewide monthly climate gives REAL national state-level "
            f"coverage ({len(states)} states x {len(periods)} periods). Hawaii "
            "has no nClimDiv statewide series and is left MISSING (documented "
            "gap, never fabricated). Availability = end-of-month + "
            f"{lag_days}d (nClimDiv is published in the first week of the "
            "following month), so leakage-safe features use fully-published "
            "months strictly before the target period. Anomalies are within-"
            "sample vs each state's long-run mean over the ingested window."
        ),
    }
    return {"resolution": resolution, "table": rows, "coverage": coverage}


# --------------------------------------------------------------------------- #
# (4c) CDC NORS -> (state, period) outbreak counts (One Health human pathway)
# --------------------------------------------------------------------------- #

#: LARGE documented availability lag for CDC NORS used as a PREDICTIVE feature.
#: NORS carries outbreak dates, not report dates, and finalised outbreak data is
#: typically not available until a year or more after the outbreak. To use NORS
#: as a leakage-safe predictor we therefore require ~12 months to pass after the
#: END of an outbreak month before its record is treated as "available" to a
#: forecaster. This is prominent and honest (Req: point 4): CDC is used mainly
#: as HISTORICAL One Health evidence; predictive use is defensible only under
#: this large lag.
CDC_NORS_AVAILABILITY_LAG_DAYS: int = 365

CDC_NORS_LIMITATION: str = (
    "LIMITATION: CDC NORS records outbreak dates, NOT report dates, and has long "
    "reporting delays (finalised data commonly lags the outbreak by a year or "
    "more). As a PREDICTIVE feature NORS is therefore joined with a large "
    f"availability lag (end-of-outbreak-month + {CDC_NORS_AVAILABILITY_LAG_DAYS} "
    "days ~= 12 months) so a forecast at cutoff t uses only outbreaks whose data "
    "would plausibly be available by t. NORS is used mainly as HISTORICAL One "
    "Health human-health evidence; predictive use is defensible only under this "
    "lag and is reported as such."
)


def _load_nors_frame() -> pd.DataFrame:
    """Load the ingested CDC NORS raw JSON file(s) into one frame (or empty)."""
    ndir = RAW_ROOT / "cdc_nors"
    frames: list[pd.DataFrame] = []
    if ndir.exists():
        for p in sorted(ndir.glob("*.json")):
            try:
                recs = json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                continue
            if recs:
                frames.append(pd.DataFrame(recs))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True, sort=False)


def harmonize_cdc_nors(
    resolution: str,
    *,
    pathogen: Optional[str] = None,
    lag_days: int = CDC_NORS_AVAILABILITY_LAG_DAYS,
) -> dict[str, Any]:
    """Aggregate CDC NORS foodborne outbreaks to ``(state, period)`` counts.

    Maps the NORS full state names to USPS codes, assigns a period at the
    pathogen resolution, and aggregates to ``(state, period)`` counts of
    foodborne outbreaks + summed illnesses, plus pathogen-specific outbreak
    counts (Salmonella / Listeria / STEC) derived from the ``etiology`` text.
    When ``pathogen`` is given, the returned ``table`` additionally carries a
    ``cdc_pathogen_outbreaks`` column selecting that pathogen's count.

    Every row carries an ``availability_date`` = ``end_of_month + lag_days``
    (the LARGE NORS lag — see :data:`CDC_NORS_LIMITATION`) so the leakage guard
    only exposes NORS data that would realistically be published by the cutoff.

    Returns a dict with ``table`` + an honest ``coverage`` note. Empty when NORS
    was not ingested (gap recorded, never fabricated)."""
    df = _load_nors_frame()
    if df.empty:
        coverage = {
            "source": "cdc_nors",
            "available": False,
            "states_covered_count": 0,
            "limitation": (
                "CDC NORS not ingested — run ingest_cdc_nors first. Recorded as "
                "a gap; no CDC features joined (never fabricated)."
            ),
            "availability_lag_days": lag_days,
            "honesty": CDC_NORS_LIMITATION,
        }
        return {"resolution": resolution, "table": [], "coverage": coverage}

    name_to_usps = _state_name_to_usps()
    work = df.copy()
    work["state"] = work["state"].map(
        lambda s: name_to_usps.get(str(s).strip().lower())
    )
    work = work.dropna(subset=["state"])
    work["year"] = pd.to_numeric(work.get("year"), errors="coerce")
    work["month"] = pd.to_numeric(work.get("month"), errors="coerce")
    work = work.dropna(subset=["year", "month"])
    work = work[(work["month"] >= 1) & (work["month"] <= 12)]
    work["illnesses"] = pd.to_numeric(work.get("illnesses"), errors="coerce").fillna(0)

    etiology = work.get("etiology", pd.Series([""] * len(work))).fillna("").str.lower()
    from src.pipeline.ingest import CDC_NORS_PATHOGEN_PATTERNS
    for pname, pats in CDC_NORS_PATHOGEN_PATTERNS.items():
        work[f"is_{pname.lower()}"] = etiology.apply(
            lambda t, pats=pats: int(any(pat in t for pat in pats))
        )

    work["availability_date"] = [
        _month_end_plus_lag(int(y), int(m), lag_days)
        for y, m in zip(work["year"].tolist(), work["month"].tolist())
    ]
    work["period"] = [
        _period_label(pd.Timestamp(year=int(y), month=int(m), day=1), resolution)
        for y, m in zip(work["year"].tolist(), work["month"].tolist())
    ]

    grouped = work.groupby(["state", "period"]).agg(
        cdc_outbreaks=("illnesses", "size"),
        cdc_illnesses=("illnesses", "sum"),
        cdc_salmonella_outbreaks=("is_salmonella", "sum"),
        cdc_listeria_outbreaks=("is_listeria", "sum"),
        cdc_stec_outbreaks=("is_stec", "sum"),
        availability_date=("availability_date", "max"),
    ).reset_index()

    if pathogen is not None:
        col = f"cdc_{pathogen.lower()}_outbreaks"
        if col in grouped.columns:
            grouped["cdc_pathogen_outbreaks"] = grouped[col]

    rows = grouped.to_dict(orient="records")
    states = sorted(grouped["state"].unique().tolist())
    periods = sorted(grouped["period"].unique().tolist())
    coverage = {
        "source": "cdc_nors",
        "available": True,
        "dataset_id": "5xkq-dg7x",
        "states_covered": states,
        "states_covered_count": len(states),
        "periods_covered_count": len(periods),
        "period_range": [periods[0], periods[-1]] if periods else [],
        "total_outbreaks": int(grouped["cdc_outbreaks"].sum()),
        "availability_lag_days": lag_days,
        "honesty": CDC_NORS_LIMITATION,
        "limitation": (
            "CDC NORS gives REAL state-level foodborne-outbreak counts aggregated "
            f"to (state, period) ({len(states)} states x {len(periods)} periods). "
            "Used mainly as historical One Health evidence; predictive join uses "
            f"a large {lag_days}-day availability lag (see honesty note)."
        ),
    }
    return {"resolution": resolution, "table": rows, "coverage": coverage}


# --------------------------------------------------------------------------- #
# (4) Census ACS county -> state vulnerability aggregates (Req 2.7)
# --------------------------------------------------------------------------- #

def harmonize_census_acs() -> dict[str, Any]:
    """Aggregate ACS county rows to per-state demographic vulnerability.

    The ingested ACS slice is the B01001 "Sex by Age" table with total
    population (``B01001_001E``) plus six elderly age-band columns — male 65-66
    / 67-69 / 85+ (``_020E`` / ``_021E`` / ``_025E``) and female 65-66 / 67-69 /
    85+ (``_044E`` / ``_045E`` / ``_049E``). Counties are rolled up to states
    via the two-digit state FIPS. We compute a PARTIAL 65+ elderly count from
    the six ingested bands and an ``elderly_share`` of total population — an
    honest *elderly-vulnerability proxy*. Under-5 was not part of the ingested
    slice, so it is recorded as a gap, never fabricated.

    Returns a dict with a ``table`` of per-state rows and a ``coverage`` note.
    """

    path = RAW_ROOT / "census" / "acs5_2022.json"
    rows: list[dict[str, Any]] = []
    gaps: list[str] = []
    elderly_cols = ["B01001_020E", "B01001_021E", "B01001_025E",
                    "B01001_044E", "B01001_045E", "B01001_049E"]
    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
        header, data = raw[0], raw[1:]
        df = pd.DataFrame(data, columns=header)
        present_elderly = [c for c in elderly_cols if c in df.columns]
        for c in ["B01001_001E", *present_elderly]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        df["state"] = df["state"].map(lambda f: STATE_FIPS.get(str(f).zfill(2)))
        df = df.dropna(subset=["state"])
        agg_spec = {"total_population": ("B01001_001E", "sum"),
                    "counties": ("NAME", "count")}
        grouped = df.groupby("state").agg(**agg_spec).reset_index()
        if present_elderly:
            df["_elderly"] = df[present_elderly].sum(axis=1)
            eld = df.groupby("state")["_elderly"].sum().reset_index(
                name="elderly_65plus_partial")
            grouped = grouped.merge(eld, on="state", how="left")
            grouped["elderly_share"] = (
                grouped["elderly_65plus_partial"] / grouped["total_population"]
            )
        else:
            gaps.append("no elderly age-band columns in ingested ACS slice")
        grouped["acs_vintage"] = "ACS5 2022"
        rows = grouped.to_dict(orient="records")
    else:
        gaps.append("ACS raw file absent")

    gaps.append(
        "under-5 (B01001_003E/_027E) NOT in the ingested ACS slice; under-5 "
        "vulnerability is a recorded GAP, not fabricated"
    )
    coverage = {
        "states_covered_count": len(rows),
        "elderly_bands_used": elderly_cols,
        "gaps": gaps,
        "limitation": (
            "ACS aggregates are static (one 2022 vintage) and keyed by state "
            "only; they carry no within-year period variation, so they join to "
            "every period of a state as a slowly-varying context feature. The "
            "'elderly_65plus_partial' count sums the six ingested 65+ bands and "
            "is a vulnerability PROXY, not the complete 65+ population."
        ),
    }
    return {"table": rows, "coverage": coverage}


# --------------------------------------------------------------------------- #
# (4) Food Access Atlas tract -> state indicators (Req 2.7)
# --------------------------------------------------------------------------- #

def harmonize_food_access() -> dict[str, Any]:
    """Aggregate the USDA Food Access Research Atlas tracts to per-state indicators.

    Reads the Atlas data sheet, maps each tract to its state (the ``State``
    column holds the full state name; the ``CensusTract`` FIPS prefix is used as
    a fallback), and computes per-state food-access indicators: share of
    low-income-and-low-access (LILA) tracts and share of low-access tracts,
    plus the population-weighted means where populations are present. Returns a
    ``table`` of per-state rows and a ``coverage`` note.
    """

    path = RAW_ROOT / "food_access" / "lram_2019_xlsx.xlsx"
    rows: list[dict[str, Any]] = []
    gaps: list[str] = []
    note = ""
    if path.exists():
        try:
            sheets = pd.read_excel(path, sheet_name=None)
            # pick the data sheet (the one with CensusTract/State columns)
            data_sheet = None
            for name, sdf in sheets.items():
                if "State" in sdf.columns and (
                    "CensusTract" in sdf.columns or "LILATracts_1And10" in sdf.columns
                ):
                    data_sheet = sdf
                    break
            if data_sheet is None:
                data_sheet = max(sheets.values(), key=len)
            df = data_sheet.copy()

            # Full-name -> USPS crosswalk (the Atlas 'State' column is a name).
            name_to_usps = _state_name_to_usps()
            df["state"] = df["State"].map(
                lambda s: name_to_usps.get(str(s).strip().lower())
            )
            # Fallback via CensusTract FIPS prefix where the name didn't map.
            if "CensusTract" in df.columns:
                fallback = df["CensusTract"].map(state_from_fips)
                df["state"] = df["state"].fillna(fallback)
            df = df.dropna(subset=["state"])

            lila_col = next(
                (c for c in ("LILATracts_1And10", "LILATracts_halfAnd10",
                             "LILATracts_1And20") if c in df.columns),
                None,
            )
            la_col = "LowIncomeTracts" if "LowIncomeTracts" in df.columns else None
            pop_col = "Pop2010" if "Pop2010" in df.columns else None

            grouped = df.groupby("state").size().reset_index(name="tracts")
            if lila_col:
                lila = df.groupby("state")[lila_col].mean().reset_index(
                    name="lila_tract_share")
                grouped = grouped.merge(lila, on="state", how="left")
            else:
                gaps.append("no LILA tract flag column found")
            if la_col:
                lowinc = df.groupby("state")[la_col].mean().reset_index(
                    name="low_income_tract_share")
                grouped = grouped.merge(lowinc, on="state", how="left")
            if pop_col:
                pop = df.groupby("state")[pop_col].sum().reset_index(
                    name="atlas_pop_2010")
                grouped = grouped.merge(pop, on="state", how="left")
            grouped["atlas_vintage"] = "FARA/LRAM 2019"
            rows = grouped.to_dict(orient="records")
            note = f"data sheet aggregated to {len(rows)} states from tract rows"
        except ImportError:
            gaps.append("openpyxl not installed; Atlas xlsx not parsed")
        except Exception as exc:  # noqa: BLE001 — record, never crash the run
            gaps.append(f"Atlas parse error: {exc!r}")
    else:
        gaps.append("Atlas raw file absent")

    coverage = {
        "states_covered_count": len(rows),
        "gaps": gaps,
        "note": note,
        "limitation": (
            "Atlas indicators are a single 2019 vintage keyed by state; they "
            "carry no period variation and join as a static context feature. "
            "Tract-level access thresholds are policy definitions, not ground "
            "truth. States with no mappable tracts are left MISSING, never "
            "fabricated."
        ),
    }
    return {"table": rows, "coverage": coverage}


def _state_name_to_usps() -> dict[str, str]:
    """Lower-cased full state name -> USPS abbreviation (for the Atlas join)."""
    names = {
        "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
        "california": "CA", "colorado": "CO", "connecticut": "CT",
        "delaware": "DE", "district of columbia": "DC", "florida": "FL",
        "georgia": "GA", "hawaii": "HI", "idaho": "ID", "illinois": "IL",
        "indiana": "IN", "iowa": "IA", "kansas": "KS", "kentucky": "KY",
        "louisiana": "LA", "maine": "ME", "maryland": "MD", "massachusetts": "MA",
        "michigan": "MI", "minnesota": "MN", "mississippi": "MS", "missouri": "MO",
        "montana": "MT", "nebraska": "NE", "nevada": "NV", "new hampshire": "NH",
        "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
        "north carolina": "NC", "north dakota": "ND", "ohio": "OH",
        "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA",
        "rhode island": "RI", "south carolina": "SC", "south dakota": "SD",
        "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT",
        "virginia": "VA", "washington": "WA", "west virginia": "WV",
        "wisconsin": "WI", "wyoming": "WY", "puerto rico": "PR",
    }
    return names


# --------------------------------------------------------------------------- #
# (5) Decision statement (Req 1.2) — reject if any of five elements missing
# --------------------------------------------------------------------------- #

class DecisionStatementError(ValueError):
    """Raised when the decision statement is missing a required element (Req 1.2)."""


#: The five required decision-statement elements (Req 1.2).
DECISION_ELEMENTS: tuple[str, ...] = (
    "decision_maker",
    "decision",
    "geography",
    "commodity_scope",
    "horizon",
)

#: The default, concrete decision statement for VulneraSafe AI.
_DEFAULT_DECISION = {
    "decision_maker": (
        "Retail Food Safety Operations Director (a national grocery retailer's "
        "food-safety operations lead who allocates inspection/testing attention "
        "and supplier scrutiny)"
    ),
    "decision": (
        "Where to direct the next period's finite inspection, lot-testing and "
        "supplier-documentation effort to reduce the chance of distributing "
        "contaminated product, given predicted surveillance risk."
    ),
    "geography": "United States, at the US-state level",
    "commodity_scope": (
        "FSIS-regulated meat/poultry: raw poultry (Salmonella), ready-to-eat "
        "products (Listeria monocytogenes), and raw beef (STEC)"
    ),
    "horizon": (
        "The next period (next month for Salmonella; next quarter for Listeria "
        "and STEC, matching each pathogen's feasibility resolution)"
    ),
    "operational_constraints": (
        "Finite inspection/testing budget per period; confirmed regulatory "
        "recalls are hard constraints (never distribute a recalled lot); "
        "high-consequence actions require Human_Review; food-access-aware "
        "options must not weaken any safety constraint."
    ),
    "authority": (
        "Decision support only — recommends where to focus effort; it is NOT a "
        "regulatory determination and does not declare product safe/unsafe."
    ),
}


def build_decision_statement(
    overrides: Optional[dict[str, Any]] = None,
    *,
    out_json: Optional[Path] = None,
) -> dict[str, Any]:
    """Build + validate the decision statement; reject if any element missing.

    Starts from the default statement, applies ``overrides``, then verifies all
    five required elements (:data:`DECISION_ELEMENTS`) are present and non-empty.
    A missing or blank element raises :class:`DecisionStatementError` naming it
    (Req 1.2). On success the statement (plus operational constraints/authority
    for retrieval by the Decision_Engine and Web_App) is written to
    ``data/interim/decision_statement.json`` and returned.
    """

    statement = dict(_DEFAULT_DECISION)
    if overrides:
        statement.update(overrides)

    missing = [
        e for e in DECISION_ELEMENTS
        if not str(statement.get(e, "")).strip()
    ]
    if missing:
        raise DecisionStatementError(
            "decision statement rejected — missing required element(s): "
            f"{missing}. All five of {list(DECISION_ELEMENTS)} must be present "
            "and non-empty (Req 1.2)."
        )

    statement["_valid"] = True
    statement["_required_elements"] = list(DECISION_ELEMENTS)
    out_json = out_json or (INTERIM_ROOT / "decision_statement.json")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(
        json.dumps(statement, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return statement


# --------------------------------------------------------------------------- #
# Per-pathogen harmonized analytic table (the core join, Req 1.1, 2.6, 2.7)
# --------------------------------------------------------------------------- #

#: Feasibility report -> program mapping (which program backs each pathogen).
_PATHOGEN_PROGRAM = {
    "Salmonella": "raw_poultry_salmonella",
    "Listeria": "rte_listeria",
    "STEC": "raw_beef_stec",
}


def _load_feasibility_resolutions(
    path: Optional[Path] = None,
) -> dict[str, str]:
    """Read each pathogen's selected resolution from the feasibility report."""
    path = path or (INTERIM_ROOT / "feasibility_report.json")
    report = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for prog, entry in report.items():
        pathogen = entry["report"]["pathogen"]
        out[pathogen] = entry["report"]["temporal_resolution"]
    return out


def harmonize_pathogen(
    pathogen: str,
    resolution: str,
    *,
    program_dirs: Optional[dict[str, Path]] = None,
    noaa: Optional[dict[str, Any]] = None,
    acs: Optional[dict[str, Any]] = None,
    food_access: Optional[dict[str, Any]] = None,
    cdc: Optional[dict[str, Any]] = None,
    lag_days: int = REPORTING_LAG_DAYS,
) -> pd.DataFrame:
    """Build the harmonized analytic table for one pathogen at its resolution.

    One row per ``(pathogen, commodity, state, period, sampling_program)``
    modeling unit. For each FSIS sample we classify the result (tri-state),
    tag its ``project_code`` into a :data:`ProgramCategory`, derive
    ``availability_date``/``lag_days`` from the assumed reporting lag, assign a
    period, and aggregate per group into samples / positives. The routine-
    surveillance rows alone carry the ``is_target`` flag so the baseline the
    forecast predicts never pools for-cause/exploratory programs (Req 2.6).

    The One Health predictors (NOAA weather, ACS demographics, Food Access
    indicators) are left-joined on ``(state, period)`` / ``state`` with their
    own lag columns; uncovered cells stay MISSING (NaN), never fabricated.
    """

    program = _PATHOGEN_PROGRAM[pathogen]
    meta = audit.PROGRAM_META[program]
    result_col = meta["result_column"]
    commodity = meta["commodity"]

    df, _schemas = audit._load_program_frame(program, program_dirs)
    if df.empty:
        return pd.DataFrame()

    coll = pd.to_datetime(df.get(audit.COL_COLLECTION_DATE), errors="coerce")
    states = (
        df[audit.COL_STATE].astype("string")
        if audit.COL_STATE in df.columns else pd.Series([pd.NA] * len(df))
    )
    codes = (
        df[audit.COL_PROJECT_CODE].astype("string")
        if audit.COL_PROJECT_CODE in df.columns else pd.Series([""] * len(df))
    )
    names = (
        df[audit.COL_PROJECT_NAME].astype("string")
        if audit.COL_PROJECT_NAME in df.columns else pd.Series([""] * len(df))
    )
    results = df[result_col]

    records: list[dict[str, Any]] = []
    for ts, state, code, name, raw in zip(
        coll.tolist(), states.tolist(), codes.tolist(), names.tolist(),
        results.tolist(),
    ):
        kind = audit.classify_result(raw)
        if kind == "other":
            # excluded from labels per the other-reconciliation (Req 1.3)
            continue
        if ts is None or pd.isna(ts):
            continue
        state_key = (state or "").strip() if isinstance(state, str) else ""
        if not state_key or state_key.upper() == "NULL":
            continue
        ts = pd.Timestamp(ts)
        category = tag_program(
            code if isinstance(code, str) else "",
            name if isinstance(name, str) else "",
        )
        records.append({
            "state": state_key,
            "period": _period_label(ts, resolution),
            "collection_date": ts,
            "sampling_program": code if isinstance(code, str) else "",
            "program_category": category,
            "is_positive": 1 if kind == "positive" else 0,
        })

    if not records:
        return pd.DataFrame()

    long = pd.DataFrame.from_records(records)
    # availability/lag from the ASSUMED reporting lag, per cell = latest sample
    grouped = long.groupby(
        ["state", "period", "sampling_program", "program_category"],
        dropna=False,
    ).agg(
        samples=("is_positive", "size"),
        positives=("is_positive", "sum"),
        collection_date=("collection_date", "max"),
    ).reset_index()
    grouped["pathogen"] = pathogen
    grouped["commodity"] = commodity
    grouped["positivity_rate"] = grouped["positives"] / grouped["samples"]
    grouped["is_target"] = (grouped["program_category"] == TARGET_CATEGORY)
    grouped = add_availability_columns(grouped, lag_days=lag_days)

    # --- join One Health predictors on (state, period) / state -------------
    if noaa and noaa.get("table"):
        ndf = pd.DataFrame(noaa["table"])
        # Carry weather's OWN availability (end-of-month + nClimDiv lag) as a
        # dedicated column so features.py gates weather on its real publication
        # lag, not the FSIS sampling lag (Req 1.5, point 3).
        if "availability_date" in ndf.columns:
            ndf = ndf.rename(columns={"availability_date": "weather_availability_date"})
        keep = [c for c in ("state", "period", "tmax_mean", "tmin_mean",
                            "prcp_total", "tmax_anomaly", "tmin_anomaly",
                            "prcp_anomaly", "noaa_lag_days",
                            "weather_availability_date") if c in ndf.columns]
        grouped = grouped.merge(ndf[keep], on=["state", "period"], how="left")

    # --- CDC NORS human-health outbreak counts (large availability lag) ----
    if cdc and cdc.get("table"):
        cdf = pd.DataFrame(cdc["table"])
        if "availability_date" in cdf.columns:
            cdf = cdf.rename(columns={"availability_date": "cdc_availability_date"})
        cdc_cols = [c for c in ("cdc_outbreaks", "cdc_illnesses",
                                "cdc_salmonella_outbreaks", "cdc_listeria_outbreaks",
                                "cdc_stec_outbreaks", "cdc_pathogen_outbreaks")
                    if c in cdf.columns]
        keep = ["state", "period", *cdc_cols]
        if "cdc_availability_date" in cdf.columns:
            keep.append("cdc_availability_date")
        grouped = grouped.merge(cdf[keep], on=["state", "period"], how="left")

    if acs and acs.get("table"):
        adf = pd.DataFrame(acs["table"])
        keep = [c for c in ("state", "total_population", "elderly_65plus_partial",
                            "elderly_share", "acs_vintage") if c in adf.columns]
        grouped = grouped.merge(adf[keep], on="state", how="left")

    if food_access and food_access.get("table"):
        fdf = pd.DataFrame(food_access["table"])
        keep = [c for c in ("state", "lila_tract_share", "low_income_tract_share",
                            "atlas_pop_2010", "atlas_vintage") if c in fdf.columns]
        grouped = grouped.merge(fdf[keep], on="state", how="left")

    # stable column order: keys first
    key_cols = ["pathogen", "commodity", "state", "period", "sampling_program",
                "program_category", "is_target", "collection_date",
                "availability_date", "lag_days", "samples", "positives",
                "positivity_rate"]
    ordered = key_cols + [c for c in grouped.columns if c not in key_cols]
    grouped = grouped[ordered].sort_values(
        ["state", "period", "sampling_program"]
    ).reset_index(drop=True)
    return grouped


# --------------------------------------------------------------------------- #
# (5) Data dictionary (Req 2.7) — every column: name, type, units, source, lag
# --------------------------------------------------------------------------- #

#: Column spec: (name, type, units, source, lag). Covers every column emitted in
#: the harmonized analytic tables. ``lag`` states the explicit lag each column
#: carries relative to the modeling period (Req 1.1 explicit lags).
_DATA_DICTIONARY: tuple[tuple[str, str, str, str, str], ...] = (
    ("pathogen", "string", "—", "FSIS program metadata", "none (key)"),
    ("commodity", "string", "—", "FSIS program metadata", "none (key)"),
    ("state", "string", "USPS 2-letter code", "FSIS establishment_state", "none (key)"),
    ("period", "string", "YYYY-MM or YYYY-Qn", "derived from collection_date", "none (key)"),
    ("sampling_program", "string", "FSIS project_code", "FSIS project_code", "none (key)"),
    ("program_category", "string",
     "routine_surveillance|for_cause|exploratory|follow_up|special",
     "tag_program(project_code, project_name)", "none"),
    ("is_target", "bool", "—",
     "derived: program_category == routine_surveillance", "none"),
    ("collection_date", "datetime", "date (latest sample in the cell)",
     "FSIS collection_date", "observed collection date"),
    ("availability_date", "datetime", "date",
     "collection_date + REPORTING_LAG_DAYS", f"ASSUMED +{REPORTING_LAG_DAYS}d (not observed)"),
    ("lag_days", "int", "days", "constant REPORTING_LAG_DAYS",
     f"assumed reporting lag ({REPORTING_LAG_DAYS})"),
    ("samples", "int", "count of tested samples (pos+neg)",
     "FSIS tri-state classification", "availability lag"),
    ("positives", "int", "count of positive detections",
     "FSIS tri-state classification", "availability lag"),
    ("positivity_rate", "float", "fraction 0..1 (positives/samples)",
     "derived", "availability lag"),
    ("tmax_mean", "float", "°C (mean daily max over period)",
     "NOAA NCEI daily-summaries", f"+{REPORTING_LAG_DAYS}d assumed"),
    ("tmin_mean", "float", "°C (mean daily min over period)",
     "NOAA NCEI daily-summaries", f"+{REPORTING_LAG_DAYS}d assumed"),
    ("prcp_total", "float", "mm (total precip over period)",
     "NOAA NCEI daily-summaries", f"+{REPORTING_LAG_DAYS}d assumed"),
    ("tmax_anomaly", "float", "°C vs state long-run mean",
     "derived from NOAA", f"+{REPORTING_LAG_DAYS}d assumed"),
    ("tmin_anomaly", "float", "°C vs state long-run mean",
     "derived from NOAA", f"+{REPORTING_LAG_DAYS}d assumed"),
    ("prcp_anomaly", "float", "mm vs state long-run mean",
     "derived from NOAA", f"+{REPORTING_LAG_DAYS}d assumed"),
    ("noaa_lag_days", "int", "days", "constant", "assumed NOAA lag"),
    ("total_population", "float", "persons", "Census ACS5 2022 B01001_001E",
     "static (2022 vintage, pre-cutoff)"),
    ("elderly_65plus_partial", "float",
     "persons (sum of six ingested 65+ bands)", "Census ACS5 2022 B01001",
     "static (2022 vintage, pre-cutoff)"),
    ("elderly_share", "float", "fraction 0..1", "derived from ACS",
     "static (2022 vintage, pre-cutoff)"),
    ("acs_vintage", "string", "—", "Census ACS", "static"),
    ("lila_tract_share", "float",
     "fraction of tracts flagged low-income & low-access",
     "USDA Food Access Research Atlas 2019", "static (2019 vintage, pre-cutoff)"),
    ("low_income_tract_share", "float", "fraction of low-income tracts",
     "USDA Food Access Research Atlas 2019", "static (2019 vintage, pre-cutoff)"),
    ("atlas_pop_2010", "float", "persons (tract Pop2010 summed)",
     "USDA Food Access Research Atlas 2019", "static"),
    ("atlas_vintage", "string", "—", "USDA ERS Food Access Atlas", "static"),
)


def write_data_dictionary(out_md: Optional[Path] = None) -> Path:
    """Write ``docs/data_dictionary.md`` with every column name/type/units/source/lag."""
    out_md = out_md or (DOCS_ROOT / "data_dictionary.md")
    out_md.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# VulneraSafe AI — Data Dictionary",
        "",
        "Every column in the harmonized per-pathogen analytic tables "
        "(`data/processed/harmonized_<pathogen>.parquet`). Each row lists the "
        "column name, type, units, source, and the explicit lag it carries "
        "relative to the modeling period (Req 1.1, 2.7).",
        "",
        f"> {AVAILABILITY_LIMITATION}",
        "",
        "| Column | Type | Units | Source | Lag |",
        "|---|---|---|---|---|",
    ]
    for name, typ, units, source, lag in _DATA_DICTIONARY:
        lines.append(f"| `{name}` | {typ} | {units} | {source} | {lag} |")
    lines.append("")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_md


# --------------------------------------------------------------------------- #
# Append the transparent "other" reconciliation section to the audit md
# --------------------------------------------------------------------------- #

def append_other_reconciliation_md(
    reconciliation: dict[str, Any], out_md: Optional[Path] = None
) -> Path:
    """Append the transparent 'other'-bucket reconciliation to data_audit.md."""
    out_md = out_md or (DOCS_REPORTS / "data_audit.md")
    out_md.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "",
        "## 'Other' result-bucket reconciliation (Task 2.9, Req 1.3)",
        "",
        "The tri-state audit places records that are neither a positive nor a "
        "negative detection into an `other` bucket. The 2,146 such records "
        "(Salmonella 200 + Listeria 1,930 + STEC 16) are enumerated below into "
        "their real categories. Every category is a non-result (lab problem, "
        "insufficient sample, blank/NULL) or — in the Lm panel — a "
        "Salmonella-only program that tests a different analyte; **all are "
        "excluded from modeling labels** because none is a valid detection of "
        "the pathogen target. Per-pathogen category counts sum back to the "
        "audit `other_count` exactly.",
        "",
    ]
    for pathogen, entry in reconciliation["per_pathogen"].items():
        lines.append(f"### {pathogen} — `{entry['program']}`")
        lines.append("")
        lines.append(
            f"- Audit `other_count`: **{entry['audit_other_count']:,}**; "
            f"reconciled total: **{entry['reconciled_total']:,}**; "
            f"reconciles: **{'YES' if entry['reconciles'] else 'NO'}**"
        )
        lines.append("")
        lines.append("| Category | Count | Disposition |")
        lines.append("|---|---:|---|")
        for cat, info in entry["categories"].items():
            lines.append(f"| `{cat}` | {info['count']:,} | {info['disposition']} |")
        lines.append("")
    lines.append(
        f"**Grand total reconciled:** {reconciliation['grand_total_other']:,} "
        f"(all pathogens reconcile: "
        f"{'YES' if reconciliation['all_reconcile'] else 'NO'})."
    )
    lines.append("")

    with out_md.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return out_md


# --------------------------------------------------------------------------- #
# Top-level orchestration (Req 1.1, 1.2, 1.3, 1.5, 2.6, 2.7, 2.8)
# --------------------------------------------------------------------------- #

def run_harmonization(
    *,
    program_dirs: Optional[dict[str, Path]] = None,
    out_processed: Optional[Path] = None,
) -> dict[str, Any]:
    """Run the full harmonization and emit every Task-2.9 artifact.

    Produces, from the real data:

    * ``data/interim/other_reconciliation.json`` (+ audit-md section),
    * ``data/interim/program_taxonomy.json``,
    * ``data/interim/decision_statement.json``,
    * ``docs/data_dictionary.md``,
    * ``data/processed/harmonized_<pathogen>.parquet`` (+ a `.sample.csv`)
      per pathogen at its feasibility resolution.

    Returns a summary dict (artifact paths, table shapes, coverage, reconciliation
    and taxonomy roll-ups) for the caller/report.
    """

    out_processed = out_processed or PROCESSED_ROOT
    out_processed.mkdir(parents=True, exist_ok=True)

    audit_report = _load_audit_report()
    reconciliation = reconcile_other(
        program_dirs=program_dirs, audit_report=audit_report
    )
    append_other_reconciliation_md(reconciliation)
    taxonomy = build_program_taxonomy(audit_report)
    decision = build_decision_statement()
    write_data_dictionary()

    resolutions = _load_feasibility_resolutions()
    acs = harmonize_census_acs()
    food_access = harmonize_food_access()

    tables: dict[str, Any] = {}
    for pathogen, resolution in resolutions.items():
        # PRIMARY weather source: nClimDiv statewide (national coverage). The
        # old single-station NOAA path is demoted — used only as a fallback if
        # nClimDiv produced no rows (recorded honestly).
        nclimdiv = harmonize_nclimdiv(resolution)
        if nclimdiv.get("table"):
            weather = nclimdiv
        else:
            weather = harmonize_noaa(resolution)
        cdc = harmonize_cdc_nors(resolution, pathogen=pathogen)
        table = harmonize_pathogen(
            pathogen, resolution,
            program_dirs=program_dirs, noaa=weather, acs=acs,
            food_access=food_access, cdc=cdc,
        )
        slug = pathogen.lower()
        parquet_path = out_processed / f"harmonized_{slug}.parquet"
        csv_path = out_processed / f"harmonized_{slug}.sample.csv"
        wrote_parquet = False
        if not table.empty:
            try:
                table.to_parquet(parquet_path, index=False)
                wrote_parquet = True
            except Exception as exc:  # noqa: BLE001 — fall back to CSV if no engine
                parquet_path = out_processed / f"harmonized_{slug}.csv"
                table.to_csv(parquet_path, index=False)
                wrote_parquet = False
                print(f"[harmonize] parquet unavailable for {pathogen}: {exc!r}; "
                      f"wrote CSV instead")
            table.head(50).to_csv(csv_path, index=False)

        # routine-only target rows vs total (Req 2.6 transparency)
        target_rows = int(table["is_target"].sum()) if not table.empty else 0
        tables[pathogen] = {
            "resolution": resolution,
            "rows": int(len(table)),
            "columns": int(table.shape[1]) if not table.empty else 0,
            "target_rows_routine_only": target_rows,
            "states": int(table["state"].nunique()) if not table.empty else 0,
            "periods": int(table["period"].nunique()) if not table.empty else 0,
            "parquet": str(parquet_path),
            "sample_csv": str(csv_path),
            "wrote_parquet": wrote_parquet,
            "weather_source": weather["coverage"].get("source", "noaa"),
            "weather_coverage": weather["coverage"],
            "cdc_coverage": cdc["coverage"],
            "weather_cells_nonmissing": (
                int(table["tmax_mean"].notna().sum())
                if (not table.empty and "tmax_mean" in table.columns) else 0
            ),
            "weather_states_nonmissing": (
                int(table.loc[table["tmax_mean"].notna(), "state"].nunique())
                if (not table.empty and "tmax_mean" in table.columns) else 0
            ),
            "cdc_cells_nonmissing": (
                int(table["cdc_outbreaks"].notna().sum())
                if (not table.empty and "cdc_outbreaks" in table.columns) else 0
            ),
        }

    summary = {
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "reporting_lag_days": REPORTING_LAG_DAYS,
        "availability_limitation": AVAILABILITY_LIMITATION,
        "other_reconciliation": {
            "all_reconcile": reconciliation["all_reconcile"],
            "per_pathogen": {
                p: {
                    "audit_other_count": e["audit_other_count"],
                    "reconciled_total": e["reconciled_total"],
                    "reconciles": e["reconciles"],
                    "categories": {k: v["count"] for k, v in e["categories"].items()},
                }
                for p, e in reconciliation["per_pathogen"].items()
            },
        },
        "program_taxonomy": {
            "total_codes_tagged": taxonomy["total_codes_tagged"],
            "untagged": taxonomy["untagged"],
            "by_category": {
                pathogen: {c: cc["codes"] for c, cc in cats.items()}
                for pathogen, cats in taxonomy["by_category"].items()
            },
        },
        "decision_statement_valid": decision.get("_valid", False),
        "acs_coverage": acs["coverage"],
        "food_access_coverage": food_access["coverage"],
        "tables": tables,
    }

    summary_path = INTERIM_ROOT / "harmonize_report.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return summary


if __name__ == "__main__":  # pragma: no cover - CLI entry for the full run
    result = run_harmonization()
    print("OTHER RECONCILIATION (sums to audit other_count):")
    for p, e in result["other_reconciliation"]["per_pathogen"].items():
        print(f"  {p}: audit={e['audit_other_count']} reconciled="
              f"{e['reconciled_total']} reconciles={e['reconciles']} "
              f"cats={e['categories']}")
    print("PROGRAM TAXONOMY by_category:")
    for p, cats in result["program_taxonomy"]["by_category"].items():
        print(f"  {p}: {cats}")
    print(f"  untagged: {result['program_taxonomy']['untagged']}")
    print(f"REPORTING_LAG_DAYS (ASSUMPTION): {result['reporting_lag_days']}")
    print("HARMONIZED TABLES:")
    for p, t in result["tables"].items():
        print(f"  {p}: rows={t['rows']} cols={t['columns']} "
              f"target_rows={t['target_rows_routine_only']} "
              f"states={t['states']} periods={t['periods']} res={t['resolution']}")
    print(f"  NOAA states covered (Salmonella pass): see coverage in report")
    print("HARMONIZE_DONE")
