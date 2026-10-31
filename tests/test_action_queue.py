"""Surveillance Actions tests — lock the honesty/correctness properties for the
decision layer. Uses small hand-built source caches (no raw-data dependency) plus
the real built artifact."""

from __future__ import annotations

from src.decision import action_queue as aq
from src.artifacts.exporter import build_action_queue


# --------------------------------------------------------------------------- #
# Synthetic source caches
# --------------------------------------------------------------------------- #
def _s04_cache():
    return {"pathogens": {"Salmonella": {"availability_status": "available",
        "commodity": "raw_poultry", "states": {
            "GA": {"periods": [
                {"period": "2025-Q1", "retro_anomaly": False, "support_status": "ok",
                 "value": 0.1, "baseline_high": 0.2, "positive_n": 10, "sample_n": 100},
                {"period": "2025-Q2", "retro_anomaly": True, "support_status": "ok",
                 "value": 0.4, "baseline_high": 0.2, "positive_n": 40, "sample_n": 100},
            ]},
            # low-support anomaly must NOT produce an action
            "WY": {"periods": [
                {"period": "2025-Q2", "retro_anomaly": True, "support_status": "low_support",
                 "value": 0.9, "baseline_high": 0.1, "positive_n": 2, "sample_n": 3},
            ]},
        }}}}


def _s03_cache():
    return {"pathogens": {"Listeria": {"availability_status": "available",
        "commodity": "rte", "establishments": {
            "1": {"establishment_id": "1", "establishment_name": "Good Plant",
                  "state": "CA", "eb_posterior": 0.3, "ci_low": 0.2, "ci_high": 0.4,
                  "support_status": "ok", "positive_n": 6, "sample_n": 20},
            "2": {"establishment_id": "2", "establishment_name": "Thin Plant",
                  "state": "TX", "eb_posterior": 0.9, "ci_low": 0.1, "ci_high": 0.99,
                  "support_status": "low_support", "positive_n": 2, "sample_n": 3},
        }}}}


def _s06_cache():
    return {"pathogens": {"STEC": {"availability_status": "available",
        "commodity": "raw_beef", "records": [
            {"region": "DE", "availability_status": "available", "hazard_component": 0.8,
             "hazard_positivity": 0.01, "lenses": [
                 {"lens": "elderly_65plus", "available": True, "priority_score": 0.7}]},
            {"region": "NM", "availability_status": "available", "hazard_component": 0.1,
             "hazard_positivity": 0.001, "lenses": [
                 {"lens": "elderly_65plus", "available": True, "priority_score": 0.2}]},
        ]}}}


def _s01_cache():
    return {"pathogens": {"Salmonella": {"commodity": "raw_poultry", "dimensions": {
        "product": {"availability_status": "available", "categories": [
            {"category": "BREAST", "sample_n": 500, "positive_n": 150, "value": 0.3,
             "ci_low": 0.26, "ci_high": 0.34},
            {"category": "TINY", "sample_n": 5, "positive_n": 4, "value": 0.8,
             "ci_low": 0.3, "ci_high": 0.99},  # below S01_MIN_N -> no action
            {"category": "(unspecified)", "sample_n": 900, "positive_n": 100, "value": 0.11,
             "ci_low": 0.09, "ci_high": 0.13},  # excluded
        ]}}}}}


def _s05_cache():
    return {"pathogens": {"Salmonella": {"availability_status": "available", "cells": [
        {"region": "GA", "period": "2015", "nors_outbreak_count": 4, "coverage_status": "ok"},
    ]}}}


# --------------------------------------------------------------------------- #
# Unit-level derivation (synthetic)
# --------------------------------------------------------------------------- #
def test_s04_only_flags_supported_latest_anomaly():
    acts = aq.derive_s04_actions(_s04_cache())
    targets = {a["target"] for a in acts}
    assert "GA" in targets           # supported latest-period anomaly -> action
    assert "WY" not in targets       # low-support anomaly -> NO action
    assert all(a["action_category"] == "prioritize_testing" for a in acts)


def test_s03_only_ranks_supported_establishments():
    acts = aq.derive_s03_actions(_s03_cache())
    names = {a["target"] for a in acts}
    assert any("Good Plant" in n for n in names)   # support ok -> action
    assert not any("Thin Plant" in n for n in names)  # low_support -> no action


def test_s01_respects_min_n_and_excludes_unspecified():
    acts = aq.derive_s01_actions(_s01_cache())
    cats = " ".join(a["target"] for a in acts)
    assert "BREAST" in cats
    assert "TINY" not in cats            # below min-n
    assert "unspecified" not in cats.lower()


def test_corroboration_is_context_only_never_creates_actions():
    acts = aq.derive_s04_actions(_s04_cache())
    before = len(acts)
    acts2 = aq.attach_corroboration(list(acts), _s05_cache())
    assert len(acts2) == before          # count unchanged — S05 never adds actions
    ga = next(a for a in acts2 if a["target"] == "GA")
    assert ga["corroboration_note"] and "not a causal link" in ga["corroboration_note"]


def test_ranking_is_deterministic():
    c04, c03, c06, c01 = _s04_cache(), _s03_cache(), _s06_cache(), _s01_cache()
    def build():
        a = (aq.derive_s04_actions(c04) + aq.derive_s03_actions(c03)
             + aq.derive_s06_actions(c06) + aq.derive_s01_actions(c01))
        return [x["rank"] for x in aq.rank_actions(a)], [x["target"] for x in aq.rank_actions(
            aq.derive_s04_actions(c04) + aq.derive_s03_actions(c03)
            + aq.derive_s06_actions(c06) + aq.derive_s01_actions(c01))]
    r1 = aq.rank_actions(aq.derive_s04_actions(c04) + aq.derive_s03_actions(c03)
                         + aq.derive_s06_actions(c06) + aq.derive_s01_actions(c01))
    r2 = aq.rank_actions(aq.derive_s04_actions(c04) + aq.derive_s03_actions(c03)
                         + aq.derive_s06_actions(c06) + aq.derive_s01_actions(c01))
    assert [a["target"] for a in r1] == [a["target"] for a in r2]
    assert [a["rank"] for a in r1] == list(range(1, len(r1) + 1))


# --------------------------------------------------------------------------- #
# Artifact-level honesty properties (real built artifact)
# --------------------------------------------------------------------------- #
def test_no_action_sourced_from_s05():
    rows = build_action_queue()
    assert all(r["source_module"] in ("S01", "S03", "S04", "S06") for r in rows)


def test_every_action_human_review_and_observed():
    rows = build_action_queue()
    for r in rows:
        assert r["human_review"] is True
        assert r["status"] == "OBSERVED"


def test_no_forbidden_terms():
    rows = build_action_queue()
    forbidden = ("recall", "contaminated", "unsafe", "seize", "destroy",
                 "government order", "mandate")
    for r in rows:
        text = (r["action"] + " " + r["triggering_signal"]).lower()
        assert not any(t in text for t in forbidden), f"forbidden term in: {r['action']}"


def test_every_action_has_evidence():
    rows = build_action_queue()
    for r in rows:
        assert r["evidence_summary"].strip()
        assert r["triggering_signal"].strip()


def test_all_three_pathogens_present_when_signals_exist():
    rows = build_action_queue()
    pathogens = {r["pathogen"] for r in rows}
    # the real caches have gated signals for all three
    assert {"Salmonella", "Listeria", "STEC"} <= pathogens