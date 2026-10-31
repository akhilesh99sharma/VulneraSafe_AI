"""Dataset audit module (Phase 1, Task 2.4).

This module computes a real, per-dataset audit of the FSIS laboratory-sampling
programs before any modeling, so modeling targets rest on verified counts,
denominators, and coverage rather than assumptions (Req 3.1-3.4).

A *dataset* here is one FSIS program (pathogen family), formed by concatenating
all fiscal-year archives for that program. The three real programs — verified
from ``data/interim/fsis_scan_summary.json`` and ``data/interim/fsis_columns``
— are:

* ``raw_poultry_salmonella``  → Salmonella, result column ``salmonella_sp_analysis``
* ``rte_listeria``            → Listeria (Lm), result column ``lm_listeria_analysis``
* ``raw_beef_stec``           → STEC, result column ``stec_analysis``

The real FSIS result vocabulary (detected by value-counting the result columns)
is tri-state: ``Positive`` / ``Negative`` (with
``Confirmed Negative of a Previous Presumptive`` also negative) / everything
else (``NULL``, blank, lab-problem codes) → *other / indeterminate*. Positives
and negatives are **never** forced to cover every row — the ``other`` bucket is
reported explicitly (Req 3.1).

Positivity is computed per FSIS **sampling program/project code**
(``project_code``) so programs whose definitions differ are never silently
pooled, and also reported overall with the denominator clearly identified
(Req 3.1).

What this module deliberately does **not** fabricate:

* FSIS sampling files carry **no publication date**, so the reporting delay
  (Req 3.2/3.3) cannot be computed from the data. That is recorded as a gap via
  :func:`src.pipeline.integrity.record_gap` and the affected audit fields are
  left ``None`` — never a made-up number (Req 4.6).
* Any required field that cannot be computed marks the audit ``complete =
  False`` (incomplete) rather than dropping the dataset (Req 3.2).

Design reference: design.md ``AuditReport`` in "Provenance and audit".
"""

from __future__ import annotations

import datetime as _dt
import json
from collections import Counter
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from src.artifacts.schemas import (
    AuditReport,
    DuplicateFindings,
    LeakageCheck,
    ProgramPositivity,
    SchemaChange,
)
from src.pipeline import integrity
from src.pipeline.ingest import (
    FSIS_PROGRAM_DIRS,
    REPO_ROOT,
    _fiscal_year_from_name,
    _iter_local_tables,
)

__all__ = [
    "PROGRAM_META",
    "POSITIVE_LABELS",
    "NEGATIVE_LABELS",
    "classify_result",
    "tri_state_counts",
    "audit_dataframe",
    "audit_program",
    "run_audit",
    "write_audit_markdown",
]

INTERIM_ROOT = REPO_ROOT / "data" / "interim"
DOCS_REPORTS = REPO_ROOT / "docs" / "reports"

# --------------------------------------------------------------------------- #
# Program metadata — the REAL result columns per program (verified by column
# inspection, not guessed). ``result_column`` is the authoritative pathogen
# result for the program's pathogen.
# --------------------------------------------------------------------------- #

PROGRAM_META: dict[str, dict[str, str]] = {
    "raw_poultry_salmonella": {
        "pathogen": "Salmonella",
        "commodity": "raw_poultry",
        "result_column": "salmonella_sp_analysis",
    },
    "rte_listeria": {
        "pathogen": "Listeria",
        "commodity": "rte",
        "result_column": "lm_listeria_analysis",
    },
    "raw_beef_stec": {
        "pathogen": "STEC",
        "commodity": "raw_beef",
        "result_column": "stec_analysis",
    },
}

# Common FSIS field names (verified present in every program).
COL_ESTABLISHMENT_ID = "establishment_id"
COL_STATE = "establishment_state"
COL_PROJECT_CODE = "project_code"
COL_PROJECT_NAME = "project_name"
COL_COLLECTION_DATE = "collection_date"
COL_SAMPLE_NUMBER = "sample_number"
# Commodity/product category: raw_poultry has ``product_type``; rte/beef use
# ``sample_source_name`` as the closest product/commodity grouping present.
COL_PRODUCT_CANDIDATES = ("product_type", "sample_source_name")

