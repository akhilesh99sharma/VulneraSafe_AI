"""S05 tests — lock the honesty/correctness properties for the FSIS-vs-NORS
human-outbreak comparison. Small hand-built fixtures + the real built artifact."""

from __future__ import annotations

from src.analysis import human_comparison as hc
from src.artifacts.exporter import build_human_outbreak_comparison

# --------------------------------------------------------------------------- #
# Unit: conservative etiology standardization
# --------------------------------------------------------------------------- #

def test_standardize_etiology_conservative_and_multi():
    assert hc.standardize_etiology("Salmonella enterica") == {"Salmonella"}
    assert hc.standardize_etiology("Listeria monocytogenes") == {"Listeria"}
    # STEC family keywords
    assert hc.standardize_etiology("Escherichia coli O157:H7") == {"STEC"}
    assert hc.standardize_etiology("Shiga toxin-producing E. coli") == {"STEC"}
    # multi-etiology splits on ';' and attributes to each match
    assert hc.standardize_etiology("Salmonella;E. coli O157") == {"Salmonella", "STEC"}
    # unmatched etiologies return empty (excluded, never force-fit)
    assert hc.standardize_etiology("Norovirus Genogroup II") == set()
    assert hc.standardize_etiology("") == set()
    assert hc.standardize_etiology(None) == set()

# --------------------------------------------------------------------------- #
# Unit: 365-day availability lag
# --------------------------------------------------------------------------- #

def test_availability_lag_is_one_year():
    assert hc.availability_year(2018) == 2019
    assert hc.availability_year(2013) == 2014

# --------------------------------------------------------------------------- #
# Property 1: 365-day lag enforced on every artifact cell
# --------------------------------------------------------------------------- #

def test_artifact_lag_enforced():
    rows = build_human_outbreak_comparison()
    for r in rows:
        if r["availability_status"] != "available":
            continue
        assert r["availability_lag_days"] == 365
        if r["period"].isdigit() and r["nors_available_from_year"] is not None:
            assert r["nors_available_from_year"] == int(r["period"]) + 1

# --------------------------------------------------------------------------- #
# Property 2: no CDC predictor leakage
# A NORS cell for year Y is only knowable from Y+1, so it can never be aligned
# as a predictor of the SAME year's FSIS value. We assert the availability year
# is always strictly after the period year (never <=).
# --------------------------------------------------------------------------- #

def test_no_cdc_predictor_leakage():
    rows = build_human_outbreak_comparison()
    for r in rows:
        if r["availability_status"] != "available":
            continue
        if r["period"].isdigit() and r["nors_available_from_year"] is not None:
            assert r["nors_available_from_year"] > int(r["period"])

# --------------------------------------------------------------------------- #
# Property 3: zero vs missing distinction
# --------------------------------------------------------------------------- #

def test_zero_vs_missing_distinction():
    rows = build_human_outbreak_comparison()
    # a covered pathogen has genuine zeros (count == 0) AND no missing-count cells
    cov_ok = [r for r in rows if r["coverage_status"] == "ok" and r["availability_status"] == "available"]
    assert any(r["nors_outbreak_count"] == 0 for r in cov_ok)
    assert all(r["nors_outbreak_count"] is not None for r in cov_ok)
    # a coverage-limited cell carries a null count (missing), never a forced zero
    limited = [r for r in rows if r["coverage_status"] == "coverage_limited"]
    assert any(r["nors_outbreak_count"] is None for r in limited)

# --------------------------------------------------------------------------- #
# Property 4: no causal / forecast / sub-state field; corroboration labeled
# --------------------------------------------------------------------------- #

def test_no_causal_or_forecast_labels():
    rows = build_human_outbreak_comparison()
    banned_substrings = ("same_strain", "samestrain", "forecast", "predicted_illness", "county")
    # The disclaimer field legitimately contains "causal" (it is the no-causal-link
    # note); exclude it from the field-name scan rather than banning the cure.
    allowed = {"no_causal_link_note"}
    for r in rows:
        for k in r.keys():
            if k in allowed:
                continue
            assert not any(b in k.lower() for b in banned_substrings), f"banned field: {k}"
        if r["availability_status"] == "available":
            assert r["comparison_status"] == "CORROBORATION"
            assert r["no_causal_link_note"]
            assert r["status"] == "OBSERVED"
            # lead-lag, when present, is explicitly exploratory
            if r["lead_lag"] is not None:
                assert r["lead_lag"]["exploratory"] is True

# --------------------------------------------------------------------------- #
# Property 5/6: all three pathogens first-class; thin pathogen coverage_limited
# --------------------------------------------------------------------------- #

def test_all_three_pathogens_with_honest_coverage():
    rows = build_human_outbreak_comparison()
    pathogens = {r["pathogen"] for r in rows}
    assert {"Salmonella", "Listeria", "STEC"} <= pathogens
    # Listeria is the sparse one -> coverage_limited on its cells (never dropped)
    listeria = [r for r in rows if r["pathogen"] == "Listeria"]
    assert listeria, "Listeria must be present"
    assert any(r["coverage_status"] == "coverage_limited" for r in listeria)

# --------------------------------------------------------------------------- #
# Property 7: denominator conservation / bounded FSIS rates
# --------------------------------------------------------------------------- #

def test_fsis_denominator_conservation():
    rows = build_human_outbreak_comparison()
    for r in rows:
        if r["fsis_sample_n"] and r["fsis_positive_n"] is not None:
            assert 0 <= r["fsis_positive_n"] <= r["fsis_sample_n"]
        for field in ("fsis_positivity", "fsis_ci_low", "fsis_ci_high"):
            v = r[field]
            if v is not None:
                assert 0.0 <= v <= 1.0
        if r["nors_outbreak_count"] is not None:
            assert r["nors_outbreak_count"] >= 0
        if r["nors_illness_count"] is not None:
            assert r["nors_illness_count"] >= 0
