"""S03 tests — lock the correctness/honesty properties for the establishment
EB surveillance detector. Small hand-built inputs; fast and deterministic."""

from __future__ import annotations

from src.analysis import establishment_surveillance as es
from src.artifacts.exporter import build_establishment_surveillance

# --------------------------------------------------------------------------- #
# Unit-level: prior fit, posterior, persistence
# --------------------------------------------------------------------------- #

def test_fit_beta_prior_recovers_mean():
    # Rates centered near 0.1 should give a prior whose mean ~ 0.1.
    rates = [0.08, 0.10, 0.12, 0.09, 0.11]
    a, b, mean = es.fit_beta_prior(rates)
    assert a > 0 and b > 0
    assert abs(mean - 0.1) < 0.02
    assert abs(a / (a + b) - mean) < 1e-9

# --------------------------------------------------------------------------- #
# Property 2: posterior smoothing — low support shrinks toward peer, wider CI
# --------------------------------------------------------------------------- #

def test_posterior_smoothing_and_interval_width():
    # Peer rate ~0.1 via a moderate prior.
    alpha0, beta0 = 2.0, 18.0  # mean 0.1
    peer = alpha0 / (alpha0 + beta0)

    # Low-support establishment: 2/4 raw = 0.5.
    lo_mean, lo_lo, lo_hi = es.eb_posterior(2, 4, alpha0, beta0)
    # High-support establishment, same raw rate 0.5: 100/200.
    hi_mean, hi_lo, hi_hi = es.eb_posterior(100, 200, alpha0, beta0)

    raw = 0.5
    # Low-support posterior lies strictly between the peer rate and the raw rate.
    assert peer < lo_mean < raw
    # High-support posterior is much closer to the raw rate than the low-support one.
    assert abs(hi_mean - raw) < abs(lo_mean - raw)
    # Interval width: low support is wider than high support (scipy present).
    if lo_lo is not None and hi_lo is not None:
        assert (lo_hi - lo_lo) > (hi_hi - hi_lo)

def test_persistence_evidence_counts():
    rows = [
        {"quarter": "2020-Q1", "quarter_start": "2020-01-01", "samples": 10, "positives": 1},
        {"quarter": "2020-Q2", "quarter_start": "2020-04-01", "samples": 0, "positives": 0},
        {"quarter": "2020-Q3", "quarter_start": "2020-07-01", "samples": 8, "positives": 0},
        {"quarter": "2020-Q4", "quarter_start": "2020-10-01", "samples": 5, "positives": 2},
    ]
    p = es._persistence(rows)
    assert p["repeated_positive_periods"] == 2   # Q1 and Q4 had positives
    assert p["periods_supported"] == 3           # Q1, Q3, Q4 had samples
    assert p["last_supported_period"] == "2020-Q4"
    assert p["sampling_gaps"] == 1               # Q2 had zero samples

# --------------------------------------------------------------------------- #
# Artifact-level properties (built from the real cache)
# --------------------------------------------------------------------------- #

def test_low_support_not_labeled_safe():
    rows = build_establishment_surveillance()
    for r in rows:
        if r["support_status"] == "low_support":
            # A low-support establishment carries no "safe"/"clean" claim; it is
            # simply flagged low_support and still shows its (shrunk) estimate.
            assert r["support_status"] == "low_support"
            assert "safe" not in (r.get("unavailable_reason") or "").lower()

def test_anonymization_no_contact_fields():
    rows = build_establishment_surveillance()
    forbidden = {"address", "phone", "email", "contact", "street", "zip", "owner"}
    for r in rows:
        keys = {k.lower() for k in r.keys()}
        assert keys.isdisjoint(forbidden), f"contact-detail field present: {keys & forbidden}"

def test_no_synthetic_supplier_relationship():
    rows = build_establishment_surveillance()
    banned = ("supplier_to", "retailer", "ships_to", "destination", "customer")
    for r in rows:
        for k in r.keys():
            assert not any(b in k.lower() for b in banned), f"relationship field present: {k}"

def test_state_establishment_uniqueness():
    rows = build_establishment_surveillance()
    keys = [
        (r["pathogen"], r["establishment_id"])
        for r in rows
        if r["availability_status"] == "available"
    ]
    assert len(keys) == len(set(keys))

def test_denominator_conservation_and_bounds():
    rows = build_establishment_surveillance()
    for r in rows:
        if r["sample_n"] is not None and r["positive_n"] is not None:
            assert 0 <= r["positive_n"] <= r["sample_n"]
        for field in ("value", "eb_posterior", "ci_low", "ci_high", "peer_rate"):
            v = r[field]
            if v is not None:
                assert 0.0 <= v <= 1.0, f"{field}={v} out of [0,1]"

def test_all_descriptive_observed_no_predicted():
    # No establishment forecast validated in the current data, so every row is
    # OBSERVED / descriptive_only — never a PREDICTED establishment forecast.
    rows = build_establishment_surveillance()
    for r in rows:
        assert r["status"] == "OBSERVED"
        assert r["predictive_status"] in (
            "descriptive_only", "insufficient_support", "not_shown",
        )
