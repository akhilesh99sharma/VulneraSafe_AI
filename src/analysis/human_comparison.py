"""S05 — Food surveillance vs. human outbreaks comparison (CDC NORS vs FSIS).

Integrates the challenge's required human-health stream — real CDC NORS
foodborne-outbreak data (data/raw/cdc_nors_outbreaks.csv) — and compares it
against the FSIS state x year surveillance reused from S04, STRICTLY as
corroboration. A modeled 365-day availability lag guarantees NORS can never act
as a leading predictor of FSIS. Nothing here asserts a same-strain link, a
food-to-illness causal relationship, or any human county-case forecast:
temporal/geographic similarity is not proof of causation.

This file both (a) provides the reusable ingest/standardization/FSIS-reuse
functions and (b) prints a Task-1 inventory report under ``__main__`` to lock the
coverage threshold and the FSIS-NORS overlap window from the real data.
"""

from __future__ import annotations

import csv
import collections
import json
from pathlib import Path
from typing import Any, Optional

from src.analysis.emerging_risk import _PATHOGEN_CONFIG, _build_series
from src.analysis.program_product import wilson_ci

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_ROOT = REPO_ROOT / "data" / "raw"
INTERIM_DIR = REPO_ROOT / "data" / "interim"
NORS_PATH = RAW_ROOT / "cdc_nors_outbreaks.csv"
CACHE_PATH = INTERIM_DIR / "s05_human_comparison.json"

MODULE_ID = "S05"
METHOD_VERSION = "s05.v1"

NORS_DATASET_ID = "5xkq-dg7x"
NORS_SOURCE_URL = "https://data.cdc.gov/api/views/5xkq-dg7x/rows.csv?accessType=DOWNLOAD"
AVAILABILITY_LAG_DAYS = 365

COVERAGE_MIN_OUTBREAKS = 300   # pathogen total foodborne outbreaks below this -> coverage_limited
OVERLAP_MIN_YEAR = 2013        # FSIS ∩ NORS overlap window (confirmed from the inventory)
OVERLAP_MAX_YEAR = 2023
NO_CAUSAL_LINK_NOTE = (
    "Corroboration only. FSIS food-surveillance positivity and CDC human-outbreak "
    "reports are shown side by side as One Health context. This is NOT evidence of a "
    "same-strain link or that food testing caused (or was caused by) human illness. "
    "NORS is modeled as available ~365 days after the event year and is never used to "
    "predict FSIS. Geography is state-level only; no sub-state or county human estimate "
    "is produced."
)


_PATHOGENS = ("Salmonella", "Listeria", "STEC")

#: US state / territory name -> USPS abbreviation, to reconcile NORS (full
#: names) with FSIS establishment_state (abbreviations). Unmatched names are
#: kept as-is (uppercased) and counted, never dropped silently.
_STATE_ABBR = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "district of columbia": "DC", "florida": "FL", "georgia": "GA", "hawaii": "HI",
    "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA",
    "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME",
    "maryland": "MD", "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE",
    "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM",
    "new york": "NY", "north carolina": "NC", "north dakota": "ND", "ohio": "OH",
    "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI",
    "south carolina": "SC", "south dakota": "SD", "tennessee": "TN", "texas": "TX",
    "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "puerto rico": "PR", "guam": "GU", "virgin islands": "VI",
    "american samoa": "AS", "northern mariana islands": "MP",
}

def _norm_state(value) -> str:
    """Normalize a NORS state name to a USPS abbreviation to match FSIS.
    Already-abbreviated or unknown values are uppercased and returned as-is."""
    if value is None:
        return ""
    s = str(value).strip()
    if s == "":
        return ""
    return _STATE_ABBR.get(s.lower(), s.upper())


