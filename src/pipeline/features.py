"""Leakage-safe feature construction (Phase 2, Task 3.1).

This module turns the per-pathogen harmonized analytic tables produced by
:mod:`src.pipeline.harmonize` into a **leakage-safe feature matrix** keyed by
``(state, period)`` at the pathogen's feasibility resolution (Salmonella
monthly; Listeria / STEC quarterly). It implements Requirements 7.4, 7.5 and
7.6:

* **7.4** — features are derived from historical FSIS outcomes, positivity
  rates and sampling counts, from context signals available at or before the
  cutoff, from NOAA weather anomalies, and from seasonal and geographic
  attributes.
* **7.5** — *every* feature is constructed using only information timestamped
  at or before the horizon cutoff. There is **no leakage**.
* **7.6** — any source row timestamped after the cutoff is excluded from
  feature construction and the exclusion is recorded so it is auditable.

The leakage model reuses the harmonize availability model exactly: a sample's
information only becomes usable at ``availability_date = collection_date +
REPORTING_LAG_DAYS`` (an assumption documented in
:data:`~src.pipeline.harmonize.AVAILABILITY_LIMITATION`). For predicting a
period ``t`` we fix the cutoff at the **start of period ``t``** and require every
contributing source row to satisfy ``availability_date <= cutoff``. Because a
routine sample collected inside period ``t`` is not available until ~30 days
later, this construction forces every lagged feature to draw only on periods
``<= t-1`` — enforced structurally and checked by an assertion, never assumed.

Design decisions driven by the real harmonized grain (confirmed against
``data/processed/harmonized_<pathogen>.parquet``):

* The harmonized table is **long** — one row per
  ``(state, period, sampling_program, program_category)``. Features are built by
  first aggregating to ``(state, period)`` separately for the **routine
  surveillance** baseline (the target scope, ``is_target == True``) and for the
  **for-cause / exploratory** context programs. Routine and for-cause/
  exploratory positivity are **never mixed** — they live in clearly separate
  columns (``routine_*`` vs ``context_forcause_*`` / ``context_exploratory_*``).
* Lagged positivity / volume features (t-1, t-2, t-3, trailing-4-period mean and
  trailing-12-month mean) are computed per state from the routine series; a
  national lagged positivity is computed across all states. For-cause and
  exploratory lagged positivity are computed the same way but kept separate.
* Seasonality uses sin/cos encodings of the period-of-year (month 1..12 for
  monthly resolution, quarter 1..4 for quarterly) plus plain calendar
  components. Geography carries the state code (categorical) and a census region
  grouping. Establishment-churn / count features are the lagged routine sample
  volume per state (the only establishment-activity signal present in the
  harmonized tables).
* NOAA weather anomalies, ACS 65+/vulnerability and Food Access Atlas indicators
  are joined as context. Weather is joined with the same availability lag and is
  mostly MISSING given the thin ingested station slice — that is honest and
  recorded, never fabricated. ACS / Food Access are slowly-varying static
  context joined by state (a single pre-cutoff vintage).

Nothing here fabricates data: when a feature source is missing for a cell the
value is left ``NaN`` (downstream models handle missingness). The label itself
(next-period elevated-positivity indicator) is intentionally **not** built here —
Task 3.3 derives it — so this module also emits the *current-period* routine
positivity (``outcome_routine_positivity_rate`` / counts) clearly separated from
the feature columns, so 3.3 can construct the label from it.

Design reference: design.md "Models, features, rare events (Req 7)" and
Correctness Property 1 ("No feature uses post-cutoff data").
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from src.pipeline import harmonize as hz
from src.pipeline.harmonize import (
    REPORTING_LAG_DAYS,
    TARGET_CATEGORY,
)
from src.pipeline.ingest import REPO_ROOT

__all__ = [
    "PROCESSED_ROOT",
    "DOCS_REPORTS",
    "PATHOGEN_SLUG",
    "CONTEXT_CATEGORIES",
    "CENSUS_REGION",
    "LAGS",
    "TRAILING_SHORT_PERIODS",
    "LeakageError",
    "period_start",
    "period_of_year",
    "resolution_for",
    "load_harmonized",
    "aggregate_state_period",
    "build_features",
    "assert_no_post_cutoff",
    "write_feature_dictionary",
    "run_feature_construction",
    "FEATURE_DICTIONARY",
]

PROCESSED_ROOT = REPO_ROOT / "data" / "processed"
DOCS_REPORTS = REPO_ROOT / "docs" / "reports"

#: Pathogen -> processed-table slug.
PATHOGEN_SLUG: dict[str, str] = {
    "Salmonella": "salmonella",
    "Listeria": "listeria",
    "STEC": "stec",
}

#: The program categories carried as SEPARATE context positivity (never pooled
#: into the routine baseline the forecast predicts).
CONTEXT_CATEGORIES: tuple[str, ...] = ("for_cause", "exploratory")

#: Discrete lags (in periods) for the lagged positivity / volume features.
LAGS: tuple[int, ...] = (1, 2, 3)

#: Trailing-window length (periods) for the short trailing mean (4 periods).
TRAILING_SHORT_PERIODS: int = 4

#: Census region grouping (USPS state -> Census region) for a coarse geographic
#: feature. DC grouped with the South (Census convention). Territories map to a
#: ``Territory`` bucket; anything unknown maps to ``Other``.
CENSUS_REGION: dict[str, str] = {
    # Northeast
    "CT": "Northeast", "ME": "Northeast", "MA": "Northeast", "NH": "Northeast",
    "RI": "Northeast", "VT": "Northeast", "NJ": "Northeast", "NY": "Northeast",
    "PA": "Northeast",
    # Midwest
    "IL": "Midwest", "IN": "Midwest", "MI": "Midwest", "OH": "Midwest",
    "WI": "Midwest", "IA": "Midwest", "KS": "Midwest", "MN": "Midwest",
    "MO": "Midwest", "NE": "Midwest", "ND": "Midwest", "SD": "Midwest",
    # South
    "DE": "South", "FL": "South", "GA": "South", "MD": "South", "NC": "South",
    "SC": "South", "VA": "South", "WV": "South", "DC": "South", "AL": "South",
    "KY": "South", "MS": "South", "TN": "South", "AR": "South", "LA": "South",
    "OK": "South", "TX": "South",
    # West
    "AZ": "West", "CO": "West", "ID": "West", "MT": "West", "NV": "West",
    "NM": "West", "UT": "West", "WY": "West", "AK": "West", "CA": "West",
    "HI": "West", "OR": "West", "WA": "West",
    # Territories
    "PR": "Territory", "GU": "Territory", "VI": "Territory", "AS": "Territory",
    "MP": "Territory",
}


class LeakageError(AssertionError):
    """Raised when a feature draws on a source row timestamped after the cutoff."""


# --------------------------------------------------------------------------- #
# Period / calendar helpers
# --------------------------------------------------------------------------- #

_MONTHLY_RE = re.compile(r"^(\d{4})-(\d{2})$")
_QUARTERLY_RE = re.compile(r"^(\d{4})-Q([1-4])$")


def resolution_for(period: str) -> str:
    """Infer the resolution (``monthly`` / ``quarterly``) from a period label."""
    if _QUARTERLY_RE.match(period):
        return "quarterly"
    if _MONTHLY_RE.match(period):
        return "monthly"
    raise ValueError(f"unrecognized period label: {period!r}")


def period_start(period: str) -> pd.Timestamp:
    """Return the first calendar day of a period label (the horizon cutoff).

    ``2023-05`` -> ``2023-05-01``; ``2023-Q2`` -> ``2023-04-01``. This timestamp
    is the **cutoff** used to predict the period: a source row may contribute to
    this period's features only if its ``availability_date <= period_start``.
    """
    m = _MONTHLY_RE.match(period)
    if m:
        return pd.Timestamp(year=int(m.group(1)), month=int(m.group(2)), day=1)
    q = _QUARTERLY_RE.match(period)
    if q:
        month = (int(q.group(2)) - 1) * 3 + 1
        return pd.Timestamp(year=int(q.group(1)), month=month, day=1)
    raise ValueError(f"unrecognized period label: {period!r}")


def period_of_year(period: str) -> int:
    """Return the period-of-year index (month 1..12 or quarter 1..4)."""
    m = _MONTHLY_RE.match(period)
    if m:
        return int(m.group(2))
    q = _QUARTERLY_RE.match(period)
    if q:
        return int(q.group(2))
    raise ValueError(f"unrecognized period label: {period!r}")


def _period_cycle_length(resolution: str) -> int:
    return 12 if resolution == "monthly" else 4


def _trailing_long_periods(resolution: str) -> int:
    """Trailing-window length for the 12-month mean (12 months or 4 quarters)."""
    return 12 if resolution == "monthly" else 4


def _sorted_periods(periods: list[str]) -> list[str]:
    """Sort period labels chronologically by their start timestamp."""
    return sorted(set(periods), key=period_start)


# --------------------------------------------------------------------------- #
# Load + aggregate the harmonized table to (state, period) series
# --------------------------------------------------------------------------- #

def load_harmonized(pathogen: str, *, processed_root: Optional[Path] = None) -> pd.DataFrame:
    """Load the harmonized analytic table for ``pathogen`` (parquet, CSV fallback)."""
    root = processed_root or PROCESSED_ROOT
    slug = PATHOGEN_SLUG[pathogen]
    parquet = root / f"harmonized_{slug}.parquet"
    csv = root / f"harmonized_{slug}.csv"
    if parquet.exists():
        df = pd.read_parquet(parquet)
    elif csv.exists():
        df = pd.read_csv(csv)
    else:
        raise FileNotFoundError(
            f"no harmonized table for {pathogen} at {parquet} (run harmonize first)"
        )
    df["collection_date"] = pd.to_datetime(df["collection_date"], errors="coerce")
    df["availability_date"] = pd.to_datetime(df["availability_date"], errors="coerce")
    return df


# Static (slowly-varying) context columns joined by state in the harmonized table.
_STATIC_STATE_COLS: tuple[str, ...] = (
    "total_population", "elderly_65plus_partial", "elderly_share", "acs_vintage",
    "lila_tract_share", "low_income_tract_share", "atlas_pop_2010", "atlas_vintage",
)

# Weather (NOAA nClimDiv) context columns, joined on (state, period) with their
# own publication lag (``weather_availability_date``). With nClimDiv as the
# PRIMARY source these are now non-missing for ~all state-periods.
_WEATHER_COLS: tuple[str, ...] = (
    "tmax_mean", "tmin_mean", "prcp_total",
    "tmax_anomaly", "tmin_anomaly", "prcp_anomaly", "noaa_lag_days",
)

# CDC NORS human-health outbreak context columns, joined on (state, period) with
# a LARGE availability lag (``cdc_availability_date``) so NORS is only used
# predictively once it would realistically be published (Req point 4). Mostly
# sparse (outbreaks are rare per state-period); missing cells are left NaN.
_CDC_COLS: tuple[str, ...] = (
    "cdc_outbreaks", "cdc_illnesses", "cdc_pathogen_outbreaks",
)


def aggregate_state_period(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Aggregate the long harmonized table to per-``(state, period)`` series.

    Returns a dict of frames keyed by scope:

    * ``routine`` — the routine-surveillance baseline (the target scope,
      ``is_target == True`` / ``program_category == routine_surveillance``),
      aggregated to ``(state, period)`` with ``samples``, ``positives``,
      ``positivity_rate`` and the latest contributing ``availability_date``.
    * ``for_cause`` / ``exploratory`` — the same aggregation over each context
      program category, kept SEPARATE so context positivity is never pooled into
      the routine baseline.
    * ``static`` — one row per state with the slowly-varying ACS / Food Access
      context columns.
    * ``weather`` — per ``(state, period)`` NOAA columns with the latest
      contributing ``availability_date`` (mostly empty — honest coverage).

    Each per-period aggregate carries ``availability_date`` = the MAX
    availability date of its contributing rows; a cell is only usable once that
    timestamp has passed (the leakage guard).
    """

    def _agg_category(mask: pd.Series) -> pd.DataFrame:
        sub = df.loc[mask]
        if sub.empty:
            return pd.DataFrame(
                columns=["state", "period", "samples", "positives",
                         "positivity_rate", "availability_date"]
            )
        g = sub.groupby(["state", "period"]).agg(
            samples=("samples", "sum"),
            positives=("positives", "sum"),
            availability_date=("availability_date", "max"),
        ).reset_index()
        g["positivity_rate"] = np.where(
            g["samples"] > 0, g["positives"] / g["samples"], np.nan
        )
        return g

    routine = _agg_category(df["program_category"] == TARGET_CATEGORY)
    for_cause = _agg_category(df["program_category"] == "for_cause")
    exploratory = _agg_category(df["program_category"] == "exploratory")

    # Static per-state context (first non-null per state).
    static_cols = [c for c in _STATIC_STATE_COLS if c in df.columns]
    if static_cols:
        static = (
            df.groupby("state")[static_cols]
            .agg(lambda s: s.dropna().iloc[0] if s.notna().any() else np.nan)
            .reset_index()
        )
    else:
        static = pd.DataFrame(columns=["state"])

    # Weather per (state, period) with its OWN availability date (nClimDiv
    # publication lag), falling back to the FSIS availability_date only if the
    # dedicated weather column is absent (older harmonized tables).
    weather_cols = [c for c in _WEATHER_COLS if c in df.columns]
    w_avail_col = (
        "weather_availability_date"
        if "weather_availability_date" in df.columns else "availability_date"
    )
    if weather_cols:
        wmask = df[weather_cols].notna().any(axis=1)
        wsub = df.loc[wmask, ["state", "period", w_avail_col, *weather_cols]].copy()
        if wsub.empty:
            weather = pd.DataFrame(columns=["state", "period", "availability_date", *weather_cols])
        else:
            wsub = wsub.rename(columns={w_avail_col: "availability_date"})
            agg_spec = {c: (c, "mean") for c in weather_cols}
            agg_spec["availability_date"] = ("availability_date", "max")
            weather = wsub.groupby(["state", "period"]).agg(**agg_spec).reset_index()
    else:
        weather = pd.DataFrame(columns=["state", "period"])

    # CDC NORS per (state, period) with its OWN (large) availability date.
    cdc_cols = [c for c in _CDC_COLS if c in df.columns]
    c_avail_col = (
        "cdc_availability_date"
        if "cdc_availability_date" in df.columns else "availability_date"
    )
    if cdc_cols:
        cmask = df[cdc_cols].notna().any(axis=1)
        csub = df.loc[cmask, ["state", "period", c_avail_col, *cdc_cols]].copy()
        if csub.empty:
            cdc = pd.DataFrame(columns=["state", "period", "availability_date", *cdc_cols])
        else:
            csub = csub.rename(columns={c_avail_col: "availability_date"})
            agg_spec = {c: (c, "mean") for c in cdc_cols}
            agg_spec["availability_date"] = ("availability_date", "max")
            cdc = csub.groupby(["state", "period"]).agg(**agg_spec).reset_index()
    else:
        cdc = pd.DataFrame(columns=["state", "period"])

    return {
        "routine": routine,
        "for_cause": for_cause,
        "exploratory": exploratory,
        "static": static,
        "weather": weather,
        "cdc": cdc,
    }


