"""S07 — County Community Impact (county vulnerability x state-level hazard).

A finer-geographic-resolution companion to the state-level S06 module
(``src/analysis/community_impact.py``), which S07 leaves entirely untouched
(Req 11). S07 produces a per-**county** vulnerability-aware priority ranking per
pathogen (Salmonella, Listeria, STEC) by overlaying READ-ONLY state food-safety
hazard (observed FSIS positivity, reused unchanged from S04/S05 via
``fsis_state_year()``) with a committed **county-level** vulnerability table
(county Census ACS 65+ share + county-aggregated USDA Atlas low-income /
low-access tract-count shares).

Every value is OBSERVED (measured/published surveillance + census); S07 performs
**no new modeling** and trains no model. It is independent of S06: a distinct
``module_id`` ("S07"), its own cache (``s07_community_impact``'s sibling
``s07_county_community_impact.json``), and it reads the shared FSIS hazard
without mutating it (Req 11.1-11.4).

The central honest constraint is the **resolution mismatch**: the two sides of
the join have different native grains. Vulnerability is county-level, but FSIS
hazard is state-only (lab sampling carries an establishment state, not a
county). So a county ranking combines county vulnerability with that county's
**state-level** hazard, and every county in a state shares that state's single
hazard value. This mismatch is labeled explicitly on every record
(``resolution_label = "county vulnerability x state-level hazard"``). S07 never
implies county contamination, county infection, or a county-measured hazard.

Because of that mismatch, the hazard component is min-max normalized over the
STATE set (its native grain) and the vulnerability component over the COUNTY
set — the two documented, testable normalization scopes below. Switching the
population lens or the weights changes only the Priority_Score ordering, never
the hazard. under-5 (not in the S07 county ACS pull) and pregnancy (never
available at county grain) lenses are shown explicitly unavailable, never
fabricated.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from src.analysis.human_comparison import fsis_state_year
from src.pipeline.harmonize import state_from_fips

REPO_ROOT = Path(__file__).resolve().parents[2]
INTERIM_DIR = REPO_ROOT / "data" / "interim"
#: DISTINCT from S06's s06_community_impact.json so the S06 cache is never touched.
CACHE_PATH = INTERIM_DIR / "s07_county_community_impact.json"
#: The committed, reviewer-visible county vulnerability table (keyed on 5-digit FIPS).
COUNTY_VULN_PATH = REPO_ROOT / "data" / "processed" / "county_vulnerability.json"

MODULE_ID = "S07"
METHOD_VERSION = "s07.v1"
RESOLUTION_LABEL = "county vulnerability x state-level hazard"

#: Documented Priority_Score weights, reused from S06's conventions and re-declared
#: locally to avoid coupling to S06 internals (hazard-leaning: food safety is the hard
#: constraint, food-security secondary). Weights sum to 1.0.
DEFAULT_WEIGHTS = (0.6, 0.4)   # (hazard, vulnerability)
ALT_WEIGHT_SETS = [(0.5, 0.5), (0.4, 0.6)]

#: Data-backed county vulnerability lenses -> the committed-table field each reads.
#: NOTE county field names are low_income_share / low_access_share (county grain),
#: NOT S06's *_tract_share — they match the committed county_vulnerability.json keys.
LENS_FIELDS = {
    "elderly_65plus": "elderly_65plus_share",
    "low_income": "low_income_share",
    "low_access": "low_access_share",
}
#: Lenses the S07 county extraction does NOT support (shown unavailable, never faked).
UNAVAILABLE_LENSES = {
    "under5": "Under-5 share is not in the S07 county ACS pull.",
    "pregnancy": "Pregnancy/newborn counts are not available in the county ACS extraction.",
}

#: The two documented, testable normalization scopes (the key honest decision).
#: Hazard is normalized over the STATE set because FSIS positivity is state-only — there
#: is no honest sub-state hazard — so the normalized hazard component is computed over
#: states (its native grain) and then assigned to every county in that state. Normalizing
#: hazard over counties would silently re-rank a state hazard at county level and imply a
#: county-measured hazard, which S07 never does. Vulnerability IS county-level, so it is
#: normalized over the COUNTY set.
HAZARD_NORMALIZATION_SCOPE = "state"
VULNERABILITY_NORMALIZATION_SCOPE = "county"

_PATHOGENS = ("Salmonella", "Listeria", "STEC")
_COMMODITY = {"Salmonella": "raw_poultry", "Listeria": "rte", "STEC": "raw_beef"}


def state_hazard() -> dict[str, dict[str, float]]:
    """READ-ONLY per-(pathogen, state) observed positivity, reused from S04/S05.

    Returns {pathogen: {state: positivity}}. This is the hazard; S07 never
    modifies it (Req 11.4). Aggregates each state's reused FSIS (state, year)
    n/pos over all years to a single positivity.
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


