"""Tests for the S01 program/product stratification analysis."""

from __future__ import annotations

import math

from src.analysis.program_product import (
    _classify_result,
    _norm_category,
    wilson_ci,
    load_cache,
)

def test_classify_result_diagnostic_mapping():
    assert _classify_result("Positive") is True
    assert _classify_result("positive") is True
    assert _classify_result("Negative") is False
    # a negative CONFIRMATION is a negative, never a positive
    assert _classify_result("Confirmed Negative of a Previous Presumptive") is False
    # non-diagnostic / lab-problem / blank are excluded (None)
    assert _classify_result("25-5  Lab problem - lab closed") is None
    assert _classify_result("") is None
    assert _classify_result(None) is None

def test_norm_category_merges_variants():
    # casing + whitespace collapse
    assert _norm_category("Alt 3") == _norm_category("ALT 3") == "ALT 3"
    assert _norm_category("Alt 2b  AMAP") == "ALT 2B AMAP"
    # leading enumerators stripped
    assert _norm_category("a. Breast") == _norm_category("Breast") == "BREAST"
    assert _norm_category("b. Leg") == "LEG"
    # NULL / blank -> explicit unspecified bucket
    assert _norm_category("NULL") == "(unspecified)"
    assert _norm_category("") == "(unspecified)"
    assert _norm_category(None) == "(unspecified)"

def test_wilson_ci_bounds_and_zero():
    lo, hi = wilson_ci(0, 0)
    assert lo is None and hi is None
    lo, hi = wilson_ci(5, 100)
    assert 0.0 <= lo <= 0.05 <= hi <= 1.0
    # interval brackets the point estimate
    assert lo < 0.05 < hi
    # a zero-positive group has lo == 0 and a positive upper bound
    lo0, hi0 = wilson_ci(0, 30)
    assert lo0 == 0.0 and hi0 > 0.0

def test_cache_denominator_conservation_and_contract():
    """The generated cache (if present) must conserve denominators, keep
    product unavailable for STEC, and never report positive_n > sample_n."""
    cache = load_cache()
    if cache is None:
        # analysis not yet run in this environment; nothing to assert
        return
    assert cache["module_id"] == "S01"
    for pathogen, pdata in cache["pathogens"].items():
        overall = pdata["overall"]
        if overall["sample_n"]:
            assert 0 <= overall["positive_n"] <= overall["sample_n"]
            # overall positivity equals positive/sample within rounding
            assert math.isclose(
                overall["value"], overall["positive_n"] / overall["sample_n"], abs_tol=1e-6
            )
        for dim_name, block in pdata["dimensions"].items():
            if block.get("availability_status") != "available":
                continue
            for c in block["categories"]:
                assert 0 <= c["positive_n"] <= c["sample_n"]  # no impossible counts
                assert c["ci_low"] is None or 0.0 <= c["ci_low"] <= 1.0
                assert c["ci_high"] is None or 0.0 <= c["ci_high"] <= 1.0

    # STEC has no product/control column -> that dimension is unavailable
    stec = cache["pathogens"].get("STEC")
    if stec:
        assert stec["dimensions"]["product"]["availability_status"] == "unavailable"

def test_no_cross_pathogen_category_leak():
    """Salmonella product categories (poultry parts) must not appear under
    Listeria's product dimension (RTE production alternatives), and vice versa."""
    cache = load_cache()
    if cache is None:
        return
    salm = cache["pathogens"].get("Salmonella", {}).get("dimensions", {}).get("product", {})
    list_ = cache["pathogens"].get("Listeria", {}).get("dimensions", {}).get("product", {})
    salm_cats = {c["category"] for c in salm.get("categories", [])}
    list_cats = {c["category"] for c in list_.get("categories", [])}
    # Listeria uses "ALT ..." production alternatives; Salmonella uses poultry parts.
    assert not any(c.startswith("ALT ") for c in salm_cats)
    assert "BREAST" not in list_cats and "WING" not in list_cats