#: Empirical ML label/result columns across all three programs. The Req 4.5
#: placeholder guard is scoped to these (never to identifier/free-text columns
#: such as ``form_id`` where a value like ``9999`` is a legitimate id).
_LABEL_COLUMNS: tuple[str, ...] = (
    "salmonella_sp_analysis",
    "lm_listeria_analysis",
    "non_lm_listeria_analysis",
    "stec_analysis",
    "pcr_stx_1_2_analysis",
    "pcr_eae_analysis",
    "campylobacter_analysis_1ml",
    "campylobacter_analysis_30ml",
    "salmonella_mpn_qualitative",
)

#: Result values that count as a positive detection (case-insensitive).
POSITIVE_LABELS: frozenset[str] = frozenset({"positive"})

#: Result values that count as a negative, including the confirmed-negative of
#: a previous presumptive result FSIS records.
NEGATIVE_LABELS: frozenset[str] = frozenset(
    {"negative", "confirmed negative of a previous presumptive"}
)


# --------------------------------------------------------------------------- #
# Tri-state result classification (Req 3.1)
# --------------------------------------------------------------------------- #

def classify_result(value: Any) -> str:
    """Classify one result cell as ``"positive"``, ``"negative"`` or ``"other"``.

    FSIS results are coded strings. ``NULL``/blank/None, lab-problem codes and
    anything outside the known positive/negative vocabulary fall into
    ``"other"`` (not-tested / indeterminate) and are **never** forced into
    positive or negative (Req 3.1).
    """

    if value is None:
        return "other"
    text = str(value).strip()
    if not text or text.upper() == "NULL":
        return "other"
    low = text.lower()
    if low in POSITIVE_LABELS:
        return "positive"
    if low in NEGATIVE_LABELS:
        return "negative"
    return "other"


def tri_state_counts(series: pd.Series) -> tuple[int, int, int]:
    """Return ``(positives, negatives, other)`` for a result ``series``.

    The three buckets sum to ``len(series)`` exactly (tri-state), so
    ``pos + neg + other == observations`` always holds (Property 3, Req 3.1).
    """

    pos = neg = other = 0
    for value in series.tolist():
        kind = classify_result(value)
        if kind == "positive":
            pos += 1
        elif kind == "negative":
            neg += 1
        else:
            other += 1
    return pos, neg, other


def _detect_vocabulary(series: pd.Series) -> tuple[list[str], list[str], list[str]]:
    """Return the distinct (positive, negative, other) label vocabularies present."""
    pos: set[str] = set()
    neg: set[str] = set()
    other: set[str] = set()
    for value in series.dropna().astype(str).unique().tolist():
        text = value.strip()
        kind = classify_result(text)
        label = text if text and text.upper() != "NULL" else "<blank/NULL>"
        if kind == "positive":
            pos.add(label)
        elif kind == "negative":
            neg.add(label)
        else:
            other.add(label)
    # a NULL / NaN presence also contributes a blank "other" label
    if series.isna().any():
        other.add("<blank/NULL>")
    return sorted(pos), sorted(neg), sorted(other)


# --------------------------------------------------------------------------- #
# Date parsing helpers (Req 3.1 yearly/quarterly, Req 3.3 ranges)
# --------------------------------------------------------------------------- #

def _parse_dates(series: pd.Series) -> tuple[pd.Series, int]:
    """Parse a collection-date series to datetimes; return (parsed, n_failures).

    Non-parsable entries become ``NaT``; the count of values that were present
    (non-empty) but failed to parse is returned so parse failures are reported
    honestly rather than hidden (Req 3.3)."""

    raw = series.astype("string")
    present = raw.notna() & (raw.str.strip() != "") & (raw.str.upper() != "NULL")
    parsed = pd.to_datetime(raw, errors="coerce")
    failures = int((present & parsed.isna()).sum())
    return parsed, failures


