"""S07 — County Community Impact tests.

Lock the honesty/correctness properties of the county-level vulnerability-aware
priority ranking (county vulnerability x state-level hazard). Mirrors
``tests/test_community_impact.py`` and ``tests/test_facility_map.py``: small
hand-built in-memory fixtures (a committed county-vulnerability table dict keyed
on 5-digit county FIPS + a per-(pathogen, state) hazard dict), the module loaders
monkeypatched to those fixtures, and ``compute_county_community_impact`` exercised
end to end. ``CACHE_PATH``/``INTERIM_DIR`` are redirected to pytest ``tmp_path`` so
the real ``data/interim/s07_county_community_impact.json`` is never clobbered and
Task 7's real build stays clean.

Property numbering (P1-P14) follows ``design.md``'s Correctness Properties:
  P1  Lens never changes the hazard.
  P2  Same state + pathogen implies identical hazard.
  P3  Priority score is the documented weighted sum or None.
  P4  No infection claim; OBSERVED; county vulnerability / state hazard.
  P5  Bounded components; affected-context is a distinct count.
  P6  Unavailable lenses (under5/pregnancy) are never fabricated.
  P7  All three pathogens first-class; unavailable counties retained.
  P8  Honest key-absent / committed-table degradation.
  P9  Determinism (byte-identical, stable ordering).
  P10 Component normalization respects the two documented scopes.
  P11 Vintage disclosure tracks availability.
  P12 Weight-sensitivity disclosure.
  P13 Schema <-> TypeScript field-name parity.
  P14 S06 independence.
"""

from __future__ import annotations

import json
import re
import typing
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from src.analysis import county_community_impact as cci


# --------------------------------------------------------------------------- #
# Hand-built in-memory fixtures
# --------------------------------------------------------------------------- #
# County FIPS chosen so the first two digits map to real USPS states via
# harmonize.state_from_fips: 06 -> CA, 48 -> TX, 36 -> NY.
_CA_A = "06037"   # Los Angeles County, CA
_CA_B = "06075"   # San Francisco County, CA
_TX_A = "48201"   # Harris County, TX
_NY_A = "36061"   # New York County, NY


def _vuln_table(*, obtained=True, counties=None, acs_vintage="ACS5 2022",
                atlas_vintage="FARA/LRAM 2019",
                share_definition="tract-count shares aggregated to 5-digit county FIPS"):
    """Committed county-vulnerability table fixture (keyed on 5-digit county FIPS)."""
    if counties is None:
        counties = _default_counties()
    return {
        "acs_vintage": acs_vintage,
        "atlas_vintage": atlas_vintage,
        "share_definition": share_definition,
        "obtained": obtained,
        "counties": counties,
    }


def _default_counties():
    """Three counties across two states (CA x2, TX x1) with distinct shares so the
    COUNTY-scope min-max has a clear low/high, plus a real population for the count."""
    return {
        _CA_A: {"county_fips": _CA_A, "county_name": "Los Angeles County", "state": "CA",
                "total_population": 10014009.0, "elderly_65plus_share": 0.1374,
                "low_income_share": 0.41, "low_access_share": 0.22},
        _CA_B: {"county_fips": _CA_B, "county_name": "San Francisco County", "state": "CA",
                "total_population": 873965.0, "elderly_65plus_share": 0.1700,
                "low_income_share": 0.30, "low_access_share": 0.05},
        _TX_A: {"county_fips": _TX_A, "county_name": "Harris County", "state": "TX",
                "total_population": 4731145.0, "elderly_65plus_share": 0.1000,
                "low_income_share": 0.50, "low_access_share": 0.40},
    }


def _hazard(*, two_states=True):
    """Per-(pathogen, state) positivity fixture {pathogen: {state: positivity}}.

    All three pathogens first-class. CA + TX carry hazard for all pathogens (so
    counties in those states are available); NY deliberately carries no hazard so
    a NY county (if added) is retained unavailable. Distinct CA/TX positivities so
    the STATE-scope min-max has a clear low (-> 0.0) and high (-> 1.0).
    """
    hz = {
        "Salmonella": {"CA": 0.20, "TX": 0.60},
        "Listeria": {"CA": 0.10, "TX": 0.30},
        "STEC": {"CA": 0.05, "TX": 0.15},
    }
    if not two_states:
        for p in hz:
            hz[p] = {"CA": hz[p]["CA"]}
    return hz


