"""S02 — Seasonal / Temporal Hazard Patterns tests.

Lock the honesty/correctness properties of the pure analysis core in
``src/analysis/seasonal_hazard_patterns.py``: pooling the national monthly
series, computing pooled per-bucket positivity + Wilson CI, the minimum-sample
gates, peak selection over AVAILABLE buckets only, the ordinal-year OLS trend
slope and its year gate, no-fabrication of unavailable statistics, and
deterministic reproducibility.

Mirrors the Hypothesis style of ``tests/test_county_community_impact.py`` and
``tests/test_community_impact.py``: ``@settings(max_examples=100, deadline=None)``
property tests over generated inputs, each tagged in a docstring/comment
``Feature: s02-seasonal-hazard-patterns, Property N: <text>``.

The analysis core is pure given an injected list of monthly cells, so these
property tests exercise the real functions directly — ``_pool_monthly_series``,
``_analyze_pooled_cells``, ``_bucket_rate``, ``_build_bucket_records``,
``_peak_label``, ``_trend_slope``, ``_annual_rates`` — with no real FSIS data and
no filesystem I/O (except the determinism test's optional cache-write path).

Property numbering follows ``design.md``'s Correctness Properties. This file
holds Task 3.1's core honesty/gating/peak/trend/determinism properties (P1, P3-P9).
Property 2 (periods_read exactness) is optional Task 3.2 and the guardrail-copy /
no-mutation EXAMPLE tests are Task 3.3 — both intentionally omitted here so a
concurrent subagent can MERGE them into this same file without collision.

Property 8 — status-layer note
-------------------------------
The S02 CACHE (what ``compute_seasonal_hazard_patterns`` / ``_analyze_pooled_cells``
produce) carries NO per-row ``status`` field; the ``status == "OBSERVED"`` tag is an
EXPORTER concern attached by ``build_seasonal_hazard_patterns`` (Task 6) and is
asserted at the record level by the exporter test (Task 7.1). So at the analysis
layer there is no status field to read. P8 is therefore implemented as the honest
EQUIVALENT at the layer that actually exists: the module emits no
forecast/predicted/simulated content anywhere in its output, and every reported
value is derived from the observed ``pos``/``n`` counts (pooled rate, Wilson CI on
those counts, seasonal index = rate/overall, OLS slope over observed annual
rates). This is documented in the test body as well.
"""

from __future__ import annotations

import copy

from hypothesis import given, settings
from hypothesis import strategies as st

from src.analysis import seasonal_hazard_patterns as shp


# --------------------------------------------------------------------------- #
# Shared Hypothesis strategies
# --------------------------------------------------------------------------- #
# Years in a small range keep the generated space broad but bounded; month is a
# full calendar month 1..12; n/pos are non-negative ints with the hard constraint
# pos <= n (an honest surveillance cell can never have more positives than
# samples). We draw n first, then pos in [0, n], so the constraint always holds.


@st.composite
def _monthly_cell(draw, *, year_min=2010, year_max=2020, n_max=200):
    """One pooled monthly cell ``{year, month, n, pos}`` with ``0 <= pos <= n``.

    This is exactly the shape :func:`shp._pool_monthly_series` emits and
    :func:`shp._analyze_pooled_cells` / :func:`shp._bucket_rate` consume, so tests
    can build pooled cells directly without needing a ``{state: [cells]}`` series.
    """
    year = draw(st.integers(min_value=year_min, max_value=year_max))
    month = draw(st.integers(min_value=1, max_value=12))
    n = draw(st.integers(min_value=0, max_value=n_max))
    pos = draw(st.integers(min_value=0, max_value=n))
    return {"year": year, "month": month, "n": n, "pos": pos}


def _pooled_cells(*, min_size=0, max_size=60, **kw):
    """A list strategy of pooled monthly cells (broad generators per the hard-
    constraint testing guidance)."""
    return st.lists(_monthly_cell(**kw), min_size=min_size, max_size=max_size)


@st.composite
def _series_cell(draw, *, year_min=2010, year_max=2020, n_max=200):
    """One raw ``_build_series``-style cell ``{period: "YYYY-MM", period_start,
    n, pos}`` for exercising :func:`shp._pool_monthly_series` on realistic input.
    ``pos <= n`` always."""
    year = draw(st.integers(min_value=year_min, max_value=year_max))
    month = draw(st.integers(min_value=1, max_value=12))
    n = draw(st.integers(min_value=0, max_value=n_max))
    pos = draw(st.integers(min_value=0, max_value=n))
    period = f"{year:04d}-{month:02d}"
    period_start = f"{year:04d}-{month:02d}-01"
    return {"period": period, "period_start": period_start, "n": n, "pos": pos}