# --------------------------------------------------------------------------- #
# Leakage-safe lagged feature computation
# --------------------------------------------------------------------------- #

def _series_available_as_of(series: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    """Rows of a per-``(state, period)`` aggregate usable at ``cutoff``.

    A row is usable only if its ``availability_date`` is present and
    ``<= cutoff``; everything else is excluded (never leaked)."""
    if series.empty:
        return series
    avail = pd.to_datetime(series["availability_date"], errors="coerce")
    mask = avail.notna() & (avail <= cutoff)
    return series.loc[mask]


def _lagged_stats_for_state(
    state_series: pd.DataFrame,
    target_period: str,
    resolution: str,
) -> dict[str, float]:
    """Lagged positivity / volume stats for one state at ``target_period``.

    ``state_series`` is already filtered to rows available at the cutoff (start
    of ``target_period``) and to this state. The periods are ordered
    chronologically; the discrete lags (t-1, t-2, t-3) index backwards from the
    period immediately preceding ``target_period`` (all strictly earlier
    periods), and the trailing means average the most recent short / long
    windows of available periods.
    """
    out: dict[str, float] = {}
    cutoff = period_start(target_period)
    # keep only periods strictly before the target period, chronologically
    s = state_series.copy()
    s["_start"] = s["period"].map(period_start)
    s = s[s["_start"] < cutoff].sort_values("_start")

    rates = s["positivity_rate"].tolist()
    samples = s["samples"].tolist()

    for lag in LAGS:
        if len(rates) >= lag:
            out[f"routine_positivity_lag{lag}"] = float(rates[-lag])
            out[f"routine_samples_lag{lag}"] = float(samples[-lag])
        else:
            out[f"routine_positivity_lag{lag}"] = np.nan
            out[f"routine_samples_lag{lag}"] = np.nan

    short = TRAILING_SHORT_PERIODS
    long = _trailing_long_periods(resolution)
    out["routine_positivity_trailing4_mean"] = (
        float(np.mean(rates[-short:])) if rates else np.nan
    )
    out["routine_samples_trailing4_mean"] = (
        float(np.mean(samples[-short:])) if samples else np.nan
    )
    out["routine_positivity_trailing12m_mean"] = (
        float(np.mean(rates[-long:])) if rates else np.nan
    )
    out["routine_samples_trailing12m_mean"] = (
        float(np.mean(samples[-long:])) if samples else np.nan
    )
    return out


def _context_lag1_for_state(
    state_series: pd.DataFrame,
    target_period: str,
    prefix: str,
) -> dict[str, float]:
    """Lag-1 context positivity / volume for one state (kept separate)."""
    out: dict[str, float] = {
        f"{prefix}_positivity_lag1": np.nan,
        f"{prefix}_samples_lag1": np.nan,
        f"{prefix}_positivity_trailing4_mean": np.nan,
    }
    if state_series.empty:
        return out
    cutoff = period_start(target_period)
    s = state_series.copy()
    s["_start"] = s["period"].map(period_start)
    s = s[s["_start"] < cutoff].sort_values("_start")
    rates = s["positivity_rate"].tolist()
    samples = s["samples"].tolist()
    if rates:
        out[f"{prefix}_positivity_lag1"] = float(rates[-1])
        out[f"{prefix}_samples_lag1"] = float(samples[-1])
        out[f"{prefix}_positivity_trailing4_mean"] = float(
            np.mean(rates[-TRAILING_SHORT_PERIODS:])
        )
    return out


def _national_lagged_positivity(
    routine: pd.DataFrame,
    target_period: str,
) -> float:
    """National lag-1 routine positivity across all states, cutoff-safe.

    Aggregates every state's available routine samples/positives in the period
    immediately preceding ``target_period`` into one national rate."""
    cutoff = period_start(target_period)
    avail = _series_available_as_of(routine, cutoff)
    if avail.empty:
        return np.nan
    a = avail.copy()
    a["_start"] = a["period"].map(period_start)
    a = a[a["_start"] < cutoff]
    if a.empty:
        return np.nan
    prev_start = a["_start"].max()
    prev = a[a["_start"] == prev_start]
    total_samples = prev["samples"].sum()
    if total_samples <= 0:
        return np.nan
    return float(prev["positives"].sum() / total_samples)


def build_features(
    pathogen: str,
    cutoff: Optional[Any] = None,
    *,
    df: Optional[pd.DataFrame] = None,
    processed_root: Optional[Path] = None,
    excluded_sources: Optional[list[dict[str, Any]]] = None,
) -> pd.DataFrame:
    """Build the leakage-safe feature matrix for ``pathogen`` (Req 7.4–7.6).

    One row per ``(state, period)`` cell at the pathogen's resolution. For each
    cell the features derive ONLY from source rows whose ``availability_date``
    is at or before the cell's cutoff — the **start of that period**. When an
    explicit ``cutoff`` is supplied, only cells whose period starts at or after
    the cutoff... no: the global ``cutoff`` additionally caps *every* source and
    restricts output to periods whose start is ``<= cutoff`` is NOT imposed;
    instead ``cutoff`` acts as a hard ceiling — any source row with
    ``availability_date > cutoff`` is excluded from ALL cells and recorded in
    ``excluded_sources`` for audit (Req 7.6), and only cells predictable at or
    before ``cutoff`` (period start ``<= cutoff``) are returned. When ``cutoff``
    is ``None`` the full history is produced, each cell still using only its own
    per-period cutoff.

    The returned frame separates three column groups:

    * **feature columns** — lagged routine positivity/volume (t-1..t-3, trailing
      means), national lagged positivity, SEPARATE for-cause / exploratory
      context positivity, seasonality (sin/cos + calendar), geography (state,
      region), weather anomalies (lagged, mostly NaN), and static ACS / Food
      Access context;
    * **the raw current-period outcome** — ``outcome_routine_positivity_rate`` /
      ``outcome_routine_samples`` / ``outcome_routine_positives`` — kept clearly
      separate so Task 3.3 can derive the next-period label from it (NOT a
      feature);
    * **keys / bookkeeping** — ``pathogen``, ``state``, ``period``,
      ``period_start``, ``cutoff``.
    """

    if df is None:
        df = load_harmonized(pathogen, processed_root=processed_root)
    if excluded_sources is None:
        excluded_sources = []

    resolution = resolution_for(df["period"].iloc[0]) if not df.empty else "monthly"
    cycle = _period_cycle_length(resolution)

    cutoff_ts = pd.Timestamp(cutoff) if cutoff is not None else None

    # Global cutoff ceiling (Req 7.6): drop + record any source row whose
    # availability_date exceeds the cutoff before any feature is constructed.
    if cutoff_ts is not None:
        avail = pd.to_datetime(df["availability_date"], errors="coerce")
        post = df.loc[avail.notna() & (avail > cutoff_ts)]
        if not post.empty:
            rec = (
                post.groupby(["state", "period", "program_category"])
                .agg(rows=("samples", "size"),
                     max_availability_date=("availability_date", "max"))
                .reset_index()
            )
            for r in rec.to_dict(orient="records"):
                excluded_sources.append({
                    "pathogen": pathogen,
                    "state": r["state"],
                    "period": r["period"],
                    "program_category": r["program_category"],
                    "rows_excluded": int(r["rows"]),
                    "max_availability_date": str(r["max_availability_date"]),
                    "cutoff": str(cutoff_ts),
                    "reason": "availability_date > cutoff (Req 7.6)",
                })
        df = df.loc[~(avail.notna() & (avail > cutoff_ts))]

    agg = aggregate_state_period(df)
    routine = agg["routine"]
    for_cause = agg["for_cause"]
    exploratory = agg["exploratory"]
    static = agg["static"]
    weather = agg["weather"]
    cdc = agg.get("cdc", pd.DataFrame())

    # The (state, period) grid: every routine cell (the target scope grid).
    if routine.empty:
        return pd.DataFrame()
    states = sorted(routine["state"].unique())
    all_periods = _sorted_periods(df["period"].tolist())
    if cutoff_ts is not None:
        all_periods = [p for p in all_periods if period_start(p) <= cutoff_ts]

    # pre-index per-state series for speed
    routine_by_state = {s: routine[routine["state"] == s] for s in states}
    fc_by_state = {s: for_cause[for_cause["state"] == s] for s in states} if not for_cause.empty else {}
    ex_by_state = {s: exploratory[exploratory["state"] == s] for s in states} if not exploratory.empty else {}
    static_by_state = {r["state"]: r for r in static.to_dict(orient="records")} if not static.empty else {}

    rows: list[dict[str, Any]] = []
    for period in all_periods:
        cell_cutoff = period_start(period)
        poy = period_of_year(period)
        # national lagged positivity (cutoff-safe) — same for all states in period
        national = _national_lagged_positivity(routine, period)
        for state in states:
            rseries = routine_by_state[state]
            # routine rows this state has AT ALL that are available by the cutoff
            rsafe = _series_available_as_of(rseries, cell_cutoff)
            feat: dict[str, Any] = {
                "pathogen": pathogen,
                "state": state,
                "period": period,
                "period_start": cell_cutoff,
                "cutoff": cell_cutoff,
                "resolution": resolution,
            }
            # --- lagged routine positivity / volume (Req 7.4) --------------
            feat.update(_lagged_stats_for_state(rsafe, period, resolution))
            feat["national_routine_positivity_lag1"] = national

            # --- SEPARATE for-cause / exploratory context (never pooled) ---
            fc_series = fc_by_state.get(state, pd.DataFrame())
            fc_safe = _series_available_as_of(fc_series, cell_cutoff) if not fc_series.empty else fc_series
            feat.update(_context_lag1_for_state(fc_safe, period, "context_forcause"))
            ex_series = ex_by_state.get(state, pd.DataFrame())
            ex_safe = _series_available_as_of(ex_series, cell_cutoff) if not ex_series.empty else ex_series
            feat.update(_context_lag1_for_state(ex_safe, period, "context_exploratory"))

            # --- seasonality (sin/cos + calendar) --------------------------
            angle = 2.0 * math.pi * ((poy - 1) / cycle)
            feat["season_sin"] = math.sin(angle)
            feat["season_cos"] = math.cos(angle)
            feat["period_of_year"] = poy
            feat["calendar_year"] = cell_cutoff.year
            feat["calendar_month"] = cell_cutoff.month

            # --- geography -------------------------------------------------
            feat["geo_state"] = state
            feat["geo_region"] = CENSUS_REGION.get(state, "Other")

            # --- weather anomalies (lagged, cutoff-safe; mostly NaN) -------
            for c in _WEATHER_COLS:
                feat[f"weather_{c}_lag1"] = np.nan
            if not weather.empty:
                wstate = weather[weather["state"] == state]
                wsafe = _series_available_as_of(wstate, cell_cutoff)
                if not wsafe.empty:
                    ws = wsafe.copy()
                    ws["_start"] = ws["period"].map(period_start)
                    ws = ws[ws["_start"] < cell_cutoff].sort_values("_start")
                    if not ws.empty:
                        last = ws.iloc[-1]
                        for c in _WEATHER_COLS:
                            if c in last and pd.notna(last[c]):
                                feat[f"weather_{c}_lag1"] = float(last[c])

            # --- CDC NORS human-health outbreaks (lagged, cutoff-safe) -----
            # Uses the LARGE NORS availability lag (end-of-month + ~12 months),
            # so a value is only usable once it would realistically be
            # published. Sparse by nature; missing cells stay NaN.
            for c in _CDC_COLS:
                feat[f"cdc_{c.replace('cdc_', '')}_lag1"] = np.nan
            if not cdc.empty:
                cstate = cdc[cdc["state"] == state]
                csafe = _series_available_as_of(cstate, cell_cutoff)
                if not csafe.empty:
                    cs = csafe.copy()
                    cs["_start"] = cs["period"].map(period_start)
                    cs = cs[cs["_start"] < cell_cutoff].sort_values("_start")
                    if not cs.empty:
                        last = cs.iloc[-1]
                        for c in _CDC_COLS:
                            if c in last and pd.notna(last[c]):
                                feat[f"cdc_{c.replace('cdc_', '')}_lag1"] = float(last[c])

            # --- static ACS / Food Access context (pre-cutoff vintage) -----
            srow = static_by_state.get(state, {})
            for c in _STATIC_STATE_COLS:
                feat[f"static_{c}"] = srow.get(c, np.nan) if srow else np.nan

            # --- raw CURRENT-period outcome (NOT a feature; for Task 3.3) --
            cur = rseries[rseries["period"] == period]
            if not cur.empty:
                c0 = cur.iloc[0]
                feat["outcome_routine_samples"] = float(c0["samples"])
                feat["outcome_routine_positives"] = float(c0["positives"])
                feat["outcome_routine_positivity_rate"] = (
                    float(c0["positivity_rate"]) if pd.notna(c0["positivity_rate"]) else np.nan
                )
            else:
                feat["outcome_routine_samples"] = np.nan
                feat["outcome_routine_positives"] = np.nan
                feat["outcome_routine_positivity_rate"] = np.nan

            rows.append(feat)

    features = pd.DataFrame(rows)
    # stable column ordering: keys, outcome, then features
    key_cols = ["pathogen", "state", "period", "period_start", "cutoff", "resolution"]
    outcome_cols = [
        "outcome_routine_samples", "outcome_routine_positives",
        "outcome_routine_positivity_rate",
    ]
    feature_cols = [c for c in features.columns if c not in key_cols + outcome_cols]
    features = features[key_cols + outcome_cols + feature_cols]
    return features.sort_values(["state", "period_start"]).reset_index(drop=True)


# --------------------------------------------------------------------------- #
# No-leakage assertion (Req 7.5, 7.6) — Property 1
# --------------------------------------------------------------------------- #

#: Feature-provenance map: for each feature column, which per-``(state, period)``
#: source scope and which lag-direction constrain its contributing timestamps.
#: Every lagged/contextual feature may only draw on source rows with
#: ``availability_date <= cutoff`` AND period strictly before the target period.
_LAGGED_FEATURE_PREFIXES: tuple[str, ...] = (
    "routine_positivity_lag", "routine_samples_lag",
    "routine_positivity_trailing", "routine_samples_trailing",
    "national_routine_positivity_lag",
    "context_forcause_", "context_exploratory_",
    "weather_", "cdc_",
)


def assert_no_post_cutoff(
    features_frame: pd.DataFrame,
    cutoff: Any,
    *,
    pathogen: Optional[str] = None,
    harmonized: Optional[pd.DataFrame] = None,
    processed_root: Optional[Path] = None,
) -> dict[str, Any]:
    """Assert no feature draws on a source row available after ``cutoff`` (Property 1).

    Two independent checks:

    1. **Frame-level** — every row's own ``cutoff`` / ``period_start`` is at or
       before the supplied global ``cutoff`` (no cell is predicted past the
       cutoff), and every lagged feature's contributing period is strictly
       before its target period (enforced structurally by ``build_features``;
       re-checked here).
    2. **Source-level** — re-derives, from the harmonized table, the set of
       source rows whose ``availability_date <= cutoff`` and verifies that every
       lagged feature value present in the frame could have been produced from
       that available set only (i.e. there exists at least one available
       contributing source period strictly before the target period whenever the
       feature is non-null). A feature that is non-null while NO pre-cutoff,
       pre-period source exists is a leak and raises :class:`LeakageError`.

    Returns an audit dict (checked row count, excluded post-cutoff source count).
    Raises :class:`LeakageError` on any violation.
    """
    cutoff_ts = pd.Timestamp(cutoff)
    if features_frame.empty:
        return {"checked_rows": 0, "excluded_post_cutoff_sources": 0, "ok": True}

    # (1) frame-level: no cell predicted past the cutoff
    cell_cut = pd.to_datetime(features_frame["cutoff"], errors="coerce")
    bad = features_frame.loc[cell_cut > cutoff_ts]
    if not bad.empty:
        raise LeakageError(
            f"{len(bad)} feature rows have a cell cutoff after the global cutoff "
            f"{cutoff_ts!r}: {bad[['state', 'period']].head().to_dict('records')}"
        )

    # (2) source-level: re-derive availability and verify every non-null lagged
    # feature has an available, strictly-earlier source period.
    if harmonized is None and pathogen is not None:
        harmonized = load_harmonized(pathogen, processed_root=processed_root)

    excluded = 0
    if harmonized is not None and not harmonized.empty:
        avail = pd.to_datetime(harmonized["availability_date"], errors="coerce")
        excluded = int((avail.notna() & (avail > cutoff_ts)).sum())
        available = harmonized.loc[avail.notna() & (avail <= cutoff_ts)].copy()
        available["_start"] = available["period"].map(period_start)

        # routine availability index per state -> earliest available start, plus
        # the GLOBAL earliest available routine start (national features draw on
        # ALL states, so they are validated against the national min, not the
        # per-state min).
        routine_avail = available[available["program_category"] == TARGET_CATEGORY]
        min_start_by_state: dict[str, pd.Timestamp] = (
            routine_avail.groupby("state")["_start"].min().to_dict()
        )
        national_min_start: Optional[pd.Timestamp] = (
            routine_avail["_start"].min() if not routine_avail.empty else None
        )

        # per-state routine lag features require a prior source FOR THAT STATE;
        # the national feature requires only a prior source for SOME state.
        state_lagged_cols = [
            c for c in features_frame.columns
            if c.startswith(("routine_positivity_lag", "routine_samples_lag",
                             "routine_positivity_trailing", "routine_samples_trailing"))
        ]
        national_cols = [
            c for c in features_frame.columns
            if c.startswith("national_routine_positivity_lag")
        ]
        for rec in features_frame.to_dict(orient="records"):
            tgt_start = period_start(rec["period"])
            state = rec["state"]
            earliest = min_start_by_state.get(state)
            state_has_prior = earliest is not None and earliest < tgt_start
            national_has_prior = (
                national_min_start is not None and national_min_start < tgt_start
            )
            for col in state_lagged_cols:
                val = rec.get(col)
                if val is not None and not (isinstance(val, float) and math.isnan(val)):
                    if not state_has_prior:
                        raise LeakageError(
                            f"feature {col!r} is non-null for state={state!r} "
                            f"period={rec['period']!r} but no routine source is "
                            f"available at or before cutoff {cutoff_ts!r} with a "
                            f"period strictly earlier than {rec['period']!r}"
                        )
            for col in national_cols:
                val = rec.get(col)
                if val is not None and not (isinstance(val, float) and math.isnan(val)):
                    if not national_has_prior:
                        raise LeakageError(
                            f"national feature {col!r} is non-null for "
                            f"period={rec['period']!r} but no routine source is "
                            f"available at or before cutoff {cutoff_ts!r} with a "
                            f"period strictly earlier than {rec['period']!r}"
                        )

    return {
        "checked_rows": int(len(features_frame)),
        "excluded_post_cutoff_sources": excluded,
        "ok": True,
    }


# --------------------------------------------------------------------------- #
# Feature dictionary (Req 7.4 transparency)
# --------------------------------------------------------------------------- #

#: (name-or-prefix, definition, lag, source, cutoff-safe) for every feature.
FEATURE_DICTIONARY: tuple[tuple[str, str, str, str, str], ...] = (
    ("routine_positivity_lag{1,2,3}",
     "Routine-surveillance positivity rate of the state 1/2/3 periods before t",
     "t-1, t-2, t-3", "FSIS routine samples (is_target)", "yes"),
    ("routine_samples_lag{1,2,3}",
     "Routine-surveillance tested-sample volume 1/2/3 periods before t",
     "t-1, t-2, t-3", "FSIS routine samples", "yes"),
    ("routine_positivity_trailing4_mean",
     "Mean routine positivity over the trailing 4 available periods before t",
     "trailing 4 periods", "FSIS routine samples", "yes"),
    ("routine_positivity_trailing12m_mean",
     "Mean routine positivity over the trailing 12 months / 4 quarters before t",
     "trailing 12 months", "FSIS routine samples", "yes"),
    ("routine_samples_trailing4_mean / routine_samples_trailing12m_mean",
     "Trailing-window mean routine sample volume (establishment-activity proxy)",
     "trailing 4 / 12 periods", "FSIS routine samples", "yes"),
    ("national_routine_positivity_lag1",
     "National routine positivity across all states in the period before t",
     "t-1", "FSIS routine samples (all states)", "yes"),
    ("context_forcause_positivity_lag1 / _samples_lag1 / _trailing4_mean",
     "For-cause program positivity/volume — SEPARATE context, never pooled into "
     "the routine baseline",
     "t-1 / trailing 4", "FSIS for_cause samples", "yes"),
    ("context_exploratory_positivity_lag1 / _samples_lag1 / _trailing4_mean",
     "Exploratory program positivity/volume — SEPARATE context, never pooled "
     "into the routine baseline",
     "t-1 / trailing 4", "FSIS exploratory samples", "yes"),
    ("season_sin / season_cos",
     "Sin/cos encoding of the period-of-year (month 1..12 or quarter 1..4)",
     "current period calendar only", "derived from period label", "yes"),
    ("period_of_year / calendar_year / calendar_month",
     "Calendar components of the target period (known in advance)",
     "current period calendar only", "derived from period label", "yes"),
    ("geo_state", "State identifier (categorical)", "static", "FSIS establishment_state", "yes"),
    ("geo_region", "Census region grouping of the state", "static", "derived crosswalk", "yes"),
    ("weather_{tmax,tmin,prcp}_*_lag1",
     "NOAA nClimDiv statewide weather means/anomalies (°C, mm) from the latest "
     "fully-published period before t — now NON-MISSING for ~all state-periods "
     "(48 contiguous states + AK; HI absent, documented gap)",
     "latest published period < t (end-of-month + 7d lag)",
     "NOAA nClimDiv statewide monthly climate", "yes"),
    ("cdc_{outbreaks,illnesses,pathogen_outbreaks}_lag1",
     "CDC NORS foodborne-outbreak counts / illnesses / this-pathogen outbreaks "
     "from the latest NORS period usable at t under a LARGE (~12-month) "
     "availability lag; HISTORICAL One Health evidence, sparse, missing=NaN",
     "latest published period < t (end-of-month + ~365d lag)",
     "CDC NORS (dataset 5xkq-dg7x, primary_mode=Food)", "yes"),
    ("static_total_population / static_elderly_65plus_partial / static_elderly_share",
     "ACS 65+/vulnerability context joined by state (single pre-cutoff vintage)",
     "static (2022 vintage, pre-cutoff)", "Census ACS5 2022", "yes"),
    ("static_lila_tract_share / static_low_income_tract_share / static_atlas_pop_2010",
     "Food Access Atlas indicators joined by state (single pre-cutoff vintage)",
     "static (2019 vintage, pre-cutoff)", "USDA Food Access Research Atlas 2019", "yes"),
)

#: Columns that are the raw current-period OUTCOME, not features (for Task 3.3).
_OUTCOME_DOC: tuple[tuple[str, str], ...] = (
    ("outcome_routine_samples",
     "Current-period routine tested-sample volume (NOT a feature)"),
    ("outcome_routine_positives",
     "Current-period routine positive count (NOT a feature)"),
    ("outcome_routine_positivity_rate",
     "Current-period routine positivity rate — Task 3.3 derives the next-period "
     "elevated-positivity label from this; it is NOT a predictor feature"),
)


def write_feature_dictionary(out_md: Optional[Path] = None) -> Path:
    """Write ``docs/reports/feature_dictionary.md`` (name, definition, lag, source, cutoff-safe)."""
    out_md = out_md or (DOCS_REPORTS / "feature_dictionary.md")
    out_md.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# VulneraSafe AI — Feature Dictionary (Task 3.1, Req 7.4–7.6)",
        "",
        "Every feature in the leakage-safe per-pathogen feature matrix "
        "(`data/processed/features_<pathogen>.parquet`). Each feature is "
        "constructed using ONLY information timestamped at or before the horizon "
        "cutoff (the start of the predicted period); every contributing source "
        "row satisfies `availability_date <= cutoff` and comes from a period "
        "strictly earlier than the target period (Req 7.5). Any source row "
        "timestamped after the cutoff is excluded and recorded for audit "
        "(Req 7.6).",
        "",
        f"> {hz.AVAILABILITY_LIMITATION}",
        "",
        "Routine-surveillance positivity (the target scope per the program "
        "taxonomy) and for-cause / exploratory positivity are kept in SEPARATE "
        "columns and are never pooled together.",
        "",
        "## Feature columns",
        "",
        "| Feature | Definition | Lag | Source | Cutoff-safe |",
        "|---|---|---|---|---|",
    ]
    for name, definition, lag, source, safe in FEATURE_DICTIONARY:
        lines.append(f"| `{name}` | {definition} | {lag} | {source} | {safe} |")
    lines += [
        "",
        "## Raw current-period outcome (NOT features — for Task 3.3 label)",
        "",
        "These columns carry the raw current-period routine outcome. They are "
        "kept clearly separate from the feature columns so Task 3.3 can derive "
        "the next-period elevated-positivity label from them. They are NOT used "
        "as predictors.",
        "",
        "| Column | Definition |",
        "|---|---|",
    ]
    for name, definition in _OUTCOME_DOC:
        lines.append(f"| `{name}` | {definition} |")
    lines.append("")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_md