def load_county_vulnerability() -> Optional[dict[str, Any]]:
    """Read the committed county_vulnerability.json; return None when absent/malformed.

    Returns the parsed committed table (with its ``counties`` map keyed on 5-digit
    county FIPS) when present. Returns None when the file is absent or cannot be parsed
    (same ``(OSError, ValueError)`` tolerance as S06's load_cache). S07 NEVER geocodes
    or pulls at runtime — it reads only the committed table. The caller handles the
    obtained=false / empty-counties honesty (unavailable + skipped_no_key gap).
    """
    if COUNTY_VULN_PATH.exists():
        try:
            return json.loads(COUNTY_VULN_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
    return None


def county_to_state(county_fips: str) -> Optional[str]:
    """Map a 5-digit county FIPS to its USPS state via the 2-digit prefix.

    Thin wrapper over ``harmonize.state_from_fips`` (which already handles a longer
    FIPS by taking the two-digit state prefix); returns None for a malformed/unknown
    FIPS. S07 never re-implements the state crosswalk.
    """
    return state_from_fips(county_fips)


def minmax_component(values: dict[str, Optional[float]]) -> dict[str, Optional[float]]:
    """Documented min-max normalization over the given set to [0,1], skipping None.
    A None input stays None (never imputed). Mirrors S06's minmax_component."""
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
    None when either component is missing (never a hazard-only or vulnerability-only
    score). Mirrors S06's priority_score exactly."""
    if hazard_c is None or vuln_c is None:
        return None
    w_h, w_v = weights
    return max(0.0, min(1.0, w_h * hazard_c + w_v * vuln_c))


def load_cache() -> Optional[dict[str, Any]]:
    """Mirror S06 load_cache: read CACHE_PATH, tolerate (OSError, ValueError) -> None."""
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
    return None

def weight_sensitivity(hazard_comp: dict[str, Optional[float]],
                       vuln_comp: dict[str, Optional[float]], *, top_k: int = 5) -> dict:
    """Top counties by Priority_Score under default vs each alternative weighting.

    Mirrors S06's ``weight_sensitivity`` exactly, but over COUNTIES: ``default_top`` and
    ``alt_top`` are lists of 5-digit county FIPS, ``rank_stable`` reports whether the top
    set is invariant across the default and alternative weightings, and the note discloses
    that the ranking is weight-dependent and no single weighting is definitive (Req 7).

    ``hazard_comp`` maps county_fips -> that county's (state-level) hazard component;
    ``vuln_comp`` maps county_fips -> the vulnerability component of the PRIMARY lens that
    drives sensitivity. Counties whose Priority_Score is None under a weighting are excluded
    from that weighting's top set (never a hazard-only or vulnerability-only score).
    """
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
            f"Top {top_k} counties by priority under default weights "
            f"{DEFAULT_WEIGHTS} vs alternatives {ALT_WEIGHT_SETS}. "
            "Ranking is weight-dependent; no single weighting is definitive."
        ),
    }