def _patch(monkeypatch, tmp_path, *, vuln=None, hazard=None):
    """Redirect the module loaders to fixtures and CACHE_PATH/INTERIM_DIR to tmp."""
    monkeypatch.setattr(cci, "load_county_vulnerability", lambda: vuln)
    monkeypatch.setattr(cci, "state_hazard",
                        lambda: hazard if hazard is not None else _hazard())
    cache_file = tmp_path / "s07_county_community_impact.json"
    monkeypatch.setattr(cci, "CACHE_PATH", cache_file)
    monkeypatch.setattr(cci, "INTERIM_DIR", tmp_path)
    return cache_file


def _all_records(cache):
    rows = []
    for pdata in cache["pathogens"].values():
        rows.extend(pdata.get("records", []))
    return rows


# --------------------------------------------------------------------------- #
# Unit: priority score, normalization, county->state (mirror S06 unit tests)
# --------------------------------------------------------------------------- #
def test_priority_score_weighting_and_null():
    # hazard 0.8, vuln 0.4, default weights (0.6, 0.4) -> 0.64
    assert abs(cci.priority_score(0.8, 0.4, (0.6, 0.4)) - 0.64) < 1e-9
    assert cci.priority_score(0.8, None, (0.6, 0.4)) is None
    assert cci.priority_score(None, 0.4, (0.6, 0.4)) is None


def test_minmax_skips_none_never_imputes():
    out = cci.minmax_component({"A": 0.0, "B": 1.0, "C": 0.5, "D": None})
    assert out["A"] == 0.0 and out["B"] == 1.0 and abs(out["C"] - 0.5) < 1e-9
    assert out["D"] is None
    # A single present value (span == 0) normalizes to 0.0, never NaN.
    assert cci.minmax_component({"X": 0.42})["X"] == 0.0


def test_county_to_state_maps_fips_prefix():
    assert cci.county_to_state(_CA_A) == "CA"
    assert cci.county_to_state(_TX_A) == "TX"
    assert cci.county_to_state(_NY_A) == "NY"


# --------------------------------------------------------------------------- #
# P1 — lens switch never changes the hazard
# --------------------------------------------------------------------------- #
def test_p1_lens_never_changes_hazard(monkeypatch, tmp_path):
    # Property 1
    _patch(monkeypatch, tmp_path, vuln=_vuln_table())
    cache = cci.compute_county_community_impact()
    for r in _all_records(cache):
        h = r["hazard_component"]
        pos = r["hazard_positivity"]
        for L in r["lenses"]:
            if L["available"] and L["priority_score"] is not None:
                # Every available lens derives its priority from the SAME single
                # hazard component; recomputing with that hazard must reproduce it.
                expected = round(0.6 * h + 0.4 * L["vulnerability_component"], 6)
                assert abs(L["priority_score"] - expected) < 2e-6, (
                    f"{r['pathogen']}/{r['county_fips']}/{L['lens']}: priority not "
                    f"derived from the record's single hazard component"
                )
        # Sanity: the record carries exactly one hazard component / positivity.
        assert isinstance(h, float) or h is None
        assert isinstance(pos, float) or pos is None


# --------------------------------------------------------------------------- #
# P2 — same state + pathogen implies identical hazard (the central invariant)
# --------------------------------------------------------------------------- #
def test_p2_same_state_pathogen_identical_hazard(monkeypatch, tmp_path):
    # Property 2 — _CA_A and _CA_B share state CA; for each pathogen their
    # hazard_component AND hazard_positivity must be identical.
    _patch(monkeypatch, tmp_path, vuln=_vuln_table())
    cache = cci.compute_county_community_impact()
    for pathogen, pdata in cache["pathogens"].items():
        by_fips = {r["county_fips"]: r for r in pdata["records"]}
        ca_a, ca_b = by_fips[_CA_A], by_fips[_CA_B]
        assert ca_a["hazard_component"] == ca_b["hazard_component"], pathogen
        assert ca_a["hazard_positivity"] == ca_b["hazard_positivity"], pathogen
        # And the TX county's hazard differs from CA's (distinct state positivity).
        tx = by_fips[_TX_A]
        assert tx["hazard_positivity"] != ca_a["hazard_positivity"], pathogen


