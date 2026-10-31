# Implementation Plan: Facility Map

## Overview

This plan converts the Facility Map design into incremental, test-driven coding tasks,
mirroring how the project's Surveillance Actions module (`src/decision/action_queue.py`
+ `build_action_queue` exporter + `SurveillanceActions.tsx`) was built. The feature
introduces **no new modeling and no model training**: it is a deterministic join plus a
one-time offline geocode over data that already exists (S03 establishment surveillance +
the ACTIONQ action_queue), producing a schema-validated `facility_map` artifact and a new
first-class web tab.

Implementation languages are fixed by the design: **Python** for the offline geocode
build script, the decision-layer module, the exporter wiring, and the schema; and
**TypeScript/React** for the web tab and its tests. The design uses concrete languages
(not pseudocode), so no language-selection step is required.

The design has a **Correctness Properties** section (Properties 1-10), so property-based
tests apply to the pure selection/join/coverage logic. Property tests use **Hypothesis**
(already a project dependency) at >=100 iterations and are tagged
`# Feature: facility-map, Property N: ...`; the web test uses **vitest + Testing
Library** with the existing `installArtifactFetch` / `renderWithSelection` helpers and the
maplibre mock.

The build order follows the design's layering: the offline geocode build script and the
Python decision core are built and unit-tested first; the schema (Python + TS mirror)
lands before the exporter; the exporter wires before the web component; tests ride
alongside each layer. All three pathogens (Salmonella, Listeria, STEC) are first-class,
and an empty result for a pathogen is an honest, displayed outcome, never fabricated.

### Honest open risk (Req 13)

We do **not** yet know the MPI Directory match/geocode rate for S03's establishment
numbers. This plan treats that as a measured, reported risk — not an assumption:

- Task 2 obtains/prepares the MPI Directory data and **measures** the actual
  match/geocode coverage; it does not assume full coverage.
- "MPI Directory not yet obtained" (`obtained=false`) and "establishment number not
  found" / "no published address" / "ambiguous match" are explicit **unplaced reasons**,
  never hidden errors.
- If the directory cannot be obtained, the fallback is honest and still shippable: every
  selected establishment is unplaced with a stated reason and coverage is reported as the
  measured value (0.0% with every row unplaced), never an empty "successful" map.

### Terminal note

Kiro's integrated PowerShell is unreliable this session for long-running commands. The
full `pytest` suite and `npm test` / `npm run build` are confirmed to run in an external
CMD window. Run the verification commands there and record exact pass/fail counts. All
files must be written **BOM-free** (UTF-8 without a byte-order mark).

## Tasks