def standardize_etiology(text: Any) -> set[str]:
    """Map the free-text NORS Etiology to a subset of {Salmonella, Listeria, STEC}.

    Conservative: lowercase, split on ';', match each token by keyword. STEC
    covers E. coli / O157 / Shiga-toxin / STEC. Unmatched tokens contribute
    nothing (excluded), never force-fit. Returns the set of matched pathogens.
    """
    if text is None:
        return set()
    out: set[str] = set()
    for token in str(text).lower().split(";"):
        t = token.strip()
        if not t:
            continue
        if "salmonella" in t:
            out.add("Salmonella")
        if "listeria" in t:
            out.add("Listeria")
        if "coli" in t or "o157" in t or "stec" in t or "shiga" in t:
            out.add("STEC")
    return out

def load_nors_foodborne(path: Path = NORS_PATH) -> tuple[list[dict], dict]:
    """Read NORS, keep Primary Mode == Food, attach standardized pathogens.

    Returns (rows, meta). Each returned row carries parsed year:int|None,
    state:str, illnesses:int, hospitalizations:int, deaths:int, and
    pathogens:set[str]. meta counts total/foodborne/unmatched/unparsable.
    """
    if not path.exists():
        return [], {"present": False, "reason": f"NORS file not found at {path}"}

    rows: list[dict] = []
    total = foodborne = unmatched = year_unparsable = 0
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            total += 1
            if r.get("Primary Mode") != "Food":
                continue
            foodborne += 1
            pathogens = standardize_etiology(r.get("Etiology"))
            if not pathogens:
                unmatched += 1
                continue
            yr_raw = (r.get("Year") or "").strip()
            if not yr_raw.isdigit():
                year_unparsable += 1
                continue
            def _int(v):
                try:
                    return int(float(v)) if v not in (None, "") else 0
                except (ValueError, TypeError):
                    return 0
            rows.append({
                "year": int(yr_raw),
                "state": _norm_state(r.get("State")),
                "illnesses": _int(r.get("Illnesses")),
                "hospitalizations": _int(r.get("Hospitalizations")),
                "deaths": _int(r.get("Deaths")),
                "pathogens": pathogens,
            })
    meta = {
        "present": True,
        "total_rows": total,
        "foodborne_rows": foodborne,
        "foodborne_unmatched_etiology": unmatched,
        "year_unparsable": year_unparsable,
        "matched_rows": len(rows),
    }
    return rows, meta

def nors_by_cell(rows: list[dict]) -> dict[tuple[str, str, int], dict]:
    """Aggregate to (pathogen, state, year) -> {outbreaks, illnesses}.

    A multi-pathogen outbreak contributes its counts to EACH matched pathogen
    (documented attribution; counts are not invented, only attributed)."""
    cells: dict[tuple[str, str, int], dict] = {}
    for r in rows:
        for p in r["pathogens"]:
            key = (p, r["state"], r["year"])
            c = cells.setdefault(key, {"outbreaks": 0, "illnesses": 0})
            c["outbreaks"] += 1
            c["illnesses"] += r["illnesses"]
    return cells

def fsis_state_year() -> dict[str, dict[tuple[str, int], dict]]:
    """Aggregate the reused S04 state x quarter series to state x year.

    Returns {pathogen: {(state, year): {"n": int, "pos": int}}}.
    """
    out: dict[str, dict[tuple[str, int], dict]] = {}
    for pathogen, cfg in _PATHOGEN_CONFIG.items():
        records = list(__import__("src.analysis.emerging_risk", fromlist=["_iter_raw_records"])._iter_raw_records(cfg["dir"]))
        series, _meta = _build_series(records, cfg["analysis_col"], "quarterly")
        by_cell: dict[tuple[str, int], dict] = {}
        for state, cells in series.items():
            for c in cells:
                year = int(c["period"].split("-Q")[0])
                g = by_cell.setdefault((state, year), {"n": 0, "pos": 0})
                g["n"] += c["n"]
                g["pos"] += c["pos"]
        out[pathogen] = by_cell
    return out

def availability_year(event_year: int) -> int:
    """Modeled 365-day availability lag: knowable from the next year."""
    return event_year + 1