def _fiscal_year_label(dt: pd.Timestamp) -> str:
    """US federal fiscal year label: FY starts Oct 1 of the prior calendar year."""
    year = dt.year + 1 if dt.month >= 10 else dt.year
    return f"FY{year}"


# --------------------------------------------------------------------------- #
# Per-program positivity breakdown (Req 3.1 — never pool differing programs)
# --------------------------------------------------------------------------- #

def _positivity_by_program(df: pd.DataFrame, result_col: str) -> list[ProgramPositivity]:
    """Compute positivity per ``project_code`` so programs are never pooled."""
    out: list[ProgramPositivity] = []
    if COL_PROJECT_CODE not in df.columns:
        return out
    name_col = COL_PROJECT_NAME if COL_PROJECT_NAME in df.columns else None
    for code, group in df.groupby(df[COL_PROJECT_CODE].astype("string").fillna("<none>")):
        pos, neg, other = tri_state_counts(group[result_col])
        denom = pos + neg  # program denominator = tested samples (pos + neg)
        project_name = ""
        if name_col is not None:
            names = group[name_col].dropna().astype(str)
            project_name = names.iloc[0] if not names.empty else ""
        out.append(
            ProgramPositivity(
                project_code=str(code),
                project_name=project_name,
                observations=int(len(group)),
                positives=int(pos),
                negatives=int(neg),
                other=int(other),
                denominator=int(denom),
                positivity_rate=(pos / denom) if denom else None,
            )
        )
    out.sort(key=lambda r: r["observations"], reverse=True)
    return out


# --------------------------------------------------------------------------- #
# Duplicate detection (report, never silently drop)
# --------------------------------------------------------------------------- #

def _detect_duplicates(df: pd.DataFrame, result_col: str) -> DuplicateFindings:
    """Count exact duplicate rows and likely-duplicate sample records.

    * exact duplicate rows: identical across all columns.
    * duplicate sample numbers: repeated ``sample_number`` values.
    * likely-duplicate records: repeated
      ``(establishment, collection_date, product, result)`` tuples.
    Nothing is dropped — counts are reported for the audit (Req audit integrity).
    """

    exact = int(df.duplicated(keep="first").sum())

    dup_sample = 0
    if COL_SAMPLE_NUMBER in df.columns:
        dup_sample = int(df.duplicated(subset=[COL_SAMPLE_NUMBER], keep="first").sum())

    product_col = next((c for c in COL_PRODUCT_CANDIDATES if c in df.columns), None)
    key_cols = [
        c
        for c in (COL_ESTABLISHMENT_ID, COL_COLLECTION_DATE, product_col, result_col)
        if c is not None and c in df.columns
    ]
    likely = int(df.duplicated(subset=key_cols, keep="first").sum()) if key_cols else 0

    return DuplicateFindings(
        exact_duplicate_rows=exact,
        duplicate_sample_numbers=dup_sample,
        likely_duplicate_records=likely,
        likely_duplicate_key="+".join(key_cols) if key_cols else "",
    )


# --------------------------------------------------------------------------- #
# Schema diff across fiscal years (Req: FSIS changed schemas over the years)
# --------------------------------------------------------------------------- #

def diff_schemas(fy_schemas: dict[int, dict[str, str]]) -> list[SchemaChange]:
    """Diff column sets + dtypes FY-to-FY (ordered by fiscal year).

    ``fy_schemas`` maps a fiscal year to ``{column: dtype}``. Returns one
    :class:`SchemaChange` per adjacent FY pair recording added/removed columns
    and dtype changes. The first FY is emitted with ``from_fy = None`` so the
    initial schema is captured."""

    changes: list[SchemaChange] = []
    prev_fy: Optional[int] = None
    prev_cols: dict[str, str] = {}
    for fy in sorted(fy_schemas):
        cols = fy_schemas[fy]
        added = sorted(set(cols) - set(prev_cols))
        removed = sorted(set(prev_cols) - set(cols))
        dtype_changes = sorted(
            f"{c}: {prev_cols[c]} -> {cols[c]}"
            for c in set(cols) & set(prev_cols)
            if prev_cols[c] != cols[c]
        )
        if prev_fy is None or added or removed or dtype_changes:
            changes.append(
                SchemaChange(
                    from_fy=prev_fy,
                    to_fy=fy,
                    added_columns=added,
                    removed_columns=removed,
                    dtype_changes=dtype_changes,
                )
            )
        prev_fy, prev_cols = fy, cols
    return changes