@st.composite
def _state_series(draw):
    """A ``{state: [cell, ...]}`` series as returned by
    ``_build_series(..., resolution='monthly')``, to drive
    :func:`shp._pool_monthly_series`. 1-3 states, each 0-20 cells."""
    n_states = draw(st.integers(min_value=1, max_value=3))
    states = ["CA", "TX", "NY"][:n_states]
    series = {}
    for s in states:
        series[s] = draw(st.lists(_series_cell(), min_size=0, max_size=20))
    return series


_MONTH_LABELS = tuple(f"{m:02d}" for m in range(1, 13))
_QUARTER_LABELS = ("Q1", "Q2", "Q3", "Q4")


def _quarter_of_month(label: str) -> str:
    """Map a month label "01".."12" to its quarter "Q1".."Q4"."""
    return f"Q{(int(label) - 1) // 3 + 1}"


# --------------------------------------------------------------------------- #
# Property 1 — read-only, no input mutation (Req 1.4, 2.1)
# --------------------------------------------------------------------------- #
@settings(max_examples=100, deadline=None)
@given(series=_state_series())
def test_p1_analysis_does_not_mutate_input(series):
    """Feature: s02-seasonal-hazard-patterns, Property 1: Read-only, no input
    mutation.

    For any generated FSIS-style series / pooled record list, running the
    analysis (``_pool_monthly_series`` then ``_analyze_pooled_cells``) leaves the
    input structurally deep-equal to a pre-run copy. The core must read its
    inputs only and never mutate the caller's data (Req 1.4, 2.1).
    """
    series_before = copy.deepcopy(series)

    pooled = shp._pool_monthly_series(series)
    pooled_before = copy.deepcopy(pooled)

    shp._analyze_pooled_cells(pooled)

    # Neither the source series nor the pooled list was mutated by the analysis.
    assert series == series_before, "series input was mutated by the analysis"
    assert pooled == pooled_before, "pooled cell list was mutated by the analysis"


# --------------------------------------------------------------------------- #
# Property 3 — pooled bucket rate + recorded counts (Req 3.1, 3.3)
# --------------------------------------------------------------------------- #
@settings(max_examples=100, deadline=None)
@given(cells=_pooled_cells())
def test_p3_pooled_bucket_rate_and_recorded_counts(cells):
    """Feature: s02-seasonal-hazard-patterns, Property 3: Pooled bucket rate and
    recorded counts.

    Each month bucket's ``n``/``pos`` equal the summed ``n``/``pos`` over that
    calendar month across all years; when available, ``rate == Σpos / Σn``; each
    quarter bucket's ``n``/``pos``/``rate`` equal the pooled sums/rate over its 3
    constituent months; counts are recorded for EVERY bucket regardless of
    availability (Req 3.1, 3.3).
    """
    result = shp._analyze_pooled_cells(cells)
    month_buckets = {b["label"]: b for b in result["month_buckets"]}
    quarter_buckets = {b["label"]: b for b in result["quarter_buckets"]}

    # All 12 months and all 4 quarters are always present.
    assert set(month_buckets) == set(_MONTH_LABELS)
    assert set(quarter_buckets) == set(_QUARTER_LABELS)

    # Independent reference sums straight from the generated cells.
    ref_month_n = {lbl: 0 for lbl in _MONTH_LABELS}
    ref_month_pos = {lbl: 0 for lbl in _MONTH_LABELS}
    for c in cells:
        lbl = f"{int(c['month']):02d}"
        ref_month_n[lbl] += int(c["n"])
        ref_month_pos[lbl] += int(c["pos"])

    for lbl in _MONTH_LABELS:
        b = month_buckets[lbl]
        # Counts recorded for every bucket regardless of availability.
        assert b["n"] == ref_month_n[lbl], f"month {lbl} n"
        assert b["pos"] == ref_month_pos[lbl], f"month {lbl} pos"
        if b["availability_status"] == "available":
            assert b["n"] > 0
            assert b["rate"] == ref_month_pos[lbl] / ref_month_n[lbl], f"month {lbl} rate"

    # Quarter sums/rate equal the pooled sums/rate over the 3 constituent months.
    for q in _QUARTER_LABELS:
        member_months = [lbl for lbl in _MONTH_LABELS if _quarter_of_month(lbl) == q]
        q_n = sum(ref_month_n[m] for m in member_months)
        q_pos = sum(ref_month_pos[m] for m in member_months)
        b = quarter_buckets[q]
        assert b["n"] == q_n, f"quarter {q} n"
        assert b["pos"] == q_pos, f"quarter {q} pos"
        if b["availability_status"] == "available":
            assert b["rate"] == q_pos / q_n, f"quarter {q} rate"


