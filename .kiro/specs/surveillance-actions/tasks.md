# Implementation Plan: Surveillance Actions decision layer

## Overview

This plan turns the Surveillance Actions design into incremental coding tasks. It
is a deterministic decision layer over the existing S01/S03/S04/S06 artifacts
(with S05 as corroboration context only), exported as a first-class
schema-validated `action_queue.json` and rendered by a new web tab. No new raw
data, no model training. Work proceeds one task at a time.

Terminal note: Kiro's integrated PowerShell is unreliable this session for
long-running commands; the full test suite is confirmed in external CMD.

## Tasks

- [x] 1. Action-derivation core
  - [x] 1.1 Per-source derivation functions
    - In a new `src/decision/action_queue.py`, implement `derive_s04_actions`, `derive_s03_actions`, `derive_s06_actions`, `derive_s01_actions`, each reading that module's existing cache via its `load_cache()` and honoring the module's support gate (S04 retro_anomaly+support; S03 support_status ok; S06 data-backed lens priority; S01 min-n gated categories); emit candidate action dicts with action text, category, target, source, triggering_signal, evidence_summary
    - _Requirements: 1.1, 1.2, 1.3, 2.1_
  - [x] 1.2 Corroboration and ranking
    - Implement `attach_corroboration` (adds non-causal S05 NORS context to a state's action when present; never creates actions) and `rank_actions` (deterministic signal-strength x support, stable tie-breaks, assign rank)
    - _Requirements: 3.1, 3.2, 4.1_

- [x] 2. Orchestrate and cache
  - Implement `compute_action_queue` (run all derivations, attach corroboration, rank, stamp human_review=true and status OBSERVED on every item) and `load_cache`; write `data/interim/action_queue.json` with method metadata (ranking rule, per-source thresholds, forbidden-terms list)
  - Run in external CMD; record the real action counts per source/pathogen
  - _Requirements: 1.4, 2.2, 4.2, 4.3_

- [x] 3. Schema: ActionQueueItem (Python) and TS mirror
  - Add the `ActionQueueItem` TypedDict to `src/artifacts/schemas.py` before the `STATUS_TAGS` anchor, matching the design field list exactly (human_review bool, status OBSERVED, corroboration_note optional, no contamination/illness field); append the mirrored TS interface to `web/src/types/artifacts.ts`
  - _Requirements: 5.1, 5.2, 5.4_

- [x] 4. Exporter and manifest wiring
  - Add `build_action_queue()` to `src/artifacts/exporter.py` mirroring the other expansion builders; validate with `validate_payload(..., ActionQueueItem, label="action_queue")`; wire import, `build_all_artifacts()` return key, and manifest entry; no hardcoded legacy reads
  - Run the exporter in external CMD; confirm `web/public/data/action_queue.json` exists and validates
  - _Requirements: 5.1, 5.3_

- [x] 5. Python tests
  - Add `tests/test_action_queue.py` covering the six correctness properties on small hand-built source caches: no action from S05 alone, human_review+OBSERVED on every action, no forbidden directive/contamination terms, below-support signal produces no action, deterministic ranking with all three pathogens, evidence present on every action
  - Run `python -m pytest` in external CMD; all existing tests must stay green
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

- [x] 6. Frontend: Surveillance Actions view
  - Build `web/src/components/panels/SurveillanceActions.tsx` using `useArtifact<ActionQueueItem[]>("action_queue")` with pathogen filter, source-module filter, a ranked list (rank, action, target, source badge, evidence summary, visible Human-Review chip), a prominent "suggestions from OBSERVED surveillance; requires human review; distinct from the SIMULATED optimizer panel" note, and an empty state; navy/teal theme, orange/red only for the human-review/elevated emphasis
  - Add the `"actions"` tab to `web/src/App.tsx`
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 7. Web tests and full verification
  - Add `web/src/components/panels/__tests__/SurveillanceActions.test.tsx` asserting the ranked list renders with evidence + human-review chips, the filters work, the distinct-from-optimizer note renders, and the artifact-missing empty state renders; add the component to the theme-discipline allow-list (it uses orange/red for the human-review/elevated emphasis)
  - Run `npm run test` and `npm run build` in external CMD; record exact pass/fail counts; confirm no existing test weakened
  - _Requirements: 6.5, 7.6_

- [ ] 8. Review gate
  - Produce the completion report: action counts per source/pathogen, example records, confirmation of the honesty properties (no S05-only, human-review everywhere, no forbidden terms), the dev URL, test commands and exact pass/fail counts, and stated limitations (suggestions not directives; OBSERVED surveillance; distinct from SIMULATED optimizer); STOP for user approval
  - _Requirements: 4.2, 6.3_

## Notes

- All three pathogens remain first-class; an empty queue for a pathogen/source is an honest result, never a fabricated action.
- S05 CDC human-outbreak data is corroboration context only and never triggers an action.
- Every action is retailer decision support with a human-review gate; never a directive, contamination, or regulatory claim.
- Distinct from the base platform's SIMULATED optimizer Recommended Action Panel.
- Each task produces something runnable; the milestone stops at task 8 for review.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2"] },
    { "id": 2, "tasks": ["2"] },
    { "id": 3, "tasks": ["3"] },
    { "id": 4, "tasks": ["4"] },
    { "id": 5, "tasks": ["5"] },
    { "id": 6, "tasks": ["6"] },
    { "id": 7, "tasks": ["7"] },
    { "id": 8, "tasks": ["8"] }
  ]
}
```