# --------------------------------------------------------------------------- #
# P3 — priority score is the documented weighted sum or None
# --------------------------------------------------------------------------- #
def test_p3_priority_is_weighted_sum_or_none(monkeypatch, tmp_path):
    # Property 3
    _patch(monkeypatch, tmp_path, vuln=_vuln_table())
    cache = cci.compute_county_community_impact()
    for r in _all_records(cache):
        h = r["hazard_component"]
        for L in r["lenses"]:
            vc = L["vulnerability_component"]
            ps = L["priority_score"]
            if h is not None and vc is not None:
                assert ps == round(0.6 * h + 0.4 * vc, 6)
            else:
                # Either component None -> never a hazard-only or vuln-only score.
                assert ps is None


@settings(max_examples=100, deadline=None)
@given(
    hazard_c=st.one_of(st.none(), st.floats(min_value=0.0, max_value=1.0)),
    vuln_c=st.one_of(st.none(), st.floats(min_value=0.0, max_value=1.0)),
)
def test_p3_priority_score_rule_property(hazard_c, vuln_c):
    # Property 3 — the weighted-sum / None rule holds across generated component
    # pairs (including Nones) directly on priority_score.
    ps = cci.priority_score(hazard_c, vuln_c, cci.DEFAULT_WEIGHTS)
    if hazard_c is None or vuln_c is None:
        assert ps is None
    else:
        expected = 0.6 * hazard_c + 0.4 * vuln_c
        assert ps == max(0.0, min(1.0, expected))
        assert 0.0 <= ps <= 1.0


# --------------------------------------------------------------------------- #
# P4 — no infection claim; OBSERVED; county vulnerability / state hazard
# --------------------------------------------------------------------------- #
_BANNED = ("county_infection", "tract_infection", "infection",
           "illness_estimate", "predicted_case", "human_case")


def test_p4_no_infection_claim_observed_labels(monkeypatch, tmp_path):
    # Property 4
    _patch(monkeypatch, tmp_path, vuln=_vuln_table())
    cache = cci.compute_county_community_impact()
    hz = _hazard()
    for r in _all_records(cache):
        for k in r.keys():
            assert not any(b in k.lower() for b in _BANNED), f"banned field: {k}"
        assert r["status"] == "OBSERVED"
        assert r["geography_level"] == "county"
        assert r["resolution_label"] == "county vulnerability x state-level hazard"
        # hazard_positivity is exactly the county's STATE positivity, never county-measured.
        if r["hazard_positivity"] is not None:
            assert r["hazard_positivity"] == round(hz[r["pathogen"]][r["state"]], 6)


# --------------------------------------------------------------------------- #
# P5 — bounded components; affected-context is a distinct count
# --------------------------------------------------------------------------- #
def test_p5_bounded_components_and_distinct_count(monkeypatch, tmp_path):
    # Property 5
    _patch(monkeypatch, tmp_path, vuln=_vuln_table())
    cache = cci.compute_county_community_impact()
    for r in _all_records(cache):
        for field in ("hazard_component", "hazard_positivity",
                      "elderly_65plus_share", "low_income_share", "low_access_share"):
            v = r[field]
            if v is not None:
                assert 0.0 <= v <= 1.0, f"{field}={v} out of [0,1]"
        for L in r["lenses"]:
            for field in ("vulnerability_component", "priority_score"):
                v = L[field]
                if v is not None:
                    assert 0.0 <= v <= 1.0
        # affected_population_context == low_access_share * total_population, a count
        # kept distinct from the [0,1] shares (>> 1 for a nonzero share over a real pop).
        las = r["low_access_share"]
        pop = r["total_population"]
        apc = r["affected_population_context"]
        if las is not None and pop is not None:
            assert apc == round(las * pop, 2)
            if las > 0:
                assert apc > 1.0
                assert apc != las  # a count, not a share
        else:
            assert apc is None


# --------------------------------------------------------------------------- #
# P6 — unavailable lenses (under5/pregnancy) never fabricated
# --------------------------------------------------------------------------- #
def test_p6_unavailable_lenses_never_fabricated(monkeypatch, tmp_path):
    # Property 6
    _patch(monkeypatch, tmp_path, vuln=_vuln_table())
    cache = cci.compute_county_community_impact()
    for r in _all_records(cache):
        assert r["under5_share"] is None
        lens_by = {L["lens"]: L for L in r["lenses"]}
        for bad in ("under5", "pregnancy"):
            assert bad in lens_by, f"{bad} lens missing from record"
            L = lens_by[bad]
            assert L["available"] is False
            assert L["vulnerability_component"] is None
            assert L["priority_score"] is None
            assert L["unavailable_reason"]