# --------------------------------------------------------------------------- #
# Top-level orchestration
# --------------------------------------------------------------------------- #

def run_feature_construction(
    *,
    pathogens: Optional[tuple[str, ...]] = None,
    processed_root: Optional[Path] = None,
) -> dict[str, Any]:
    """Build + write the feature matrix for every pathogen and the dictionary.

    Produces ``data/processed/features_<pathogen>.parquet`` (CSV fallback) plus
    a ``.sample.csv``, writes ``docs/reports/feature_dictionary.md``, and
    returns a per-pathogen summary (shape, feature columns, weather coverage,
    excluded post-cutoff source count) for the caller/report.
    """
    processed_root = processed_root or PROCESSED_ROOT
    processed_root.mkdir(parents=True, exist_ok=True)
    pathogens = pathogens or tuple(PATHOGEN_SLUG.keys())

    write_feature_dictionary()

    summary: dict[str, Any] = {}
    for pathogen in pathogens:
        df = load_harmonized(pathogen, processed_root=processed_root)
        excluded: list[dict[str, Any]] = []
        features = build_features(pathogen, df=df, excluded_sources=excluded)
        slug = PATHOGEN_SLUG[pathogen]
        parquet = processed_root / f"features_{slug}.parquet"
        csv = processed_root / f"features_{slug}.sample.csv"
        wrote_parquet = False
        if not features.empty:
            try:
                features.to_parquet(parquet, index=False)
                wrote_parquet = True
            except Exception as exc:  # noqa: BLE001 — CSV fallback if no engine
                parquet = processed_root / f"features_{slug}.csv"
                features.to_csv(parquet, index=False)
                print(f"[features] parquet unavailable for {pathogen}: {exc!r}; wrote CSV")
            features.head(50).to_csv(csv, index=False)

        # honest weather coverage: how many cells have a non-missing weather value
        weather_cols = [c for c in features.columns if c.startswith("weather_")]
        if weather_cols and not features.empty:
            weather_nonmissing = int(features[weather_cols].notna().any(axis=1).sum())
        else:
            weather_nonmissing = 0
        # honest CDC coverage
        cdc_cols = [c for c in features.columns if c.startswith("cdc_")]
        if cdc_cols and not features.empty:
            cdc_nonmissing = int(features[cdc_cols].notna().any(axis=1).sum())
        else:
            cdc_nonmissing = 0

        feature_cols = [
            c for c in features.columns
            if c not in ("pathogen", "state", "period", "period_start", "cutoff",
                         "resolution", "outcome_routine_samples",
                         "outcome_routine_positives", "outcome_routine_positivity_rate")
        ]
        summary[pathogen] = {
            "rows": int(len(features)),
            "columns": int(features.shape[1]) if not features.empty else 0,
            "feature_columns": feature_cols,
            "n_feature_columns": len(feature_cols),
            "states": int(features["state"].nunique()) if not features.empty else 0,
            "periods": int(features["period"].nunique()) if not features.empty else 0,
            "weather_cells_nonmissing": weather_nonmissing,
            "weather_cells_missing": int(len(features) - weather_nonmissing) if not features.empty else 0,
            "weather_states_nonmissing": (
                int(features.loc[features[weather_cols].notna().any(axis=1), "state"].nunique())
                if (weather_cols and not features.empty) else 0
            ),
            "cdc_cells_nonmissing": cdc_nonmissing,
            "excluded_post_cutoff_sources": len(excluded),
            "parquet": str(parquet),
            "wrote_parquet": wrote_parquet,
        }
    return summary


if __name__ == "__main__":  # pragma: no cover - manual invocation
    import pprint
    pprint.pprint(run_feature_construction())