# --------------------------------------------------------------------------- #
# Property 4 — peak over AVAILABLE buckets only (Req 3.4)
# --------------------------------------------------------------------------- #
@settings(max_examples=100, deadline=None)
@given(cells=_pooled_cells())
def test_p4_peak_is_argmax_over_available_only(cells):
    """Feature: s02-seasonal-hazard-patterns, Property 4: Peak_Season is the
    argmax over available buckets only.

    ``peak_month``/``peak_quarter`` is the label of the bucket with the highest
    ``rate`` among AVAILABLE buckets, is never an unavailable bucket even when a
    gated bucket has a higher raw rate, and is ``None`` when no bucket in that view
    is available (Req 3.4).
    """
    result = shp._analyze_pooled_cells(cells)

    for view in ("month_buckets", "quarter_buckets"):
        peak_key = "peak_month" if view == "month_buckets" else "peak_quarter"
        buckets = result[view]
        peak = result[peak_key]
        available = [b for b in buckets if b["availability_status"] == "available"]

        if not available:
            # No bucket available -> peak is None.
            assert peak is None, f"{peak_key} should be None when none available"
            continue

        # The peak names a real, AVAILABLE bucket.
        peak_bucket = next((b for b in buckets if b["label"] == peak), None)
        assert peak_bucket is not None, f"{peak_key} names a nonexistent bucket"
        assert peak_bucket["availability_status"] == "available", (
            f"{peak_key} must never name an unavailable bucket"
        )

        # It is the argmax rate over AVAILABLE buckets.
        max_available_rate = max(b["rate"] for b in available)
        assert peak_bucket["rate"] == max_available_rate, (
            f"{peak_key} is not the argmax rate over available buckets"
        )

        # A gated (unavailable) bucket with a higher raw rate never wins.
        for b in buckets:
            if b["availability_status"] != "available" and b["rate"] is not None:
                assert b["label"] != peak, (
                    f"{peak_key} selected a gated bucket {b['label']}"
                )


# --------------------------------------------------------------------------- #
# Property 5 — trend slope sign + year gate (Req 3.2, 4.4)
# --------------------------------------------------------------------------- #
@settings(max_examples=100, deadline=None)
@given(
    n_years=st.integers(min_value=1, max_value=8),
    start_year=st.integers(min_value=2000, max_value=2015),
    base=st.floats(min_value=0.0, max_value=0.5),
    step=st.floats(min_value=0.001, max_value=0.1),
    direction=st.sampled_from(("increasing", "decreasing", "constant")),
)
def test_p5_trend_slope_sign_and_year_gate(n_years, start_year, base, step, direction):
    """Feature: s02-seasonal-hazard-patterns, Property 5: Trend slope sign and
    year gate.

    With >= MIN_YEARS_FOR_TREND distinct years, a strictly increasing annual
    series yields slope > 0, strictly decreasing yields slope < 0, and a constant
    series yields slope == 0 (float tolerance). With fewer than
    MIN_YEARS_FOR_TREND distinct years the trend is unavailable with a null slope
    and ``years_used`` records the years found (Req 3.2, 4.4).
    """
    years = [start_year + i for i in range(n_years)]
    if direction == "increasing":
        annual = {y: base + step * i for i, y in enumerate(years)}
    elif direction == "decreasing":
        annual = {y: base + step * (n_years - 1 - i) for i, y in enumerate(years)}
    else:  # constant
        annual = {y: base for y in years}

    slope, years_used = shp._trend_slope(annual)
    # years_used always records exactly the distinct years found, sorted.
    assert years_used == sorted(years)

    if n_years < shp.MIN_YEARS_FOR_TREND:
        # Below the year gate: unavailable with a null slope.
        assert slope is None, "slope must be None below the year gate"
    else:
        assert slope is not None, "slope must be computed at/above the year gate"
        tol = 1e-9
        if direction == "increasing":
            assert slope > tol, f"increasing series slope not > 0: {slope}"
        elif direction == "decreasing":
            assert slope < -tol, f"decreasing series slope not < 0: {slope}"
        else:
            assert abs(slope) <= tol, f"constant series slope not ~0: {slope}"

    # The _build_trend wrapper mirrors the gate end-to-end over real cells.
    cells = []
    for i, y in enumerate(years):
        # one month cell per year carrying the target annual rate (pos/n == rate)
        n = 1000
        pos = round(annual[y] * n)
        cells.append({"year": y, "month": (i % 12) + 1, "n": n, "pos": pos})
    trend = shp._build_trend(cells)
    if n_years < shp.MIN_YEARS_FOR_TREND:
        assert trend["availability_status"] == "unavailable"
        assert trend["slope"] is None
        assert trend["years_used"] == sorted(years)
        assert trend["unavailable_reason"]
    else:
        assert trend["availability_status"] == "available"
        assert trend["slope"] is not None


