"""Surveillance Actions — reproducible decision layer over the science modules.

Turns the OBSERVED surveillance signals already produced by S01/S03/S04/S06 into
a ranked list of suggested, human-review-gated operational actions for the
retailer Food Safety Operations Director. S05 (CDC human outbreaks) is attached
as corroboration context only and NEVER triggers an action (non-causality).

Decision support only: retailer-appropriate verbs (prioritize testing, request
supplier verification, protect access, scrutinize sourcing, gather information),
never "recall"/"contaminated"/"unsafe"/a regulatory directive. Every action
carries human_review=True and status OBSERVED. Below-support signals (each
module's own gate) never produce actions. No new data, no model training.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
INTERIM_DIR = REPO_ROOT / "data" / "interim"
CACHE_PATH = INTERIM_DIR / "action_queue.json"

MODULE_ID = "ACTIONQ"
METHOD_VERSION = "aq.v1"

#: Keep each source focused; top-N by its signal strength.
TOP_N_S04 = 12
TOP_N_S03 = 12
TOP_N_S06 = 8
TOP_N_S01 = 6

#: S01 category min support (mirrors the S01 panel n>=30 guard).
S01_MIN_N = 30

#: Forbidden directive/contamination vocabulary (enforced by a test).
FORBIDDEN_TERMS = ("recall", "contaminated", "unsafe", "seize", "shut down",
                   "destroy", "government order", "mandate")

_COMMODITY = {"Salmonella": "raw_poultry", "Listeria": "rte", "STEC": "raw_beef"}


def _load(module: str):
    """Load a source module cache by its loader; None if unavailable."""
    try:
        if module == "S01":
            from src.analysis.program_product import load_cache
        elif module == "S03":
            from src.analysis.establishment_surveillance import load_cache
        elif module == "S04":
            from src.analysis.emerging_risk import load_cache
        elif module == "S06":
            from src.analysis.community_impact import load_cache
        elif module == "S05":
            from src.analysis.human_comparison import load_cache
        else:
            return None
        return load_cache()
    except Exception:  # noqa: BLE001 - a missing source simply yields no actions
        return None


def derive_s04_actions(cache: Optional[dict]) -> list[dict]:
    """Emerging anomaly (latest period, support ok) -> prioritize testing."""
    out: list[dict] = []
    if not cache or not cache.get("pathogens"):
        return out
    for pathogen, pdata in cache["pathogens"].items():
        if pdata.get("availability_status") != "available":
            continue
        for state, sdata in pdata.get("states", {}).items():
            periods = sdata.get("periods", [])
            if not periods:
                continue
            latest = periods[-1]  # periods are ordered by period_start
            if latest.get("support_status") != "ok":
                continue
            if latest.get("retro_anomaly") is not True:
                continue
            val = latest.get("value")
            band = latest.get("baseline_high")
            strength = (val - band) if (val is not None and band is not None) else 0.0
            out.append({
                "pathogen": pathogen,
                "commodity": _COMMODITY.get(pathogen, pdata.get("commodity", "")),
                "action": f"Prioritize testing / heightened monitoring for {pathogen} in {state} next period",
                "action_category": "prioritize_testing",
                "target_type": "state",
                "target": state,
                "source_module": "S04",
                "triggering_signal": f"Emerging signal: {state} {latest.get('period')} positivity {val} exceeded its prior-only expected band {band}",
                "evidence_summary": f"observed {val} vs expected<= {band}; {latest.get('positive_n')}/{latest.get('sample_n')} positive (OBSERVED, leakage-safe)",
                "_strength": max(0.0, float(strength)),
            })
    out.sort(key=lambda a: -a["_strength"])
    return out[:TOP_N_S04]


def derive_s03_actions(cache: Optional[dict]) -> list[dict]:
    """High EB-posterior establishment (support ok) -> request supplier verification."""
    out: list[dict] = []
    if not cache or not cache.get("pathogens"):
        return out
    for pathogen, pdata in cache["pathogens"].items():
        if pdata.get("availability_status") != "available":
            continue
        ests = [e for e in pdata.get("establishments", {}).values()
                if e.get("support_status") == "ok" and e.get("eb_posterior") is not None]
        ests.sort(key=lambda e: -(e.get("eb_posterior") or 0.0))
        for e in ests[:TOP_N_S03]:
            name = e.get("establishment_name") or f"Establishment {e.get('establishment_id')}"
            state = e.get("state", "UNK")
            eb = e.get("eb_posterior")
            out.append({
                "pathogen": pathogen,
                "commodity": _COMMODITY.get(pathogen, pdata.get("commodity", "")),
                "action": f"Request supplier verification / additional testing for {name} ({state})",
                "action_category": "request_supplier_verification",
                "target_type": "establishment",
                "target": f"{name} ({state})",
                "source_module": "S03",
                "triggering_signal": f"Establishment {name} has an elevated shrinkage-estimated {pathogen} positivity",
                "evidence_summary": f"EB posterior {eb} [{e.get('ci_low')}, {e.get('ci_high')}]; {e.get('positive_n')}/{e.get('sample_n')} positive (OBSERVED, peer-pooled)",
                "_strength": float(eb or 0.0),
            })
    return out


def derive_s06_actions(cache: Optional[dict]) -> list[dict]:
    """High priority (hazard x vulnerability) state -> protect access when allocating."""
    out: list[dict] = []
    if not cache or not cache.get("pathogens"):
        return out
    for pathogen, pdata in cache["pathogens"].items():
        if pdata.get("availability_status") != "available":
            continue
        scored = []
        for r in pdata.get("records", []):
            if r.get("availability_status") != "available":
                continue
            lens = next((l for l in r.get("lenses", []) if l.get("lens") == "elderly_65plus" and l.get("available")), None)
            if not lens or lens.get("priority_score") is None:
                continue
            scored.append((lens["priority_score"], r))
        scored.sort(key=lambda t: -t[0])
        for ps, r in scored[:TOP_N_S06]:
            state = r.get("region")
            commodity = _COMMODITY.get(pathogen, pdata.get("commodity", ""))
            out.append({
                "pathogen": pathogen,
                "commodity": commodity,
                "action": f"When allocating {commodity}, protect access in {state} (elevated {pathogen} hazard + high need)",
                "action_category": "protect_access",
                "target_type": "state",
                "target": state,
                "source_module": "S06",
                "triggering_signal": f"{state} ranks high on hazard x community-vulnerability priority for {pathogen}",
                "evidence_summary": f"priority {round(ps,4)} (hazard {r.get('hazard_component')} x 65+ vulnerability); hazard positivity {r.get('hazard_positivity')} (OBSERVED, lens does not change hazard)",
                "_strength": float(ps or 0.0),
            })
    return out


def derive_s01_actions(cache: Optional[dict]) -> list[dict]:
    """High-positivity gated product/program category -> scrutinize sourcing."""
    out: list[dict] = []
    if not cache or not cache.get("pathogens"):
        return out
    for pathogen, pdata in cache["pathogens"].items():
        commodity = pdata.get("commodity", "")
        cats = []
        for dim_name, block in pdata.get("dimensions", {}).items():
            if block.get("availability_status") != "available":
                continue
            for c in block.get("categories", []):
                if c.get("category") == "(unspecified)":
                    continue
                if (c.get("sample_n") or 0) < S01_MIN_N:
                    continue
                if c.get("value") is None:
                    continue
                cats.append((c["value"], dim_name, c))
        cats.sort(key=lambda t: -t[0])
        for val, dim_name, c in cats[:TOP_N_S01]:
            cat = c.get("category")
            out.append({
                "pathogen": pathogen,
                "commodity": commodity,
                "action": f"Scrutinize {cat} sourcing for {pathogen}",
                "action_category": "scrutinize_sourcing",
                "target_type": "product_category",
                "target": f"{cat} ({dim_name})",
                "source_module": "S01",
                "triggering_signal": f"{cat} shows elevated historical {pathogen} positivity",
                "evidence_summary": f"positivity {val} [{c.get('ci_low')}, {c.get('ci_high')}]; {c.get('positive_n')}/{c.get('sample_n')} positive (OBSERVED, pooled across fiscal years)",
                "_strength": float(val or 0.0),
            })
    return out


def attach_corroboration(actions: list[dict], s05_cache: Optional[dict]) -> list[dict]:
    """Attach non-causal NORS corroboration context to state-targeted actions.
    Never creates or removes actions."""
    # (pathogen, state) -> total NORS foodborne outbreaks in the overlap window
    index: dict[tuple[str, str], int] = {}
    if s05_cache and s05_cache.get("pathogens"):
        for pathogen, pdata in s05_cache["pathogens"].items():
            if pdata.get("availability_status") != "available":
                continue
            for cell in pdata.get("cells", []):
                oc = cell.get("nors_outbreak_count")
                if oc:
                    key = (pathogen, cell.get("region"))
                    index[key] = index.get(key, 0) + int(oc)
    for a in actions:
        a["corroboration_note"] = None
        if a.get("target_type") == "state":
            n = index.get((a["pathogen"], a["target"]))
            if n:
                a["corroboration_note"] = (
                    f"CDC NORS recorded {n} foodborne {a['pathogen']} outbreak(s) in "
                    f"{a['target']} over 2013-2023 — corroboration only, lagged ~365 days, "
                    "not a causal link to this surveillance signal."
                )
    return actions


def rank_actions(actions: list[dict]) -> list[dict]:
    """Deterministic rank by signal strength, stable tie-breaks. Assigns 1..N."""
    actions.sort(key=lambda a: (-(a.get("_strength") or 0.0), a["source_module"],
                                a["pathogen"], str(a["target"])))
    for i, a in enumerate(actions, start=1):
        a["rank"] = i
        a.pop("_strength", None)
    return actions


def compute_action_queue(*, round_to: int = 6) -> dict[str, Any]:
    """Build the full action queue from the existing module caches; write cache."""
    s04 = derive_s04_actions(_load("S04"))
    s03 = derive_s03_actions(_load("S03"))
    s06 = derive_s06_actions(_load("S06"))
    s01 = derive_s01_actions(_load("S01"))
    actions = s04 + s03 + s06 + s01
    actions = attach_corroboration(actions, _load("S05"))
    actions = rank_actions(actions)

    for a in actions:
        a["human_review"] = True
        a["status"] = "OBSERVED"
        a["availability_status"] = "available"

    cache = {
        "module_id": MODULE_ID,
        "method_version": METHOD_VERSION,
        "ranking_rule": (
            "Deterministic: primary key = per-source normalized signal strength "
            "(S04 band exceedance, S03 EB posterior, S06 priority score, S01 "
            "positivity); tie-break by source, pathogen, target. Rank 1..N."
        ),
        "source_gates": {
            "S04": "latest-period retro_anomaly True AND support_status ok",
            "S03": "support_status ok, ranked by eb_posterior",
            "S06": "data-backed 65+ lens priority_score",
            "S01": f"category sample_n >= {S01_MIN_N}, excl (unspecified)",
            "S05": "corroboration context only, never a trigger",
        },
        "forbidden_terms": list(FORBIDDEN_TERMS),
        "counts_by_source": {
            "S04": len(s04), "S03": len(s03), "S06": len(s06), "S01": len(s01),
        },
        "actions": actions,
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
    result = compute_action_queue()
    print("counts_by_source", result["counts_by_source"])
    print("total actions", len(result["actions"]))
    for a in result["actions"][:10]:
        corr = " [+NORS corrob]" if a.get("corroboration_note") else ""
        print(f"  #{a['rank']} [{a['source_module']}] {a['pathogen']}: {a['action']}{corr}")