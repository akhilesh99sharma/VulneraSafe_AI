# Design Document

Surveillance Actions — reproducible decision layer over the science modules.

## Overview

Surveillance Actions converts the OBSERVED surveillance signals already produced
by S01/S03/S04/S06 into a ranked, human-review-gated Action_Queue for the
retailer Food Safety Operations Director, exported as a first-class
schema-validated artifact (action_queue.json). S05 (CDC human outbreaks) is
attached as corroboration context only and never triggers an action. The logic
is deterministic Python in the reproducible pipeline, property-tested, and
auditable — no new raw data, no model training.

It reads the existing offline caches / artifacts, applies documented derivation
rules that respect each source module's support gate, and emits one
ActionQueueItem per qualifying signal. A new Surveillance Actions web tab renders
the queue with evidence and a visible human-review indicator.

### Non-goals / honesty boundaries

- Decision support only: retailer-appropriate verbs (prioritize testing, request
  supplier verification, protect access, scrutinize sourcing, gather info), never
  "recall", "contaminated", "unsafe", or a regulatory directive.
- Every action carries human_review=true and status OBSERVED.
- S05 human-outbreak data is corroboration context only, never a sole trigger
  (non-causality).
- Below-support signals (each module's own gate) never produce actions.
- Distinct from the base platform's SIMULATED optimizer Recommended Action Panel;
  labeled so the two are not confused.

## Architecture

Data flow (offline derivation to cache to artifact to UI):

1. Read the existing module caches/artifacts: S04 emerging_risk, S03
   establishment_surveillance, S06 community_impact, S01
   multipathogen_program_product, and S05 one_health_human_comparison (context).
2. src/decision/action_queue.py applies deterministic per-source rules, each
   honoring that module's support gate, to produce candidate actions.
3. Attach S05 corroboration context to an action when the same state has NORS
   data in the overlap window (labeled non-causal).
4. Rank by a documented rule (signal strength x support), assign ranks.
5. Cache to data/interim/action_queue.json.
6. exporter.build_action_queue() shapes and validates
   web/public/data/action_queue.json and registers it in the manifest.
7. The Surveillance Actions tab renders the ranked queue.

## Components and Interfaces

### 1. src/decision/action_queue.py

Reads the module caches via their existing load_cache() functions (S03/S04/S06)
and the exporter builders where convenient; reads S05 cache for corroboration.
No new data access.

New constants:
- MODULE_ID = "ACTIONQ", METHOD_VERSION = "aq.v1".
- Per-source selection thresholds (documented; reuse module gates): S04 uses
  retro_anomaly in the latest period; S03 uses support_status == ok ranked by
  eb_posterior; S06 uses the top priority_score states (data-backed lens); S01
  uses the highest-positivity gated categories.
- TOP_N per source to keep the queue focused.
- FORBIDDEN_TERMS = {"recall", "contaminated", "unsafe", ...} enforced in a test.

Key functions:
- derive_s04_actions(cache) -> list[dict]  (emerging anomaly -> prioritize testing/monitoring)
- derive_s03_actions(cache) -> list[dict]  (high-EB establishment -> request supplier verification)
- derive_s06_actions(cache) -> list[dict]  (high priority state -> protect access when allocating)
- derive_s01_actions(cache) -> list[dict]  (high-positivity category -> scrutinize sourcing)
- attach_corroboration(actions, s05_cache) -> list[dict]  (adds non-causal NORS context; never creates actions)
- rank_actions(actions) -> list[dict]  (deterministic signal-strength x support; assigns rank)
- compute_action_queue(round_to=6) -> dict  (orchestrate, write cache)
- load_cache().

### 2. Frontend — Surveillance Actions view

New component web/src/components/panels/SurveillanceActions.tsx, a tab in App.tsx
(Tab union extended with "actions"). Uses useArtifact<ActionQueueItem[]>("action_queue"),
StatusTag, EmptyState, PanelShell/ArtifactBody.

Controls and panels:
- pathogen filter and source-module filter (all three pathogens first-class).
- a ranked list: rank, action text, target (region/establishment/category),
  triggering source badge, evidence summary, and a visible Human-Review chip.
- a prominent note that these are suggestions from OBSERVED surveillance requiring
  human review, distinct from the SIMULATED optimizer panel.
- navy/teal theme; orange/red reserved for the human-review / elevated emphasis.

### 3. Exporter — build_action_queue()

In src/artifacts/exporter.py, mirroring the other expansion builders: reads the
cache via from src.decision.action_queue import load_cache, flattens to
list[ActionQueueItem], validates with validate_payload(..., ActionQueueItem,
label="action_queue"), returns the keyed payload from build_all_artifacts()
(auto-written and manifest-registered).

## Data Models

### ActionQueueItem (Python) plus TS mirror

Added to src/artifacts/schemas.py next to the other expansion records (before the
STATUS_TAGS anchor), mirrored in web/src/types/artifacts.ts. One record per
suggested action.

Fields:
- artifact_version: str
- module_id: str  ("ACTIONQ")
- method_version: str
- rank: int
- pathogen: str
- commodity: str
- action: str  (the suggested action text, retailer-appropriate)
- action_category: str  (prioritize_testing | request_supplier_verification | protect_access | scrutinize_sourcing | gather_information)
- target_type: str  (state | establishment | product_category)
- target: str  (the specific region/establishment/category)
- source_module: str  (S01 | S03 | S04 | S06)
- triggering_signal: str  (plain-language description of the OBSERVED finding)
- evidence_summary: str  (the underlying metric + uncertainty where available)
- corroboration_note: Optional[str]  (non-causal S05 context, or null)
- human_review: bool  (always true)
- status: StatusTag  (OBSERVED)
- availability_status: str  ("available")
- generated_at: str

Status discipline: status is OBSERVED for every action (derived from observed
surveillance). No action is PREDICTED or SIMULATED. No field encodes contamination,
human illness, or causation; corroboration_note is explicitly non-causal context.

## Algorithm detail

Per-source derivation (each honoring the module gate):
- S04: for the latest period, each state with retro_anomaly True (support ok)
  yields "Prioritize testing / heightened monitoring for {pathogen} in {state}
  next period"; evidence = observed positivity vs trailing baseline.
- S03: establishments with support_status ok, ranked by eb_posterior (top N per
  pathogen), yield "Request supplier verification / additional testing for
  {establishment} ({state})"; evidence = EB posterior + credible interval +
  support.
- S06: states with the highest priority_score under the default (65+) lens yield
  "When allocating {commodity}, protect access in {state} (elevated hazard +
  high need)"; evidence = hazard component + vulnerability + priority.