# --------------------------------------------------------------------------- #
# Leakage checks (Req 3.4)
# --------------------------------------------------------------------------- #

def _leakage_checks(
    df: pd.DataFrame, parsed_dates: pd.Series, parse_failures: int
) -> list[LeakageCheck]:
    """Run per-dataset leakage checks and return pass/fail with triggers.

    FSIS sampling files carry only a collection date (no feature/label split at
    this stage), so the checks that are *computable now* are:

    * ``collection_date_present`` — a usable collection date exists for most
      rows (needed to enforce a temporal cutoff downstream).
    * ``no_future_collection_dates`` — no collection date lies in the future
      (a future-dated sample would be a time-ordering/leakage red flag).
    """

    checks: list[LeakageCheck] = []

    n = len(df)
    n_parsed = int(parsed_dates.notna().sum())
    present_ratio = (n_parsed / n) if n else 0.0
    checks.append(
        LeakageCheck(
            name="collection_date_present",
            passed=bool(present_ratio >= 0.5),
            triggering_fields=[] if present_ratio >= 0.5 else [COL_COLLECTION_DATE],
            detail=(
                f"{n_parsed}/{n} rows have a parseable collection_date "
                f"({present_ratio:.3f}); {parse_failures} present-but-unparsable."
            ),
        )
    )

    today = pd.Timestamp(_dt.date.today())
    future = parsed_dates.dropna() > today
    n_future = int(future.sum())
    checks.append(
        LeakageCheck(
            name="no_future_collection_dates",
            passed=bool(n_future == 0),
            triggering_fields=[] if n_future == 0 else [COL_COLLECTION_DATE],
            detail=f"{n_future} rows have a collection_date after today ({today.date()}).",
        )
    )

    return checks


# --------------------------------------------------------------------------- #
# Audit one assembled program DataFrame (Req 3.1-3.4)
# --------------------------------------------------------------------------- #

