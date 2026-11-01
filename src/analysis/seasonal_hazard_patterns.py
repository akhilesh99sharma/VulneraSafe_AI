"""S02 — Seasonal / Temporal Hazard Patterns (descriptive).

S02 is an additive analytical module that decomposes each FSIS-monitored
pathogen's historical OBSERVED positivity time series into a month-of-year and a
calendar-quarter seasonality profile plus a long-run annual trend. It answers a
single operational question: in which parts of the calendar year is each hazard
(Salmonella in raw poultry, Listeria in RTE, STEC in raw beef) most elevated, so
that inspection and testing cadence can be planned seasonally.

The module is STRICTLY DESCRIPTIVE. It trains no model, produces no forecast, and
makes no contamination claim. Every value it reports is OBSERVED FSIS surveillance
positivity, aggregated into calendar-month and calendar-quarter buckets plus an
ordinal-year OLS trend slope. Where a bucket lacks enough samples to compute an
honest statistic, S02 records an explicit ``availability_status = "unavailable"``
with a reason and the actual count found, and computes NO value — it never
interpolates, estimates, carries forward, or substitutes a placeholder.

The module reuses the dated-series machinery already built for S04
(``src/analysis/emerging_risk.py``) READ-ONLY — it introduces no new ingestion, no
new data source, and does not touch any S01/S03–S07 cache, source file, or web
file. It mirrors the identity/honesty conventions of its siblings (S05
``human_comparison.py``, S07 ``county_community_impact.py``): a fixed
``MODULE_ID``/``METHOD_VERSION``, a dedicated cache, a single source file.

Identity (Req 1.1, 1.2): ``MODULE_ID = "S02"``, ``METHOD_VERSION = "s02.v1"``,
implemented in ``src/analysis/seasonal_hazard_patterns.py``, caching to
``data/interim/s02_seasonal_hazard_patterns.json``.

This file holds the Task-1 analysis CORE (pure given injected records/series).
The offline orchestration/cache-write entry point
(``compute_seasonal_hazard_patterns``) and the tolerant ``load_cache`` reader are
Task 2; the helpers here are structured so Task 2 can call them cleanly.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Optional

# Read-only reuse from siblings — S02 CALLS these but never mutates their inputs
# or outputs (Req 1.4, 2.1). Confirmed signatures/return shapes against the real
# source before import:
#   _iter_raw_records(program_dir) -> yields (fiscal_year, record_dict)
#   _build_series(records, analysis_col, resolution) -> (series, meta) where
#       series == {state: [ {period: "YYYY-MM", period_start: iso, n, pos}, ... ]}
#   _parse_date(value) -> Optional[datetime.date]
#   _period_label(d, resolution) -> "YYYY-MM" (monthly) | "YYYY-Qn" (quarterly)
#   _period_start(d, resolution) -> datetime.date (first day of the period)
#   _PATHOGEN_CONFIG -> {pathogen: {dir, analysis_col, product_col, commodity}}
#   wilson_ci(positives, n) -> (low, high) or (None, None) when n <= 0
from src.analysis.emerging_risk import (  # noqa: F401  (re-exported for Task 2)
    _PATHOGEN_CONFIG,
    _build_series,
    _iter_raw_records,
    _parse_date,
    _period_label,
    _period_start,
)
from src.analysis.program_product import wilson_ci

REPO_ROOT = Path(__file__).resolve().parents[2]
INTERIM_DIR = REPO_ROOT / "data" / "interim"
CACHE_PATH = INTERIM_DIR / "s02_seasonal_hazard_patterns.json"

MODULE_ID = "S02"
METHOD_VERSION = "s02.v1"

# --- Minimum-sample gates (documented, testable; Req 4.1) ----------------- #
#: Each calendar-month bucket's pooled ``n`` must meet this to report a rate.
MIN_BUCKET_SAMPLES_MONTH = 30
#: Each calendar-quarter bucket's pooled ``n`` must meet this to report a rate.
MIN_BUCKET_SAMPLES_QUARTER = 30
#: Distinct years of history required before an annual trend slope is reported.
MIN_YEARS_FOR_TREND = 3

# --- Method strings (recorded in the cache so every choice is auditable) --- #
RESOLUTION = "monthly"
AGGREGATION = "pooled_positivity"
CI_METHOD = "wilson_95"
TREND_METHOD = "ordinal_year_ols_slope"

#: Quarter labels in canonical order; a month ``m`` maps to ``(m - 1) // 3 + 1``.
_QUARTER_LABELS = ("Q1", "Q2", "Q3", "Q4")


# --------------------------------------------------------------------------- #
# Pooling the per-state monthly series into one national monthly list
# --------------------------------------------------------------------------- #
def _pool_monthly_series(series: dict[str, list[dict]]) -> list[dict]:
    """Flatten the ``{state: [cell, ...]}`` map from
    ``_build_series(..., resolution="monthly")`` into one national list of
    monthly records, each carrying ``(year, month, n, pos)``.

    Each input ``cell`` carries ``period`` ("YYYY-MM"), ``period_start`` (iso
    date), ``n`` and ``pos``. The national grain is the honest one for a
    calendar-time seasonality question (geography is S04/S06/S07's lens) and it
    maximizes per-bucket sample counts.

    This is READ-ONLY over ``series``: it reads each cell's fields and builds
    fresh dicts; it never mutates the input cells or the series map (Req 1.4).

    Returns one record per ``(state, period)`` cell (not yet collapsed across
    states) so callers retain the full set of monthly observations; bucketing in
    :func:`_bucket_rate` sums across these. Year/month are derived from the
    ``period`` label, falling back to ``period_start`` when the label is
    malformed.
    """
    pooled: list[dict] = []
    for cells in series.values():
        for cell in cells:
            year, month = _year_month_of_cell(cell)
            if year is None or month is None:
                continue
            pooled.append(
                {
                    "year": year,
                    "month": month,
                    "n": int(cell.get("n", 0) or 0),
                    "pos": int(cell.get("pos", 0) or 0),
                }
            )
    return pooled


def _year_month_of_cell(cell: dict) -> tuple[Optional[int], Optional[int]]:
    """Derive ``(year, month)`` from a monthly cell's ``period`` ("YYYY-MM"),
    falling back to its ``period_start`` iso date. Returns ``(None, None)`` when
    neither yields a valid calendar month 1..12."""
    period = cell.get("period")
    if isinstance(period, str):
        parts = period.split("-")
        if len(parts) >= 2:
            try:
                year = int(parts[0])
                month = int(parts[1])
                if 1 <= month <= 12:
                    return year, month
            except ValueError:
                pass
    # Fallback: parse the iso period_start.
    start = cell.get("period_start")
    if start is not None:
        d = _parse_date(start)
        if d is not None:
            return d.year, d.month
    return None, None


# --------------------------------------------------------------------------- #
# Bucket aggregation (pooled positivity + Wilson CI) — Req 3.1, 3.3
# --------------------------------------------------------------------------- #
def _month_key(rec: dict) -> str:
    """Calendar-month key "01".."12" for a pooled monthly record."""
    return f"{int(rec['month']):02d}"


def _quarter_key(rec: dict) -> str:
    """Calendar-quarter key "Q1".."Q4" for a pooled monthly record."""
    return f"Q{(int(rec['month']) - 1) // 3 + 1}"


def _all_month_labels() -> list[str]:
    """All 12 calendar-month bucket labels in order."""
    return [f"{m:02d}" for m in range(1, 13)]


def _bucket_rate(
    cells: list[dict], key_fn: Callable[[dict], str]
) -> dict[str, dict[str, Any]]:
    """Group pooled monthly ``cells`` by the bucket ``key_fn`` returns (calendar
    month "01".."12" or quarter "Q1".."Q4"), summing ``n`` and ``pos`` per bucket
    and computing the pooled ``rate = pos / n`` (only when ``n > 0``) plus the
    Wilson 95% CI via ``wilson_ci(pos, n)``.

    ``n`` and ``pos`` are recorded for EVERY bucket regardless of availability
    (Req 3.3). Every month bucket (all 12) and every quarter bucket (all 4) is
    always produced; a bucket with no observed data has ``n = 0`` (and therefore
    ``rate``/CI ``None``). Pooling (Σpos / Σn) is the maximum-likelihood
    positivity estimate and matches how every sibling module reports positivity.

    Returns ``{label: {n, pos, rate, ci_low, ci_high}}``. Gating and the seasonal
    index are applied by the caller, not here, so this stays a pure aggregation.
    """
    # Seed all buckets so absent months/quarters are present-but-empty.
    if key_fn is _quarter_key:
        buckets: dict[str, dict[str, Any]] = {q: {"n": 0, "pos": 0} for q in _QUARTER_LABELS}
    elif key_fn is _month_key:
        buckets = {lbl: {"n": 0, "pos": 0} for lbl in _all_month_labels()}
    else:  # generic fallback: discover labels from the data
        buckets = {}

    for rec in cells:
        label = key_fn(rec)
        b = buckets.setdefault(label, {"n": 0, "pos": 0})
        b["n"] += int(rec.get("n", 0) or 0)
        b["pos"] += int(rec.get("pos", 0) or 0)

    out: dict[str, dict[str, Any]] = {}
    for label, b in buckets.items():
        n = b["n"]
        pos = b["pos"]
        if n > 0:
            rate: Optional[float] = pos / n
            lo, hi = wilson_ci(pos, n)
        else:
            rate = None
            lo, hi = (None, None)
        out[label] = {"n": n, "pos": pos, "rate": rate, "ci_low": lo, "ci_high": hi}
    return out


def _overall_rate(cells: list[dict]) -> Optional[float]:
    """Pathogen pooled overall positivity Σpos / Σn over all pooled cells; None
    when the total denominator is 0 (avoids division by zero)."""
    total_n = sum(int(c.get("n", 0) or 0) for c in cells)
    total_pos = sum(int(c.get("pos", 0) or 0) for c in cells)
    if total_n <= 0:
        return None
    return total_pos / total_n


def _seasonal_index(bucket_rate: Optional[float], overall_rate: Optional[float]) -> Optional[float]:
    """Seasonal index ``bucket_rate / overall_rate`` (Req 3.1). Skipped (None)
    when the bucket is unavailable (``bucket_rate is None``) or the pathogen's
    overall rate is 0/None, so no index is ever invented for a gated bucket."""
    if bucket_rate is None or not overall_rate:
        return None
    return bucket_rate / overall_rate


# --------------------------------------------------------------------------- #
# Minimum-sample gating — Req 4.2, 4.3, 4.5
# --------------------------------------------------------------------------- #
def _gate_bucket(
    label: str,
    agg: dict[str, Any],
    min_samples: int,
    *,
    view: str,
    overall_rate: Optional[float],
) -> dict[str, Any]:
    """Apply the minimum-sample gate to one aggregated bucket and shape its final
    record. ``view`` is "month" or "quarter" (names the gate in the reason).

    * Passing (``n >= min_samples``) → ``availability_status = "available"`` with
      ``rate``, ``ci_low``, ``ci_high`` and ``seasonal_index`` reported.
    * Failing (``n < min_samples``) → ``availability_status = "unavailable"`` with
      an ``unavailable_reason`` naming the gate AND the actual count, and
      ``rate``/CI/``seasonal_index`` held at ``None`` (never fabricated).

    ``n`` and ``pos`` are recorded in BOTH cases (Req 3.3, 4.3).
    """
    n = agg["n"]
    pos = agg["pos"]
    if n >= min_samples:
        rate = agg["rate"]
        return {
            "label": label,
            "n": n,
            "pos": pos,
            "rate": rate,
            "ci_low": agg["ci_low"],
            "ci_high": agg["ci_high"],
            "seasonal_index": _seasonal_index(rate, overall_rate),
            "availability_status": "available",
            "unavailable_reason": None,
        }
    reason = f"Only {n} samples; {view} bucket requires >= {min_samples}."
    return {
        "label": label,
        "n": n,
        "pos": pos,
        "rate": None,
        "ci_low": None,
        "ci_high": None,
        "seasonal_index": None,
        "availability_status": "unavailable",
        "unavailable_reason": reason,
    }


def _build_bucket_records(
    cells: list[dict],
    key_fn: Callable[[dict], str],
    min_samples: int,
    *,
    view: str,
    overall_rate: Optional[float],
) -> list[dict]:
    """Aggregate ``cells`` into buckets via :func:`_bucket_rate`, apply the gate,
    and return the gated records in canonical label order (all 12 months or all 4
    quarters). Convenience wrapper so Task 2 can emit a pathogen's buckets in one
    call."""
    agg = _bucket_rate(cells, key_fn)
    order = _QUARTER_LABELS if key_fn is _quarter_key else _all_month_labels()
    # Include any extra labels a generic key_fn produced, after the canonical set.
    ordered_labels = list(order) + [lbl for lbl in sorted(agg) if lbl not in order]
    return [
        _gate_bucket(
            label, agg[label], min_samples, view=view, overall_rate=overall_rate
        )
        for label in ordered_labels
        if label in agg
    ]


# --------------------------------------------------------------------------- #
# Peak selection — argmax over AVAILABLE buckets only — Req 3.4
# --------------------------------------------------------------------------- #
def _peak_label(bucket_records: list[dict]) -> Optional[str]:
    """The label of the bucket with the highest ``rate`` among buckets whose
    ``availability_status == "available"``; ``None`` when no bucket in the view is
    available. A gated-out bucket (unavailable) is NEVER chosen even if its raw
    rate is higher (Req 3.4). Ties break on the canonical (ascending-label) order,
    since ``bucket_records`` is already in canonical order and ``max`` keeps the
    first maximizer.
    """
    best_label: Optional[str] = None
    best_rate: Optional[float] = None
    for rec in bucket_records:
        if rec.get("availability_status") != "available":
            continue
        rate = rec.get("rate")
        if rate is None:
            continue
        if best_rate is None or rate > best_rate:
            best_rate = rate
            best_label = rec["label"]
    return best_label


# --------------------------------------------------------------------------- #
# Trend — closed-form ordinal-year OLS slope over pooled annual positivity
# --------------------------------------------------------------------------- #
def _annual_rates(cells: list[dict]) -> dict[int, float]:
    """Pooled annual positivity ``Σpos / Σn`` per distinct year over the pooled
    monthly ``cells``. A year with a zero denominator is dropped (no rate is
    invented). Returns ``{year: rate}``."""
    by_year_n: dict[int, int] = {}
    by_year_pos: dict[int, int] = {}
    for rec in cells:
        year = int(rec["year"])
        by_year_n[year] = by_year_n.get(year, 0) + int(rec.get("n", 0) or 0)
        by_year_pos[year] = by_year_pos.get(year, 0) + int(rec.get("pos", 0) or 0)
    return {y: by_year_pos[y] / by_year_n[y] for y in by_year_n if by_year_n[y] > 0}


def _trend_slope(annual_rates: dict[int, float]) -> tuple[Optional[float], list[int]]:
    """Closed-form ordinal-year OLS slope over pooled ANNUAL positivity.

    ``annual_rates`` maps distinct year -> pooled annual positivity rate. Years
    are sorted ascending and indexed ``0, 1, 2, …`` (ordinal-year, so the slope
    is "change in positivity per year" regardless of gaps between calendar
    years). The slope is the ordinary-least-squares estimate

        slope = Σ (x_i - x̄)(y_i - ȳ) / Σ (x_i - x̄)²

    Returns ``(slope, years_used)``. The slope is ``None`` when fewer than
    ``MIN_YEARS_FOR_TREND`` distinct years are present (the year gate; Req 4.4) or
    when the x-variance is 0 (degenerate). ``years_used`` always lists the
    distinct years found, sorted ascending, so a gated trend still records them.

    This is descriptive summary arithmetic over OBSERVED annual rates — not a
    trained predictor and never extrapolated into a future period (Req 5.3).
    """
    years = sorted(annual_rates)
    if len(years) < MIN_YEARS_FOR_TREND:
        return None, years

    xs = list(range(len(years)))
    ys = [annual_rates[y] for y in years]
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    sxx = sum((x - x_mean) ** 2 for x in xs)
    if sxx == 0:
        return None, years
    sxy = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    return sxy / sxx, years


def _build_trend(cells: list[dict]) -> dict[str, Any]:
    """Shape a pathogen's trend block: compute the annual rates, the ordinal-year
    OLS slope, and apply the distinct-year gate (Req 3.2, 4.4).

    * ``>= MIN_YEARS_FOR_TREND`` distinct years → ``availability_status =
      "available"`` with the ``slope`` and ``years_used``.
    * Fewer distinct years → ``availability_status = "unavailable"``,
      ``unavailable_reason`` naming the gate and the count, ``slope`` held None,
      ``years_used`` recording the years found.
    """
    annual = _annual_rates(cells)
    slope, years = _trend_slope(annual)
    n_years = len(years)
    if slope is None and n_years < MIN_YEARS_FOR_TREND:
        reason = f"Only {n_years} distinct years; trend requires >= {MIN_YEARS_FOR_TREND}."
        status = "unavailable"
    else:
        reason = None
        status = "available"
    return {
        "method": TREND_METHOD,
        "slope": slope,
        "years_used": years,
        "availability_status": status,
        "unavailable_reason": reason,
    }


# --------------------------------------------------------------------------- #
# Per-pathogen assembly (pure given pooled cells) — structured so Task 2's
# compute_seasonal_hazard_patterns can call it directly after reading records.
# --------------------------------------------------------------------------- #
def _analyze_pooled_cells(cells: list[dict]) -> dict[str, Any]:
    """Compute a pathogen's full seasonal decomposition from pooled national
    monthly ``cells`` (each ``{year, month, n, pos}`` from
    :func:`_pool_monthly_series`). PURE: reads ``cells`` only, writes nothing.

    Returns the per-pathogen analytic payload (without identity/audit fields,
    which Task 2 adds): ``overall_rate``, ``month_buckets`` (12), ``quarter_buckets``
    (4), ``trend``, ``peak_month`` and ``peak_quarter``. Peaks are the argmax rate
    over AVAILABLE buckets only, so a gated bucket can never win.
    """
    overall = _overall_rate(cells)
    month_buckets = _build_bucket_records(
        cells, _month_key, MIN_BUCKET_SAMPLES_MONTH, view="month", overall_rate=overall
    )
    quarter_buckets = _build_bucket_records(
        cells, _quarter_key, MIN_BUCKET_SAMPLES_QUARTER, view="quarter", overall_rate=overall
    )
    return {
        "overall_rate": overall,
        "month_buckets": month_buckets,
        "quarter_buckets": quarter_buckets,
        "trend": _build_trend(cells),
        "peak_month": _peak_label(month_buckets),
        "peak_quarter": _peak_label(quarter_buckets),
    }


# --------------------------------------------------------------------------- #
# Task 2 — cache build orchestration + tolerant reader
# --------------------------------------------------------------------------- #
def _fsis_input_id(commodity: str, pathogen: str) -> str:
    """Deterministic identifier of the FSIS input used for a pathogen (Req 2.3).

    Derived from the pathogen config — ``_PATHOGEN_CONFIG`` carries no explicit
    id, so we compose one from ``commodity`` + lower-cased ``pathogen`` to match
    the design's worked example ("raw_poultry_salmonella"). This is a stable,
    reproducible string, not a path, so the recorded audit id does not drift with
    the checkout location.
    """
    return f"{commodity}_{pathogen.lower()}"


def _periods_read(pooled: list[dict]) -> list[str]:
    """Sorted distinct "YYYY-MM" labels present in a pathogen's pooled monthly
    cells (Req 2.3, 8.2) — the auditable set of reporting periods read. Built
    from the pooled ``(year, month)`` so it reflects exactly what was observed."""
    labels = {f"{int(c['year']):04d}-{int(c['month']):02d}" for c in pooled}
    return sorted(labels)


def _round_floats(obj: Any, round_to: int) -> Any:
    """Recursively round every ``float`` in ``obj`` to ``round_to`` decimals so
    two runs over identical inputs are byte-identical (Req 8.1, 8.3). Walks dicts
    and lists; leaves ``int``/``str``/``None``/``bool`` untouched. ``bool`` is a
    subclass of ``int`` (not ``float``) so it is never coerced."""
    if isinstance(obj, float):
        return round(obj, round_to)
    if isinstance(obj, dict):
        return {k: _round_floats(v, round_to) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_round_floats(v, round_to) for v in obj]
    return obj


#: Fixed deterministic stamp used only if the exporter resolver is unavailable;
#: mirrors S04's ``emerging_risk._GENERATED_AT_FALLBACK`` so S02 never depends on
#: the wall clock.
_GENERATED_AT_FALLBACK = "2026-01-01T00:00:00Z"


def _resolve_generated_at() -> str:
    """Resolve the deterministic ``generated_at`` stamp (Req 8.1, 8.3).

    Mirrors the project convention: the exporter's ``resolve_generated_at`` is
    the single source of truth (``VULNERASAFE_GENERATED_AT`` env →
    ``SOURCE_DATE_EPOCH`` → input provenance → the fixed documented default), so
    the S02 cache stamp agrees with every exported artifact. Imported lazily to
    avoid a circular import (the exporter imports the analysis modules). If the
    exporter cannot be imported for any reason, fall back to a fixed constant
    that mirrors S04's ``_GENERATED_AT_FALLBACK`` — the default is NEVER
    ``datetime.now()``, so repeated runs stay byte-identical.
    """
    try:
        from src.artifacts.exporter import resolve_generated_at

        return resolve_generated_at()
    except Exception:  # pragma: no cover - defensive; keeps the build deterministic
        return os.environ.get("VULNERASAFE_GENERATED_AT") or _GENERATED_AT_FALLBACK


def _unavailable_pathogen_block(pathogen: str, commodity: str, reason: str) -> dict[str, Any]:
    """A pathogen-level ``availability_status = "unavailable"`` block for a
    pathogen whose series could not be built (Req 2.4). Carries the identity and
    audit fields with empty analytic payload; computes NO value and never raises,
    so the module continues with the other pathogens."""
    return {
        "pathogen": pathogen,
        "commodity": commodity,
        "fsis_input_id": _fsis_input_id(commodity, pathogen),
        "periods_read": [],
        "availability_status": "unavailable",
        "unavailable_reason": reason,
        "overall_rate": None,
        "month_buckets": [],
        "quarter_buckets": [],
        "trend": {
            "method": TREND_METHOD,
            "slope": None,
            "years_used": [],
            "availability_status": "unavailable",
            "unavailable_reason": reason,
        },
        "peak_month": None,
        "peak_quarter": None,
    }


def compute_seasonal_hazard_patterns(*, round_to: int = 6) -> dict[str, Any]:
    """Orchestrate S02 over all three pathogens and write the S02 cache (Req 2.3,
    2.4, 8.1, 8.2, 8.3). The single offline entry point, run under ``__main__``
    like the siblings.

    For each pathogen in ``_PATHOGEN_CONFIG`` (Salmonella/raw_poultry,
    Listeria/rte, STEC/raw_beef) this reads the raw FSIS records READ-ONLY via
    ``_iter_raw_records(cfg["dir"])``, builds the monthly per-state series with
    ``_build_series(records, analysis_col, resolution="monthly")`` (which returns
    ``(series, meta)``), pools the series into one national monthly list via
    :func:`_pool_monthly_series`, and runs the pure core
    :func:`_analyze_pooled_cells` to get ``overall_rate``, the 12 month buckets,
    the 4 quarter buckets, the trend block, ``peak_month`` and ``peak_quarter``.

    A pathogen whose series fails to build (no records / empty series) is emitted
    as a pathogen-level unavailable block with a missing-input reason, and the run
    CONTINUES with the remaining pathogens (Req 2.4) — it never raises.

    Determinism (Req 8.1, 8.3): ``generated_at`` is a resolved, non-wall-clock
    stamp; every float is rounded to ``round_to``; the cache is written with
    ``sort_keys=True``. Two runs over identical inputs are byte-identical.
    """
    pathogens_out: dict[str, Any] = {}

    for pathogen, cfg in _PATHOGEN_CONFIG.items():
        commodity = cfg["commodity"]
        analysis_col = cfg["analysis_col"]
        records = list(_iter_raw_records(cfg["dir"]))
        series, _meta = _build_series(records, analysis_col, resolution="monthly")

        if not series:
            pathogens_out[pathogen] = _unavailable_pathogen_block(
                pathogen,
                commodity,
                f"Required FSIS input '{_fsis_input_id(commodity, pathogen)}' is "
                "absent or unreadable; no monthly series could be built.",
            )
            continue

        pooled = _pool_monthly_series(series)
        if not pooled:
            pathogens_out[pathogen] = _unavailable_pathogen_block(
                pathogen,
                commodity,
                f"Required FSIS input '{_fsis_input_id(commodity, pathogen)}' "
                "yielded no dated monthly observations.",
            )
            continue

        analysis = _analyze_pooled_cells(pooled)
        pathogens_out[pathogen] = {
            "pathogen": pathogen,
            "commodity": commodity,
            "fsis_input_id": _fsis_input_id(commodity, pathogen),
            "periods_read": _periods_read(pooled),
            "availability_status": "available",
            "unavailable_reason": None,
            **analysis,
        }

    cache: dict[str, Any] = {
        "module_id": MODULE_ID,
        "method_version": METHOD_VERSION,
        "generated_at": _resolve_generated_at(),
        "resolution": RESOLUTION,
        "aggregation": AGGREGATION,
        "ci_method": CI_METHOD,
        "trend_method": TREND_METHOD,
        "min_bucket_samples_month": MIN_BUCKET_SAMPLES_MONTH,
        "min_bucket_samples_quarter": MIN_BUCKET_SAMPLES_QUARTER,
        "min_years_for_trend": MIN_YEARS_FOR_TREND,
        "pathogens": pathogens_out,
    }

    cache = _round_floats(cache, round_to)

    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(
        json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8"
    )
    return cache


def load_cache() -> Optional[dict[str, Any]]:
    """Tolerant read of the S02 cache (mirrors S05/S07 ``load_cache``): return the
    parsed cache dict, or ``None`` when the file is absent or cannot be parsed
    (``(OSError, ValueError) -> None``)."""
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
    return None


if __name__ == "__main__":
    compute_seasonal_hazard_patterns()
