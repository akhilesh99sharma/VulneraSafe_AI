# Requirements Document

## Introduction

**Surveillance Actions — a decision surface over the science modules.** This
expansion adds a reproducible decision layer that turns the OBSERVED surveillance
signals produced by the existing science modules (S01 Pathogen Explorer, S03
Supplier Monitor, S04 Emerging Signals, S06 Vulnerable Communities, with S05 One
Health Insights as corroboration only) into a ranked list of suggested,
human-review-gated operational actions for the retailer's Food Safety Operations
Director. It directly serves the challenge's Operational Decision Support
objective: the tool should change or improve a real decision, not just visualize
data.

The decision logic is implemented in Python as a first-class, schema-validated
artifact (`action_queue.json`) so it is reproducible, property-tested, and
auditable in source — consistent with the data-science-rigor and reproducibility
criteria. It introduces no new raw data and no new science; it is a deterministic
derivation over artifacts the pipeline already produces.

The hardest rule: a suggested action is **decision support, never a directive or
a contamination claim.** Every action is a retailer-appropriate suggestion
(verify, test, prioritize, protect access, gather more information), carries a
Human_Review gate, shows its supporting evidence and OBSERVED status, and is
derived only from signals that cleared their own module's support gate.

## Glossary

- **Action_Queue**: The ranked list of suggested operational actions derived from the surveillance artifacts.
- **Suggested_Action**: One retailer-appropriate recommendation (e.g. prioritize testing, request supplier verification, protect access, scrutinize sourcing, gather more information) with a triggering signal, evidence, rank, and a Human_Review flag.
- **Triggering_Signal**: The specific OBSERVED surveillance finding that produced an action (e.g. an S04 emerging anomaly, an S03 high-EB establishment).
- **Human_Review**: A required flag on every action indicating a person must evaluate it before any operational step; the tool supports, never replaces, judgment.
- **Corroboration_Only**: S05 CDC human-outbreak data informs context on an action when present but SHALL NOT, by itself, generate an action (non-causality guardrail).
- **Support_Gate**: Each source module's existing honesty gate (S03 min support, S04 min support + leakage-safe flag, S06 data-backed lens, S01 min-n). A signal that did not clear its module gate SHALL NOT produce an action.
- **action_queue.json**: The typed artifact this module exports, registered in the exporter and manifest.
- **ActionQueueItem**: The TypedDict (Python) / interface (TS) for one record of the artifact.

## Requirements

### Requirement 1: Derive actions only from gated OBSERVED signals

**User Story:** As the Food Safety Operations Director, I want each suggested
action backed by a real surveillance signal that already passed its own quality
gate, so I am never prompted to act on noise.

#### Acceptance Criteria

1. The Action_Queue SHALL derive each Suggested_Action from an OBSERVED signal in an existing artifact (S01/S03/S04/S06), never from fabricated or model-only-without-evidence values.
2. A signal that did not clear its source module's Support_Gate SHALL NOT generate a Suggested_Action.
3. Each Suggested_Action SHALL record its Triggering_Signal, the source module, and the evidence (the underlying metric with its uncertainty where the source provides it).
4. Each Suggested_Action SHALL carry status OBSERVED; the queue SHALL NOT assert a PREDICTED or SIMULATED action.

### Requirement 2: Retailer-appropriate, human-gated, non-contamination actions

**User Story:** As a responsible publisher, I want actions phrased as retailer
decision support with a review gate, so the tool never issues directives or
implies contamination.

#### Acceptance Criteria

1. Every Suggested_Action SHALL be a retailer-appropriate action verb (prioritize testing/monitoring, request supplier verification, protect access, scrutinize sourcing, gather more information) and SHALL NOT use "recall", "contaminated", "unsafe", or any regulatory directive.
2. Every Suggested_Action SHALL carry a Human_Review flag set true.
3. The Action_Queue SHALL NOT claim any product is contaminated or safe, and SHALL NOT infer human illness or causation from a surveillance signal.

### Requirement 3: S05 is corroboration only, never an action trigger

**User Story:** As a reviewer, I want human-outbreak data used only as context,
so temporal similarity is never turned into an operational trigger.

