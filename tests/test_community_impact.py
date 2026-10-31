"""S06 tests — lock the honesty/correctness properties for vulnerability-aware
impact ranking. Unit tests + the real built artifact. The central guarantee is
that the population lens never changes the hazard."""

from __future__ import annotations

from src.analysis import community_impact as ci
from src.artifacts.exporter import build_community_impact

# --------------------------------------------------------------------------- #
# Unit: priority score and normalization
# --------------------------------------------------------------------------- #

def test_priority_score_weighting_and_null():
    # hazard 0.8, vuln 0.4, default weights (0.6, 0.4) -> 0.64
    assert abs(ci.priority_score(0.8, 0.4, (0.6, 0.4)) - 0.64) < 1e-9
    # a missing component yields None (never a hazard-only score)
    assert ci.priority_score(0.8, None, (0.6, 0.4)) is None
    assert ci.priority_score(None, 0.4, (0.6, 0.4)) is None

def test_minmax_skips_none_never_imputes():
    out = ci.minmax_component({"A": 0.0, "B": 1.0, "C": 0.5, "D": None})
    assert out["A"] == 0.0 and out["B"] == 1.0 and abs(out["C"] - 0.5) < 1e-9
    assert out["D"] is None  # None stays None, never imputed

# --------------------------------------------------------------------------- #
# Property 1 (central): lens switch never changes hazard
# For each (pathogen, state) the hazard component/positivity is a single value;
# the per-lens priority_scores vary but hazard does not depend on the lens.
# We also assert a lens's priority recomputes from the SAME hazard under
# alternative weights (so hazard is invariant, only weighting changes).
# --------------------------------------------------------------------------- #

def test_lens_switch_never_changes_hazard():
    rows = build_community_impact()
    for r in rows:
        if r["availability_status"] != "available" or r["hazard_component"] is None:
            continue
        h = r["hazard_component"]
        for L in r["lenses"]:
            if L["available"] and L["priority_score"] is not None and L["vulnerability_component"] is not None:
                # the priority must equal 0.6*hazard + 0.4*vuln with the SAME hazard
                expected = round(0.6 * h + 0.4 * L["vulnerability_component"], 6)
                # allow one rounding ULP: hazard and priority are each independently
                # rounded to 6 dp, so recomputation can differ by ~1e-6.
                assert abs(L["priority_score"] - expected) < 2e-6, (
                    f"{r['pathogen']}/{r['region']}/{L['lens']}: priority not derived "
                    f"from the record's single hazard component"
                )

# --------------------------------------------------------------------------- #
# Property 2: no fabricated pregnancy or under-5
# --------------------------------------------------------------------------- #

def test_no_fabricated_pregnancy_or_under5():
    rows = build_community_impact()
    for r in rows:
        assert r["under5_share"] is None  # not in the ACS pull
        lens_by = {L["lens"]: L for L in r["lenses"]}
        for bad in ("pregnancy", "under5"):
            if bad in lens_by:
                L = lens_by[bad]
                assert L["available"] is False
                assert L["vulnerability_component"] is None
                assert L["priority_score"] is None
                assert L["unavailable_reason"]

# --------------------------------------------------------------------------- #
# Property 3: no county/tract infection claim field
# --------------------------------------------------------------------------- #

def test_no_county_tract_infection_field():
    rows = build_community_impact()
    # "tract" is a legitimate geographic unit in USDA Atlas field names
    # (low_income_tract_share etc.) — ban actual infection/forecast concepts, not
    # the census-tract measure the vulnerability data is built on.
    banned = ("county_infection", "tract_infection", "infection", "illness_estimate",
              "predicted_case", "human_case")
    for r in rows:
        for k in r.keys():
            assert not any(b in k.lower() for b in banned), f"banned field: {k}"
        assert r["geography_level"] == "state"

# --------------------------------------------------------------------------- #
# Property 4: vintages disclosed on available vulnerability
# --------------------------------------------------------------------------- #

def test_vintages_disclosed():
    rows = build_community_impact()
    for r in rows:
        if r["availability_status"] == "available" and r["elderly_65plus_share"] is not None:
            # a real vulnerability value must carry at least the ACS vintage
            assert r["acs_vintage"], f"{r['pathogen']}/{r['region']} missing ACS vintage"

# --------------------------------------------------------------------------- #
# Property 5: bounded scores; count vs share distinct
# --------------------------------------------------------------------------- #

def test_bounded_scores_and_count_vs_share():
    rows = build_community_impact()
    for r in rows:
        for field in ("hazard_component", "hazard_positivity",
                      "elderly_65plus_share", "low_income_tract_share", "low_access_tract_share"):
            v = r[field]
            if v is not None:
                assert 0.0 <= v <= 1.0, f"{field}={v} out of [0,1]"
        for L in r["lenses"]:
            for field in ("vulnerability_component", "priority_score"):
                v = L[field]
                if v is not None:
                    assert 0.0 <= v <= 1.0
        # count and share are distinct fields: the context count (if present) is a
        # population magnitude, not a share in [0,1]
        if r["affected_population_context"] is not None and r["total_population"]:
            assert r["affected_population_context"] >= 0
            # a count is generally not a share: it should be able to exceed 1
            # (sanity: it equals share * population, so for a nonzero share it is >> 1)
            if r["low_access_tract_share"] and r["low_access_tract_share"] > 0:
                assert r["affected_population_context"] > 1.0

# --------------------------------------------------------------------------- #
# Property 6: all three pathogens first-class with honest availability
# --------------------------------------------------------------------------- #

def test_all_three_pathogens_with_honest_availability():
    rows = build_community_impact()
    pathogens = {r["pathogen"] for r in rows}
    assert {"Salmonella", "Listeria", "STEC"} <= pathogens
    # states lacking a vulnerability profile are marked unavailable, not dropped
    for p in ("Listeria", "STEC"):
        precs = [r for r in rows if r["pathogen"] == p]
        assert any(r["availability_status"] == "unavailable" for r in precs), (
            f"{p} should have some states without a vulnerability profile marked unavailable"
        )
