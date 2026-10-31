# Implementation Plan: S03 Persistent Establishment Surveillance Monitor

## Overview

This plan turns the S03 design into incremental coding tasks. S03 adds an establishment-level beta-binomial Empirical Bayes surveillance detector reusing the S01 raw-FSIS readers and the S04 period helpers, plus a Supplier Monitor dashboard tab. Work proceeds one task at a time; after the module lands, the milestone stops for user review.

Terminal note: Kiro's integrated PowerShell is non-functional this session, so all Python/npm runs happen in an external CMD and file contents are hand-pasted. Tasks are sequenced so each produces something runnable before the next.

## Tasks

- [ ] 1. Inventory and prior-fit audit
  - Confirm the existing src/models/establishment.py surface (load_establishment_samples, build_establishment_quarters, descriptive_establishment_scores) and that no latitude/longitude field exists; run a scoping audit of the establishment support distribution and candidate beta priors per pathogen
  - Lock MIN_SUPPORT_ESTABLISHMENT=20 and PRIOR_FIT_MIN_SUPPORT=30; note the prior will be re-fit on the routine-only cohort in the real module
  - _Requirements: 3.1, 4.1_


- [ ] 2. Build the establishment EB layer over the existing module
  - [ ] 2.1 Load + aggregate via the existing module
    - In src/analysis/establishment_surveillance.py, call load_establishment_samples(pathogen) and build_establishment_quarters(frame); aggregate to per-establishment totals (eligible_n, positive_n) and retain quarter rows; carry FSIS identity (id, name, state) only; count establishment_missing; each sample counted once
    - _Requirements: 2.1, 5.1, 8.1_
  - [ ] 2.2 Per-pathogen MoM beta prior and partial-pooling posterior
    - Fit Beta(alpha0, beta0) by method of moments over establishments with eligible_n >= PRIOR_FIT_MIN_SUPPORT on the routine cohort; compute eb_posterior (Beta(alpha0+pos, beta0+n-pos) mean + 95% equal-tailed credible interval via scipy.stats.beta with a graceful fallback); record alpha0/beta0/peer_rate
    - _Requirements: 1.1, 1.2, 3.1, 3.3_
  - [ ] 2.3 Persistence evidence and low-support handling
    - From the quarter rows compute repeated-positive periods, periods supported, last supported period, sampling gaps; apply MIN_SUPPORT_ESTABLISHMENT=20 (below -> support_status low_support, never ranked as clean)
    - _Requirements: 1.4, 2.2, 2.3_


- [ ] 3. Orchestrate and cache
  - Implement `compute_establishment_surveillance` (all three pathogens, first-class) and `load_cache`; write `data/interim/s03_establishment_surveillance.json` with method metadata (prior, thresholds, establishment_missing, predictive_status per pathogen); mark unsupported pathogen/establishment unavailable with a reason and null numerics
  - Run in external CMD and record real counts for the completion report
  - _Requirements: 4.2, 4.4, 6.3_

- [ ] 4. Schema: EstablishmentSurveillanceRecord (Python) and TS mirror
  - Add `PersistenceEvidence` and `EstablishmentSurveillanceRecord` TypedDicts to `src/artifacts/schemas.py` before the `STATUS_TAGS` anchor, matching the design field list exactly (identity fields only, no contact detail; latitude/longitude null; coordinates_status "unavailable"); append the mirrored TS interfaces to `web/src/types/artifacts.ts`
  - _Requirements: 5.1, 6.1, 6.2, 6.5_

- [ ] 5. Exporter and manifest wiring
  - Add `build_establishment_surveillance()` to `src/artifacts/exporter.py` mirroring `build_emerging_risk()`; validate with `validate_payload(..., EstablishmentSurveillanceRecord, label="establishment_surveillance")`; wire import, `build_all_artifacts()` return key, and manifest entry; emit only the four identity fields and never a contact field; no hardcoded legacy reads
  - Run the exporter in external CMD; confirm `web/public/data/establishment_surveillance.json` exists and validates
  - _Requirements: 6.1, 6.4_

- [ ] 6. Python tests
  - Add `tests/test_establishment_surveillance.py` covering the seven correctness properties on small synthetic record sets: no double-counted samples, posterior smoothing, low-support-not-safety, anonymization (no contact field), no synthetic supplier relationship, known-vs-unseen separation, leakage-safety and denominator conservation
  - Run `python -m pytest` in external CMD; all existing tests must stay green
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

- [ ] 7. Frontend: Supplier Monitor view
  - Build `web/src/components/panels/SupplierMonitor.tsx` using `useArtifact<EstablishmentSurveillanceRecord[]>("establishment_surveillance")` with pathogen selector, region filter, ranked establishment list showing EB posterior + credible interval + support + persistence summary, a "how to read this / low support is not safety" box, a separated de-emphasized low-support group, and a facility-map panel that shows an explicit coordinates-unavailable state; navy/teal theme with orange/red only on active elevated indicators; a Page-06-deferred note
  - Add the `"supplier"` tab to `web/src/App.tsx`
  - _Requirements: 1.4, 5.2, 7.1, 7.2, 7.3, 7.4, 7.5_

- [ ] 8. Web tests and full verification
  - Add `web/src/components/panels/__tests__/SupplierMonitor.test.tsx` asserting the ranked list renders EB posterior with interval, low-support establishments are separated and not labeled clean, the coordinates-unavailable map state renders, and the artifact-missing empty state renders; add `SupplierMonitor.tsx` to the theme-discipline allow-list if it uses alert colors
  - Run `npm run test` and `npm run build` in external CMD; record exact pass/fail counts; confirm no existing test weakened
  - _Requirements: 7.3, 7.4, 8.7_

- [ ] 9. Review gate
  - Produce the completion report: real establishment counts per pathogen, support distribution, fitted prior and peer rate, top EB-ranked establishments with intervals, establishment_missing count, per-pathogen predictive_status (descriptive-only expected), one example artifact record, the dev URL, test commands and exact pass/fail counts, and stated data limitations (no coordinates; low testing is not safety; sampling-intensity caveat); STOP for user approval
  - _Requirements: 4.2, 6.3, 7.3_

## Notes

- All three pathogens remain first-class; a descriptive-only outcome (no establishment forecast) is an allowed, honest result and is reported as such.
- Establishment geography is sampling location only; no supplier, destination, or illness claims; only FSIS-published identity, no contact detail.
- Low testing is never shown as safety; low-support establishments are separated and de-emphasized, not ranked as clean.
- Each task produces something runnable; the milestone stops at task 9 for review before any next module.

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
    { "id": 10, "tasks": ["9"] }
  ]
}
```