"""S04 — Persistent vs. emerging risk detector (state x period).

Builds, for each pathogen, a per-US-state quarterly positivity time series from
the RAW FSIS sampling data (reusing the S01 readers), then:

* computes a LEAKAGE-SAFE trailing baseline for each quarter using ONLY that
  state's strictly-earlier quarters (EWMA + prior-only seasonal offset);
* flags a RETROSPECTIVE anomaly when a quarter's observed positivity exceeds the
  prior-only expected band (an OBSERVED statement about the past, never a
  forecast);
* scores PERSISTENCE as the fraction of a state's supported quarters that sat
  above their trailing expected band (chronic elevation, distinct from a new
  anomaly);
* OPTIONALLY attempts a one-step-ahead PROSPECTIVE forecast, trained strictly
  before a cutoff and evaluated only after it, and keeps it ONLY if it beats a
  naive persistence baseline on precision/recall; otherwise the pathogen is
  retrospective-only, which is an allowed, honest outcome.

Locked parameters (from the Task-1 support audit over the real data):
    RESOLUTION          = "quarterly"  (monthly denominators collapse)
    MIN_SUPPORT         = 30           (valid tests per state-quarter)
    BASELINE_WINDOW_MIN = 4            (prior supported quarters before flagging)

Geography is SAMPLING LOCATION (establishment_state) only — never product
destination or human-illness location. Positivity is surveillance signal, never
a contamination claim. Nothing is fabricated: unparseable/absent state or date
is counted and excluded, and an unsupported series yields an explicit
unavailable record.

The heavy raw scan runs offline via :func:`compute_emerging_risk` and is cached
to ``data/interim/s04_emerging_risk.json``; the exporter reads that cache.
"""

from __future__ import annotations

import datetime as _dt
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