- [x] 1. Build the offline geocode build script and the decision-layer core (no exporter yet)
  - [x] 1.1 Implement `normalize_establishment_number` and module constants in `src/decision/facility_map.py`
    - Create `src/decision/facility_map.py` with the module constants exactly as designed: `REPO_ROOT`, `INTERIM_DIR`, `EXTERNAL_DIR`, `CACHE_PATH = data/interim/facility_map.json`, `GEOCODE_CACHE_PATH = data/external/facility_geocode.json`, `MODULE_ID = "FACILITYMAP"`, `METHOD_VERSION = "fm.v1"`, `TOP_N_S03 = 12` (re-declared with the comment that it mirrors `action_queue.TOP_N_S03`), `FORBIDDEN_TERMS`, `_PATHOGENS`, `_COMMODITY`
    - Implement `normalize_establishment_number(raw: str) -> str` as a pure, order-independent function: trim whitespace, strip leading zeros (keep at least one digit, "00" -> "0"), uppercase
    - _Requirements: 2.1_
  - [ ]* 1.2 Write unit tests for normalization and the TOP_N_S03 mirror
    - Assert normalization is deterministic/idempotent on sample inputs (whitespace, leading zeros, case) and that both join sides normalize to the same key
    - Assert the local `TOP_N_S03` equals `src.decision.action_queue.TOP_N_S03` so the two constants cannot silently diverge
    - _Requirements: 2.1, 1.1_
  - [x] 1.3 Implement the swappable Geocoder interface and `GazetteerGeocoder`
    - Add the `Geocoder` Protocol (`geocode(address) -> Optional[tuple[float, float]]`, offline-only, build-time only) and a concrete `GazetteerGeocoder` that resolves against a committed local gazetteer file; document that the runtime build never calls a Geocoder
    - _Requirements: 3.1_
  - [x] 1.4 Implement selection helpers in `src/decision/facility_map.py`
    - `select_s03_elevated`: per pathogen, the top `TOP_N_S03` establishments among `support_status == "ok"` with non-null `eb_posterior`, ordered by `eb_posterior` desc; `low_support` never included
    - `select_action_queue_establishments`: per pathogen, action_queue entries with `target_type == "establishment"`, carrying forward `human_review=True` and `status="OBSERVED"`
    - `select_signal_bearing`: per-pathogen union de-duplicated by `(pathogen, establishment_id)`, recording `source_selection` in `{"s03","action_queue","both"}`; establishments that are neither are excluded
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 10.4_
  - [ ]* 1.5 Write unit tests for selection helpers
    - Assert only top-`TOP_N_S03` `ok` establishments plus action_queue establishment targets are selected; a `low_support` establishment with a high `eb_posterior` is excluded from elevated selection and never labeled safe; `source_selection` is `s03` / `action_queue` / `both` correctly
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_
  - [x] 1.6 Implement join, coverage, and the orchestrator in `src/decision/facility_map.py`
    - `load_geocode_cache`: read the committed geocode cache (never geocodes); handle `obtained=false` (empty entries)
    - `place_establishment`: exact-equality join on `normalized_establishment_number`; return a placed row (real lat/lon/address) or an unplaced row with the documented stated reason ("MPI Directory not yet obtained" / "establishment number not found in MPI Directory" / "no published address in MPI Directory" / "ambiguous match in MPI Directory")
    - `compute_coverage`: `total/placed/unplaced`, `coverage_pct = round(100*placed/total, 1)` in [0.0,100.0] when total>0; `None` + `coverage_state="not_applicable"` when total==0; invariant placed+unplaced==total
    - `compute_facility_map(*, round_to=6)`: select -> place -> split -> per-pathogen coverage -> stamp every row `human_review=True`, `status="OBSERVED"` -> sort rows by `normalized_establishment_number` -> write `CACHE_PATH` with `json.dumps(cache, indent=2, sort_keys=True)`
    - `load_cache`: read `CACHE_PATH` back with the same `(OSError, ValueError) -> None` try/except as S03
    - Keep all three pathogens first-class; an `available` pathogen with zero signal-bearing establishments is an explicit empty result; an `unavailable` pathogen is retained as a filter value with its `unavailable_reason`
    - _Requirements: 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 3.3, 3.4, 3.5, 3.7, 4.1, 4.2, 4.5, 4.6, 7.3, 7.4, 7.5, 8.6, 10.3_
  - [x] 1.7 Implement `scripts/build_facility_geocode.py` (offline, once, committed output)
    - Mirror `scripts/build_us_geojson.py`: obtain the MPI Directory, normalize every establishment number with `normalize_establishment_number`, geocode each published address once via a `Geocoder`, and write the committed cache `data/external/facility_geocode.json` keyed on `normalized_establishment_number` with the designed shape (`source`, `normalization`, `obtained`, `conflicts`, `entries`)
    - Handle the duplicate-key rule: when >=2 MPI rows normalize to the same key, write a single entry and record the key in `conflicts`
    - The script is maintainer-run and its output committed; it is never invoked at build time
    - _Requirements: 3.1, 3.2_

