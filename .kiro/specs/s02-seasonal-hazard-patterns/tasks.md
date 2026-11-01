# Implementation Plan: S02 — Seasonal / Temporal Hazard Patterns

## Overview

This plan converts the approved S02 design into incremental coding tasks for an **additive** module on the existing VulneraSafe AI platform. S02 adds one new analysis source file, one new cache, one new artifact (schema + TS mirror + exporter builder), and one new web tab — editing only `exporter.py`, `schemas.py`, `artifacts.ts`, and `App.tsx` by addition. No existing module cache, source file, or web tab is modified.

Implementation languages are fixed by the design: **Python** for the analysis/exporter layer and **TypeScript/React** for the web tab. The design uses concrete Python/TS (no pseudocode), so no language-selection step is required.

Tasks are ordered so each builds on the prior with no big-bang integration: analysis core → cache/build entry point → core honesty/gating tests → schema TypedDict → TS mirror + parity → exporter builder + file-count bump → exporter tests → web panel → App wiring → web component test. The analysis functions are pure given an injected record list, the exporter builder reads a cache from a temp path, and the web component reads a fixture artifact — so every unit is testable in isolation.

Property tests map to the nine Correctness Properties in `design.md` and use **Hypothesis** (Python) at ≥100 iterations, tagged `Feature: s02-seasonal-hazard-patterns, Property N: <text>`. The web tab uses **vitest + Testing Library**. Core honesty/gating/peak/trend/determinism property tests are **first-class (not optional)** because honesty is the project's hard constraint; only genuinely redundant or extra tests are marked optional with `*`.

## Tasks

- [x] 1. Implement the S02 analysis core
  - Create `src/analysis/seasonal_hazard_patterns.py` with module identity constants: `MODULE_ID = "S02"`, `METHOD_VERSION = "s02.v1"`, `CACHE_PATH = data/interim/s02_seasonal_hazard_patterns.json`, and gate/method constants `MIN_BUCKET_SAMPLES_MONTH = 30`, `MIN_BUCKET_SAMPLES_QUARTER = 30`, `MIN_YEARS_FOR_TREND = 3`, plus method strings `resolution="monthly"`, `aggregation="pooled_positivity"`, `ci_method="wilson_95"`, `trend_method="ordinal_year_ols_slope"`
  - Import read-only from siblings: `_iter_raw_records`, `_build_series`, `_parse_date`, `_period_label`, `_period_start`, `_PATHOGEN_CONFIG` from `src.analysis.emerging_risk`, and `wilson_ci` from `src.analysis.program_product`; never mutate their inputs or outputs
  - Implement `_pool_monthly_series(series)` flattening `{state: [cells]}` from `_build_series(..., "monthly")` into one national list of `(year, month, n, pos)`
  - Implement `_bucket_rate(cells, key_fn)` grouping by calendar month (1–12) or quarter (Q1–Q4, month → `(m-1)//3 + 1`), summing `n`/`pos` and computing pooled `rate = Σpos/Σn` with `wilson_ci(pos, n)` CI; record `n`/`pos` for every bucket regardless of availability
  - Implement `_trend_slope(annual_rates)` as a closed-form ordinal-year OLS slope over pooled annual positivity; implement seasonal index per bucket (`bucket_rate / overall_rate`, skipped when `overall_rate == 0`)
  - Implement peak selection as argmax `rate` over available buckets only (month and quarter independently), `null` when no bucket in a view is available
  - Implement the gating logic: a bucket/trend passing its gate is `availability_status="available"`; below gate is `availability_status="unavailable"` with an `unavailable_reason` naming the gate and the actual count, and no computed value; never interpolate, estimate, carry-forward, or substitute a placeholder
  - _Requirements: 1.1, 1.2, 2.1, 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 4.4, 4.5_
  - _Design: Decomposition Method; Minimum-Sample Gating; Components and Interfaces_

