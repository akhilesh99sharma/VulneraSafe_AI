# Implementation Plan: S05 Food Surveillance vs. Human Outbreaks Comparison

## Overview

This plan turns the S05 design into incremental coding tasks. S05 integrates real CDC NORS human-outbreak data (already downloaded to data/raw/cdc_nors_outbreaks.csv) and compares it against the FSIS state-year surveillance reused from S04, strictly as corroboration with a 365-day leakage-safe lag and no causal claims. Work proceeds one task at a time; after the module lands, the milestone stops for user review.

Terminal note: Kiro's integrated PowerShell is non-functional this session, so all Python/npm runs happen in an external CMD and file contents are hand-pasted. Tasks are sequenced so each produces something runnable before the next.

## Tasks

- [ ] 1. NORS inventory and parameter lock
  - Add a `__main__`-guarded inventory report to a new `src/analysis/human_comparison.py` that reads data/raw/cdc_nors_outbreaks.csv, filters to foodborne, standardizes etiology, and prints per-pathogen outbreak/illness/state coverage, the computed FSIS-NORS overlap window, counts of excluded/unmatched etiologies, and joined comparison-cell counts
  - Run it in external CMD; lock COVERAGE_MIN_OUTBREAKS and the overlap window from the real numbers
  - _Requirements: 4.1, 4.2_

- [ ] 2. NORS ingest and pathogen standardization
  - [ ] 2.1 Etiology standardization
    - Implement `standardize_etiology` (lowercase, semicolon-split, conservative match to Salmonella / Listeria / STEC where STEC covers coli/o157/shiga/stec; unmatched → empty set) with a unit test fixture
    - _Requirements: 4.1, 7.5_
  - [ ] 2.2 Foodborne load and cell aggregation
    - Implement `load_nors_foodborne` (keep Primary Mode == Food; parse Year/State/Illnesses; attach standardized pathogens; count excluded/unparsable) and `nors_by_cell` ((pathogen, state, year) → outbreaks, illnesses; multi-agent rows attributed to each matched pathogen)
    - _Requirements: 1.1, 1.4, 4.3, 4.4_

- [ ] 3. FSIS state-year reuse and lagged join
  - Implement `fsis_state_year` (aggregate the reused S04 `_build_series` quarters to (state, year) n/pos with a Wilson interval), `availability_year` (event year + 1; the 365-day lag), and the join on (pathogen, state, year) within the overlap window; flag coverage_limited and nors_not_available cells, distinguishing a true zero from missing
  - _Requirements: 1.2, 3.1, 3.2, 3.3, 4.2, 4.3_

- [ ] 4. Exploratory lead-lag and orchestration/cache
  - Implement `lead_lag_summary` (national per-pathogen annual FSIS vs NORS series; descriptive cross-correlation at small year lags with permutation p-value + bootstrap CI; exploratory=true), and `compute_human_comparison` + `load_cache`; write data/interim/s05_human_comparison.json with provenance (NORS dataset id + access date), lag, overlap window, coverage, and exclusion counts
  - Run in external CMD and record real counts for the completion report
  - _Requirements: 2.4, 5.3, 1.2_

- [ ] 5. Schema: HumanOutbreakComparison (Python) and TS mirror
  - Add `LeadLagSummary` and `HumanOutbreakComparison` TypedDicts to `src/artifacts/schemas.py` before the `STATUS_TAGS` anchor, matching the design field list exactly (comparison_status "CORROBORATION"; no causal/linkage/sub-state/forecast field; status OBSERVED); append the mirrored TS interfaces to `web/src/types/artifacts.ts`
  - _Requirements: 2.1, 2.2, 2.3, 5.1, 5.2, 5.5_

- [ ] 6. Exporter and manifest wiring
  - Add `build_human_outbreak_comparison()` to `src/artifacts/exporter.py` mirroring `build_emerging_risk()`; validate with `validate_payload(..., HumanOutbreakComparison, label="one_health_human_comparison")`; wire import, `build_all_artifacts()` return key, and manifest entry; no hardcoded legacy reads
  - Run the exporter in external CMD; confirm `web/public/data/one_health_human_comparison.json` exists and validates
  - _Requirements: 5.1, 5.4_

- [ ] 7. Python tests
  - Add `tests/test_human_comparison.py` covering the six correctness properties on small hand-built NORS/FSIS fixtures: 365-day lag enforced, no CDC predictor leakage, zero-vs-missing distinction, no causal/forecast labels, conservative etiology standardization, all three pathogens first-class with honest coverage; plus a standardize_etiology unit test
  - Run `python -m pytest` in external CMD; all existing tests must stay green
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

- [ ] 8. Frontend: One Health Insights view
  - Build `web/src/components/panels/OneHealthInsights.tsx` using `useArtifact<HumanOutbreakComparison[]>("one_health_human_comparison")` with pathogen selector, state filter, linked FSIS/CDC dual time series with distinct source badges, a prominent no-causal-link explanation (and 365-day-lag note), an explicitly-exploratory lead-lag summary, and explicit coverage_limited / nors_not_available states; navy/teal theme, orange/red only on active alerts; a note that sub-state human geography is not produced
  - Add the `"onehealth"` tab to `web/src/App.tsx`
  - _Requirements: 2.4, 6.1, 6.2, 6.3, 6.4, 6.5_

- [ ] 9. Web tests and full verification
  - Add `web/src/components/panels/__tests__/OneHealthInsights.test.tsx` asserting the dual FSIS/CDC timelines render with distinct source badges, the no-causal-link explanation is present, a coverage-limited state renders, and the artifact-missing empty state renders; add the component to the theme-discipline allow-list if it uses alert colors
  - Run `npm run test` and `npm run build` in external CMD; record exact pass/fail counts; confirm no existing test weakened
  - _Requirements: 6.4, 7.6_

- [ ] 10. Review gate
  - Produce the completion report: NORS row/foodborne counts, per-pathogen outbreak/illness/state coverage, overlap window, excluded/unmatched etiology counts, joined comparison-cell counts, example artifact record, the exploratory lead-lag result (with uncertainty), the dev URL, test commands and exact pass/fail counts, and stated data limitations (state×year only; corroboration not causation; Listeria coverage-limited; NORS ends 2023); STOP for user approval
  - _Requirements: 2.4, 5.3, 6.3_

## Notes

- All three pathogens remain first-class; Listeria is coverage-limited (144 foodborne outbreaks, 21 states) shown with real counts, never zeroed.
- The comparison is corroboration only: no same-strain link, no food-to-illness causation, no human county-case forecast; lead-lag is exploratory descriptive only.
- NORS is lagged 365 days and can never act as a leading predictor of FSIS.
- Each task produces something runnable; the milestone stops at task 10 for review before any next module.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2"] },
    { "id": 3, "tasks": ["3"] },
    { "id": 4, "tasks": ["4"] },
    { "id": 5, "tasks": ["5"] },
    { "id": 6, "tasks": ["6"] },
    { "id": 7, "tasks": ["7"] },
    { "id": 8, "tasks": ["8"] },
    { "id": 9, "tasks": ["9"] },
    { "id": 10, "tasks": ["10"] }
  ]
}
```