def lead_lag_summary(fsis_year_rate: dict[int, float], nors_year_count: dict[int, int],
                     *, max_lag: int = 2, n_perm: int = 1000, seed: int = 12345) -> Optional[dict]:
    """EXPLORATORY national lead-lag correlation between the FSIS annual positivity
    series and the NORS annual outbreak-count series. Descriptive only — never
    causal or predictive. Returns None when too few overlapping years.

    Reports the best small-integer year lag by absolute Pearson correlation, a
    permutation p-value (shuffle NORS years), and a bootstrap 95% CI.
    """
    import random
    import statistics

    years = sorted(set(fsis_year_rate) & set(nors_year_count))
    if len(years) < 5:
        return None

    def _pearson(a: list[float], b: list[float]) -> Optional[float]:
        n = len(a)
        if n < 3:
            return None
        ma, mb = statistics.fmean(a), statistics.fmean(b)
        num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
        da = sum((x - ma) ** 2 for x in a) ** 0.5
        db = sum((y - mb) ** 2 for y in b) ** 0.5
        if da == 0 or db == 0:
            return None
        return num / (da * db)

    best = None  # (abs_corr, lag, corr, paired_f, paired_n)
    for lag in range(-max_lag, max_lag + 1):
        pf, pn = [], []
        for y in years:
            yy = y - lag  # NORS year shifted by lag relative to FSIS
            if yy in nors_year_count and y in fsis_year_rate:
                pf.append(fsis_year_rate[y])
                pn.append(float(nors_year_count[yy]))
        corr = _pearson(pf, pn)
        if corr is None:
            continue
        if best is None or abs(corr) > best[0]:
            best = (abs(corr), lag, corr, pf, pn)
    if best is None:
        return None
    _abscorr, lag, corr, pf, pn = best

    rng = random.Random(seed)
    # permutation p-value: shuffle the NORS series
    ge = 0
    for _ in range(n_perm):
        shuf = pn[:]
        rng.shuffle(shuf)
        c = _pearson(pf, shuf)
        if c is not None and abs(c) >= abs(corr):
            ge += 1
    p_perm = (ge + 1) / (n_perm + 1)
    # bootstrap 95% CI on the correlation
    boots = []
    idx = list(range(len(pf)))
    for _ in range(n_perm):
        samp = [rng.choice(idx) for _ in idx]
        c = _pearson([pf[i] for i in samp], [pn[i] for i in samp])
        if c is not None:
            boots.append(c)
    boots.sort()
    ci_low = boots[int(0.025 * len(boots))] if boots else None
    ci_high = boots[int(0.975 * len(boots))] if boots else None

    return {
        "lag_years": lag,
        "correlation": round(corr, 6),
        "p_value_permutation": round(p_perm, 6),
        "ci_low": round(ci_low, 6) if ci_low is not None else None,
        "ci_high": round(ci_high, 6) if ci_high is not None else None,
        "exploratory": True,
        "note": ("Exploratory descriptive lead-lag only (permutation p-value, bootstrap CI). "
                 "Not causal, not predictive; small annual sample."),
    }