- [x] 2. Implement the cache build entry point and tolerant reader
  - Add `compute_seasonal_hazard_patterns(*, round_to=6)` to `src/analysis/seasonal_hazard_patterns.py` that orchestrates all three pathogens (Salmonella/raw_poultry, Listeria/rte, STEC/raw_beef from `_PATHOGEN_CONFIG`), building month buckets (all 12), quarter buckets (all 4), the trend block, and `peak_month`/`peak_quarter` per pathogen
  - For a pathogen whose series fails to build, emit a pathogen-level `availability_status="unavailable"` block with a missing-input `unavailable_reason` and continue with the other pathogens
  - Record per-pathogen `fsis_input_id`, `periods_read` (the distinct `YYYY-MM` labels read), and `overall_rate`; record top-level `module_id`, `method_version`, `generated_at`, `resolution`, `aggregation`, `ci_method`, `trend_method`, and the three gate constants
  - Write the cache to `data/interim/s02_seasonal_hazard_patterns.json` with `json.dumps(..., indent=2, sort_keys=True)` and fixed float rounding so repeated runs over identical inputs are byte-identical; add a `__main__` entry point that calls `compute_seasonal_hazard_patterns()`
  - Add `load_cache()` with a tolerant read (`(OSError, ValueError) -> None`), mirroring the sibling `load_cache`
  - _Requirements: 2.3, 2.4, 8.1, 8.2, 8.3_
  - _Design: Cache Schema; Error Handling_

- [x] 3. Write the core honesty, gating, peak, trend, and determinism tests
  - Create `tests/test_seasonal_hazard_patterns.py` implementing all nine Correctness Properties as single Hypothesis tests at ≥100 iterations over generated monthly cells, each tagged `Feature: s02-seasonal-hazard-patterns, Property N: <text>`
  - [x] 3.1 Implement core honesty/gating property tests (not optional — honesty is the hard constraint)
    - **Property 1: Read-only, no input mutation** — injected record list deep-equals a pre-run copy — **Validates: Requirements 1.4, 2.1**
    - **Property 3: Pooled bucket rate and recorded counts** — bucket `n`/`pos` equal pooled sums; `rate == Σpos/Σn` when available; counts recorded even when unavailable — **Validates: Requirements 3.1, 3.3**
    - **Property 4: Peak_Season is the argmax over available buckets only** — a gated higher-rate bucket never wins; `null` when none available — **Validates: Requirements 3.4**
    - **Property 5: Trend slope sign and year gate** — increasing → slope > 0, decreasing → slope < 0, constant → slope == 0; below the year gate → unavailable with null slope and recorded years — **Validates: Requirements 3.2, 4.4**
    - **Property 6: Gate availability in both directions** — `n >= gate` → available with non-null rate; `n < gate` → unavailable with reason naming the gate and actual count — **Validates: Requirements 4.2, 4.3**
    - **Property 7: No fabricated fills for unavailable statistics** — every unavailable bucket/trend has null rate/ci/seasonal_index/slope — **Validates: Requirements 4.5, 6.4**
    - **Property 8: Every record is OBSERVED** — every emitted record carries `status == "OBSERVED"` — **Validates: Requirements 5.1, 6.4**
    - **Property 9: Deterministic, reproducible cache** — two runs over identical inputs produce byte-identical cache JSON — **Validates: Requirements 8.1, 8.3**
    - _Design: Correctness Properties; Testing Strategy_
  - [ ]* 3.2 Implement the audit-exactness property test
    - **Property 2: periods_read is exactly the months present** — `periods_read` equals the set of distinct `YYYY-MM` labels in the pathogen's input — **Validates: Requirements 2.3**
  - [x] 3.3 Write example tests for guardrail copy and no-mutation
    - Assert `pattern_label == "historical seasonal pattern"` on emitted content (Req 5.2); assert the injected record list is unmodified after a build (no-mutation example complementing Property 1)
    - _Requirements: 5.2, 1.4_
    - _Design: Honesty / Guardrails Recap_