- [x] 2. Obtain the MPI Directory and MEASURE actual geocode coverage (honest-risk task)
  - [x] 2.1 Obtain/prepare the MPI Directory and build the committed geocode cache
    - Attempt to obtain the FSIS MPI Directory; run `scripts/build_facility_geocode.py` to produce `data/external/facility_geocode.json`
    - **If the directory is obtained:** record `obtained=true` and the entries; capture any duplicate-key `conflicts`
    - **If the directory cannot be obtained:** commit the cache with `obtained=false` and empty `entries` so every selected establishment becomes unplaced with reason "MPI Directory not yet obtained" — a shippable, honest artifact, not a failure
    - Do NOT assume full coverage anywhere; "directory not obtained" and "key missing" are explicit unplaced reasons
    - _Requirements: 2.7, 3.1, 3.2, 13.1, 13.2_
  - [x] 2.2 Measure and record actual match/geocode coverage
    - Run `compute_facility_map()` against the real S03 + action_queue + committed geocode caches; record the **measured** per-pathogen placed/unplaced counts and `coverage_pct` and the distribution of unplaced reasons
    - Confirm that a below-100% coverage surfaces the measured percentage and the unplaced reasons rather than presenting complete coverage
    - _Requirements: 4.1, 4.3, 4.5, 13.3_

- [x] 3. Add the Facility_Map schema and its TypeScript mirror (before the exporter)
  - [x] 3.1 Add `FacilityMapCoverage` and `FacilityMapItem` TypedDicts to `src/artifacts/schemas.py`
    - Insert both TypedDicts immediately **before** the `STATUS_TAGS` anchor (the `#: All status-bearing literal values...` comment + the `STATUS_TAGS` frozenset), **after** the `ActionQueueItem` class, following the `ActionQueueItem` `Optional[...]` style
    - Use the exact field sets from the design (coverage: `pathogen,total_selected,placed,unplaced,coverage_pct,coverage_state`; item: the full `FacilityMapItem` field list ending with `coverage`, `human_review`, `status`, `generated_at`)
    - _Requirements: 8.5, 8.6_
  - [x] 3.2 Append the mirrored TypeScript interfaces to `web/src/types/artifacts.ts`
    - Append `FacilityMapCoverage` and `FacilityMapItem` after the existing `ActionQueueItem` interface with **identical snake_case field names** so the parity test passes
    - _Requirements: 8.5, 12.4_
  - [ ]* 3.3 Write the schema key-set and cross-language parity tests
    - Python: assert the `FacilityMapItem` / `FacilityMapCoverage` annotated key sets exactly match the documented set (mirrors `tests/test_schemas.py` key-set checks)
    - Parity: assert the serialized snake_case field names of the Python TypedDicts equal the field names of the mirrored TS interfaces, so a field present in one but absent from the other fails
    - **Property 10: Schema <-> TypeScript field-name parity**
    - **Validates: Requirements 8.5, 12.4**