#### Acceptance Criteria

1. The Action_Queue SHALL NOT generate a Suggested_Action whose sole Triggering_Signal is CDC NORS human-outbreak data.
2. WHEN a state with an action also has NORS corroboration in the overlap window THEN S05 data MAY be attached as supporting context, explicitly labeled corroboration and non-causal.

### Requirement 4: Transparent ranking and all three pathogens

**User Story:** As a reviewer, I want the ranking method stated and all pathogens
represented, so the queue is auditable and complete.

#### Acceptance Criteria

1. The Action_Queue SHALL rank actions by a documented, deterministic rule (e.g. signal strength and support), recorded in the artifact method metadata, with no black-box score.
2. The Action_Queue SHALL cover Salmonella, Listeria, and STEC wherever each has gated signals, and SHALL NOT drop a pathogen that has qualifying signals.
3. WHEN no qualifying signal exists for a pathogen/source THEN the queue SHALL simply contain no action for it (an empty result is honest, never a fabricated action).

### Requirement 5: Typed, provenance-bearing artifact

**User Story:** As a frontend developer, I want the queue as a versioned,
schema-validated artifact consistent with the existing contract.

#### Acceptance Criteria

1. The module SHALL export `action_queue.json` validated against an `ActionQueueItem` TypedDict before writing.
2. Each record SHALL carry schema/method version, rank, pathogen, action, action_category, target (region/establishment/category), triggering source module, a plain-language rationale, the evidence summary, human_review (true), status (OBSERVED), and any corroboration note; fields MAY be null with a reason.
3. The module SHALL register the artifact in the exporter and manifest and SHALL NOT read from any hardcoded legacy directory.
4. The TypeScript interface SHALL mirror the Python TypedDict and be covered by the existing schema parity mechanism.

### Requirement 6: Surveillance Actions interaction

**User Story:** As the Decision_Maker, I want a single ranked action surface with
visible evidence and review gates, so I can decide where to act next.

#### Acceptance Criteria

1. The Web_App SHALL present a Surveillance Actions view fed by `action_queue.json` with a pathogen filter and a source-module filter (all three pathogens first-class).
2. Each action SHALL display its rank, the action text, the target, the triggering source, the evidence summary, and a visible Human_Review indicator.
3. The view SHALL state that these are suggestions derived from OBSERVED surveillance requiring human review, and SHALL distinguish itself from the base platform's SIMULATED optimizer action panel.
4. WHEN the artifact is missing or empty THEN the view SHALL show an explicit empty/not-available state and other panels SHALL continue to render.
5. The Web_App SHALL preserve the navy/teal theme and restrict orange/red to active elevated-signal / human-review emphasis.

### Requirement 7: Tests and no regression

**User Story:** As a maintainer, I want the action logic covered by tests that
lock its honesty rules.

#### Acceptance Criteria

1. Tests SHALL assert no action is generated solely from S05 CDC human-outbreak data.
2. Tests SHALL assert every action carries human_review=true and status OBSERVED.
3. Tests SHALL assert no action uses a forbidden term ("recall", "contaminated", "unsafe", regulatory directive).
4. Tests SHALL assert a below-support signal produces no action.
5. Tests SHALL assert the ranking is deterministic and all three pathogens appear when they have qualifying signals.
6. The module SHALL NOT replace or weaken any existing passing test; the full suite SHALL pass after it lands.

## Constraints and Assumptions

- **Terminal**: Kiro's integrated PowerShell is unreliable this session for long/append operations; verification of long commands (full test suites) runs in external CMD.
- **No new data or science**: this module is a deterministic decision layer over existing artifacts (S01/S03/S04/S06 caches, S05 for corroboration context only). It adds no raw data and trains no model.
- **Distinct from the base optimizer panel**: the base platform's Recommended Action Panel is driven by the SIMULATED operational optimizer; Surveillance Actions is a separate surface derived from OBSERVED surveillance and is labeled as such.
- **Non-causality / responsible use (brief guardrail)**: surveillance signals never establish contamination or human illness; actions are retailer decision support with a human-review gate, never directives or regulatory determinations.