- S01: gated highest-positivity categories yield "Scrutinize {category} sourcing
  for {pathogen}"; evidence = observed positivity + CI + sample n. Phrased as
  sourcing scrutiny, acknowledging national-pooled coarseness.

Corroboration: for any action on a state, if S05 has NORS foodborne data for that
pathogen+state in the overlap window, attach a corroboration_note (counts +
"corroboration only, not causal, lagged ~365 days"). Never creates an action.

Ranking: deterministic. Primary key: a normalized signal-strength per source
(S04 exceedance over band; S03 eb_posterior; S06 priority_score; S01 positivity),
each already in a comparable [0,1]-ish range; tie-break by support/sample size,
then pathogen, then target for stability. Rank assigned 1..N. The exact rule is
recorded in cache metadata (no black-box score).

## Correctness Properties

The tests (tests/test_action_queue.py, Python; and
web/src/components/panels/__tests__/SurveillanceActions.test.tsx, web) assert the
following.

### Property 1: No action from S05 alone
**Validates: Requirements 3.1, 7.1**
No ActionQueueItem has source_module S05 / CDC; every action traces to S01/S03/S04/S06.

### Property 2: Human-review and OBSERVED on every action
**Validates: Requirements 2.2, 1.4, 7.2**
Every item has human_review=true and status OBSERVED.

### Property 3: No forbidden directive/contamination terms
**Validates: Requirements 2.1, 2.3, 7.3**
No action or triggering_signal contains recall / contaminated / unsafe / a regulatory directive.

### Property 4: Below-support signals produce no action
**Validates: Requirements 1.2, 7.4**
A synthetic below-support signal from any source yields no ActionQueueItem.

### Property 5: Deterministic ranking, pathogens first-class
**Validates: Requirements 4.1, 4.2, 7.5**
Ranking is a pure function of inputs (stable across runs); all three pathogens appear when they have qualifying signals.

### Property 6: Evidence present on every action
**Validates: Requirements 1.3, 5.2**
Every ActionQueueItem carries a non-empty evidence_summary and a triggering_signal.

## Error Handling

- A missing source cache simply contributes no actions from that source (never a
  fabricated action); the queue is built from whatever gated signals exist.
- An empty queue is a valid honest result and is exported as an empty list with
  method metadata, surfaced in the UI as an explicit empty state.
- S05 cache missing -> actions still generate; corroboration_note is null.

## Testing Strategy

- Python: tests/test_action_queue.py with the six properties on small hand-built
  source caches (no raw-data dependency), fast and deterministic.
- Web: SurveillanceActions.test.tsx asserts the ranked list renders with evidence
  and human-review chips, the pathogen/source filters work, the distinct-from-
  optimizer note renders, and the empty state renders.
- Full suite (pytest + vitest + build) run in external CMD after implementation.