# --------------------------------------------------------------------------- #
# Property 6 — gate availability in both directions (Req 4.2, 4.3)
# --------------------------------------------------------------------------- #
@settings(max_examples=100, deadline=None)
@given(cells=_pooled_cells(min_size=1))
def test_p6_gate_availability_both_directions(cells):
    """Feature: s02-seasonal-hazard-patterns, Property 6: Gate availability in
    both directions.

    A bucket with pooled ``n >= gate`` is "available" with a non-null ``rate``; a
    bucket with pooled ``n < gate`` is "unavailable" with a non-empty
    ``unavailable_reason`` naming the gate, and its recorded ``n`` equals the
    actual count (Req 4.2, 4.3).
    """
    result = shp._analyze_pooled_cells(cells)

    for b in result["month_buckets"]:
        gate = shp.MIN_BUCKET_SAMPLES_MONTH
        if b["n"] >= gate:
            assert b["availability_status"] == "available", f"month {b['label']}"
            assert b["rate"] is not None
        else:
            assert b["availability_status"] == "unavailable", f"month {b['label']}"
            assert b["rate"] is None
            assert b["unavailable_reason"]
            assert "month" in b["unavailable_reason"]
            assert str(gate) in b["unavailable_reason"]
            assert str(b["n"]) in b["unavailable_reason"]

    for b in result["quarter_buckets"]:
        gate = shp.MIN_BUCKET_SAMPLES_QUARTER
        if b["n"] >= gate:
            assert b["availability_status"] == "available", f"quarter {b['label']}"
            assert b["rate"] is not None
        else:
            assert b["availability_status"] == "unavailable", f"quarter {b['label']}"
            assert b["rate"] is None
            assert b["unavailable_reason"]
            assert "quarter" in b["unavailable_reason"]
            assert str(gate) in b["unavailable_reason"]
            assert str(b["n"]) in b["unavailable_reason"]


# --------------------------------------------------------------------------- #
# Property 7 — no fabricated fills for unavailable statistics (Req 4.5, 6.4)
# --------------------------------------------------------------------------- #
@settings(max_examples=100, deadline=None)
@given(cells=_pooled_cells())
def test_p7_no_fabricated_fills_for_unavailable(cells):
    """Feature: s02-seasonal-hazard-patterns, Property 7: No fabricated fills for
    unavailable statistics.

    Every bucket or trend whose ``availability_status == "unavailable"`` has null
    ``rate``/``ci_low``/``ci_high``/``seasonal_index`` (or null ``trend_slope``) —
    no interpolated, estimated, carried-forward, or placeholder value appears
    anywhere (Req 4.5, 6.4).
    """
    result = shp._analyze_pooled_cells(cells)

    for view in ("month_buckets", "quarter_buckets"):
        for b in result[view]:
            if b["availability_status"] == "unavailable":
                assert b["rate"] is None, f"{view} {b['label']} rate not null"
                assert b["ci_low"] is None, f"{view} {b['label']} ci_low not null"
                assert b["ci_high"] is None, f"{view} {b['label']} ci_high not null"
                assert b["seasonal_index"] is None, (
                    f"{view} {b['label']} seasonal_index not null"
                )

    trend = result["trend"]
    if trend["availability_status"] == "unavailable":
        assert trend["slope"] is None, "unavailable trend slope not null"


# --------------------------------------------------------------------------- #
# Property 8 — every emitted value is OBSERVED-honest (Req 5.1, 6.4)
# --------------------------------------------------------------------------- #
# Status-layer resolution (see module docstring): the cache carries no per-row
# `status` field — the OBSERVED tag is attached by the exporter and asserted at
# the record level by the exporter test (Task 7.1). At the analysis layer we
# assert the honest equivalent: the module produces NO forecast/predicted/
# simulated content, and every reported value is derived from the observed counts.
_FORECAST_TOKENS = (
    "forecast", "predicted", "prediction", "simulated", "future",
    "estimate_fill", "imputed", "extrapolat", "placeholder",
)