#: The data-backed lens that drives the per-pathogen county rank and the
#: weight_sensitivity top sets. We pick the elderly 65+ lens (the first data-backed
#: lens), mirroring S06's diagnostic which surfaces the elderly_65plus sensitivity;
#: this is a documented, deterministic choice. Ranking and sensitivity both read this
#: lens's vulnerability component so the two disclosures are consistent.
_PRIMARY_LENS = "elderly_65plus"


def compute_county_community_impact(*, round_to: int = 6) -> dict[str, Any]:
    """Overlay the READ-ONLY state hazard with the committed county vulnerability table
    into a documented per-county priority ranking per pathogen; write the S07 cache.

    The hazard is never modified. Hazard is min-max normalized over the STATE scope (its
    native grain) and assigned to every county in that state, so two counties in the same
    state+pathogen share an identical ``hazard_component`` AND ``hazard_positivity``
    (Property 2 / Req 1.2). Vulnerability is min-max normalized over the COUNTY scope.
    Switching the lens or weights re-orders only the Priority_Score, never the hazard.

    Availability precedence (deterministic, documented): a county with no vulnerability
    profile is ``unavailable`` ("No county vulnerability profile."); otherwise a county
    whose state has no hazard for the pathogen is ``unavailable`` ("State has no hazard for
    this pathogen."); otherwise ``available``. Unavailable counties are retained with a
    reason, never dropped or fabricated (Req 5).

    Rank and weight_sensitivity are driven by the primary (elderly_65plus) lens.
    """
    hz = state_hazard()

    weights_label = f"hazard {DEFAULT_WEIGHTS[0]} / vulnerability {DEFAULT_WEIGHTS[1]}"
    contextual_count_note = (
        "affected_population_context = low-access share x county population. A "
        "contextual/illustrative count of people who could be affected IF exposed "
        "— never an observed exposure or illness count."
    )

    county_vuln_table = load_county_vulnerability()
    counties_map: dict[str, Any] = {}
    obtained = False
    acs_vintage_top: Optional[str] = None
    atlas_vintage_top: Optional[str] = None
    share_definition: Optional[str] = None
    if isinstance(county_vuln_table, dict):
        raw_counties = county_vuln_table.get("counties")
        if isinstance(raw_counties, dict):
            counties_map = raw_counties
        obtained = bool(county_vuln_table.get("obtained", True))
        acs_vintage_top = county_vuln_table.get("acs_vintage")
        atlas_vintage_top = county_vuln_table.get("atlas_vintage")
        share_definition = county_vuln_table.get("share_definition")

    gaps: list[dict[str, Any]] = []

    # (a) HONEST key-absent / no-committed-table path: no table, empty counties, or an
    # explicit obtained=false. Every pathogen is still first-class but carries no county
    # records (there are no committed counties to emit), with a skipped_no_key-style gap.
    if county_vuln_table is None or not counties_map or not obtained:
        gaps.append({
            "source": "census_acs",
            "reason": "skipped-no-key",
            "detail": (
                "CENSUS_API_KEY absent or committed county vulnerability table not "
                "present; county vulnerability unavailable."
            ),
        })
        unavailable_reason = (
            "CENSUS_API_KEY absent or committed county vulnerability table not "
            "present; county vulnerability unavailable."
        )
        pathogens_out: dict[str, Any] = {}
        for pathogen in _PATHOGENS:
            pathogens_out[pathogen] = {
                "pathogen": pathogen,
                "commodity": _COMMODITY[pathogen],
                "availability_status": "unavailable",
                "unavailable_reason": unavailable_reason,
                "weight_sensitivity": weight_sensitivity({}, {}),
                "records": [],
            }
        cache = _assemble_cache(
            pathogens_out,
            acs_vintage=acs_vintage_top,
            atlas_vintage=atlas_vintage_top,
            share_definition=share_definition,
            gaps=gaps,
        )
        INTERIM_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")
        return cache

    # (c) Build the county universe keyed on 5-digit FIPS; map each county -> state.
    county_state: dict[str, Optional[str]] = {}
    for fips in counties_map:
        state = county_to_state(fips) if isinstance(fips, str) else None
        if state is None:
            gaps.append({
                "source": "county_vulnerability",
                "reason": "unmappable-fips",
                "detail": f"County FIPS {fips!r} is malformed or maps to no known state.",
                "county_fips": fips,
            })
        county_state[fips] = state

    pathogens_out = {}
    for pathogen in _PATHOGENS:
        hz_p = hz.get(pathogen, {})

        # (d) HAZARD over the STATE scope. Normalize over the set of states that have a
        # hazard for this pathogen; each county reads its state's component / positivity,
        # guaranteeing identical hazard for same state+pathogen (Property 2 / Req 1.2).
        hazard_comp_by_state = minmax_component({s: hz_p.get(s) for s in hz_p})

        # VULNERABILITY over the COUNTY scope, per data-backed lens.
        vuln_comp_by_county: dict[str, dict[str, Optional[float]]] = {}
        for lens, field in LENS_FIELDS.items():
            vuln_values = {
                fips: counties_map[fips].get(field) for fips in counties_map
            }
            vuln_comp_by_county[lens] = minmax_component(vuln_values)

        # Per-county hazard component / positivity maps (keyed on county_fips) for the
        # primary lens rank + weight_sensitivity.
        hazard_comp_by_county = {
            fips: hazard_comp_by_state.get(county_state.get(fips))
            for fips in counties_map
        }
        primary_vuln_by_county = {
            fips: vuln_comp_by_county[_PRIMARY_LENS].get(fips) for fips in counties_map
        }

        # Per-county primary priority (for ranking available-scored counties).
        primary_priority: dict[str, Optional[float]] = {
            fips: priority_score(
                hazard_comp_by_county.get(fips),
                primary_vuln_by_county.get(fips),
                DEFAULT_WEIGHTS,
            )
            for fips in counties_map
        }
        ranked_fips = sorted(
            (f for f in counties_map if primary_priority.get(f) is not None),
            key=lambda f: (-primary_priority[f], f),
        )
        rank_by_fips = {f: i + 1 for i, f in enumerate(ranked_fips)}

        records = []
        for fips in sorted(counties_map):
            profile = counties_map[fips]
            state = county_state.get(fips)
            hazard_c = hazard_comp_by_state.get(state) if state is not None else None
            hazard_pos = hz_p.get(state) if state is not None else None

            # A county has a vulnerability profile when ANY data-backed lens value is present.
            have_vuln = any(
                profile.get(field) is not None for field in LENS_FIELDS.values()
            )
            has_hazard = hazard_c is not None

            lenses = []
            for lens, field in LENS_FIELDS.items():
                vc = vuln_comp_by_county[lens].get(fips)
                if vc is None:
                    lenses.append({
                        "lens": lens,
                        "available": False,
                        "vulnerability_component": None,
                        "priority_score": None,
                        "weights": weights_label,
                        "unavailable_reason": (
                            "No county vulnerability profile." if not have_vuln
                            else f"{field} not available for this county."
                        ),
                    })
                else:
                    ps = priority_score(hazard_c, vc, DEFAULT_WEIGHTS)
                    lenses.append({
                        "lens": lens,
                        "available": True,
                        "vulnerability_component": round(vc, round_to),
                        "priority_score": round(ps, round_to) if ps is not None else None,
                        "weights": weights_label,
                        "unavailable_reason": None,
                    })
            for lens, reason in UNAVAILABLE_LENSES.items():
                lenses.append({
                    "lens": lens,
                    "available": False,
                    "vulnerability_component": None,
                    "priority_score": None,
                    "weights": weights_label,
                    "unavailable_reason": reason,
                })

            total_population = profile.get("total_population")
            elderly_share = profile.get("elderly_65plus_share")
            low_income_share = profile.get("low_income_share")
            low_access_share = profile.get("low_access_share")
            affected_ctx = (
                round(low_access_share * total_population, 2)
                if (low_access_share is not None and total_population is not None)
                else None
            )

            # Vintages track availability (Req 9): disclosed only when the county carries an
            # available ACS / Atlas value respectively; None otherwise.
            acs_vintage = acs_vintage_top if elderly_share is not None else None
            atlas_vintage = (
                atlas_vintage_top
                if (low_income_share is not None or low_access_share is not None)
                else None
            )

            # Availability precedence (documented): no vuln profile -> unavailable;
            # else no state hazard for pathogen -> unavailable; else available.
            if not have_vuln:
                availability_status = "unavailable"
                unavailable_reason = "No county vulnerability profile."
            elif not has_hazard:
                availability_status = "unavailable"
                unavailable_reason = "State has no hazard for this pathogen."
            else:
                availability_status = "available"
                unavailable_reason = None

            records.append({
                "county_fips": fips,
                "county_name": profile.get("county_name"),
                "state": state,
                "geography_level": "county",
                "resolution_label": RESOLUTION_LABEL,
                "commodity": _COMMODITY[pathogen],
                "pathogen": pathogen,
                "hazard_positivity": round(hazard_pos, round_to) if hazard_pos is not None else None,
                "hazard_component": round(hazard_c, round_to) if hazard_c is not None else None,
                "rank": rank_by_fips.get(fips),
                "affected_population_context": affected_ctx,
                "total_population": total_population,
                "elderly_65plus_share": elderly_share,
                "low_income_share": low_income_share,
                "low_access_share": low_access_share,
                "under5_share": None,
                "acs_vintage": acs_vintage,
                "atlas_vintage": atlas_vintage,
                "lenses": lenses,
                "contextual_count_note": contextual_count_note,
                "status": "OBSERVED",
                "availability_status": availability_status,
                "unavailable_reason": unavailable_reason,
            })

        sensitivity = weight_sensitivity(
            hazard_comp_by_county, primary_vuln_by_county, top_k=5
        )

        pathogens_out[pathogen] = {
            "pathogen": pathogen,
            "commodity": _COMMODITY[pathogen],
            "availability_status": "available",
            "unavailable_reason": None,
            "weight_sensitivity": sensitivity,
            "records": records,
        }

    cache = _assemble_cache(
        pathogens_out,
        acs_vintage=acs_vintage_top,
        atlas_vintage=atlas_vintage_top,
        share_definition=share_definition,
        gaps=gaps,
    )
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")
    return cache