- [x] 4. Add the SeasonalHazardRecord TypedDict to the Python schema
  - Append a new `SeasonalHazardRecord` TypedDict to `src/artifacts/schemas.py` (addition only — no existing TypedDict edited) with the 27 fields from the design Data Models table: `artifact_version`, `module_id`, `method_version`, `pathogen`, `commodity`, `view`, `bucket_label`, `sample_n`, `positive_n`, `rate`, `ci_low`, `ci_high`, `ci_method`, `seasonal_index`, `overall_rate`, `is_peak`, `trend_method`, `trend_slope`, `trend_years_used`, `trend_availability_status`, `trend_unavailable_reason`, `pattern_label`, `status`, `availability_status`, `unavailable_reason`, `periods_read_count`, `generated_at`
  - Tag every value-bearing field OBSERVED via `status: StatusTag` (always "OBSERVED"); carry `availability_status`/`unavailable_reason` per statistic; use `Optional[...]` for the null-when-unavailable fields; reuse the shared `StatusTag` union
  - Ensure no field name contains a banned fabrication token (`forecast`, `predicted`, `prediction`, `contaminat`, `infection`, `illness_estimate`, `future`)
  - _Requirements: 6.1, 6.4_
  - _Design: Data Models — Artifact TypedDict + TS Type_

- [x] 5. Add the TS mirror interface and the Python↔TS parity test
  - [x] 5.1 Add the mirrored SeasonalHazardRecord interface to the web types
    - Append a `SeasonalHazardRecord` interface to `web/src/types/artifacts.ts` with identical `snake_case` field names and mirrored types (`number | null`, `string | null`, `boolean`, `number[]`), reusing the shared `StatusTag` union — addition only
    - _Requirements: 6.1, 6.5_
    - _Design: Web Tab; Data Models_
  - [x] 5.2 Write the Python↔TS parity test
    - In `tests/test_seasonal_hazard_patterns.py`, mirror `test_p13_county_community_impact_python_ts_parity` using the existing `_ts_interface_fields` helper: assert `set(typing.get_type_hints(SeasonalHazardRecord)) == _ts_interface_fields(artifacts_ts, "SeasonalHazardRecord")` and `len == 27`, reporting any field present on only one side
    - _Requirements: 6.5_
    - _Design: Testing Strategy — Parity test_

- [x] 6. Add the exporter builder and register it
  - Add `build_seasonal_hazard_patterns()` to `src/artifacts/exporter.py`, mirroring `build_county_community_impact()`: `from src.analysis.seasonal_hazard_patterns import load_cache, METHOD_VERSION` and read the cache; when the cache is absent emit one `availability_status="unavailable"` sentinel row per pathogen (`view="quarter"`, `bucket_label="(all)"`) with a run-the-build reason and never raise (mirrors the S07 cache-missing path)
  - Shape one `SeasonalHazardRecord` per `(pathogen, view, bucket)` with `_round(...)` on every float, `status="OBSERVED"`, `pattern_label="historical seasonal pattern"`, the pathogen's trend/peak fields repeated on each row, and `is_peak = (bucket_label == peak_month)` for month rows / `(bucket_label == peak_quarter)` for quarter rows; sort deterministically by `(pathogen, view, bucket_label)`
  - Run the forbidden-field guard over row keys using the existing `_banned` token-scan, extended with `forecast`, `predicted`, `prediction`, `contaminat`, `infection`, `future`; raise `SchemaValidationError` and write nothing on a hit
  - Register in `build_all_artifacts()`: call the builder, run `validate_payload(seasonal_hazard_patterns, SeasonalHazardRecord, label="seasonal_hazard_patterns")`, and add `"seasonal_hazard_patterns": seasonal_hazard_patterns` to the returned payload dict (not in `_CSV_ARTIFACTS`)
  - _Requirements: 6.2, 6.3, 6.4_
  - _Design: Exporter Integration; Error Handling_

