"""S04 tests — lock the six correctness properties for the emerging-risk detector.

These use small hand-built series (no raw-data dependency) so they are fast and
deterministic. They enforce the honesty rules: leakage-safety, low-n handling,
retrospective != forecast, uniqueness, denominator conservation, and the
persistence-vs-anomaly distinction.
"""

from __future__ import annotations

import copy

from src.analysis import emerging_risk as er
from src.artifacts.exporter import build_emerging_risk

# --------------------------------------------------------------------------- #
# Helpers to build synthetic state series
# --------------------------------------------------------------------------- #
def _cell(period, start, n, pos):
    return {"period": period, "period_start": start, "n": n, "pos": pos}

def _steady_series(n_quarters, n=100, pos=5, start_year=2014):
    """A flat, well-supported series (rate 0.05 every quarter)."""
    cells = []
    for i in range(n_quarters):
        year = start_year + i // 4
        q = i % 4 + 1
        cells.append(_cell(f"{year}-Q{q}", f"{year}-{(q-1)*3+1:02d}-01", n, pos))
    return cells

# --------------------------------------------------------------------------- #
# Property 1: no future threshold / baseline (leakage-safety)
# --------------------------------------------------------------------------- #
def test_baseline_and_threshold_ignore_future_periods():
    base = _steady_series(12)
    # Compute baselines/flags for the original series.
    b1 = er.trailing_baseline(base)
    r1 = er.detect_retrospective(base, b1)

    # Mutate ONLY the last three periods (the "future" relative to earlier ones).
    mutated = copy.deepcopy(base)
    for i in (-1, -2, -3):
        mutated[i]["pos"] = mutated[i]["n"]  # force 100% positivity in the tail
    b2 = er.trailing_baseline(mutated)
    r2 = er.detect_retrospective(mutated, b2)

    # Baselines/flags for every period BEFORE the mutated tail must be identical.
    cut = len(base) - 3
    assert b1[:cut] == b2[:cut]
    assert [x["retro_anomaly"] for x in r1[:cut]] == [x["retro_anomaly"] for x in r2[:cut]]

# --------------------------------------------------------------------------- #
# Property 2: low-n is never flagged as a (non-)anomaly by default
# --------------------------------------------------------------------------- #
def test_low_support_not_flagged_negative():
    cells = _steady_series(10)
    # Make one well-supported period tiny (below MIN_SUPPORT).
    cells[6]["n"] = er.MIN_SUPPORT - 1
    cells[6]["pos"] = 0
    bases = er.trailing_baseline(cells)
    retro = er.detect_retrospective(cells, bases)
    assert retro[6]["support_status"] == "low_support"
    # NOT False-by-default: a low-support cell is unflagged (None).
    assert retro[6]["retro_anomaly"] is None

# --------------------------------------------------------------------------- #
# Property 3: no retrospective row is labeled a forecast / PREDICTED
# --------------------------------------------------------------------------- #
def test_no_retrospective_row_labeled_predicted():
    rows = build_emerging_risk()
    for r in rows:
        if r["status"] == "PREDICTED":
            # A PREDICTED row must be a validated prospective alert, never a
            # bare retrospective anomaly.
            assert r["prospective_status"] == "validated"
            assert r["prospective_alert"] is True
    # In the current data no forecast validated, so there must be zero PREDICTED.
    assert all(r["status"] == "OBSERVED" for r in rows)

# --------------------------------------------------------------------------- #
# Property 4: (pathogen, region, period) is unique across the artifact
# --------------------------------------------------------------------------- #
def test_state_period_uniqueness():
    rows = build_emerging_risk()
    keys = [(r["pathogen"], r["region"], r["period"]) for r in rows
            if r["availability_status"] == "available"]
    assert len(keys) == len(set(keys))

# --------------------------------------------------------------------------- #
# Property 5: denominator conservation and bounded rates
# --------------------------------------------------------------------------- #
def test_denominator_conservation_and_bounds():
    rows = build_emerging_risk()
    for r in rows:
        if r["sample_n"] is not None and r["positive_n"] is not None:
            assert 0 <= r["positive_n"] <= r["sample_n"]
        for field in ("value", "ci_low", "ci_high", "trailing_baseline", "baseline_high"):
            v = r[field]
            if v is not None:
                assert 0.0 <= v <= 1.0, f"{field}={v} out of [0,1]"

# --------------------------------------------------------------------------- #
# Property 6: persistence != anomaly
# --------------------------------------------------------------------------- #
def test_persistence_distinct_from_current_anomaly():
    # A chronically-elevated series: low baseline for the first 2 quarters, then
    # a sustained high plateau. The EWMA baseline adapts to the plateau over
    # time, so persistence is driven by the quarters right after the jump.
    cells = []
    for i in range(12):
        year = 2014 + i // 4
        q = i % 4 + 1
        pos = 2 if i < 2 else 30
        cells.append(_cell(f"{year}-Q{q}", f"{year}-{(q-1)*3+1:02d}-01", 100, pos))
    bases = er.trailing_baseline(cells)
    retro = er.detect_retrospective(cells, bases)
    pscore_high = er.persistent_score(cells, bases)

    # A flat, never-elevated series of the same length and support.
    flat = _steady_series(12, n=100, pos=5)
    pscore_flat = er.persistent_score(flat, er.trailing_baseline(flat))

    # The chronically-elevated series must score meaningfully above the flat one.
    assert pscore_high is not None and pscore_flat is not None
    assert pscore_high > pscore_flat
    assert pscore_high > 0.0 and pscore_flat < 0.1

    # And the FINAL plateau quarter is NOT a new increase (baseline has caught
    # up), so it must not be flagged as a current-period anomaly.
    assert retro[-1]["retro_anomaly"] in (False, None)

# --------------------------------------------------------------------------- #
# Extra: persistence support floor (no thin-data chart-toppers)
# --------------------------------------------------------------------------- #
def test_persistence_requires_minimum_quarters():
    thin = _steady_series(er.PERSISTENCE_MIN_QUARTERS - 1, n=100, pos=90)  # very high but short
    bases = er.trailing_baseline(thin)
    assert er.persistent_score(thin, bases) is None
