"""S03 — Persistent establishment surveillance monitor (EB, descriptive).

A THIN layer over the existing, tested ``src/models/establishment.py``. For each
pathogen it reuses:

* ``load_establishment_samples(pathogen)`` — the leakage-safe per-sample table
  (routine-surveillance cohort, FSIS identity, tri-state result), and
* ``build_establishment_quarters(frame)`` — the establishment x quarter panel.

On top of that it applies S03's OWN locked parameters (a per-pathogen
method-of-moments beta prior, and MIN_SUPPORT_ESTABLISHMENT = 20) rather than the
existing module's fixed strong_prior=100 / HISTORY_MIN_SAMPLES=10, and emits the
FULL ranked establishment list (not that module's top-20 summary). The existing
module is neither edited nor weakened.

For each establishment it reports an uncertainty-aware beta-binomial Empirical
Bayes posterior positivity (partially pooled toward the pathogen peer rate) with
a 95% credible interval, plus persistence evidence (repeated-positive quarters,
recent support, sampling gaps). The central rule: low testing is NEVER safety — a
thinly-sampled establishment is shrunk toward the peer rate with a wide interval
and flagged low-support, never "clean".

Geography is sampling (establishment) location only; identity is FSIS-published
(id / number-as-name / state), never contact detail; no establishment is implied
to supply any retailer. Positivity is surveillance signal, not contamination.

The scan runs offline via :func:`compute_establishment_surveillance` and caches
to ``data/interim/s03_establishment_surveillance.json``; the exporter reads it.
"""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path
from typing import Any, Optional