- [x] 4. Wire `build_facility_map` into the exporter
  - [x] 4.1 Implement `build_facility_map()` and wire it into `build_all_artifacts`
    - In `src/artifacts/exporter.py`: add `FacilityMapItem` (and the coverage type) to the `from src.artifacts.schemas import (...)` block
    - Implement `build_facility_map()`: read `facility_map.load_cache()`; if missing return `[]` (an empty map is honest); build one `FacilityMapItem` per row across all pathogens; stamp `artifact_version`, `module_id="FACILITYMAP"`, `method_version`, `generated_at=resolve_generated_at()`; sort rows by `(pathogen, normalized_establishment_number)`
    - Enforce the **FORBIDDEN_TERMS guard** before any write: scan every string-valued field of every row case-insensitively and raise `SchemaValidationError` naming the offending field if a forbidden term is found
    - Implement the fail-loud contract for a required-but-missing committed geocode key (strict policy): raise naming the missing key, perform no network geocode, write nothing
    - In `build_all_artifacts()`: build + `validate_payload(rows, FacilityMapItem, label="facility_map[item]")`, then add `"facility_map": facility_map` to the returned mapping so the generic writer emits `web/public/data/facility_map.json` and records its manifest entry (sha256 + count)
    - _Requirements: 3.4, 8.1, 8.2, 8.3, 8.4, 10.1, 10.2_
  - [ ]* 4.2 Write the Python property/unit tests in `tests/test_facility_map.py`
    - Build small hand-built S03 + action_queue + geocode-cache fixtures (same spirit as `test_action_queue.py` helpers)
    - **Property 1: Only signal-bearing establishments appear** — **Validates: Requirements 1.1, 1.2, 1.3**
    - **Property 2: Low-support is never elevated-selected and never called safe** — **Validates: Requirements 1.4, 6.4**
    - **Property 3: Placed + unplaced equals total selected, per pathogen** (Hypothesis over random fixtures) — **Validates: Requirements 4.6**
    - **Property 4: Every placed row has a real cached location, never fabricated** — **Validates: Requirements 2.6, 3.1, 3.3**
    - **Property 5: Every unplaced row has a non-empty stated reason** — **Validates: Requirements 2.3, 2.4, 2.5, 2.7, 4.4**
    - **Property 6: Coverage is the measured percentage, never assumed 100%** — **Validates: Requirements 4.1, 4.2, 4.5, 13.3**
    - **Property 7: Every row is human-reviewed and OBSERVED** — **Validates: Requirements 7.3, 8.6, 10.3, 10.4, 11.2**
    - **Property 8: No forbidden language in any field** (injected forbidden term causes `build_facility_map` to raise and write nothing) — **Validates: Requirements 10.1, 10.2**
    - **Property 9: Deterministic, sorted output** (two builds byte-identical excluding `generated_at`; rows sorted by `normalized_establishment_number`) — **Validates: Requirements 3.5, 3.6, 3.7**
    - Also assert the placement-honesty check required by Req 12.2 (placed rows trace to the committed cache; no placeholder coordinates)
    - _Requirements: 12.1, 12.2_

- [x] 5. Checkpoint — Python layer green
  - Ensure all Python tests pass, ask the user if questions arise.

- [x] 6. Build the Facility Map web tab and wire it into the app
  - [x] 6.1 Implement `web/src/components/panels/FacilityMap.tsx`
    - Tab-root component (no props), `const state = useArtifact<FacilityMapItem[]>("facility_map")`; pathogen filter state ("" = all; else Salmonella|Listeria|STEC) and source filter state ("" = all; else "s03"|"action_queue")
    - Loading: render a loading indication only; do NOT render ranked list, map view, or unplaced panel. Error: render `EmptyState` naming `facility_map`
    - Filters: pathogen filter = distinct pathogens present + "All"; source filter = s03 / action_queue / all; changing either restricts the ranked list, map view, and unplaced count to rows matching **both** filters
    - Map view: reuse the `MapView` fallback-grid pattern; render one selectable `data-testid="facility-pin"` element per **placed** establishment under the jsdom fallback
    - Ranked list: placed+unplaced establishments ordered by descending `eb_posterior` (nulls last); each shows FSIS identity (number, published name or number-only when name is null, state), the Surveillance_Signal labeled as such with its `[ci_low, ci_high]` pair in the same view, the evidence summary, a low-support indicator when `sample_n < 30`, and a visible Human-Review chip; empty filtered list renders an `EmptyState`
    - Unplaced panel: coverage % + placed/total counts + each unplaced establishment with its stated reason, read from the carried coverage block (not recomputed)
    - Framing note labeling content OBSERVED and distinguishing it from the SIMULATED optimizer and the state-level PREDICTED risk map; no element labeled PREDICTED or SIMULATED
    - Theme: navy/teal/slate/gray only, except an orange alert accent on elevated-signal / human-review emphasis
    - _Requirements: 5.1, 5.2, 5.3, 6.1, 6.3, 6.5, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 9.10, 10.3, 11.1, 11.2, 11.3, 11.4_
  - [x] 6.2 Wire the `facilitymap` tab into `web/src/App.tsx` and update the theme allowlist
    - Extend the `Tab` union with `"facilitymap"`; import `FacilityMap`; add `{ id: "facilitymap", label: "Facility Map" }` to the header `tabs` array after `actions`; add the render branch `) : tab === "facilitymap" ? ( <FacilityMap /> )`
    - Because `FacilityMap.tsx` uses an orange alert accent, add `panels/FacilityMap.tsx` to the `ALERT_CONTEXT_FILES` allowlist in `web/src/components/__tests__/themeDiscipline.test.tsx`
    - _Requirements: 9.1, 11.4_
  - [x]* 6.3 Write `web/src/components/panels/__tests__/FacilityMap.test.tsx`
    - Use `installArtifactFetch` / `renderWithSelection` (and the maplibre mock); assert the tab renders and loads via `useArtifact("facility_map")`; the pathogen filter and source filter are present and functional (changing the source filter drops non-matching rows); the ranked list renders by descending `eb_posterior` with FSIS identity, the Surveillance_Signal + `[ci_low, ci_high]` pair, the evidence summary, and a visible Human-Review chip on every surfaced establishment; the unplaced panel shows the coverage %, placed/total counts, and each unplaced establishment with its reason; the framing note distinguishing OBSERVED from SIMULATED and PREDICTED is present; a missing artifact degrades to an `EmptyState` naming `facility_map`
    - _Requirements: 12.3_