def _assemble_cache(pathogens_out: dict[str, Any], *, acs_vintage: Optional[str],
                    atlas_vintage: Optional[str], share_definition: Optional[str],
                    gaps: list[dict[str, Any]]) -> dict[str, Any]:
    """Assemble the deterministic S07 cache dict (documented metadata + gaps + pathogens)."""
    return {
        "module_id": MODULE_ID,
        "method_version": METHOD_VERSION,
        "geography_level": "county",
        "resolution_label": RESOLUTION_LABEL,
        "default_weights": {"hazard": DEFAULT_WEIGHTS[0], "vulnerability": DEFAULT_WEIGHTS[1]},
        "alt_weight_sets": [{"hazard": h, "vulnerability": v} for h, v in ALT_WEIGHT_SETS],
        "data_backed_lenses": sorted(LENS_FIELDS),
        "unavailable_lenses": UNAVAILABLE_LENSES,
        "component_normalization": (
            "min-max to [0,1], None skipped (never imputed): hazard over the STATE set "
            "(its native state-level grain, assigned to every county in that state), "
            "vulnerability over the COUNTY set."
        ),
        "hazard_normalization_scope": HAZARD_NORMALIZATION_SCOPE,
        "vulnerability_normalization_scope": VULNERABILITY_NORMALIZATION_SCOPE,
        "acs_vintage": acs_vintage,
        "atlas_vintage": atlas_vintage,
        "share_definition": share_definition,
        "gaps": gaps,
        "pathogens": pathogens_out,
    }