# --------------------------------------------------------------------------- #
# P7 — all three pathogens first-class; unavailable counties retained
# --------------------------------------------------------------------------- #
def test_p7_three_pathogens_and_unavailable_counties_retained(monkeypatch, tmp_path):
    # Property 7 — build one fully-covered county (CA), one county whose state has
    # NO hazard for any pathogen (NY -> _hazard has no NY), and one county with no
    # vulnerability profile (all share fields None). All must be retained.
    counties = _default_counties()
    counties[_NY_A] = {"county_fips": _NY_A, "county_name": "New York County",
                       "state": "NY", "total_population": 1600000.0,
                       "elderly_65plus_share": 0.16, "low_income_share": 0.25,
                       "low_access_share": 0.08}
    # A county WITH a FIPS/state but NO vulnerability profile (all None).
    counties["48113"] = {"county_fips": "48113", "county_name": "Dallas County",
                         "state": "TX", "total_population": None,
                         "elderly_65plus_share": None, "low_income_share": None,
                         "low_access_share": None}
    _patch(monkeypatch, tmp_path, vuln=_vuln_table(counties=counties))
    cache = cci.compute_county_community_impact()

    assert set(cache["pathogens"].keys()) == {"Salmonella", "Listeria", "STEC"}

    for pathogen, pdata in cache["pathogens"].items():
        by_fips = {r["county_fips"]: r for r in pdata["records"]}
        # Every county is retained in every pathogen group (never dropped).
        assert set(by_fips) == set(counties)
        for r in pdata["records"]:
            assert r["availability_status"] in ("available", "unavailable")

        # NY county: state has no hazard for the pathogen -> unavailable, retained.
        ny = by_fips[_NY_A]
        assert ny["availability_status"] == "unavailable"
        assert ny["unavailable_reason"] == "State has no hazard for this pathogen."

        # No-profile county -> unavailable with the no-profile reason, retained.
        noprof = by_fips["48113"]
        assert noprof["availability_status"] == "unavailable"
        assert noprof["unavailable_reason"] == "No county vulnerability profile."

        # CA county with hazard + profile -> available.
        assert by_fips[_CA_A]["availability_status"] == "available"


# --------------------------------------------------------------------------- #
# P8 — honest key-absent / committed-table degradation
# --------------------------------------------------------------------------- #
def test_p8_no_table_degrades_honestly(monkeypatch, tmp_path):
    # Property 8 — load_county_vulnerability -> None: all three pathogens present,
    # each unavailable with records == [] and a skipped-no-key gap; no raise.
    cache_file = _patch(monkeypatch, tmp_path, vuln=None)
    cache = cci.compute_county_community_impact()

    assert set(cache["pathogens"].keys()) == {"Salmonella", "Listeria", "STEC"}
    for pdata in cache["pathogens"].values():
        assert pdata["availability_status"] == "unavailable"
        assert pdata["records"] == []
    assert any(g.get("reason") == "skipped-no-key" for g in cache["gaps"])
    # No numeric county vulnerability written anywhere in the degraded cache.
    assert _all_records(cache) == []
    assert cache_file.exists()


def test_p8_obtained_false_and_empty_counties_degrade(monkeypatch, tmp_path):
    # Property 8 — obtained=False OR empty counties also degrade honestly.
    for vuln in (_vuln_table(obtained=False),
                 _vuln_table(counties={})):
        _patch(monkeypatch, tmp_path, vuln=vuln)
        cache = cci.compute_county_community_impact()
        assert set(cache["pathogens"].keys()) == {"Salmonella", "Listeria", "STEC"}
        for pdata in cache["pathogens"].values():
            assert pdata["availability_status"] == "unavailable"
            assert pdata["records"] == []
        assert any(g.get("reason") == "skipped-no-key" for g in cache["gaps"])


def test_p8_table_present_yields_real_values(monkeypatch, tmp_path):
    # Property 8 — a valid committed table -> covered counties available with values.
    _patch(monkeypatch, tmp_path, vuln=_vuln_table())
    cache = cci.compute_county_community_impact()
    ca = next(r for r in cache["pathogens"]["Salmonella"]["records"]
              if r["county_fips"] == _CA_A)
    assert ca["availability_status"] == "available"
    assert ca["elderly_65plus_share"] == 0.1374
    assert ca["total_population"] == 10014009.0