def audit_dataframe(
    df: pd.DataFrame,
    *,
    program: str,
    pathogen: str,
    commodity: str,
    result_column: str,
    fy_schemas: Optional[dict[int, dict[str, str]]] = None,
    publication_date: Optional[str] = None,
) -> AuditReport:
    """Audit a single assembled program frame into an :class:`AuditReport`.

    Every required field is computed from the real data; anything uncomputable
    is recorded as a gap and flips ``complete`` to ``False`` (Req 3.2). The
    empirical frame is checked for placeholder sentinels first (Req 4.5)."""

    gaps: list[dict] = []
    complete = True

    # Req 4.5 protects empirical ML *labels* from placeholder values. Apply the
    # placeholder guard to the pathogen result/label columns specifically, not
    # to free-form identifier columns (e.g. ``form_id``) where a value such as
    # ``9999`` is a legitimate FSIS form id, not a fabricated placeholder.
    label_cols = [c for c in _LABEL_COLUMNS if c in df.columns]
    if label_cols:
        integrity.assert_no_placeholder_in_empirical(df[label_cols], program)

    # --- result column presence -------------------------------------------
    if result_column not in df.columns:
        integrity.record_gap(
            gaps,
            field=result_column,
            reason=f"result column '{result_column}' absent from {program}",
            dataset=program,
        )
        complete = False
        result_series = pd.Series([], dtype="object")
        pos = neg = other = 0
        pos_labels: list[str] = []
        neg_labels: list[str] = []
        other_labels: list[str] = []
        by_program: list[ProgramPositivity] = []
    else:
        result_series = df[result_column]
        pos, neg, other = tri_state_counts(result_series)
        pos_labels, neg_labels, other_labels = _detect_vocabulary(result_series)
        by_program = _positivity_by_program(df, result_column)

    observations = int(len(df))
    denominator = pos + neg  # tested samples (positives + negatives)
    positivity = (pos / denominator) if denominator else None
    if denominator == 0:
        integrity.record_gap(
            gaps,
            field="positivity_rate",
            reason="program denominator (pos+neg) is zero; positivity undefined",
            dataset=program,
        )
        complete = False

    # --- dates: ranges, parse failures, yearly/quarterly (Req 3.1, 3.3) ----
    yearly: dict[str, int] = {}
    quarterly: dict[str, int] = {}
    pathogen_by_fy: dict[str, dict[str, Optional[float]]] = {}
    date_range: list[Optional[str]] = [None, None]
    parse_failures = 0
    if COL_COLLECTION_DATE in df.columns:
        parsed, parse_failures = _parse_dates(df[COL_COLLECTION_DATE])
        valid = parsed.dropna()
        if not valid.empty:
            date_range = [valid.min().date().isoformat(), valid.max().date().isoformat()]
        else:
            integrity.record_gap(
                gaps,
                field="collection_date_range",
                reason="no parseable collection dates",
                dataset=program,
            )
            complete = False
        # yearly (calendar) and quarterly distributions
        yearly = {
            str(int(y)): int(c)
            for y, c in valid.dt.year.value_counts().sort_index().items()
        }
        q_series = valid.dt.year.astype(int).astype(str) + "-Q" + valid.dt.quarter.astype(int).astype(str)
        quarterly = {str(k): int(v) for k, v in q_series.value_counts().sort_index().items()}

        # pathogen positivity broken out by fiscal year (Req 3.1 breakdowns)
        if result_column in df.columns:
            tmp = pd.DataFrame(
                {"fy": parsed.map(lambda d: _fiscal_year_label(d) if pd.notna(d) else None),
                 "result": result_series.values}
            )
            for fy_label, grp in tmp.dropna(subset=["fy"]).groupby("fy"):
                p, nn, oo = tri_state_counts(grp["result"])
                den = p + nn
                pathogen_by_fy[str(fy_label)] = {
                    "observations": float(len(grp)),
                    "positives": float(p),
                    "negatives": float(nn),
                    "other": float(oo),
                    "positivity_rate": (p / den) if den else None,
                }
    else:
        parsed = pd.Series([], dtype="datetime64[ns]")
        integrity.record_gap(
            gaps,
            field=COL_COLLECTION_DATE,
            reason="collection_date column absent",
            dataset=program,
        )
        complete = False

    # --- commodity / product category distribution (Req 3.1 breakdown) -----
    product_col = next((c for c in COL_PRODUCT_CANDIDATES if c in df.columns), None)
    commodity_distribution: dict[str, int] = {}
    if product_col is not None:
        commodity_distribution = {
            str(k): int(v)
            for k, v in df[product_col].astype("string").fillna("<none>").value_counts().items()
        }
    else:
        integrity.record_gap(
            gaps,
            field="product/commodity category",
            reason=f"no product category column ({COL_PRODUCT_CANDIDATES}) present",
            dataset=program,
        )
        # product category is a breakdown, not strictly required; do not flip complete.

    # --- establishment identifiers (Req 3.1) ------------------------------
    est_present = COL_ESTABLISHMENT_ID in df.columns
    est_count = 0
    if est_present:
        est_count = int(df[COL_ESTABLISHMENT_ID].dropna().nunique())
    else:
        integrity.record_gap(
            gaps,
            field=COL_ESTABLISHMENT_ID,
            reason="establishment id column absent",
            dataset=program,
        )
        complete = False

    # --- geographic coverage (Req 3.1 location identifiers) ----------------
    state_count = 0
    state_missing_frac = 1.0
    if COL_STATE in df.columns:
        states = df[COL_STATE].astype("string")
        present = states.notna() & (states.str.strip() != "")
        state_count = int(states[present].nunique())
        state_missing_frac = float(1.0 - (present.sum() / len(df))) if len(df) else 1.0
    else:
        integrity.record_gap(
            gaps,
            field=COL_STATE,
            reason="establishment_state column absent",
            dataset=program,
        )
        complete = False

    # --- publication date & reporting delay (Req 3.2, 3.3) -----------------
    # FSIS sampling files carry NO publication date; record a gap, never fabricate.
    reporting_delay: Optional[int] = None
    if publication_date is None:
        integrity.record_gap(
            gaps,
            field="publication_date",
            reason=(
                "FSIS laboratory-sampling files contain no publication/"
                "public-availability date column; reporting delay cannot be "
                "computed from the data (not fabricated)."
            ),
            dataset=program,
        )
        integrity.record_gap(
            gaps,
            field="reporting_delay_days",
            reason="depends on unavailable publication_date",
            dataset=program,
        )
        complete = False
    elif date_range[1] is not None:
        try:
            pub = _dt.date.fromisoformat(publication_date)
            latest = _dt.date.fromisoformat(date_range[1])
            reporting_delay = (pub - latest).days
        except ValueError:
            integrity.record_gap(
                gaps, field="reporting_delay_days",
                reason="publication_date not ISO-parseable", dataset=program,
            )
            complete = False

    leakage = _leakage_checks(df, parsed, parse_failures)
    duplicates = _detect_duplicates(df, result_column if result_column in df.columns else "")
    schema_changes = diff_schemas(fy_schemas) if fy_schemas else []

    return AuditReport(
        dataset=program,
        pathogen=pathogen,
        commodity=commodity,
        result_column=result_column,
        positive_labels=pos_labels,
        negative_labels=neg_labels,
        other_labels=other_labels,
        observation_count=observations,
        positive_count=int(pos),
        negative_count=int(neg),
        other_count=int(other),
        program_denominator=int(denominator),
        positivity_rate=positivity,
        positivity_by_program=by_program,
        pathogen_by_fiscal_year=pathogen_by_fy,
        yearly_distribution=yearly,
        quarterly_distribution=quarterly,
        commodity_distribution=commodity_distribution,
        establishment_id_present=est_present,
        establishment_count=est_count,
        collection_date_range=date_range,
        collection_date_parse_failures=int(parse_failures),
        publication_date=publication_date,
        reporting_delay_days=reporting_delay,
        state_coverage_count=state_count,
        state_coverage_missing_fraction=round(state_missing_frac, 6),
        leakage_checks=leakage,
        duplicates=duplicates,
        schema_changes=schema_changes,
        gaps=gaps,
        complete=complete,
    )


