"""S06 — Vulnerability-aware impact ranking (state level).

Overlays READ-ONLY state food-safety hazard (observed positivity, reused from
S04/S05) with the existing per-state ACS 2022 / USDA Food Access Atlas 2019
vulnerability context (the exporter's build_vulnerability output) to produce a
transparent, documented multi-criteria priority ranking per pathogen.

The hazard is never modified: switching the population lens or the weights
changes only the Priority_Score ordering, never a risk value. Population
demographics describe who could be more affected IF exposed; they never
establish who was exposed or ill. No county/tract infection claim; under-5 (not
in the current ACS pull) and pregnancy (never available) lenses are shown as
explicitly unavailable, never fabricated. State-level only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from src.analysis.human_comparison import fsis_state_year

REPO_ROOT = Path(__file__).resolve().parents[2]
INTERIM_DIR = REPO_ROOT / "data" / "interim"
CACHE_PATH = INTERIM_DIR / "s06_community_impact.json"

MODULE_ID = "S06"
METHOD_VERSION = "s06.v1"

#: Data-backed vulnerability lenses -> the VulnerabilityProfile field each reads.
LENS_FIELDS = {
    "elderly_65plus": "elderly_65plus_share",
    "low_income": "low_income_tract_share",
    "low_access": "low_access_tract_share",
}
#: Lenses the current ACS extraction does NOT support (shown unavailable, never faked).
UNAVAILABLE_LENSES = {
    "under5": "Under-5 share is not in the current ACS pull (state aggregation).",
    "pregnancy": "Pregnancy/newborn counts are not available in the current ACS extraction.",
}

#: Documented Priority_Score weights (hazard-leaning per the brief: food safety is
#: the hard constraint, food-security secondary). Fixed from development evidence.
DEFAULT_WEIGHTS = (0.6, 0.4)   # (hazard, vulnerability)
ALT_WEIGHT_SETS = [(0.5, 0.5), (0.4, 0.6)]

_PATHOGENS = ("Salmonella", "Listeria", "STEC")
_COMMODITY = {"Salmonella": "raw_poultry", "Listeria": "rte", "STEC": "raw_beef"}

def state_hazard() -> dict[str, dict[str, float]]:
    """READ-ONLY per-(pathogen, state) observed positivity, reused from S04/S05.

    Returns {pathogen: {state: positivity}}. This is the hazard; S06 never
    modifies it. Aggregates each state's reused FSIS (state, year) n/pos over all
    years to a single positivity.
    """
    fsis = fsis_state_year()  # {pathogen: {(state, year): {n, pos}}}
    out: dict[str, dict[str, float]] = {}
    for pathogen, cells in fsis.items():
        by_state: dict[str, list[int]] = {}
        for (state, _year), g in cells.items():
            acc = by_state.setdefault(state, [0, 0])
            acc[0] += g["n"]
            acc[1] += g["pos"]
        out[pathogen] = {
            s: (pos / n) for s, (n, pos) in by_state.items() if n > 0
        }
    return out

def load_vulnerability() -> dict[str, dict[str, Any]]:
    """Per-state ACS/Atlas vulnerability fields + vintages, via build_vulnerability.
    Reuses the exporter's existing reader; S06 derives nothing new."""
    from src.artifacts.exporter import build_vulnerability

    out: dict[str, dict[str, Any]] = {}
    for rec in build_vulnerability():
        out[str(rec["region"])] = rec
    return out

def minmax_component(values: dict[str, Optional[float]]) -> dict[str, Optional[float]]:
    """Documented min-max normalization over states to [0,1], skipping None.
    A None input stays None (never imputed)."""
    present = [v for v in values.values() if v is not None]
    if not present:
        return {s: None for s in values}
    lo, hi = min(present), max(present)
    span = hi - lo
    out: dict[str, Optional[float]] = {}
    for s, v in values.items():
        if v is None:
            out[s] = None
        elif span == 0:
            out[s] = 0.0
        else:
            out[s] = (v - lo) / span
    return out