def compute_human_comparison(*, round_to: int = 6) -> dict[str, Any]:
    """Join FSIS state-year surveillance with NORS human outbreaks (corroboration);
    write the S05 cache. Honest coverage flags; no causal claims."""
    import datetime as _dt

    nors_rows, nmeta = load_nors_foodborne()
    fsis = fsis_state_year()
    accessed = _dt.date.today().isoformat()

    pathogens_out: dict[str, Any] = {}
    if not nmeta.get("present"):
        for pathogen, cfg in _PATHOGEN_CONFIG.items():
            pathogens_out[pathogen] = {
                "pathogen": pathogen, "commodity": cfg["commodity"],
                "availability_status": "unavailable",
                "unavailable_reason": nmeta.get("reason", "NORS data not present; run the documented download."),
                "cells": [], "lead_lag": None, "coverage_status": "nors_not_available",
            }
        return _write_cache(pathogens_out, nmeta, accessed, round_to)

    cells = nors_by_cell(nors_rows)
    # per-pathogen total outbreaks -> full vs coverage_limited
    totals = collections.Counter()
    for (p, _s, _y), c in cells.items():
        totals[p] += c["outbreaks"]

    for pathogen, cfg in _PATHOGEN_CONFIG.items():
        commodity = cfg["commodity"]
        fsis_cells = fsis.get(pathogen, {})
        coverage = "ok" if totals.get(pathogen, 0) >= COVERAGE_MIN_OUTBREAKS else "coverage_limited"

        # national annual series for the exploratory lead-lag (within overlap).
        fsis_year_rate: dict[int, float] = {}
        fsis_year_np: dict[int, tuple[int, int]] = {}
        for (s, y), g in fsis_cells.items():
            if OVERLAP_MIN_YEAR <= y <= OVERLAP_MAX_YEAR:
                n, pos = fsis_year_np.get(y, (0, 0))
                fsis_year_np[y] = (n + g["n"], pos + g["pos"])
        for y, (n, pos) in fsis_year_np.items():
            fsis_year_rate[y] = (pos / n) if n else 0.0
        nors_year_count: dict[int, int] = collections.Counter()
        for (p, _s, y), c in cells.items():
            if p == pathogen and OVERLAP_MIN_YEAR <= y <= OVERLAP_MAX_YEAR:
                nors_year_count[y] += c["outbreaks"]
        lead_lag = lead_lag_summary(fsis_year_rate, dict(nors_year_count)) if coverage == "ok" else None

        # the union of FSIS and NORS (state, year) keys within the overlap window
        keys = set()
        for (s, y) in fsis_cells:
            if OVERLAP_MIN_YEAR <= y <= OVERLAP_MAX_YEAR:
                keys.add((s, y))
        for (p, s, y) in cells:
            if p == pathogen and OVERLAP_MIN_YEAR <= y <= OVERLAP_MAX_YEAR:
                keys.add((s, y))

        cell_rows = []
        for (s, y) in sorted(keys):
            fg = fsis_cells.get((s, y))
            ng = cells.get((pathogen, s, y))
            fsis_n = fg["n"] if fg else None
            fsis_pos = fg["pos"] if fg else None
            positivity = (fsis_pos / fsis_n) if (fsis_n and fsis_pos is not None) else None
            lo, hi = wilson_ci(fsis_pos or 0, fsis_n or 0) if fsis_n else (None, None)
            # NORS present for this cell? distinguish true zero vs missing coverage.
            if ng is not None:
                nors_out, nors_ill, cov = ng["outbreaks"], ng["illnesses"], coverage
            else:
                # FSIS-only cell: NORS reported nothing here. Within a covered
                # pathogen this is a genuine zero; for a coverage-limited pathogen
                # mark it limited rather than asserting zero human burden.
                if coverage == "ok":
                    nors_out, nors_ill, cov = 0, 0, "ok"
                else:
                    nors_out, nors_ill, cov = None, None, "coverage_limited"
            cell_rows.append({
                "region": s, "period": str(y),
                "fsis_sample_n": fsis_n, "fsis_positive_n": fsis_pos,
                "fsis_positivity": round(positivity, round_to) if positivity is not None else None,
                "fsis_ci_low": round(lo, round_to) if lo is not None else None,
                "fsis_ci_high": round(hi, round_to) if hi is not None else None,
                "nors_outbreak_count": nors_out,
                "nors_illness_count": nors_ill,
                "nors_available_from_year": availability_year(y),
                "coverage_status": cov,
            })

        pathogens_out[pathogen] = {
            "pathogen": pathogen, "commodity": commodity,
            "availability_status": "available" if cell_rows else "unavailable",
            "unavailable_reason": None if cell_rows else "No overlapping FSIS/NORS cells.",
            "coverage_status": coverage,
            "total_nors_outbreaks": totals.get(pathogen, 0),
            "lead_lag": lead_lag,
            "cells": cell_rows,
        }

    return _write_cache(pathogens_out, nmeta, accessed, round_to)