@settings(max_examples=100, deadline=None)
@given(n_ca=st.integers(min_value=0, max_value=5),
       n_tx=st.integers(min_value=0, max_value=5))
def test_p8_counting_determinism_property(n_ca, n_tx):
    # Property 8 / 9 — across randomized small fixtures, every run keeps all three
    # pathogens first-class, retains exactly the committed county count per pathogen,
    # and a repeat run over identical fixtures is byte-identical. Fresh monkeypatch
    # + tmp dir per Hypothesis example (mirrors test_facility_map's property style).
    from _pytest.monkeypatch import MonkeyPatch
    import tempfile

    counties = {}
    for i in range(n_ca):
        fips = "06" + f"{i:03d}"
        counties[fips] = {"county_fips": fips, "county_name": f"CA {i}", "state": "CA",
                          "total_population": 100000.0 + i, "elderly_65plus_share": 0.10 + i * 0.01,
                          "low_income_share": 0.20, "low_access_share": 0.15}
    for i in range(n_tx):
        fips = "48" + f"{i:03d}"
        counties[fips] = {"county_fips": fips, "county_name": f"TX {i}", "state": "TX",
                          "total_population": 200000.0 + i, "elderly_65plus_share": 0.12 + i * 0.01,
                          "low_income_share": 0.30, "low_access_share": 0.25}
    n_total = len(counties)

    vuln = {"acs_vintage": "ACS5 2022", "atlas_vintage": "FARA/LRAM 2019",
            "share_definition": "x", "obtained": True, "counties": counties}

    mp = MonkeyPatch()
    tmp = Path(tempfile.mkdtemp())
    try:
        mp.setattr(cci, "load_county_vulnerability", lambda: vuln)
        mp.setattr(cci, "state_hazard", lambda: _hazard())
        mp.setattr(cci, "CACHE_PATH", tmp / "s07_county_community_impact.json")
        mp.setattr(cci, "INTERIM_DIR", tmp)
        cache = cci.compute_county_community_impact()
        first_bytes = (tmp / "s07_county_community_impact.json").read_bytes()
        cci.compute_county_community_impact()
        second_bytes = (tmp / "s07_county_community_impact.json").read_bytes()
    finally:
        mp.undo()

    assert set(cache["pathogens"].keys()) == {"Salmonella", "Listeria", "STEC"}
    assert first_bytes == second_bytes
    if n_total == 0:
        for pdata in cache["pathogens"].values():
            assert pdata["records"] == []
    else:
        for pdata in cache["pathogens"].values():
            assert len(pdata["records"]) == n_total


# --------------------------------------------------------------------------- #
# P9 — determinism (byte-identical, stable ordering)
# --------------------------------------------------------------------------- #
def test_p9_deterministic_and_sorted(monkeypatch, tmp_path):
    # Property 9
    cache_file = _patch(monkeypatch, tmp_path, vuln=_vuln_table())
    first = cci.compute_county_community_impact()
    first_bytes = cache_file.read_bytes()
    second = cci.compute_county_community_impact()
    second_bytes = cache_file.read_bytes()
    assert first == second
    assert first_bytes == second_bytes
    # Records sorted by county_fips within a pathogen.
    for pdata in first["pathogens"].values():
        fipses = [r["county_fips"] for r in pdata["records"]]
        assert fipses == sorted(fipses)


# --------------------------------------------------------------------------- #
# P10 — component normalization respects the two documented scopes
# --------------------------------------------------------------------------- #
def test_p10_normalization_scopes(monkeypatch, tmp_path):
    # Property 10 — HAZARD min-max over the STATE set, VULNERABILITY over the COUNTY set.
    hz = _hazard()  # CA/TX per pathogen; CA is the min state, TX the max.
    _patch(monkeypatch, tmp_path, vuln=_vuln_table(), hazard=hz)
    cache = cci.compute_county_community_impact()

    for pathogen, pdata in cache["pathogens"].items():
        by_fips = {r["county_fips"]: r for r in pdata["records"]}
        # STATE-scope min-max: the lower-positivity state (CA) -> 0.0, higher (TX) -> 1.0.
        assert by_fips[_CA_A]["hazard_component"] == 0.0, pathogen
        assert by_fips[_TX_A]["hazard_component"] == 1.0, pathogen

    # VULNERABILITY (elderly) min-max over the COUNTY set: TX=0.10 (min)->0.0,
    # SF=0.17 (max)->1.0, LA=0.1374 -> (0.1374-0.10)/(0.17-0.10).
    salm = {r["county_fips"]: r for r in cache["pathogens"]["Salmonella"]["records"]}

    def _elderly_comp(rec):
        return next(L["vulnerability_component"] for L in rec["lenses"]
                    if L["lens"] == "elderly_65plus")

    assert _elderly_comp(salm[_TX_A]) == 0.0
    assert _elderly_comp(salm[_CA_B]) == 1.0
    expected_la = round((0.1374 - 0.10) / (0.17 - 0.10), 6)
    assert _elderly_comp(salm[_CA_A]) == expected_la