def priority_score(hazard_c: Optional[float], vuln_c: Optional[float],
                   weights: tuple[float, float]) -> Optional[float]:
    """Weighted combination w_h*hazard + w_v*vulnerability in [0,1].
    None when either component is missing (never a hazard-only score mislabeled
    as vulnerability-aware)."""
    if hazard_c is None or vuln_c is None:
        return None
    w_h, w_v = weights
    return max(0.0, min(1.0, w_h * hazard_c + w_v * vuln_c))

def weight_sensitivity(hazard_comp: dict[str, Optional[float]],
                       vuln_comp: dict[str, Optional[float]], *, top_k: int = 5) -> dict:
    """Top states by Priority_Score under default vs each alternative weighting.
    Reports whether the top set is stable, so no single weighting is definitive."""
    def _top(weights):
        scored = [
            (s, priority_score(hazard_comp.get(s), vuln_comp.get(s), weights))
            for s in hazard_comp
        ]
        scored = [(s, v) for s, v in scored if v is not None]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [s for s, _ in scored[:top_k]]

    default_top = _top(DEFAULT_WEIGHTS)
    alt_tops = [_top(w) for w in ALT_WEIGHT_SETS]
    rank_stable = all(set(a) == set(default_top) for a in alt_tops)
    return {
        "default_top": default_top,
        "alt_top": alt_tops[0] if alt_tops else [],
        "rank_stable": bool(rank_stable),
        "note": (
            f"Top {top_k} states by priority under default weights "
            f"{DEFAULT_WEIGHTS} vs alternatives {ALT_WEIGHT_SETS}. "
            "Ranking is weight-dependent; no single weighting is definitive."
        ),
    }