def _write_cache(pathogens_out: dict, nmeta: dict, accessed: str, round_to: int) -> dict[str, Any]:
    cache = {
        "module_id": MODULE_ID,
        "method_version": METHOD_VERSION,
        "dataset_sources": f"CDC NORS ({NORS_DATASET_ID}); USDA FSIS laboratory sampling",
        "source_accessed_at": accessed,
        "nors_dataset_id": NORS_DATASET_ID,
        "nors_source_url": NORS_SOURCE_URL,
        "availability_lag_days": AVAILABILITY_LAG_DAYS,
        "overlap_window": [OVERLAP_MIN_YEAR, OVERLAP_MAX_YEAR],
        "coverage_min_outbreaks": COVERAGE_MIN_OUTBREAKS,
        "no_causal_link_note": NO_CAUSAL_LINK_NOTE,
        "nors_meta": nmeta,
        "pathogens": pathogens_out,
    }
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")
    return cache

def load_cache() -> Optional[dict[str, Any]]:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
    return None


if __name__ == "__main__":
    nors_rows, nmeta = load_nors_foodborne()
    if not nmeta.get("present"):
        print("NORS NOT PRESENT:", nmeta.get("reason"))
        raise SystemExit(1)

    cells = nors_by_cell(nors_rows)
    print("S05 NORS INVENTORY — diagnostic.")
    print(f"  NORS: total={nmeta['total_rows']} foodborne={nmeta['foodborne_rows']} "
          f"matched={nmeta['matched_rows']} unmatched_etiology={nmeta['foodborne_unmatched_etiology']} "
          f"year_unparsable={nmeta['year_unparsable']}")

    nors_years = sorted({y for (_p, _s, y) in cells})
    print(f"  NORS year range: {nors_years[0]}..{nors_years[-1]}")

    print("  building FSIS state-year (reusing S04)...")
    fsis = fsis_state_year()
    fsis_years = sorted({y for p in fsis for (_s, y) in fsis[p]})
    print(f"  FSIS year range: {fsis_years[0]}..{fsis_years[-1]}")

    ov_lo = max(nors_years[0], fsis_years[0])
    ov_hi = min(nors_years[-1], fsis_years[-1])
    print(f"  OVERLAP WINDOW (FSIS ∩ NORS): {ov_lo}..{ov_hi}")

    for p in _PATHOGENS:
        p_cells = [(s, y) for (pp, s, y) in cells if pp == p]
        p_states = {s for (s, _y) in p_cells}
        p_out = sum(cells[(p, s, y)]["outbreaks"] for (s, y) in p_cells)
        p_ill = sum(cells[(p, s, y)]["illnesses"] for (s, y) in p_cells)
        # joined cells within overlap window that also have FSIS data
        joined = sum(
            1 for (s, y) in p_cells
            if ov_lo <= y <= ov_hi and (s, y) in fsis.get(p, {})
        )
        in_window = sum(1 for (_s, y) in p_cells if ov_lo <= y <= ov_hi)
        print(f"  {p}: outbreaks={p_out} illnesses={p_ill} states={len(p_states)} "
              f"nors_cells_in_window={in_window} joined_with_fsis={joined}")


    print("\n  computing full comparison + writing cache...")
    result = compute_human_comparison()
    for p, d in result["pathogens"].items():
        ll = d.get("lead_lag")
        ll_s = (f"lag={ll['lag_years']} r={ll['correlation']} p={ll['p_value_permutation']}"
                if ll else "none (coverage_limited or too few years)")
        print(f"  {p}: coverage={d['coverage_status']} cells={len(d['cells'])} lead_lag[exploratory]: {ll_s}")
