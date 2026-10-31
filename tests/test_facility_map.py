"""Facility Map tests — lock the honesty/correctness properties of the decision
layer that geographically plots signal-bearing FSIS-sampled establishments.

Mirrors ``test_action_queue.py``: small hand-built in-memory source caches (no
raw-data dependency), the module loaders monkeypatched to those fixtures, and
``compute_facility_map`` exercised end to end. ``CACHE_PATH``/``INTERIM_DIR`` are
redirected to pytest ``tmp_path`` so the real ``data/interim`` cache is never
clobbered and no network geocode is ever attempted (the path reads committed
caches only).

Property numbering (P1-P9) follows the Task-5 checkpoint spec:
  P1 only signal-bearing establishments appear (elevated S03 top-12 OR an
     action_queue establishment target); neither-source is excluded.
  P2 a low_support high-eb_posterior establishment is never elevated-selected
     and is never labeled safe.
  P3 per pathogen: placed + unplaced == total_selected AND
     historical_candidate + unresolved == unplaced.
  P4 every placed (mpi_verified) row has real lat/lon/address from the geocode
     cache; verified_against_fsis_id is True; location_status == "mpi_verified".
  P5 every unplaced row carries a non-empty unplaced_reason.
  P6 coverage_pct is the VERIFIED placed-only percentage, never inflated by the
     supplemental historical-candidate overlay.
  P7 every row is human_review True and status == "OBSERVED".
  P8 overlay honesty: a supplemental-overlay row is never verified_against_fsis_id
     and its historical_inspection_number is never equated to establishment_id; a
     do_not_map/unresolved supplemental entry stays unresolved/unplaced.
  P9 deterministic + sorted output over identical fixtures.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.decision import action_queue as aq
from src.decision import facility_map as fm


# --------------------------------------------------------------------------- #
# Hand-built in-memory source caches
# --------------------------------------------------------------------------- #
def _s03_cache():
    """S03 establishment-surveillance cache fixture.

    Listeria: one elevated (support ok) + one low_support high-eb_posterior
    establishment that must never be elevated-selected (P2).
    Salmonella: two elevated establishments (both support ok).
    STEC: available but with zero elevated establishments (stays first-class).
    """
    return {"pathogens": {
        "Listeria": {"availability_status": "available", "commodity": "rte",
            "establishments": {
                "1": {"establishment_id": "1", "establishment_name": "Good RTE Plant",
                      "state": "CA", "eb_posterior": 0.30, "ci_low": 0.20, "ci_high": 0.40,
                      "support_status": "ok", "positive_n": 6, "sample_n": 20},
                "2": {"establishment_id": "2", "establishment_name": "Thin Plant",
                      "state": "TX", "eb_posterior": 0.95, "ci_low": 0.10, "ci_high": 0.99,
                      "support_status": "low_support", "positive_n": 2, "sample_n": 3},
            }},
        "Salmonella": {"availability_status": "available", "commodity": "raw_poultry",
            "establishments": {
                "10": {"establishment_id": "10", "establishment_name": "Poultry A",
                       "state": "GA", "eb_posterior": 0.50, "ci_low": 0.40, "ci_high": 0.60,
                       "support_status": "ok", "positive_n": 20, "sample_n": 100},
                "20": {"establishment_id": "20", "establishment_name": "Poultry B",
                       "state": "AL", "eb_posterior": 0.45, "ci_low": 0.30, "ci_high": 0.55,
                       "support_status": "ok", "positive_n": 15, "sample_n": 90},
            }},
        "STEC": {"availability_status": "available", "commodity": "raw_beef",
            "establishments": {}},
    }}


def _aq_cache():
    """action_queue cache fixture with a single establishment-target action that
    matches the Salmonella "Poultry B (AL)" S03 record by its display label, so
    that establishment is source_selection=="both"."""
    return {"actions": [
        {"target_type": "establishment", "pathogen": "Salmonella",
         "target": "Poultry B (AL)", "source_module": "S03",
         "evidence_summary": "elevated establishment signal", "human_review": True,
         "status": "OBSERVED"},
        # A region-target action must be ignored by the facility map selection.
        {"target_type": "region", "pathogen": "Salmonella", "target": "GA",
         "source_module": "S04", "evidence_summary": "region anomaly"},
    ]}


def _geocode_cache(obtained=True, entries=None, conflicts=None):
    """Geocode_Cache fixture. Keys are NORMALIZED establishment numbers."""
    return {
        "source": "FSIS MPI Directory",
        "normalization": "trim; strip leading zeros; uppercase",
        "obtained": obtained,
        "conflicts": list(conflicts or []),
        "entries": dict(entries or {}),
    }


def _supplemental(entries=None):
    """Supplemental historical-candidate overlay fixture (keyed on S03 numeric
    establishment_id string)."""
    return {"entries": dict(entries or {})}


def _patch(monkeypatch, tmp_path, *, s03=None, aq_c=None, geocode=None, supp=None):
    """Redirect the four module loaders to fixtures and CACHE_PATH/INTERIM_DIR to
    a tmp file so the real interim cache is never touched."""
    monkeypatch.setattr(fm, "load_s03_cache", lambda: s03)
    monkeypatch.setattr(fm, "load_aq_cache", lambda: aq_c)
    monkeypatch.setattr(fm, "load_geocode_cache", lambda: geocode if geocode is not None else _geocode_cache())
    monkeypatch.setattr(fm, "load_supplemental_mapping", lambda: supp if supp is not None else _supplemental())
    cache_file = tmp_path / "facility_map.json"
    monkeypatch.setattr(fm, "CACHE_PATH", cache_file)
    monkeypatch.setattr(fm, "INTERIM_DIR", tmp_path)
    return cache_file


def _all_rows(cache):
    rows = []
    for pdata in cache["pathogens"].values():
        rows.extend(pdata["rows"])
    return rows


# --------------------------------------------------------------------------- #
# Constant mirror + normalization (unit)
# --------------------------------------------------------------------------- #
def test_top_n_s03_mirrors_action_queue():
    # The facility map re-declares TOP_N_S03; it must never silently diverge from
    # the action_queue's locked top-N selection.
    assert fm.TOP_N_S03 == aq.TOP_N_S03


def test_normalize_establishment_number_cases_and_idempotence():
    assert fm.normalize_establishment_number("  007 ") == "7"
    assert fm.normalize_establishment_number("00") == "0"
    assert fm.normalize_establishment_number("0a5") == "A5"
    assert fm.normalize_establishment_number(None) == ""
    assert fm.normalize_establishment_number("   ") == ""
    # Idempotent: normalizing an already-normalized value is a no-op.
    for raw in ("007", "00", "0a5", "m44857", " 12 "):
        once = fm.normalize_establishment_number(raw)
        assert fm.normalize_establishment_number(once) == once


# --------------------------------------------------------------------------- #
# P1 — only signal-bearing establishments appear
# --------------------------------------------------------------------------- #
def test_p1_only_signal_bearing_establishments_appear(monkeypatch, tmp_path):
    # Property 1
    s03 = _s03_cache()
    # Add a neither-source establishment: support ok but NOT in elevated top-N only
    # because we inject it as an extra ok record while keeping top-N large enough to
    # include it would make it signal-bearing. Instead demonstrate exclusion using
    # the low_support record (never elevated) and absence of any action for it.
    _patch(monkeypatch, tmp_path, s03=s03, aq_c=_aq_cache())
    cache = fm.compute_facility_map()

    listeria_ids = {r["establishment_id"] for r in cache["pathogens"]["Listeria"]["rows"]}
    # "1" is elevated S03 -> present. "2" is low_support with no action -> excluded.
    assert "1" in listeria_ids
    assert "2" not in listeria_ids

    salm_rows = cache["pathogens"]["Salmonella"]["rows"]
    salm_ids = {r["establishment_id"] for r in salm_rows}
    assert {"10", "20"} <= salm_ids
    # "20" was both elevated-S03 AND an action-queue target -> source_selection "both".
    poultry_b = next(r for r in salm_rows if r["establishment_id"] == "20")
    assert poultry_b["source_selection"] == "both"
    poultry_a = next(r for r in salm_rows if r["establishment_id"] == "10")
    assert poultry_a["source_selection"] == "s03"


def test_p1_action_queue_only_target_is_signal_bearing(monkeypatch, tmp_path):
    # Property 1 — an action-queue establishment target that matches no S03 record
    # is still signal-bearing (keyed on its label, no fabricated establishment_id).
    aq_c = {"actions": [
        {"target_type": "establishment", "pathogen": "STEC",
         "target": "Unknown Beef Co (NE)", "source_module": "S03",
         "evidence_summary": "aq-only target"},
    ]}
    _patch(monkeypatch, tmp_path, s03=_s03_cache(), aq_c=aq_c)
    cache = fm.compute_facility_map()
    stec_rows = cache["pathogens"]["STEC"]["rows"]
    labels = {r["establishment_id"] for r in stec_rows}
    assert "Unknown Beef Co (NE)" in labels
    aq_only = next(r for r in stec_rows if r["establishment_id"] == "Unknown Beef Co (NE)")
    assert aq_only["source_selection"] == "action_queue"
    assert aq_only["normalized_establishment_number"] == ""


# --------------------------------------------------------------------------- #
# P2 — low_support high-posterior is never elevated-selected, never labeled safe
# --------------------------------------------------------------------------- #
def test_p2_low_support_not_elevated_and_never_safe(monkeypatch, tmp_path):
    # Property 2
    _patch(monkeypatch, tmp_path, s03=_s03_cache(), aq_c=None)
    cache = fm.compute_facility_map()
    rows = _all_rows(cache)
    # The low_support "Thin Plant" (id 2, eb_posterior 0.95) must not be selected.
    assert all(r["establishment_id"] != "2" for r in rows)
    # Nothing is ever labeled safe/clean: support_status is only ok/low_support/unknown
    # and no row carries any safe/clean marker.
    for r in rows:
        assert r["support_status"] in ("ok", "low_support", "unknown")
        serialized = str(r).lower()
        assert "safe" not in serialized
        assert "clean" not in serialized


# --------------------------------------------------------------------------- #
# P3 — counting partitions (example + property-based)
# --------------------------------------------------------------------------- #
def test_p3_counting_partition_example(monkeypatch, tmp_path):
    # Property 3
    entries = {"1": {"lat": 34.0, "lon": -118.0, "address": "1 RTE Way, CA"}}
    supp = _supplemental({
        "10": {"location_status": "historical_candidate", "lat": 33.7, "lon": -84.3,
               "historical_address": "10 Poultry Rd, GA", "coordinate_source": "external geocode"},
    })
    _patch(monkeypatch, tmp_path, s03=_s03_cache(), aq_c=_aq_cache(),
           geocode=_geocode_cache(entries=entries), supp=supp)
    cache = fm.compute_facility_map()
    for pdata in cache["pathogens"].values():
        cov = pdata["coverage"]
        if cov["coverage_state"] == "not_applicable":
            assert cov["total_selected"] == 0
            continue
        assert cov["placed"] + cov["unplaced"] == cov["total_selected"]
        assert cov["historical_candidate"] + cov["unresolved"] == cov["unplaced"]


@settings(max_examples=100, deadline=None)
@given(
    n_salm=st.integers(min_value=0, max_value=6),
    n_placed=st.integers(min_value=0, max_value=6),
    n_hist=st.integers(min_value=0, max_value=6),
)
def test_p3_counting_partition_property(n_salm, n_placed, n_hist):
    # Property 3 — over randomized small Salmonella fixtures, the two partition
    # invariants (placed+unplaced==total, historical+unresolved==unplaced) always
    # hold. Hypothesis drives the counts; we build a fresh monkeypatch per example.
    from _pytest.monkeypatch import MonkeyPatch
    import tempfile
    from pathlib import Path

    ests = {}
    for i in range(n_salm):
        eid = str(100 + i)
        ests[eid] = {"establishment_id": eid, "establishment_name": f"Plant {i}",
                     "state": "GA", "eb_posterior": 0.5 - i * 0.01, "ci_low": 0.1,
                     "ci_high": 0.9, "support_status": "ok", "positive_n": 5, "sample_n": 50}
    s03 = {"pathogens": {"Salmonella": {"availability_status": "available",
        "commodity": "raw_poultry", "establishments": ests}}}

    # Place the first n_placed via the geocode cache (normalized key == eid here).
    geo_entries = {}
    placeable = list(ests.keys())[:n_placed]
    for eid in placeable:
        geo_entries[fm.normalize_establishment_number(eid)] = {
            "lat": 33.0, "lon": -84.0, "address": f"{eid} Rd"}
    # Mark the next n_hist unplaced ids as supplemental historical candidates w/ coords.
    supp_entries = {}
    remaining = list(ests.keys())[n_placed:]
    for eid in remaining[:n_hist]:
        supp_entries[eid] = {"location_status": "historical_candidate",
                             "lat": 32.0, "lon": -83.0,
                             "historical_address": f"{eid} Historic Rd",
                             "coordinate_source": "external geocode"}

    mp = MonkeyPatch()
    tmp = Path(tempfile.mkdtemp())
    try:
        mp.setattr(fm, "load_s03_cache", lambda: s03)
        mp.setattr(fm, "load_aq_cache", lambda: None)
        mp.setattr(fm, "load_geocode_cache",
                   lambda: _geocode_cache(entries=geo_entries))
        mp.setattr(fm, "load_supplemental_mapping", lambda: _supplemental(supp_entries))
        mp.setattr(fm, "CACHE_PATH", tmp / "facility_map.json")
        mp.setattr(fm, "INTERIM_DIR", tmp)
        cache = fm.compute_facility_map()
    finally:
        mp.undo()

    cov = cache["pathogens"]["Salmonella"]["coverage"]
    if n_salm == 0:
        assert cov["coverage_state"] == "not_applicable"
        assert cov["total_selected"] == 0
    else:
        assert cov["total_selected"] == n_salm
        assert cov["placed"] + cov["unplaced"] == cov["total_selected"]
        assert cov["historical_candidate"] + cov["unresolved"] == cov["unplaced"]
        assert cov["placed"] == min(n_placed, n_salm)


# --------------------------------------------------------------------------- #
# P4 — placed rows carry real coords/address + verified provenance
# --------------------------------------------------------------------------- #
def test_p4_placed_rows_have_real_verified_location(monkeypatch, tmp_path):
    # Property 4
    entries = {
        "1": {"lat": 34.05, "lon": -118.24, "address": "1 RTE Way, CA"},
        "10": {"lat": 33.74, "lon": -84.38, "address": "10 Poultry Rd, GA"},
    }
    _patch(monkeypatch, tmp_path, s03=_s03_cache(), aq_c=_aq_cache(),
           geocode=_geocode_cache(entries=entries))
    cache = fm.compute_facility_map()
    placed = [r for r in _all_rows(cache) if r["placement_status"] == "placed"]
    assert placed, "expected at least one placed row"
    for r in placed:
        norm = r["normalized_establishment_number"]
        assert norm in entries
        src = entries[norm]
        assert r["lat"] == pytest.approx(src["lat"])
        assert r["lon"] == pytest.approx(src["lon"])
        assert r["address"] == src["address"]
        assert r["location_status"] == "mpi_verified"
        assert r["verified_against_fsis_id"] is True
        assert r["coordinate_source"] == fm._MPI_COORDINATE_SOURCE
        assert r["unplaced_reason"] is None


# --------------------------------------------------------------------------- #
# P5 — every unplaced row has a non-empty reason
# --------------------------------------------------------------------------- #
def test_p5_unplaced_rows_have_reason(monkeypatch, tmp_path):
    # Property 5 — empty geocode cache -> every row unplaced with a stated reason.
    _patch(monkeypatch, tmp_path, s03=_s03_cache(), aq_c=_aq_cache(),
           geocode=_geocode_cache(obtained=False))
    cache = fm.compute_facility_map()
    rows = _all_rows(cache)
    assert rows
    for r in rows:
        if r["placement_status"] in ("unplaced",):
            assert r["unplaced_reason"], f"unplaced row missing reason: {r['establishment_id']}"
            assert r["unplaced_reason"].strip()


# --------------------------------------------------------------------------- #
# P6 — coverage_pct is verified placed-only, never inflated by overlay
# --------------------------------------------------------------------------- #
def test_p6_coverage_not_inflated_by_historical_candidate_with_coords(monkeypatch, tmp_path):
    # Property 6 — a supplemental candidate WITH coords becomes
    # placement_status=="historical_candidate" and is counted in that sub-count, but
    # coverage_pct stays placed-only.
    s03 = {"pathogens": {"Salmonella": {"availability_status": "available",
        "commodity": "raw_poultry", "establishments": {
            "10": {"establishment_id": "10", "establishment_name": "Poultry A",
                   "state": "GA", "eb_posterior": 0.5, "ci_low": 0.4, "ci_high": 0.6,
                   "support_status": "ok", "positive_n": 20, "sample_n": 100},
            "20": {"establishment_id": "20", "establishment_name": "Poultry B",
                   "state": "AL", "eb_posterior": 0.45, "ci_low": 0.3, "ci_high": 0.55,
                   "support_status": "ok", "positive_n": 15, "sample_n": 90},
        }}}}
    # Only id 10 verified-placed; id 20 is a supplemental historical candidate w/ coords.
    geo = _geocode_cache(entries={"10": {"lat": 33.7, "lon": -84.3, "address": "10 Rd, GA"}})
    supp = _supplemental({
        "20": {"location_status": "historical_candidate", "lat": 32.4, "lon": -86.9,
               "historical_address": "20 Historic Rd, AL",
               "historical_inspection_number": "M44857 / P44857",
               "coordinate_source": "external geocode",
               "evidence_urls": ["https://example.org/evidence"]},
    })
    _patch(monkeypatch, tmp_path, s03=s03, aq_c=None, geocode=geo, supp=supp)
    cache = fm.compute_facility_map()
    cov = cache["pathogens"]["Salmonella"]["coverage"]
    rows = cache["pathogens"]["Salmonella"]["rows"]

    row20 = next(r for r in rows if r["establishment_id"] == "20")
    assert row20["placement_status"] == "historical_candidate"
    assert row20["location_status"] == "historical_candidate"
    assert row20["lat"] == pytest.approx(32.4)
    assert row20["lon"] == pytest.approx(-86.9)

    assert cov["total_selected"] == 2
    assert cov["placed"] == 1
    assert cov["historical_candidate"] == 1
    assert cov["unresolved"] == 0
    assert cov["unplaced"] == 1
    # VERIFIED coverage is placed-only: 1/2 == 50.0, NOT inflated to 100.
    assert cov["coverage_pct"] == pytest.approx(50.0)


def test_p6_null_coord_candidate_stays_unplaced_not_counted(monkeypatch, tmp_path):
    # Property 6 — a supplemental candidate with NULL coords stays unplaced with
    # location_status=="historical_candidate" but is NOT promoted to a
    # placement_status=="historical_candidate" (so not in that sub-count).
    s03 = {"pathogens": {"Salmonella": {"availability_status": "available",
        "commodity": "raw_poultry", "establishments": {
            "10": {"establishment_id": "10", "establishment_name": "Poultry A",
                   "state": "GA", "eb_posterior": 0.5, "ci_low": 0.4, "ci_high": 0.6,
                   "support_status": "ok", "positive_n": 20, "sample_n": 100},
            "30": {"establishment_id": "30", "establishment_name": "Poultry C",
                   "state": "MS", "eb_posterior": 0.4, "ci_low": 0.3, "ci_high": 0.5,
                   "support_status": "ok", "positive_n": 10, "sample_n": 80},
        }}}}
    geo = _geocode_cache(entries={"10": {"lat": 33.7, "lon": -84.3, "address": "10 Rd, GA"}})
    supp = _supplemental({
        "30": {"location_status": "historical_candidate", "lat": None, "lon": None,
               "historical_address": "30 Historic Rd, MS",
               "historical_inspection_number": "M99999"},
    })
    _patch(monkeypatch, tmp_path, s03=s03, aq_c=None, geocode=geo, supp=supp)
    cache = fm.compute_facility_map()
    rows = cache["pathogens"]["Salmonella"]["rows"]
    cov = cache["pathogens"]["Salmonella"]["coverage"]

    row30 = next(r for r in rows if r["establishment_id"] == "30")
    assert row30["placement_status"] == "unplaced"
    assert row30["location_status"] == "historical_candidate"
    assert row30["lat"] is None and row30["lon"] is None

    assert cov["placed"] == 1
    assert cov["total_selected"] == 2
    # The null-coord candidate is NOT a historical_candidate PLACEMENT sub-count.
    assert cov["historical_candidate"] == 0
    assert cov["unresolved"] == 1
    assert cov["coverage_pct"] == pytest.approx(50.0)


# --------------------------------------------------------------------------- #
# P7 — every row human_review True + status OBSERVED
# --------------------------------------------------------------------------- #
def test_p7_every_row_human_review_and_observed(monkeypatch, tmp_path):
    # Property 7
    entries = {"1": {"lat": 34.0, "lon": -118.0, "address": "1 RTE Way"}}
    _patch(monkeypatch, tmp_path, s03=_s03_cache(), aq_c=_aq_cache(),
           geocode=_geocode_cache(entries=entries))
    cache = fm.compute_facility_map()
    rows = _all_rows(cache)
    assert rows
    for r in rows:
        assert r["human_review"] is True
        assert r["status"] == "OBSERVED"
        assert r["status"] not in ("PREDICTED", "SIMULATED")


# --------------------------------------------------------------------------- #
# P8 — overlay honesty
# --------------------------------------------------------------------------- #
def test_p8_overlay_never_verified_and_inspection_number_not_id(monkeypatch, tmp_path):
    # Property 8
    s03 = {"pathogens": {"Salmonella": {"availability_status": "available",
        "commodity": "raw_poultry", "establishments": {
            "20": {"establishment_id": "20", "establishment_name": "Poultry B",
                   "state": "AL", "eb_posterior": 0.45, "ci_low": 0.3, "ci_high": 0.55,
                   "support_status": "ok", "positive_n": 15, "sample_n": 90},
        }}}}
    geo = _geocode_cache(entries={})  # nothing verified-placed
    supp = _supplemental({
        "20": {"location_status": "historical_candidate", "lat": 32.4, "lon": -86.9,
               "historical_address": "20 Historic Rd, AL",
               "historical_inspection_number": "M44857 / P44857",
               "coordinate_source": "external geocode"},
    })
    _patch(monkeypatch, tmp_path, s03=s03, aq_c=None, geocode=geo, supp=supp)
    cache = fm.compute_facility_map()
    row = cache["pathogens"]["Salmonella"]["rows"][0]
    assert row["verified_against_fsis_id"] is False
    assert row["historical_inspection_number"] == "M44857 / P44857"
    # The numeric establishment_id is NEVER asserted equal to the inspection string.
    assert row["establishment_id"] == "20"
    assert row["establishment_id"] != row["historical_inspection_number"]


def test_p8_do_not_map_supplemental_stays_unresolved(monkeypatch, tmp_path):
    # Property 8 — a do_not_map / unresolved supplemental entry (like id 632) stays
    # location_status=="unresolved" and unplaced.
    s03 = {"pathogens": {"Salmonella": {"availability_status": "available",
        "commodity": "raw_poultry", "establishments": {
            "632": {"establishment_id": "632", "establishment_name": "Do Not Map Co",
                    "state": "TX", "eb_posterior": 0.6, "ci_low": 0.5, "ci_high": 0.7,
                    "support_status": "ok", "positive_n": 12, "sample_n": 70},
        }}}}
    geo = _geocode_cache(entries={})
    supp = _supplemental({
        "632": {"location_status": "unresolved", "do_not_map": True,
                "historical_inspection_number": "M632", "lat": 30.0, "lon": -97.0},
    })
    _patch(monkeypatch, tmp_path, s03=s03, aq_c=None, geocode=geo, supp=supp)
    cache = fm.compute_facility_map()
    row = cache["pathogens"]["Salmonella"]["rows"][0]
    assert row["placement_status"] == "unplaced"
    assert row["location_status"] == "unresolved"
    assert row["lat"] is None and row["lon"] is None
    assert row["verified_against_fsis_id"] is False
    assert row["unplaced_reason"] and row["unplaced_reason"].strip()


# --------------------------------------------------------------------------- #
# P9 — deterministic + sorted
# --------------------------------------------------------------------------- #
def test_p9_deterministic_and_sorted(monkeypatch, tmp_path):
    # Property 9 — two runs over identical fixtures produce identical row ordering
    # (sorted by normalized_establishment_number) and identical values.
    entries = {
        "1": {"lat": 34.0, "lon": -118.0, "address": "1 RTE Way"},
        "10": {"lat": 33.7, "lon": -84.3, "address": "10 Poultry Rd"},
        "20": {"lat": 32.4, "lon": -86.9, "address": "20 Poultry Rd"},
    }
    _patch(monkeypatch, tmp_path, s03=_s03_cache(), aq_c=_aq_cache(),
           geocode=_geocode_cache(entries=entries))
    first = fm.compute_facility_map()
    second = fm.compute_facility_map()
    assert first == second

    for pdata in first["pathogens"].values():
        norms = [r["normalized_establishment_number"] for r in pdata["rows"]]
        keys = [(r["normalized_establishment_number"], r["establishment_id"]) for r in pdata["rows"]]
        assert keys == sorted(keys)
        # floats are rounded to the default 6 places.
        for r in pdata["rows"]:
            for k in ("eb_posterior", "ci_low", "ci_high", "lat", "lon"):
                v = r.get(k)
                if isinstance(v, float):
                    assert round(v, 6) == v


# --------------------------------------------------------------------------- #
# Schema <-> TypeScript parity (FacilityMapItem / FacilityMapCoverage)
# --------------------------------------------------------------------------- #
import re
import typing
from pathlib import Path

from src.artifacts.schemas import FacilityMapCoverage, FacilityMapItem

_ARTIFACTS_TS = Path(__file__).resolve().parents[1] / "web" / "src" / "types" / "artifacts.ts"


def _ts_interface_fields(ts_text: str, interface_name: str) -> set[str]:
    """Parse the field names of a TypeScript interface body.

    Extracts the ``interface <name> { ... }`` block and pulls each
    ``fieldName:`` key, ignoring comments. Deliberately simple: the parity
    contract is key-set equality, so we only need the identifiers.
    """
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
        # Drop trailing line comments.
        stripped = stripped.split("//", 1)[0].strip()
        fm_match = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s*[?]?\s*:", stripped)
        if fm_match:
            fields.add(fm_match.group(1))
    return fields


def test_facility_map_coverage_python_ts_parity():
    ts_text = _ARTIFACTS_TS.read_text(encoding="utf-8")
    py_keys = set(typing.get_type_hints(FacilityMapCoverage).keys())
    ts_keys = _ts_interface_fields(ts_text, "FacilityMapCoverage")
    assert py_keys == ts_keys, (
        f"FacilityMapCoverage parity mismatch: "
        f"py-only={py_keys - ts_keys}, ts-only={ts_keys - py_keys}")


def test_facility_map_item_python_ts_parity():
    ts_text = _ARTIFACTS_TS.read_text(encoding="utf-8")
    py_keys = set(typing.get_type_hints(FacilityMapItem).keys())
    ts_keys = _ts_interface_fields(ts_text, "FacilityMapItem")
    assert py_keys == ts_keys, (
        f"FacilityMapItem parity mismatch: "
        f"py-only={py_keys - ts_keys}, ts-only={ts_keys - py_keys}")