def compute_community_impact(*, round_to: int = 6) -> dict[str, Any]:
    """Overlay read-only hazard with vulnerability into a documented priority
    ranking per pathogen; write the S06 cache. Hazard is never modified."""
    vuln = load_vulnerability()
    hz = state_hazard()

    vuln_raw = {
        lens: {s: vuln[s].get(field) for s in vuln}
        for lens, field in LENS_FIELDS.items()
    }
    vuln_comp = {lens: minmax_component(vals) for lens, vals in vuln_raw.items()}

    pathogens_out: dict[str, Any] = {}
    for pathogen in _PATHOGENS:
        commodity = _COMMODITY[pathogen]
        hz_p = hz.get(pathogen, {})
        if not hz_p:
            pathogens_out[pathogen] = {
                "pathogen": pathogen, "commodity": commodity,
                "availability_status": "unavailable",
                "unavailable_reason": "No state hazard available for this pathogen.",
                "records": [],
            }
            continue

        hazard_comp = minmax_component({s: hz_p.get(s) for s in hz_p})

        sensitivity_by_lens = {
            lens: weight_sensitivity(hazard_comp, vuln_comp[lens])
            for lens in LENS_FIELDS
        }

        records = []
        for s in sorted(hz_p):
            vprofile = vuln.get(s, {})
            have_vuln = s in vuln
            lenses = []
            for lens, field in LENS_FIELDS.items():
                vc = vuln_comp[lens].get(s)
                if not have_vuln or vc is None:
                    lenses.append({
                        "lens": lens, "available": False,
                        "vulnerability_component": None, "priority_score": None,
                        "weights": f"hazard {DEFAULT_WEIGHTS[0]} / vulnerability {DEFAULT_WEIGHTS[1]}",
                        "unavailable_reason": (
                            "No vulnerability profile for this state." if not have_vuln
                            else f"{field} not available for this state."
                        ),
                    })
                else:
                    ps = priority_score(hazard_comp.get(s), vc, DEFAULT_WEIGHTS)
                    lenses.append({
                        "lens": lens, "available": True,
                        "vulnerability_component": round(vc, round_to),
                        "priority_score": round(ps, round_to) if ps is not None else None,
                        "weights": f"hazard {DEFAULT_WEIGHTS[0]} / vulnerability {DEFAULT_WEIGHTS[1]}",
                        "unavailable_reason": None,
                    })
            for lens, reason in UNAVAILABLE_LENSES.items():
                lenses.append({
                    "lens": lens, "available": False,
                    "vulnerability_component": None, "priority_score": None,
                    "weights": f"hazard {DEFAULT_WEIGHTS[0]} / vulnerability {DEFAULT_WEIGHTS[1]}",
                    "unavailable_reason": reason,
                })

            pop = vprofile.get("total_population") if have_vuln else None
            la_share = vprofile.get("low_access_tract_share") if have_vuln else None
            affected_ctx = (round(la_share * pop, 2) if (la_share is not None and pop is not None) else None)

            records.append({
                "region": s,
                "hazard_component": round(hazard_comp.get(s), round_to) if hazard_comp.get(s) is not None else None,
                "hazard_positivity": round(hz_p.get(s), round_to) if hz_p.get(s) is not None else None,
                "total_population": pop,
                "affected_population_context": affected_ctx,
                "elderly_65plus_share": vprofile.get("elderly_65plus_share") if have_vuln else None,
                "low_income_tract_share": vprofile.get("low_income_tract_share") if have_vuln else None,
                "low_access_tract_share": la_share,
                "under5_share": None,
                "acs_vintage": vprofile.get("acs_vintage") if have_vuln else None,
                "atlas_vintage": vprofile.get("atlas_vintage") if have_vuln else None,
                "lenses": lenses,
                "availability_status": "available" if have_vuln else "unavailable",
                "unavailable_reason": None if have_vuln else "No ACS/Atlas vulnerability profile for this state.",
            })

        pathogens_out[pathogen] = {
            "pathogen": pathogen, "commodity": commodity,
            "availability_status": "available",
            "unavailable_reason": None,
            "weight_sensitivity_by_lens": sensitivity_by_lens,
            "records": records,
        }

    cache = {
        "module_id": MODULE_ID,
        "method_version": METHOD_VERSION,
        "geography_level": "state",
        "default_weights": {"hazard": DEFAULT_WEIGHTS[0], "vulnerability": DEFAULT_WEIGHTS[1]},
        "alt_weight_sets": [{"hazard": h, "vulnerability": v} for h, v in ALT_WEIGHT_SETS],
        "data_backed_lenses": sorted(LENS_FIELDS),
        "unavailable_lenses": UNAVAILABLE_LENSES,
        "component_normalization": "min-max over states to [0,1], None skipped (never imputed)",
        "contextual_count_note": (
            "affected_population_context = low-access share x state population. A "
            "contextual/illustrative count of people who could be affected IF exposed "
            "— never an observed exposure or illness count."
        ),
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
    print("S06 INVENTORY + RANKING — diagnostic.")
    vuln = load_vulnerability()
    print(f"  states with vulnerability profile: {len(vuln)}")
    fields = ["total_population", "elderly_65plus_share", "under5_share",
              "low_income_tract_share", "low_access_tract_share",
              "acs_vintage", "atlas_vintage"]
    for f in fields:
        present = sum(1 for r in vuln.values() if r.get(f) is not None)
        print(f"    {f}: present in {present}/{len(vuln)} states")
    acs_vins = {r.get("acs_vintage") for r in vuln.values() if r.get("acs_vintage")}
    atlas_vins = {r.get("atlas_vintage") for r in vuln.values() if r.get("atlas_vintage")}
    print(f"  ACS vintage(s): {sorted(acs_vins)}  Atlas vintage(s): {sorted(atlas_vins)}")

    print("  computing READ-ONLY hazard + full ranking (reusing S04/S05)...")
    result = compute_community_impact()
    for p, d in result["pathogens"].items():
        if d["availability_status"] != "available":
            print(f"  {p}: UNAVAILABLE — {d['unavailable_reason']}")
            continue
        sens = d["weight_sensitivity_by_lens"]["elderly_65plus"]
        avail = sum(1 for r in d["records"] if r["availability_status"] == "available")
        print(f"  {p}: records={len(d['records'])} with_vulnerability={avail}")
        print(f"      65+ lens top (default 0.6/0.4): {sens['default_top']}")
        print(f"      65+ lens top (alt {ALT_WEIGHT_SETS[1]}): {sens['alt_top']}  rank_stable={sens['rank_stable']}")