# --------------------------------------------------------------------------- #
# Load + audit one program from its real archives
# --------------------------------------------------------------------------- #

def _load_program_frame(
    program: str, program_dirs: Optional[dict[str, Path]] = None
) -> tuple[pd.DataFrame, dict[int, dict[str, str]]]:
    """Load + concatenate every fiscal-year archive for ``program``.

    Returns the concatenated frame plus a ``{fiscal_year: {col: dtype}}`` map
    for the FY-to-FY schema diff. A ``_fiscal_year`` column is added so the
    audit can group by FY."""

    program_dirs = program_dirs or FSIS_PROGRAM_DIRS
    pdir = program_dirs[program]
    frames: list[pd.DataFrame] = []
    fy_schemas: dict[int, dict[str, str]] = {}
    archives = sorted(p for p in pdir.iterdir() if p.suffix.lower() in (".zip", ".json", ".csv"))
    for archive in archives:
        fy = _fiscal_year_from_name(archive.name)
        for _name, _raw, df in _iter_local_tables(archive):
            if df is None:
                continue
            if fy is not None:
                fy_schemas[fy] = {str(c): str(df[c].dtype) for c in df.columns}
                df = df.copy()
                df["_fiscal_year"] = fy
            frames.append(df)
    if not frames:
        return pd.DataFrame(), fy_schemas
    combined = pd.concat(frames, ignore_index=True, sort=False)
    return combined, fy_schemas