def test_p10_single_state_scope_gives_zero(monkeypatch, tmp_path):
    # Property 10 — a single-state hazard fixture: the lone state's min-max is 0.0
    # for every county (span == 0 -> 0.0), confirming the STATE scope.
    counties = {_CA_A: _default_counties()[_CA_A], _CA_B: _default_counties()[_CA_B]}
    _patch(monkeypatch, tmp_path, vuln=_vuln_table(counties=counties),
           hazard=_hazard(two_states=False))
    cache = cci.compute_county_community_impact()
    for pdata in cache["pathogens"].values():
        for r in pdata["records"]:
            assert r["hazard_component"] == 0.0


# --------------------------------------------------------------------------- #
# P11 — vintage disclosure tracks availability
# --------------------------------------------------------------------------- #
def test_p11_vintage_disclosure(monkeypatch, tmp_path):
    # Property 11 — acs_vintage present iff an elderly (ACS) value present; atlas_vintage
    # present iff a low_income/low_access (Atlas) value present; None otherwise.
    counties = _default_counties()
    # A county with ONLY an ACS value (no Atlas values) -> acs_vintage set, atlas None.
    counties["48029"] = {"county_fips": "48029", "county_name": "Bexar County", "state": "TX",
                         "total_population": 2000000.0, "elderly_65plus_share": 0.14,
                         "low_income_share": None, "low_access_share": None}
    # A county with ONLY Atlas values (no ACS) -> atlas_vintage set, acs None.
    counties["06001"] = {"county_fips": "06001", "county_name": "Alameda County", "state": "CA",
                         "total_population": 1600000.0, "elderly_65plus_share": None,
                         "low_income_share": 0.33, "low_access_share": 0.12}
    _patch(monkeypatch, tmp_path, vuln=_vuln_table(counties=counties))
    cache = cci.compute_county_community_impact()
    for r in _all_records(cache):
        if r["elderly_65plus_share"] is not None:
            assert r["acs_vintage"] == "ACS5 2022"
        else:
            assert r["acs_vintage"] is None
        if r["low_income_share"] is not None or r["low_access_share"] is not None:
            assert r["atlas_vintage"] == "FARA/LRAM 2019"
        else:
            assert r["atlas_vintage"] is None


# --------------------------------------------------------------------------- #
# P12 — weight-sensitivity disclosure
# --------------------------------------------------------------------------- #
def test_p12_weight_sensitivity_disclosure(monkeypatch, tmp_path):
    # Property 12
    _patch(monkeypatch, tmp_path, vuln=_vuln_table())
    cache = cci.compute_county_community_impact()
    for pathogen, pdata in cache["pathogens"].items():
        sens = pdata["weight_sensitivity"]
        assert isinstance(sens["default_top"], list)
        assert isinstance(sens["alt_top"], list)
        assert isinstance(sens["rank_stable"], bool)
        assert sens["note"] and "weight-dependent" in sens["note"]
        # Top lists hold county FIPS strings from the committed table.
        for fips in sens["default_top"] + sens["alt_top"]:
            assert fips in _default_counties()


# --------------------------------------------------------------------------- #
# P13 — schema <-> TypeScript field-name parity (+ exporter smoke)
# --------------------------------------------------------------------------- #
from src.artifacts import exporter as _exporter
from src.artifacts.schemas import CountyCommunityImpactRecord

_ARTIFACTS_TS = Path(__file__).resolve().parents[1] / "web" / "src" / "types" / "artifacts.ts"