- [x] 7. Verification — run the suites in external CMD and record exact counts
  - Python: in external CMD run `python -m pytest tests/test_facility_map.py -q` for the new tests, then `python -m pytest -q` to confirm the full suite stays green; record exact pass/fail counts
  - Web: in external CMD run `npm run test` (Facility Map component test + themeDiscipline + parity) and `npm run build` (confirms the new tab and types compile); record exact pass/fail counts and build result
  - Reminder: Kiro's integrated PowerShell is unreliable this session for long-running commands — use external CMD and keep all files BOM-free
  - Fix any failure and re-run until Python full suite, `npm run test`, and `npm run build` are all green
  - _Requirements: 8.1, 12.1, 12.2, 12.3, 12.4_

- [x] 8. Review gate — completion report, then STOP for user approval
  - Produce a completion report recording: selection counts per source and per pathogen; the **measured** geocode coverage (per pathogen placed/unplaced counts and `coverage_pct`); the distribution of unplaced reasons; confirmation of the honesty properties (every row OBSERVED + human_review=True; no forbidden terms; coverage measured, never assumed 100%; empty/unplaced results stated honestly); the local dev URL for the new Facility Map tab; the exact test pass/fail counts from Task 7; and stated limitations (notably the MPI Directory match rate and any `obtained=false` fallback)
    - STOP and wait for user approval before any further work
    - _Requirements: 4.3, 13.3_

## Notes

- Tasks marked with `*` are optional (all test sub-tasks) and are not implemented automatically; core implementation tasks (and the honest-risk Task 2, verification Task 7, and review-gate Task 8) are never optional.
- Each coding task references specific requirement sub-clauses and/or the exact Correctness Property (Properties 1-10) from `design.md` for traceability.
- The honest open risk (Req 13) is handled by Task 2, which **measures** real coverage; no task assumes full coverage, and "directory not obtained" / "key missing" are explicit unplaced reasons. If the directory cannot be obtained, the fallback is an honest all-unplaced artifact with measured 0.0% coverage.
- Build order: offline geocode script + Python core (Task 1) and real-coverage measurement (Task 2) before the exporter; schema + TS mirror (Task 3) before the exporter (Task 4); exporter before the web component (Task 6); tests ride alongside each layer; a Python checkpoint (Task 5) precedes the web work.
- Verification (Task 7) runs in external CMD with exact counts recorded; the review gate (Task 8) produces the completion report and stops for user approval. Files are written BOM-free.
- All three pathogens are first-class and empty results are honest, displayed outcomes.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.4"] },
    { "id": 2, "tasks": ["1.5", "1.6"] },
    { "id": 3, "tasks": ["1.7", "3.1"] },
    { "id": 4, "tasks": ["2.1", "3.2"] },
    { "id": 5, "tasks": ["2.2", "3.3", "4.1"] },
    { "id": 6, "tasks": ["4.2", "6.1"] },
    { "id": 7, "tasks": ["6.2"] },
    { "id": 8, "tasks": ["6.3"] }
  ]
}
```