def audit_program(
    program: str, program_dirs: Optional[dict[str, Path]] = None
) -> AuditReport:
    """Load and audit one FSIS program end to end (Req 3.1-3.4)."""
    meta = PROGRAM_META[program]
    df, fy_schemas = _load_program_frame(program, program_dirs)
    return audit_dataframe(
        df,
        program=program,
        pathogen=meta["pathogen"],
        commodity=meta["commodity"],
        result_column=meta["result_column"],
        fy_schemas=fy_schemas,
    )


# --------------------------------------------------------------------------- #
# Full audit over all real programs + artifact emission
# --------------------------------------------------------------------------- #

def run_audit(
    program_dirs: Optional[dict[str, Path]] = None,
    *,
    out_json: Optional[Path] = None,
    out_md: Optional[Path] = None,
) -> dict[str, AuditReport]:
    """Audit every real FSIS program and emit the machine- + human-readable reports.

    Writes ``data/interim/audit_report.json`` (per program, all fields) and
    ``docs/reports/data_audit.md`` (real-count tables). Returns the per-program
    :class:`AuditReport` map."""

    program_dirs = program_dirs or FSIS_PROGRAM_DIRS
    reports: dict[str, AuditReport] = {}
    for program in PROGRAM_META:
        if program not in program_dirs:
            continue
        reports[program] = audit_program(program, program_dirs)

    out_json = out_json or (INTERIM_ROOT / "audit_report.json")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(
        json.dumps(reports, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    out_md = out_md or (DOCS_REPORTS / "data_audit.md")
    write_audit_markdown(reports, out_md)
    return reports


# --------------------------------------------------------------------------- #
# Human-readable markdown report
# --------------------------------------------------------------------------- #

def _fmt_rate(rate: Optional[float]) -> str:
    return "n/a" if rate is None else f"{rate:.4f} ({rate * 100:.2f}%)"


def write_audit_markdown(reports: dict[str, AuditReport], path: Path) -> Path:
    """Write the human-readable data-audit markdown with real-count tables."""

    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# FSIS Dataset Audit")
    lines.append("")
    lines.append(
        f"Generated {_dt.datetime.now().isoformat(timespec='seconds')}. "
        "All counts are computed from the real FSIS laboratory-sampling "
        "archives (FY2014-FY2026). Positive/negative/other are tri-state; the "
        "`other` bucket is not-tested/indeterminate/blank and is never folded "
        "into positives or negatives (Req 3.1)."
    )
    lines.append("")

    # --- headline table ----------------------------------------------------
    lines.append("## Headline per-pathogen counts")
    lines.append("")
    lines.append(
        "| Pathogen | Program | Observations | Positives | Negatives | Other | "
        "Denominator (pos+neg) | Overall positivity | Complete |"
    )
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|:--:|")
    for program, r in reports.items():
        lines.append(
            f"| {r['pathogen']} | {program} | {r['observation_count']:,} | "
            f"{r['positive_count']:,} | {r['negative_count']:,} | "
            f"{r['other_count']:,} | {r['program_denominator']:,} | "
            f"{_fmt_rate(r['positivity_rate'])} | "
            f"{'yes' if r['complete'] else 'NO (incomplete)'} |"
        )
    lines.append("")

    for program, r in reports.items():
        lines.append(f"## {r['pathogen']} — `{program}`")
        lines.append("")
        lines.append(f"- Result column audited: `{r['result_column']}`")
        lines.append(f"- Positive vocabulary: {r['positive_labels']}")
        lines.append(f"- Negative vocabulary: {r['negative_labels']}")
        lines.append(f"- Other/indeterminate vocabulary: {r['other_labels']}")
        lines.append(
            f"- Collection-date range: {r['collection_date_range'][0]} .. "
            f"{r['collection_date_range'][1]} "
            f"({r['collection_date_parse_failures']} present-but-unparsable)"
        )
        lines.append(
            f"- Establishments: {r['establishment_count']:,} distinct "
            f"(id present: {r['establishment_id_present']})"
        )
        lines.append(
            f"- Geographic coverage: {r['state_coverage_count']} distinct states; "
            f"missing fraction {r['state_coverage_missing_fraction']:.4f}"
        )
        lines.append(
            f"- Publication date: {r['publication_date'] or 'UNAVAILABLE (gap)'}; "
            f"reporting delay: "
            f"{r['reporting_delay_days'] if r['reporting_delay_days'] is not None else 'UNAVAILABLE (gap)'}"
        )
        lines.append("")

        # positivity by FY
        if r["pathogen_by_fiscal_year"]:
            lines.append("### Positivity by fiscal year")
            lines.append("")
            lines.append("| Fiscal year | Observations | Positives | Negatives | Other | Positivity |")
            lines.append("|---|---:|---:|---:|---:|---:|")
            for fy in sorted(r["pathogen_by_fiscal_year"]):
                d = r["pathogen_by_fiscal_year"][fy]
                lines.append(
                    f"| {fy} | {int(d['observations']):,} | {int(d['positives']):,} | "
                    f"{int(d['negatives']):,} | {int(d['other']):,} | "
                    f"{_fmt_rate(d['positivity_rate'])} |"
                )
            lines.append("")

        # positivity by program/project code
        if r["positivity_by_program"]:
            lines.append("### Positivity by sampling program / project code (not pooled)")
            lines.append("")
            lines.append("| Project code | Project name | Observations | Positives | Negatives | Other | Positivity |")
            lines.append("|---|---|---:|---:|---:|---:|---:|")
            for pp in r["positivity_by_program"][:40]:
                lines.append(
                    f"| {pp['project_code']} | {pp['project_name'][:48]} | "
                    f"{pp['observations']:,} | {pp['positives']:,} | "
                    f"{pp['negatives']:,} | {pp['other']:,} | "
                    f"{_fmt_rate(pp['positivity_rate'])} |"
                )
            lines.append("")

        # duplicates
        dup = r["duplicates"]
        lines.append("### Duplicate findings (reported, not dropped)")
        lines.append("")
        lines.append(f"- Exact duplicate rows: {dup['exact_duplicate_rows']:,}")
        lines.append(f"- Duplicate sample numbers: {dup['duplicate_sample_numbers']:,}")
        lines.append(
            f"- Likely-duplicate records on `{dup['likely_duplicate_key']}`: "
            f"{dup['likely_duplicate_records']:,}"
        )
        lines.append("")

        # schema changes
        lines.append("### Schema changes across fiscal years")
        lines.append("")
        if r["schema_changes"]:
            for sc in r["schema_changes"]:
                frm = f"FY{sc['from_fy']}" if sc["from_fy"] else "(baseline)"
                lines.append(
                    f"- {frm} -> FY{sc['to_fy']}: "
                    f"added={sc['added_columns']} removed={sc['removed_columns']} "
                    f"dtype_changes={sc['dtype_changes']}"
                )
        else:
            lines.append("- No schema changes detected across fiscal years.")
        lines.append("")

        # leakage
        lines.append("### Leakage checks")
        lines.append("")
        for lc in r["leakage_checks"]:
            lines.append(
                f"- `{lc['name']}`: {'PASS' if lc['passed'] else 'FAIL'} — {lc['detail']}"
            )
        lines.append("")

        # gaps
        if r["gaps"]:
            lines.append("### Recorded gaps (uncomputable fields — never fabricated)")
            lines.append("")
            for g in r["gaps"]:
                lines.append(f"- `{g['field']}`: {g['reason']}")
            lines.append("")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


if __name__ == "__main__":  # pragma: no cover - CLI entry for the full run
    result = run_audit()
    for prog, rep in result.items():
        print(
            f"{prog}: obs={rep['observation_count']} pos={rep['positive_count']} "
            f"neg={rep['negative_count']} other={rep['other_count']} "
            f"positivity={rep['positivity_rate']} complete={rep['complete']}"
        )
    print("AUDIT_DONE")