def _walk_strings(obj):
    """Yield every string appearing as a key or a string value anywhere in obj."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str):
                yield k
            yield from _walk_strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _walk_strings(v)
    elif isinstance(obj, str):
        yield obj


@settings(max_examples=100, deadline=None)
@given(cells=_pooled_cells())
def test_p8_every_value_is_observed_honest(cells):
    """Feature: s02-seasonal-hazard-patterns, Property 8: Every record is
    OBSERVED.

    The analysis layer carries no per-row ``status`` field (the OBSERVED tag is an
    exporter concern covered by Task 7.1's record-level test). So here we assert
    the honest equivalent at the layer that exists: the module emits NO
    forecast/predicted/simulated content anywhere, and every reported value is
    derived purely from the observed ``pos``/``n`` counts — pooled rate = Σpos/Σn,
    Wilson CI on those counts, seasonal_index = rate/overall_rate, and the trend
    slope is an OLS fit over observed annual rates (Req 5.1, 6.4).
    """
    result = shp._analyze_pooled_cells(cells)

    # (a) No fabrication/forecast token anywhere in the analysis output.
    for s in _walk_strings(result):
        low = s.lower()
        for tok in _FORECAST_TOKENS:
            assert tok not in low, f"forecast/fabrication token {tok!r} in output: {s!r}"

    overall = result["overall_rate"]
    # (b) Every AVAILABLE value is reproducible from the observed counts alone.
    for view in ("month_buckets", "quarter_buckets"):
        for b in result[view]:
            if b["availability_status"] != "available":
                continue
            # rate is exactly the pooled positivity of the recorded counts.
            assert b["rate"] == b["pos"] / b["n"]
            # seasonal_index is exactly rate/overall (or None when overall is 0).
            if overall:
                assert b["seasonal_index"] == b["rate"] / overall
            else:
                assert b["seasonal_index"] is None
            # CI bounds are present and bounded in [0, 1] — derived from the counts.
            if b["ci_low"] is not None:
                assert 0.0 <= b["ci_low"] <= 1.0
            if b["ci_high"] is not None:
                assert 0.0 <= b["ci_high"] <= 1.0


# --------------------------------------------------------------------------- #
# Property 9 — deterministic, reproducible (Req 8.1, 8.3)
# --------------------------------------------------------------------------- #
@settings(max_examples=100, deadline=None)
@given(cells=_pooled_cells())
def test_p9_analysis_is_deterministic(cells):
    """Feature: s02-seasonal-hazard-patterns, Property 9: Deterministic,
    reproducible.

    Two independent runs of the pure analysis over identical generated inputs
    produce equal results. Tested at the pure-function level
    (``_analyze_pooled_cells`` on identical inputs -> equal dicts) so no real FSIS
    data is needed; the byte-identical cache JSON is additionally exercised by
    :func:`test_p9_compute_cache_is_byte_identical` via an injected record source
    and a temp CACHE_PATH (Req 8.1, 8.3).
    """
    first = shp._analyze_pooled_cells(cells)
    # A separate deep copy of the input guarantees run two shares no state.
    second = shp._analyze_pooled_cells(copy.deepcopy(cells))
    assert first == second


def test_p9_compute_cache_is_byte_identical(tmp_path):
    """Feature: s02-seasonal-hazard-patterns, Property 9: Deterministic,
    reproducible (full compute, byte-identical cache).

    One fixed input demonstrates the determinism property fully, so this is a plain
    example test (NOT ``@given``): Hypothesis forbids a ``@given`` test from
    using a function-scoped fixture like pytest's ``monkeypatch`` (it would not
    reset between generated inputs), so we patch with ``unittest.mock.patch``
    context managers. The pure-function determinism over RANDOM inputs is
    already covered by :func:`test_p9_analysis_is_deterministic` (Req 8.1, 8.3).

    Records are injected by patching the siblings the compute function calls
    (``_iter_raw_records`` -> empty, ``_build_series`` -> a fixed generated
    series) so every pathogen pools the SAME series, and ``CACHE_PATH``/
    ``INTERIM_DIR`` point at ``tmp_path`` so the real ``data/interim`` cache is
    never clobbered (Req 8.1, 8.3).
    """
    from unittest import mock

    # A fixed, non-trivial national monthly series: two states, several months
    # across three years so the trend gate is satisfied and buckets are mixed
    # available/unavailable. Deterministic by construction.
    series = {
        "CA": [
            {"period": f"{y:04d}-{m:02d}", "period_start": f"{y:04d}-{m:02d}-01",
             "n": n, "pos": pos}
            for (y, m, n, pos) in [
                (2021, 1, 100, 12), (2021, 7, 10, 1), (2022, 1, 90, 8),
                (2022, 7, 80, 9), (2023, 1, 70, 5), (2023, 7, 60, 7),
            ]
        ],
        "TX": [
            {"period": f"{y:04d}-{m:02d}", "period_start": f"{y:04d}-{m:02d}-01",
             "n": n, "pos": pos}
            for (y, m, n, pos) in [
                (2021, 4, 50, 3), (2022, 4, 55, 4), (2023, 4, 40, 2),
            ]
        ],
    }
    cache_file = tmp_path / "s02_seasonal_hazard_patterns.json"

    with mock.patch.object(shp, "_iter_raw_records", lambda _dir: iter(())), \
         mock.patch.object(
             shp, "_build_series",
             lambda _records, _col, resolution="monthly": (copy.deepcopy(series), {})), \
         mock.patch.object(shp, "CACHE_PATH", cache_file), \
         mock.patch.object(shp, "INTERIM_DIR", tmp_path):
        first = shp.compute_seasonal_hazard_patterns()
        first_bytes = cache_file.read_bytes()
        second = shp.compute_seasonal_hazard_patterns()
        second_bytes = cache_file.read_bytes()

    assert first == second
    assert first_bytes == second_bytes


# --------------------------------------------------------------------------- #
# Task 5.2 — Python <-> TypeScript field-name parity (Req 6.5)
# --------------------------------------------------------------------------- #
# Mirrors ``tests/test_county_community_impact.py``'s
# ``test_p13_county_community_impact_python_ts_parity`` and the sibling
# ``tests/test_facility_map.py`` parity test: each test file carries its OWN copy
# of the simple brace-body ``_ts_interface_fields`` parser (we copy it here rather
# than importing across test modules, as the siblings do). The parity contract is
# key-set equality between the Python ``SeasonalHazardRecord`` TypedDict and the
# mirrored TypeScript ``SeasonalHazardRecord`` interface in
# ``web/src/types/artifacts.ts`` (27 fields each).

import re
import typing
from pathlib import Path

from src.artifacts.schemas import SeasonalHazardRecord

_ARTIFACTS_TS = Path(__file__).resolve().parents[1] / "web" / "src" / "types" / "artifacts.ts"


def _ts_interface_fields(ts_text: str, interface_name: str) -> set[str]:
    """Parse the field names of a TypeScript interface body (mirror of the
    ``test_county_community_impact.py`` / ``test_facility_map.py`` helper).
    Deliberately simple: the parity contract is key-set equality, so only the
    identifiers are needed."""
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


def test_seasonal_hazard_record_python_ts_parity():
    """Feature: s02-seasonal-hazard-patterns, Property 13-equivalent: Python <->
    TypeScript field-name parity.

    The Python ``SeasonalHazardRecord`` TypedDict and the mirrored TypeScript
    ``SeasonalHazardRecord`` interface in ``web/src/types/artifacts.ts`` carry the
    IDENTICAL set of 27 snake_case field names, so the web tab reads exactly the
    fields the exporter writes with no drift (Req 6.5).
    """
    ts_text = _ARTIFACTS_TS.read_text(encoding="utf-8")
    py_keys = set(typing.get_type_hints(SeasonalHazardRecord).keys())
    ts_keys = _ts_interface_fields(ts_text, "SeasonalHazardRecord")
    assert py_keys == ts_keys, (
        f"SeasonalHazardRecord parity mismatch: "
        f"py-only={py_keys - ts_keys}, ts-only={ts_keys - py_keys}")
    assert len(py_keys) == 27


# --------------------------------------------------------------------------- #
# Task 7.1 — exporter builder validation + forbidden-field guard (Req 6.2, 6.3)
# --------------------------------------------------------------------------- #
# Mirrors ``tests/test_county_community_impact.py``'s exporter smoke tests
# (``test_exporter_rows_validate_and_carry_weight_sensitivity`` and
# ``test_exporter_missing_cache_degrades_to_unavailable``) and its ``_BANNED``
# forbidden-field guard. The S02 builder does
# ``from src.analysis.seasonal_hazard_patterns import load_cache`` INSIDE the
# function, so the cache is made present/absent by monkeypatching
# ``src.analysis.seasonal_hazard_patterns.load_cache`` (i.e. ``shp.load_cache``) —
# no filesystem cache is read and the real ``data/interim`` artifact is never
# touched.

from src.artifacts import exporter as _exporter
from src.artifacts.exporter import SchemaValidationError
from src.artifacts.schemas import SeasonalHazardRecord as _SeasonalHazardRecord

# The forbidden fabrication tokens the S02 builder's inline guard scans row KEYS
# for (mirrors ``build_seasonal_hazard_patterns``'s ``_banned`` tuple and the S07
# ``_BANNED`` set). Field NAMES — never values — are checked, case-insensitively.
_BANNED = (
    "forecast", "predicted", "prediction", "contaminat", "infection",
    "future", "illness_estimate", "predicted_case", "human_case",
)


def _s02_fixture_cache():
    """A small, hand-built S02 cache dict (the shape
    ``compute_seasonal_hazard_patterns`` writes) with ONE pathogen. It carries a
    couple of month buckets (one available with ``n >= 30``, one unavailable with
    ``n < 30``), the 4 quarter buckets, an available trend block, and
    ``peak_month``/``peak_quarter``. Peaks point at the AVAILABLE buckets so the
    ``is_peak`` flag lands on a reported row (Req 3.4)."""
    return {
        "module_id": "S02",
        "method_version": "s02.v1",
        "generated_at": "2024-01-01T00:00:00Z",
        "resolution": "monthly",
        "aggregation": "pooled_positivity",
        "ci_method": "wilson_95",
        "trend_method": "ordinal_year_ols_slope",
        "min_bucket_samples_month": 30,
        "min_bucket_samples_quarter": 30,
        "min_years_for_trend": 3,
        "pathogens": {
            "Salmonella": {
                "pathogen": "Salmonella",
                "commodity": "raw_poultry",
                "fsis_input_id": "fsis:raw_poultry:salmonella",
                "periods_read": ["2021-01", "2021-07", "2022-01", "2022-07",
                                 "2023-01", "2023-07"],
                "availability_status": "available",
                "unavailable_reason": None,
                "overall_rate": 0.1,
                "month_buckets": [
                    {
                        "label": "01", "n": 100, "pos": 12, "rate": 0.12,
                        "ci_low": 0.07, "ci_high": 0.2, "seasonal_index": 1.2,
                        "availability_status": "available", "unavailable_reason": None,
                    },
                    {
                        "label": "07", "n": 10, "pos": 1, "rate": None,
                        "ci_low": None, "ci_high": None, "seasonal_index": None,
                        "availability_status": "unavailable",
                        "unavailable_reason": "month bucket has 10 samples (< 30 minimum)",
                    },
                ],
                "quarter_buckets": [
                    {
                        "label": "Q1", "n": 120, "pos": 14, "rate": 0.1167,
                        "ci_low": 0.07, "ci_high": 0.19, "seasonal_index": 1.167,
                        "availability_status": "available", "unavailable_reason": None,
                    },
                    {
                        "label": "Q2", "n": 110, "pos": 8, "rate": 0.0727,
                        "ci_low": 0.037, "ci_high": 0.137, "seasonal_index": 0.727,
                        "availability_status": "available", "unavailable_reason": None,
                    },
                    {
                        "label": "Q3", "n": 15, "pos": 2, "rate": None,
                        "ci_low": None, "ci_high": None, "seasonal_index": None,
                        "availability_status": "unavailable",
                        "unavailable_reason": "quarter bucket has 15 samples (< 30 minimum)",
                    },
                    {
                        "label": "Q4", "n": 90, "pos": 9, "rate": 0.1,
                        "ci_low": 0.053, "ci_high": 0.18, "seasonal_index": 1.0,
                        "availability_status": "available", "unavailable_reason": None,
                    },
                ],
                "trend": {
                    "method": "ordinal_year_ols_slope",
                    "slope": 0.015,
                    "years_used": [2021, 2022, 2023],
                    "availability_status": "available",
                    "unavailable_reason": None,
                },
                "peak_month": "01",
                "peak_quarter": "Q1",
            },
        },
    }


def test_exporter_rows_validate_and_carry_observed_pattern(monkeypatch):
    """Req 6.2: ``build_seasonal_hazard_patterns()`` over a present (monkeypatched)
    S02 cache returns rows that pass ``validate_payload`` against
    ``SeasonalHazardRecord``, every row is ``status == "OBSERVED"`` with the
    constant ``pattern_label == "historical seasonal pattern"``, available buckets
    carry a non-null ``rate`` while unavailable buckets carry a null ``rate`` + a
    reason, ``is_peak`` is True exactly for the per-view peak bucket, and the
    pathogen's trend fields are repeated across its rows."""
    cache = _s02_fixture_cache()
    monkeypatch.setattr(shp, "load_cache", lambda: cache)

    rows = _exporter.build_seasonal_hazard_patterns()
    assert rows
    # Does not raise -> the builder output conforms to the TypedDict contract.
    _exporter.validate_payload(
        rows, _SeasonalHazardRecord, label="seasonal_hazard_patterns")

    for r in rows:
        assert r["status"] == "OBSERVED"
        assert r["pattern_label"] == "historical seasonal pattern"
        assert r["module_id"] == "S02"

    # Availability honesty: available -> non-null rate; unavailable -> null rate
    # with a reason, never a fabricated value (Req 6.2).
    for r in rows:
        if r["availability_status"] == "available":
            assert r["rate"] is not None
        else:
            assert r["rate"] is None
            assert r["ci_low"] is None and r["ci_high"] is None
            assert r["seasonal_index"] is None
            assert r["unavailable_reason"]

    # is_peak is True exactly for the view's peak bucket label (and only an
    # AVAILABLE bucket can be the peak; Req 3.4).
    peaks = {"month": "01", "quarter": "Q1"}
    for r in rows:
        expected_peak = (r["bucket_label"] == peaks[r["view"]])
        assert r["is_peak"] is expected_peak
        if r["is_peak"]:
            assert r["availability_status"] == "available"

    # Trend fields are repeated verbatim across every row of the pathogen.
    sal_rows = [r for r in rows if r["pathogen"] == "Salmonella"]
    assert sal_rows
    assert {r["trend_slope"] for r in sal_rows} == {sal_rows[0]["trend_slope"]}
    assert all(r["trend_years_used"] == [2021, 2022, 2023] for r in sal_rows)
    assert all(r["trend_availability_status"] == "available" for r in sal_rows)
    assert all(r["overall_rate"] == sal_rows[0]["overall_rate"] for r in sal_rows)

    # Forbidden-field guard holds on the real (clean) rows: no banned token in any
    # row KEY (mirrors the S07 exporter smoke's trailing _BANNED assertion).
    for r in rows:
        for k in r.keys():
            assert not any(b in k.lower() for b in _BANNED), f"banned field: {k}"