def _ts_interface_fields(ts_text: str, interface_name: str) -> set[str]:
    """Parse the field names of a TypeScript interface body (mirror of the
    ``test_facility_map.py`` helper). Deliberately simple: the parity contract is
    key-set equality, so only the identifiers are needed."""
    m = re.search(
        r"export\s+interface\s+" + re.escape(interface_name) + r"\s*\{(.*?)\}",
        ts_text, re.DOTALL)
    assert m, f"interface {interface_name} not found in artifacts.ts"
    body = m.group(1)
    fields: set[str] = set()
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        stripped = stripped.split("//", 1)[0].strip()
        fm_match = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s*[?]?\s*:", stripped)
        if fm_match:
            fields.add(fm_match.group(1))
    return fields


def test_p13_county_community_impact_python_ts_parity():
    # Property 13
    ts_text = _ARTIFACTS_TS.read_text(encoding="utf-8")
    py_keys = set(typing.get_type_hints(CountyCommunityImpactRecord).keys())
    ts_keys = _ts_interface_fields(ts_text, "CountyCommunityImpactRecord")
    assert py_keys == ts_keys, (
        f"CountyCommunityImpactRecord parity mismatch: "
        f"py-only={py_keys - ts_keys}, ts-only={ts_keys - py_keys}")
    assert len(py_keys) == 28


def _fixture_cache(tmp_path, monkeypatch):
    """Build a tiny real S07 cache (hermetic) and point the exporter's load_cache
    (imported from the compute module) at it."""
    _patch(monkeypatch, tmp_path, vuln=_vuln_table())
    cache = cci.compute_county_community_impact()
    monkeypatch.setattr(cci, "load_cache", lambda: cache)
    return cache


def test_exporter_rows_validate_and_carry_weight_sensitivity(monkeypatch, tmp_path):
    # Exporter smoke (hermetic): build_county_community_impact() over a monkeypatched
    # fixture cache returns rows that validate against the schema and carry
    # weight_sensitivity on available rows.
    _fixture_cache(tmp_path, monkeypatch)
    rows = _exporter.build_county_community_impact()
    assert rows
    _exporter.validate_payload(rows, CountyCommunityImpactRecord,
                               label="county_community_impact")
    available = [r for r in rows if r["availability_status"] == "available"]
    assert available, "expected at least one available county row"
    for r in available:
        assert r["weight_sensitivity"] is not None
        assert r["module_id"] == "S07"
        assert r["status"] == "OBSERVED"
    # Forbidden-field guard holds (no banned token in any row key).
    for r in rows:
        for k in r.keys():
            assert not any(b in k.lower() for b in _BANNED), f"banned field: {k}"


def test_exporter_missing_cache_degrades_to_unavailable(monkeypatch, tmp_path):
    # Exporter smoke — a missing cache yields one explicit per-pathogen unavailable
    # record so the artifact still validates and writes.
    monkeypatch.setattr(cci, "load_cache", lambda: None)
    rows = _exporter.build_county_community_impact()
    _exporter.validate_payload(rows, CountyCommunityImpactRecord,
                               label="county_community_impact")
    pathogens = {r["pathogen"] for r in rows}
    assert {"Salmonella", "Listeria", "STEC"} <= pathogens
    for r in rows:
        assert r["availability_status"] == "unavailable"


# --------------------------------------------------------------------------- #
# P14 — S06 independence
# --------------------------------------------------------------------------- #
def test_p14_module_id_and_cache_path_are_s07():
    # Property 14 — distinct module id and an s07_* cache filename.
    assert cci.MODULE_ID == "S07"
    assert cci.CACHE_PATH.name.startswith("s07_")
    assert "s06" not in cci.CACHE_PATH.name


def test_p14_compute_does_not_touch_s06_cache_or_mutate_hazard(monkeypatch, tmp_path):
    # Property 14 — compute writes only its own s07_* cache (never s06_*), and the
    # shared hazard object is not mutated across the run.
    from src.analysis import community_impact as s06

    hz = _hazard()
    import copy
    hz_snapshot = copy.deepcopy(hz)
    cache_file = _patch(monkeypatch, tmp_path, vuln=_vuln_table(), hazard=hz)
    cci.compute_county_community_impact()

    # S07 wrote only its own s07_* cache into tmp; no s06 file created there.
    written = [p.name for p in tmp_path.iterdir()]
    assert cache_file.name in written
    assert not any("s06" in n for n in written)
    # The S06 module's cache path is distinct and untouched by S07's constant.
    assert s06.CACHE_PATH != cci.CACHE_PATH
    assert s06.CACHE_PATH.name != cci.CACHE_PATH.name
    # The read-only hazard object S07 consumed was not mutated.
    assert hz == hz_snapshot