- [x] 7. Add exporter tests and bump the written-file-count assertion
  - [x] 7.1 Write the exporter builder validation and guard tests
    - `build_seasonal_hazard_patterns()` output passes `validate_payload(..., SeasonalHazardRecord, label="seasonal_hazard_patterns")`; the cache-missing path yields per-pathogen unavailable sentinel rows without raising
    - Forbidden-field guard: injecting a row key containing a banned token raises `SchemaValidationError` and writes nothing
    - _Requirements: 6.2, 6.3_
    - _Design: Testing Strategy — Exporter test_
  - [x] 7.2 Bump the exporter written-file-count assertion from 28 to 29
    - Locate the exporter test asserting the written-file / artifact count and change the expected value from 28 to 29 to account for the one new `seasonal_hazard_patterns.json` artifact (not a CSV companion)
    - _Requirements: 6.2_
    - _Design: Exporter Integration — File count_

- [x] 8. Build the SeasonalHazard web panel
  - Create `web/src/components/panels/SeasonalHazard.tsx` — charts and tables only, NO map/maplibre — using the existing navy/teal shells (`PanelShell`, `StatusTag`, `EmptyState`, `ArtifactBody`) and reading the `seasonal_hazard_patterns` artifact
  - Pathogen selector: three buttons Salmonella / Listeria / STEC (`data-testid="pathogen-selector"`); panel root `data-testid="seasonal-hazard"`
  - Month-of-year chart (`data-testid="month-chart"`): 12 inline SVG/flex bars of positivity with Wilson CI whiskers; gated months render a "not available" marker carrying the reason. Quarter chart (`data-testid="quarter-chart"`): Q1–Q4 with CI and the same unavailable treatment
  - Trend readout (`data-testid="trend-readout"`): plain-language sign + magnitude, or an explicit unavailable note with the reason. Peak Season callout (`data-testid="peak-season"`): labeled "historical seasonal pattern", never "forecast"/"prediction"/"risk forecast". Reusable unavailable indicator (`data-testid="unavailable-note"`) renders `unavailable_reason` in place of a value, never a blank or fabricated number
  - On missing/invalid artifact, render `ArtifactBody`'s error state identifying `seasonal_hazard_patterns` and no fabricated content
  - _Requirements: 5.4, 7.2, 7.3, 7.4, 7.5_
  - _Design: Web Tab_

- [x] 9. Wire the new Seasonal Patterns tab into the app
  - Edit `web/src/App.tsx` additively: extend the `Tab` union with `"seasonal"`, add `{ id: "seasonal", label: "Seasonal Patterns" }` to the `tabs` array, import `SeasonalHazard`, and add a `tab === "seasonal" ? <SeasonalHazard /> : …` branch in `AppBody` — all existing tabs, panels, and their tests untouched
  - _Requirements: 7.1_
  - _Design: Web Tab — App wiring_

- [x] 10. Write the SeasonalHazard web component test
  - Create `web/src/components/panels/__tests__/SeasonalHazard.test.tsx` reading a fixture artifact: renders available buckets with their rate/CI; renders the `unavailable-note` with the reason for a gated bucket; the pathogen selector switches the displayed statistics; the peak-season callout text reads "historical seasonal pattern" and contains neither "forecast" nor "prediction"
  - _Requirements: 7.2, 7.3, 7.4_
  - _Design: Testing Strategy — Web component test_

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster path; core honesty/gating/peak/trend/determinism tests (3.1) are first-class because honesty is the project's hard constraint.
- Each leaf task references specific requirement clauses and the design section it traces to.
- Analysis functions are pure given an injected record list; the exporter builder reads a cache from a temp path; the web component reads a fixture artifact — so each unit is testable in isolation.
- The module is strictly additive: only `exporter.py`, `schemas.py`, `artifacts.ts`, and `App.tsx` are edited, each by addition only.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2", "4"] },
    { "id": 2, "tasks": ["3.1", "3.2", "3.3", "5.1"] },
    { "id": 3, "tasks": ["5.2", "6"] },
    { "id": 4, "tasks": ["7.1", "7.2", "8"] },
    { "id": 5, "tasks": ["9"] },
    { "id": 6, "tasks": ["10"] }
  ]
}
```