def test_exporter_missing_cache_degrades_to_unavailable(monkeypatch):
    """Req 6.2: a missing S02 cache (``load_cache`` returns ``None``) yields one
    explicit per-pathogen unavailable sentinel row (``view == "quarter"``,
    ``bucket_label == "(all)"``, a run-the-build reason) WITHOUT raising, and the
    sentinel rows still pass ``validate_payload``. Mirrors the S07 cache-missing
    exporter path."""
    monkeypatch.setattr(shp, "load_cache", lambda: None)

    rows = _exporter.build_seasonal_hazard_patterns()
    _exporter.validate_payload(
        rows, _SeasonalHazardRecord, label="seasonal_hazard_patterns")

    # One sentinel per pathogen the whole export is built on.
    assert {r["pathogen"] for r in rows} == {"Salmonella", "Listeria", "STEC"}
    assert len(rows) == 3
    for r in rows:
        assert r["availability_status"] == "unavailable"
        assert r["view"] == "quarter"
        assert r["bucket_label"] == "(all)"
        assert r["unavailable_reason"]
        assert "run" in r["unavailable_reason"].lower()
        assert r["status"] == "OBSERVED"
        assert r["rate"] is None


def test_exporter_forbidden_field_guard_rejects_banned_token(monkeypatch):
    """Req 6.3: the inline forbidden-field guard rejects a row whose KEY carries a
    banned fabrication token and writes nothing (raises ``SchemaValidationError``).

    The 27 real ``SeasonalHazardRecord`` field names are clean, so the guard never
    fires on real rows. To exercise the guard — matching the S07 ``_BANNED``
    row-key scan technique — we inject a banned-named KEY (``forecast_rate``) into
    every row the builder constructs by monkeypatching the record factory the
    builder calls (``exporter.SeasonalHazardRecord``, a ``TypedDict`` that is a
    plain ``dict`` at runtime) so the banned key propagates into the rows and the
    builder's own inline ``_banned`` token-scan trips."""
    cache = _s02_fixture_cache()
    monkeypatch.setattr(shp, "load_cache", lambda: cache)

    def _poisoned_record(**fields):
        # Build the real record, then inject a banned-named field so the guard's
        # row-KEY scan (never a value scan) finds a forbidden token.
        row = dict(fields)
        row["forecast_rate"] = 0.42
        return row

    monkeypatch.setattr(_exporter, "SeasonalHazardRecord", _poisoned_record)

    raised = False
    try:
        _exporter.build_seasonal_hazard_patterns()
    except SchemaValidationError as exc:
        raised = True
        msg = str(exc).lower()
        assert "forecast" in msg
        assert "forecast_rate" in msg
    assert raised, (
        "expected build_seasonal_hazard_patterns to raise SchemaValidationError "
        "on a row key carrying a banned token")
