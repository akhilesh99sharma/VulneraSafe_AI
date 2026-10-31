# Implementation Plan: S04 Persistent vs. Emerging Risk Detector

## Overview

This plan turns the S04 design into incremental coding tasks. S04 adds a state-by-period surveillance-signal detector reusing the S01 raw-FSIS readers and the base platform's data contract. Work proceeds one task at a time; after the module lands, the milestone stops for user review.

Terminal note: Kiro's integrated PowerShell is non-functional this session, so all Python/npm runs happen in an external CMD and file contents are hand-pasted. Tasks are sequenced so each produces something runnable before the next.

## Tasks

- [ ] 1. Support audit and parameter lock
  - Add a `__main__`-guarded support-audit report to a new `src/analysis/emerging_risk.py` that reuses the S01 readers to print, per pathogen: distinct state count, median per-(state, quarter) and per-(state, month) denominators, and the share of state-periods clearing candidate thresholds 20 / 30 / 50
  - Run it in external CMD; record the chosen RESOLUTION (default quarterly) and MIN_SUPPORT per pathogen in module constants and in a short note for the cache method metadata
  - _Requirements: 3.4, 6.4_

- [ ] 2. Build the leakage-safe state-by-period analysis
  - [ ] 2.1 State and period extraction plus series builder
    - Implement `_record_state`, `_record_period` (quarterly/monthly bucketing of `collection_date`), and `_build_series` producing per-state period-ordered (period, period_start, n, pos) using the S01 tri-state classifier; count and expose `state_missing` and `date_unparsable`, never silently zeroed
    - _Requirements: 2.1, 3.1, 3.3_
  - [ ] 2.2 Trailing baseline with prior-only seasonal adjustment
    - Implement `trailing_baseline` using only strictly-earlier periods (EWMA + prior-only seasonal offset + Wilson band widened by prior dispersion); return None when fewer than the minimum prior supported periods exist
    - _Requirements: 2.1, 2.3, 2.4_
  - [ ] 2.3 Retrospective anomaly detector and persistence score
    - Implement `detect_retrospective` (sequential EWMA/posterior-exceedance flag using only data at or before each period) and `persistent_score` (fraction of supported periods above the trailing expected-high band); keep the two concepts distinct
    - _Requirements: 1.1, 1.2, 1.3, 2.2, 3.1, 3.2_

- [ ] 3. Optional gated prospective forecast
  - Implement `forecast_prospective`: train a one-step-ahead rule strictly before a fixed cutoff, test only after it, compare precision/recall against the persistence baseline, and report lead time with an availability-lag note; return None / `insufficient_support` when support is thin; emit an alert only when it beats persistence, else `not_shown_did_not_beat_persistence`
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [ ] 4. Orchestrate and cache
  - Implement `compute_emerging_risk` (all three pathogens, all first-class) and `load_cache`; write `data/interim/s04_emerging_risk.json` with method metadata (resolution, MIN_SUPPORT, missingness counts, prospective_status per pathogen); mark a pathogen/series `unavailable` with a reason and null numerics when unsupported, never dropped
  - Run in external CMD and record real counts for the completion report
  - _Requirements: 5.3, 6.1, 6.2, 6.3_

- [ ] 5. Schema: EmergingRiskStratum (Python) and TS mirror
  - Add `ProspectiveEval` and `EmergingRiskStratum` TypedDicts to `src/artifacts/schemas.py` before the `STATUS_TAGS` anchor, matching the design field list exactly; append the mirrored TS interfaces to `web/src/types/artifacts.ts`
  - _Requirements: 5.1, 5.2, 5.5_

- [ ] 6. Exporter and manifest wiring
  - Add `build_emerging_risk()` to `src/artifacts/exporter.py` mirroring `build_multipathogen_program_product()`; validate with `validate_payload(..., EmergingRiskStratum, label="emerging_risk")`; wire the import, the `build_all_artifacts()` return key, and a manifest entry recording per-pathogen prospective_status; no hardcoded legacy directory reads
  - Run the exporter in external CMD; confirm `web/public/data/emerging_risk.json` exists and validates
  - _Requirements: 5.1, 5.4_

- [ ] 7. Python tests
  - Add `tests/test_emerging_risk.py` covering the six correctness properties on small hand-built synthetic series: no-future-leakage (mutation check), low-n not flagged negative, no retro row labeled forecast, state-by-period uniqueness, denominator conservation, persistence-not-equal-to-anomaly
  - Run `python -m pytest` in external CMD; all existing tests must stay green
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

- [ ] 8. Frontend: Emerging Signals view
  - Build `web/src/components/panels/EmergingSignals.tsx` using `useArtifact<EmergingRiskStratum[]>("emerging_risk")` with pathogen selector, persistent/emerging toggle, trend chart with trailing-baseline band and anomaly markers, time scrubber restricting to at-or-before the selected period, "How to read this" box, de-emphasized low_support, the "no prospective signal beat a naive guess" note when applicable, and a Multi-Map-deferred note; navy/teal theme with orange/red only on active anomaly markers
  - Add the `"emerging"` tab to `web/src/App.tsx`
  - _Requirements: 1.4, 4.3, 6.2, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

- [ ] 9. Web tests and full verification
  - Add `web/src/components/panels/__tests__/EmergingSignals.test.tsx` asserting the toggle, the scrubber restriction, low-support de-emphasis, and the no-prospective-signal note render from a small fixture
  - Run `npm run test` and `npm run build` in external CMD; record exact pass/fail counts; confirm no existing web test weakened
  - _Requirements: 7.5, 8.6_

- [ ] 10. Review gate
  - Produce the completion report: real input row counts, supported years/periods, state_missing/date_unparsable counts, per-pathogen prospective_status with signed delta vs persistence (or descriptive-only result), one example artifact record, the dev URL, test commands and exact pass/fail counts, and stated data limitations; STOP for user approval
  - _Requirements: 4.3, 4.4, 6.2_

## Notes

- All three pathogens remain first-class; a descriptive-only (retrospective) outcome for any pathogen is an allowed, honest result and is reported as such.
- Geography is sampling location only; no product-destination or human-illness claims.
- Each task produces something runnable; the milestone stops at task 10 for review before any next module.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2"] },
    { "id": 3, "tasks": ["2.3"] },
    { "id": 4, "tasks": ["3"] },
    { "id": 5, "tasks": ["4"] },
    { "id": 6, "tasks": ["5"] },
    { "id": 7, "tasks": ["6"] },
    { "id": 8, "tasks": ["7"] },
    { "id": 9, "tasks": ["8"] },
    { "id": 10, "tasks": ["9"] },
    { "id": 11, "tasks": ["10"] }
  ]
}
```