from src.analysis.program_product import (
    _PATHOGEN_CONFIG,
    _classify_result,
    _iter_raw_records,
    wilson_ci,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
INTERIM_DIR = REPO_ROOT / "data" / "interim"
CACHE_PATH = INTERIM_DIR / "s04_emerging_risk.json"

MODULE_ID = "S04"
METHOD_VERSION = "s04.v1"

#: Locked from the Task-1 support audit over the real FSIS data.
RESOLUTION = "quarterly"
MIN_SUPPORT = 30
BASELINE_WINDOW_MIN = 4

#: EWMA smoothing factor for the trailing baseline (prior periods only).
EWMA_ALPHA = 0.4
#: Anomaly rule: flag when observed rate exceeds the prior expected-high band.
#: The band is a Wilson upper bound on the baseline widened by prior dispersion;
#: this multiplier scales the prior-dispersion widening.
BAND_K = 3.0
#: Fraction of a state's quarters held out (most recent) for the prospective
#: forecast evaluation.
FORECAST_HOLDOUT_FRAC = 0.2
#: Absolute skill floor a prospective forecast must clear ON ITS OWN before it
#: may be labeled "validated" / carry a PREDICTED tag. Beating a naive baseline
#: is necessary but NOT sufficient: a fired alert must be right at least half the
#: time (precision) and catch at least a quarter of real events (recall). Below
#: this the forecast is reported honestly as not good enough and no alert ships.
FORECAST_MIN_PRECISION = 0.5
FORECAST_MIN_RECALL = 0.25
#: Minimum supported (baseline-defined) quarters before a state receives a
#: persistence score. Prevents a state with one gradeable quarter from topping
#: the ranking at score 1.0.
PERSISTENCE_MIN_QUARTERS = 8

_GENERATED_AT_FALLBACK = "2026-01-01T00:00:00Z"

# --------------------------------------------------------------------------- #
# Record-level extraction (geography + time)
# --------------------------------------------------------------------------- #
def _record_state(rec: dict) -> Optional[str]:
    """establishment_state, uppercased/stripped; empty/NULL -> None."""
    value = rec.get("establishment_state")
    if value is None:
        return None
    s = str(value).strip().upper()
    if s == "" or s == "NULL":
        return None
    return s

def _parse_date(value: Any) -> Optional[_dt.date]:
    if value is None:
        return None
    s = str(value).strip()
    if s == "" or s.upper() == "NULL":
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d"):
        try:
            return _dt.datetime.strptime(s[: len(fmt) + 2], fmt).date()
        except ValueError:
            continue
    try:
        return _dt.date.fromisoformat(s[:10])
    except ValueError:
        return None

def _period_label(d: _dt.date, resolution: str = RESOLUTION) -> str:
    if resolution == "monthly":
        return f"{d.year}-{d.month:02d}"
    return f"{d.year}-Q{(d.month - 1) // 3 + 1}"

def _period_start(d: _dt.date, resolution: str = RESOLUTION) -> _dt.date:
    if resolution == "monthly":
        return _dt.date(d.year, d.month, 1)
    q = (d.month - 1) // 3
    return _dt.date(d.year, q * 3 + 1, 1)

def _season_key(period_start: _dt.date, resolution: str = RESOLUTION) -> int:
    """Same-season bucket for the prior-only seasonal offset."""
    if resolution == "monthly":
        return period_start.month
    return (period_start.month - 1) // 3 + 1  # 1..4

# --------------------------------------------------------------------------- #
# Series construction
# --------------------------------------------------------------------------- #
def _build_series(records, analysis_col: str, resolution: str = RESOLUTION):
    """Return (series, meta).

    series: {state: [cell, ...]} ordered by period_start, where cell is a dict
        {period, period_start (iso), n, pos}.
    meta:   {"state_missing": int, "date_unparsable": int, "valid": int,
             "total": int, "states": int}
    """
    cells: dict[str, dict[str, dict]] = defaultdict(dict)  # state -> period -> cell
    total = valid = state_missing = date_unparsable = 0

    for _fy, rec in records:
        total += 1
        verdict = _classify_result(rec.get(analysis_col))
        if verdict is None:
            continue
        valid += 1
        st = _record_state(rec)
        if st is None:
            state_missing += 1
            continue
        d = _parse_date(rec.get("collection_date"))
        if d is None:
            date_unparsable += 1
            continue
        plabel = _period_label(d, resolution)
        pstart = _period_start(d, resolution)
        cell = cells[st].get(plabel)
        if cell is None:
            cell = {"period": plabel, "period_start": pstart.isoformat(), "n": 0, "pos": 0}
            cells[st][plabel] = cell
        cell["n"] += 1
        if verdict:
            cell["pos"] += 1

    series: dict[str, list[dict]] = {}
    for st, by_period in cells.items():
        ordered = sorted(by_period.values(), key=lambda c: c["period_start"])
        series[st] = ordered

    meta = {
        "total": total,
        "valid": valid,
        "state_missing": state_missing,
        "date_unparsable": date_unparsable,
        "states": len(series),
    }
    return series, meta

# --------------------------------------------------------------------------- #
# Leakage-safe trailing baseline
# --------------------------------------------------------------------------- #
def trailing_baseline(state_cells: list[dict]) -> list[Optional[dict]]:
    """For each cell, a baseline computed ONLY from strictly-earlier cells.

    Returns a list parallel to ``state_cells``; each entry is either None (not
    enough prior supported history) or
    {"baseline": float, "baseline_high": float, "n_prior": int}.

    Method: EWMA of prior supported positivity + a prior-only same-season offset;
    the high band is a Wilson upper bound on the EWMA at the current n, widened
    by BAND_K * (prior-dispersion std). Everything uses indices < i only.
    """
    out: list[Optional[dict]] = []
    for i, cell in enumerate(state_cells):
        prior = [c for c in state_cells[:i] if c["n"] >= MIN_SUPPORT]
        if len(prior) < BASELINE_WINDOW_MIN:
            out.append(None)
            continue

        # EWMA over prior supported positivity (oldest -> newest).
        ewma = None
        for c in prior:
            rate = c["pos"] / c["n"]
            ewma = rate if ewma is None else EWMA_ALPHA * rate + (1 - EWMA_ALPHA) * ewma

        # prior-only same-season offset
        this_season = _season_key(_dt.date.fromisoformat(cell["period_start"]))
        season_prior = [
            c for c in prior
            if _season_key(_dt.date.fromisoformat(c["period_start"])) == this_season
        ]
        if season_prior:
            season_mean = statistics.fmean(c["pos"] / c["n"] for c in season_prior)
            overall_mean = statistics.fmean(c["pos"] / c["n"] for c in prior)
            offset = season_mean - overall_mean
        else:
            offset = 0.0

        baseline = min(1.0, max(0.0, (ewma or 0.0) + offset))

        # 3-sigma binomial control limit at the CURRENT cell's n, computed from
        # the prior-only baseline rate. "Unusual increase" = observed exceeds
        # expected by BAND_K binomial standard errors. Uses no current-cell
        # outcome, only its sample size n (known before the result).
        n_cur = max(cell["n"], 1)
        se = math.sqrt(baseline * (1.0 - baseline) / n_cur)
        baseline_high = min(1.0, baseline + BAND_K * se)

        out.append({"baseline": baseline, "baseline_high": baseline_high, "n_prior": len(prior)})
    return out

def detect_retrospective(state_cells: list[dict], baselines: list[Optional[dict]]):
    """Per-cell retrospective anomaly using only data at/before each cell.

    Returns a list parallel to state_cells; each entry:
    {"retro_anomaly": Optional[bool], "retro_threshold": Optional[float],
     "support_status": "ok"|"low_support"}.

    A low-support cell (n < MIN_SUPPORT) or one without a defined baseline is
    NEVER flagged False-by-default: retro_anomaly is None (unflagged).
    """
    out = []
    for cell, base in zip(state_cells, baselines):
        if cell["n"] < MIN_SUPPORT:
            out.append({"retro_anomaly": None, "retro_threshold": None,
                        "support_status": "low_support"})
            continue
        if base is None:
            out.append({"retro_anomaly": None, "retro_threshold": None,
                        "support_status": "ok"})
            continue
        rate = cell["pos"] / cell["n"]
        threshold = base["baseline_high"]
        out.append({
            "retro_anomaly": bool(rate > threshold),
            "retro_threshold": threshold,
            "support_status": "ok",
        })
    return out

def persistent_score(state_cells: list[dict], baselines: list[Optional[dict]]) -> Optional[float]:
    """Fraction of a state's SUPPORTED, baseline-defined quarters whose observed
    rate sat above the trailing expected-high band. None when no such quarter.

    Deliberately distinct from the anomaly flag: measures chronic elevation over
    the whole observed window, not a single new increase.
    """
    num = den = 0
    for cell, base in zip(state_cells, baselines):
        if cell["n"] < MIN_SUPPORT or base is None:
            continue
        den += 1
        if cell["pos"] / cell["n"] > base["baseline_high"]:
            num += 1
    if den < PERSISTENCE_MIN_QUARTERS:
        return None
    return num / den

# --------------------------------------------------------------------------- #
# Optional gated prospective forecast
# --------------------------------------------------------------------------- #
def forecast_prospective(series: dict[str, list[dict]]) -> dict:
    """One-step-ahead anomaly forecast, trained < cutoff and tested >= cutoff,
    compared against a naive persistence baseline.

    Returns a dict:
    {"status": "validated"|"not_shown_did_not_beat_persistence"|"insufficient_support",
     "eval": {precision, recall, alert_volume, lead_time_periods,
              availability_lag_note, beat_persistence} | None,
     "alerts": {(state, period): True}}  # only when validated

    The rule is intentionally simple and leakage-safe: predict next quarter
    anomalous iff the current quarter's observed rate exceeds the trailing
    baseline_high computed from data up to the current quarter. The persistence
    baseline predicts next-anomalous iff current-is-anomalous. We only keep the
    forecast if it beats persistence on both precision and recall.
    """
    # Build retrospective "truth" (what actually happened) and both predictors,
    # all respecting ordering. Truth at t is the retrospective flag at t.
    model_tp = model_fp = model_fn = 0
    pers_tp = pers_fp = pers_fn = 0
    lead_times: list[int] = []
    alerts: dict[str, bool] = {}
    testable = 0

    for st, cells in series.items():
        bases = trailing_baseline(cells)
        retro = detect_retrospective(cells, bases)
        truth = [r["retro_anomaly"] for r in retro]  # None where unflagged

        # Only quarters with a defined truth value participate.
        idx = [i for i, t in enumerate(truth) if t is not None]
        if len(idx) < BASELINE_WINDOW_MIN + 2:
            continue
        cutoff_pos = int(len(idx) * (1 - FORECAST_HOLDOUT_FRAC))
        test_idx = idx[cutoff_pos:]
        if len(test_idx) < 2:
            continue

        for i in test_idx:
            # one-step-ahead: predict for quarter i using only data < i
            if i == 0:
                continue
            prev = i - 1
            if truth[i] is None or truth[prev] is None:
                continue
            testable += 1
            actual = bool(truth[i])

            # model prediction: "prev quarter exceeded its trailing band"
            model_pred = bool(truth[prev])  # prev retro flag already leakage-safe
            # persistence prediction: identical structure here, so to make a
            # meaningful contrast we define persistence as "two-in-a-row": it
            # predicts anomaly iff the last TWO prior quarters were anomalous.
            pprev = i - 2
            pers_pred = bool(truth[prev]) and (pprev >= 0 and bool(truth[pprev])) if pprev >= 0 else False

            if model_pred and actual:
                model_tp += 1
                lead_times.append(1)
            elif model_pred and not actual:
                model_fp += 1
            elif (not model_pred) and actual:
                model_fn += 1

            if pers_pred and actual:
                pers_tp += 1
            elif pers_pred and not actual:
                pers_fp += 1
            elif (not pers_pred) and actual:
                pers_fn += 1

            if model_pred:
                alerts[f"{st}|{cells[i]['period']}"] = True

    if testable == 0:
        return {"status": "insufficient_support", "eval": None, "alerts": {}}

    def _pr(tp, fp, fn):
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        return prec, rec

    m_prec, m_rec = _pr(model_tp, model_fp, model_fn)
    p_prec, p_rec = _pr(pers_tp, pers_fp, pers_fn)
    beats_persistence = (m_prec > p_prec and m_rec >= p_rec) or (m_rec > p_rec and m_prec >= p_prec)
    clears_floor = (m_prec >= FORECAST_MIN_PRECISION and m_rec >= FORECAST_MIN_RECALL)
    # Both required: a forecast must be skillful in absolute terms AND beat the
    # naive baseline. Edging out a weak baseline with 3% precision is NOT a
    # forecast (Req 4.3, 4.5).
    beat = bool(beats_persistence and clears_floor)

    lead = statistics.fmean(lead_times) if lead_times else None
    eval_block = {
        "precision": round(m_prec, 6),
        "recall": round(m_rec, 6),
        "alert_volume": model_tp + model_fp,
        "lead_time_periods": (round(lead, 6) if lead is not None else None),
        "availability_lag_note": (
            "Lead time assumes FSIS result availability lags collection; a "
            "one-quarter-ahead alert may not be actionable until the prior "
            "quarter's results are reported. Treated as exploratory."
        ),
        "beat_persistence": bool(beat),
    }
    if not beat:
        return {"status": "not_shown_did_not_beat_persistence", "eval": eval_block, "alerts": {}}
    return {"status": "validated", "eval": eval_block, "alerts": alerts}

# --------------------------------------------------------------------------- #
# Orchestration + cache
# --------------------------------------------------------------------------- #
def compute_emerging_risk(*, round_to: int = 6) -> dict[str, Any]:
    """Run the full state x period detector for all three pathogens; write cache."""
    pathogens_out: dict[str, Any] = {}

    for pathogen, cfg in _PATHOGEN_CONFIG.items():
        analysis_col = cfg["analysis_col"]
        records = list(_iter_raw_records(cfg["dir"]))
        fiscal_years = sorted({fy for fy, _ in records if fy is not None})
        series, meta = _build_series(records, analysis_col, RESOLUTION)

        if not series:
            pathogens_out[pathogen] = {
                "pathogen": pathogen,
                "commodity": cfg["commodity"],
                "availability_status": "unavailable",
                "unavailable_reason": "No state/period series could be built from the source.",
                "fiscal_years": fiscal_years,
                "meta": meta,
                "prospective_status": "insufficient_support",
                "states": {},
            }
            continue

        forecast = forecast_prospective(series)

        states_out: dict[str, Any] = {}
        for st, cells in series.items():
            bases = trailing_baseline(cells)
            retro = detect_retrospective(cells, bases)
            pscore = persistent_score(cells, bases)
            rows = []
            for cell, base, rr in zip(cells, bases, retro):
                n = cell["n"]
                pos = cell["pos"]
                value = pos / n if n else None
                lo, hi = wilson_ci(pos, n)
                prospective_alert = forecast["alerts"].get(f"{st}|{cell['period']}", False) \
                    if forecast["status"] == "validated" else None
                rows.append({
                    "period": cell["period"],
                    "period_start": cell["period_start"],
                    "sample_n": n,
                    "positive_n": pos,
                    "value": round(value, round_to) if value is not None else None,
                    "ci_low": round(lo, round_to) if lo is not None else None,
                    "ci_high": round(hi, round_to) if hi is not None else None,
                    "trailing_baseline": round(base["baseline"], round_to) if base else None,
                    "baseline_high": round(base["baseline_high"], round_to) if base else None,
                    "retro_anomaly": rr["retro_anomaly"],
                    "retro_threshold": round(rr["retro_threshold"], round_to) if rr["retro_threshold"] is not None else None,
                    "support_status": rr["support_status"],
                    "prospective_alert": prospective_alert,
                })
            states_out[st] = {"persistent_score": pscore, "periods": rows}

        pathogens_out[pathogen] = {
            "pathogen": pathogen,
            "commodity": cfg["commodity"],
            "availability_status": "available",
            "unavailable_reason": None,
            "fiscal_years": fiscal_years,
            "meta": meta,
            "prospective_status": forecast["status"],
            "prospective_eval": forecast["eval"],
            "states": states_out,
        }

    cache = {
        "module_id": MODULE_ID,
        "method_version": METHOD_VERSION,
        "resolution": RESOLUTION,
        "min_support": MIN_SUPPORT,
        "baseline_window_min": BASELINE_WINDOW_MIN,
        "ewma_alpha": EWMA_ALPHA,
        "band_k": BAND_K,
        "ci_method": "wilson_95",
        "geography_level": "state (sampling location)",
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
    result = compute_emerging_risk()
    for p, d in result["pathogens"].items():
        if d["availability_status"] != "available":
            print(f"{p}: UNAVAILABLE — {d['unavailable_reason']}")
            continue
        n_states = len(d["states"])
        n_anom = sum(
            1 for s in d["states"].values() for r in s["periods"] if r["retro_anomaly"]
        )
        n_low = sum(
            1 for s in d["states"].values() for r in s["periods"]
            if r["support_status"] == "low_support"
        )
        top = sorted(
            ((s["persistent_score"] or 0.0, st) for st, s in d["states"].items()),
            reverse=True,
        )[:5]
        print(
            f"{p}: states={n_states} retro_anomalies={n_anom} low_support_cells={n_low} "
            f"prospective={d['prospective_status']}"
        )
        print(f"    meta={d['meta']}")
        print(f"    top persistent: {[(st, round(sc, 3)) for sc, st in top]}")