from src.models.establishment import (
    build_establishment_quarters,
    load_establishment_samples,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
INTERIM_DIR = REPO_ROOT / "data" / "interim"
CACHE_PATH = INTERIM_DIR / "s03_establishment_surveillance.json"

MODULE_ID = "S03"
METHOD_VERSION = "s03.v1"

#: Locked from the Task-1 inventory audit.
MIN_SUPPORT_ESTABLISHMENT = 20   # rank above this; below = low_support (uncertain)
PRIOR_FIT_MIN_SUPPORT = 30       # establishments informing the beta-prior fit

#: pathogen -> commodity (for the artifact; mirrors the S01/S04 mapping).
_COMMODITY = {"Salmonella": "raw_poultry", "Listeria": "rte", "STEC": "raw_beef"}
_PATHOGENS = ("Salmonella", "Listeria", "STEC")

#: FSIS MPI establishment directory -> per-establishment location. This is the
#: official FSIS-published plant directory (data/raw/fsis/...), keyed by the
#: same numeric establishment_id the sampling files carry. It gives each plant's
#: PROCESSING-SITE county + coordinates - never a consumption or illness location.
MPI_DIRECTORY = REPO_ROOT / "data" / "raw" / "fsis" / "MPI_Directory_by_Establishment_Number.csv"

def _clean(val: Optional[str]) -> Optional[str]:
    if val is None:
        return None
    t = str(val).strip()
    return t or None

def _float(val: Optional[str]) -> Optional[float]:
    t = _clean(val)
    if t is None:
        return None
    try:
        return float(t)
    except ValueError:
        return None

def load_mpi_directory() -> dict[str, dict]:
    """Map establishment_id -> {county, fips_code, city, latitude, longitude}.

    Reads the official FSIS MPI directory. Missing/unparsable location fields
    stay None (never fabricated). Returns {} if the file is absent so S03
    degrades honestly to coordinates-unavailable.
    """
    import csv
    out: dict[str, dict] = {}
    if not MPI_DIRECTORY.exists():
        return out
    with open(MPI_DIRECTORY, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            eid = _clean(row.get("establishment_id"))
            if eid is None:
                continue
            out[eid] = {
                "county": _clean(row.get("county")),
                "fips_code": _clean(row.get("fips_code")),
                "city": _clean(row.get("city")),
                "latitude": _float(row.get("latitude")),
                "longitude": _float(row.get("longitude")),
            }
    return out

def fit_beta_prior(rates: list[float]) -> tuple[float, float, float]:
    """Method-of-moments Beta(alpha0, beta0) from per-establishment rates.

    Returns (alpha0, beta0, peer_rate). Falls back to a weak prior centered on
    the mean when the variance is degenerate.
    """
    if len(rates) < 2:
        m = rates[0] if rates else 0.0
        return (max(m, 1e-6), max(1.0 - m, 1e-6), m)
    m = statistics.fmean(rates)
    v = statistics.pvariance(rates)
    if v <= 0 or m <= 0 or m >= 1:
        return (max(m, 1e-6) * 2, max(1.0 - m, 1e-6) * 2, m)
    common = m * (1.0 - m) / v - 1.0
    if common <= 0:
        return (max(m, 1e-6) * 2, max(1.0 - m, 1e-6) * 2, m)
    return (m * common, (1.0 - m) * common, m)

def _beta_ci(a: float, b: float) -> tuple[Optional[float], Optional[float]]:
    """95% equal-tailed Beta credible interval; None when scipy unavailable."""
    try:
        from scipy.stats import beta as _beta  # type: ignore
        return (float(_beta.ppf(0.025, a, b)), float(_beta.ppf(0.975, a, b)))
    except Exception:  # noqa: BLE001 - scipy optional (mirrors src/models/establishment.py)
        return (None, None)

def eb_posterior(pos: int, n: int, alpha0: float, beta0: float):
    """Posterior Beta(alpha0+pos, beta0+n-pos): (mean, ci_low, ci_high)."""
    a = alpha0 + pos
    b = beta0 + (n - pos)
    mean = a / (a + b) if (a + b) > 0 else None
    lo, hi = _beta_ci(a, b)
    return mean, lo, hi

def _persistence(quarter_rows: list[dict]) -> dict[str, Any]:
    """Descriptive, prior-independent persistence evidence from quarter rows.

    quarter_rows: [{"quarter": str, "quarter_start": iso, "samples": int,
                    "positives": int}, ...] ordered by quarter_start.
    """
    supported = [r for r in quarter_rows if r["samples"] > 0]
    positive_qs = [r for r in supported if r["positives"] > 0]
    # sampling gaps = supported quarters missing between first and last support
    gaps = 0
    if len(supported) >= 2:
        # count distinct quarter indices actually present vs the span; a gap is
        # any quarter with zero samples lying between the first and last support.
        present = len(supported)
        # span in quarters is just (#rows between first/last that have samples);
        # we approximate gaps as (rows with zero samples) within the observed
        # quarter_start range.
        zero_rows = [r for r in quarter_rows if r["samples"] == 0]
        gaps = len(zero_rows)
    return {
        "repeated_positive_periods": len(positive_qs),
        "periods_supported": len(supported),
        "last_supported_period": supported[-1]["quarter"] if supported else None,
        "sampling_gaps": gaps,
    }

def compute_establishment_surveillance(*, round_to: int = 6) -> dict[str, Any]:
    """Run the EB establishment surveillance for all three pathogens; write cache."""
    pathogens_out: dict[str, Any] = {}
    mpi = load_mpi_directory()

    for pathogen in _PATHOGENS:
        commodity = _COMMODITY[pathogen]
        try:
            es = load_establishment_samples(pathogen)
        except FileNotFoundError as exc:
            pathogens_out[pathogen] = {
                "pathogen": pathogen,
                "commodity": commodity,
                "availability_status": "unavailable",
                "unavailable_reason": f"establishment samples unavailable: {exc}",
                "establishments": {},
                "meta": {},
            }
            continue

        panel = build_establishment_quarters(es.frame)
        fiscal_years = sorted(
            {int(q.split("-Q")[0]) for q in panel["quarter"].astype(str) if "-Q" in q}
        )

        # Aggregate to per-establishment totals + ordered quarter rows.
        establishments: dict[str, dict] = {}
        est_missing = 0
        for r in panel.itertuples(index=False):
            eid = str(getattr(r, "establishment_id"))
            if eid in ("", "nan", "None", "<NA>"):
                est_missing += 1
                continue
            e = establishments.setdefault(eid, {
                "establishment_id": eid,
                "state": str(getattr(r, "state", "UNK")),
                "n": 0, "pos": 0, "quarters": [],
            })
            n = int(getattr(r, "samples"))
            pos = int(getattr(r, "positives"))
            e["n"] += n
            e["pos"] += pos
            e["quarters"].append({
                "quarter": str(getattr(r, "quarter")),
                "quarter_start": str(getattr(r, "quarter_start")),
                "samples": n,
                "positives": pos,
            })

        # establishment_name lookup from the sample frame (FSIS-published).
        name_by_id: dict[str, Optional[str]] = {}
        try:
            fr = es.frame[["establishment_id", "establishment_name"]].drop_duplicates()
            for row in fr.itertuples(index=False):
                nm = getattr(row, "establishment_name")
                name_by_id[str(getattr(row, "establishment_id"))] = (
                    None if (nm is None or str(nm) in ("nan", "<NA>", "None", "")) else str(nm)
                )
        except Exception:  # noqa: BLE001 - name optional; never fabricate
            name_by_id = {}

        # Fit the per-pathogen MoM beta prior on the routine cohort.
        rates = [
            e["pos"] / e["n"]
            for e in establishments.values()
            if e["n"] >= PRIOR_FIT_MIN_SUPPORT
        ]
        alpha0, beta0, peer_rate = fit_beta_prior(rates)

        # Per-establishment EB posterior + persistence.
        est_out = {}
        coord_hit = 0
        for eid, e in establishments.items():
            n, pos = e["n"], e["pos"]
            e["quarters"].sort(key=lambda q: q["quarter_start"])
            mean, lo, hi = eb_posterior(pos, n, alpha0, beta0)
            loc = mpi.get(eid, {})
            if loc.get("latitude") is not None and loc.get("longitude") is not None:
                coord_hit += 1
            est_out[eid] = {
                "establishment_id": eid,
                "establishment_name": name_by_id.get(eid),
                "state": e["state"],
                "sample_n": n,
                "positive_n": pos,
                "value": round(pos / n, round_to) if n else None,
                "eb_posterior": round(mean, round_to) if mean is not None else None,
                "ci_low": round(lo, round_to) if lo is not None else None,
                "ci_high": round(hi, round_to) if hi is not None else None,
                "support_status": "ok" if n >= MIN_SUPPORT_ESTABLISHMENT else "low_support",
                "persistence": _persistence(e["quarters"]),
                "county": loc.get("county"),
                "fips_code": loc.get("fips_code"),
                "city": loc.get("city"),
                "latitude": loc.get("latitude"),
                "longitude": loc.get("longitude"),
                "coordinates_status": (
                    "available"
                    if (loc.get("latitude") is not None and loc.get("longitude") is not None)
                    else "unavailable"
                ),
            }

        pathogens_out[pathogen] = {
            "pathogen": pathogen,
            "commodity": commodity,
            "availability_status": "available" if est_out else "unavailable",
            "unavailable_reason": None if est_out else "no establishments with testable samples.",
            "fiscal_years": fiscal_years,
            "peer_rate": round(peer_rate, round_to),
            "prior_alpha0": round(alpha0, round_to),
            "prior_beta0": round(beta0, round_to),
            "prior_fit_n": len(rates),
            "predictive_status": "descriptive_only",
            "establishment_missing": est_missing,
            "n_establishments": len(est_out),
            "coordinates_available": coord_hit,
            "coordinates_total": len(est_out),
            "establishments": est_out,
        }

    cache = {
        "module_id": MODULE_ID,
        "method_version": METHOD_VERSION,
        "resolution": "quarterly",
        "min_support_establishment": MIN_SUPPORT_ESTABLISHMENT,
        "prior_fit_min_support": PRIOR_FIT_MIN_SUPPORT,
        "ci_method": "beta_eb_95",
        "geography_level": "establishment (sampling location); county/coordinates from the FSIS MPI directory are the processing-site location, never a consumption or illness location",
        "cohort": "routine_surveillance_only (via load_establishment_samples)",
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
    result = compute_establishment_surveillance()
    for p, d in result["pathogens"].items():
        if d["availability_status"] != "available":
            print(f"{p}: UNAVAILABLE — {d['unavailable_reason']}")
            continue
        ests = d["establishments"].values()
        ranked = sorted(
            (e for e in ests if e["support_status"] == "ok"),
            key=lambda e: (e["eb_posterior"] or 0.0),
            reverse=True,
        )
        low = sum(1 for e in ests if e["support_status"] == "low_support")
        print(
            f"{p}: establishments={d['n_establishments']} "
            f"(low_support={low}) peer_rate={d['peer_rate']} "
            f"prior=({d['prior_alpha0']},{d['prior_beta0']}) fit_n={d['prior_fit_n']} "
            f"predictive={d['predictive_status']}"
        )
        print("    top EB-ranked (id, eb, [ci], n, pos):")
        for e in ranked[:5]:
            ci = f"[{e['ci_low']}, {e['ci_high']}]"
            print(f"      {e['establishment_id']}: eb={e['eb_posterior']} {ci} "
                  f"n={e['sample_n']} pos={e['positive_n']}")
