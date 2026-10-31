# Requirements Document
## Introduction
**S03 — Persistent Establishment Surveillance Monitor.** S03 is an expansion
module for VulneraSafe AI. It identifies FSIS establishments (plants) with
repeatedly elevated historical pathogen positivity, across all three pathogens,
**without confusing low testing with safety**. It is the establishment-level
companion to S04's state-level persistent/emerging detector.

The governing science specification is
`VulneraSafe_Kiro_Ready_to_Use_Packets/03_Scientific_Research_Modules/S03_persistent_establishment_surveillance_monitor.docx`
(extracted text reviewed). Where this document and that spec conflict, the spec
governs and the conflict is recorded in Constraints and Assumptions.

The single hardest rule in S03 is that **absence of positives is not evidence of
safety**: an establishment with few tests is uncertain, never "clean". The
ranking therefore uses an uncertainty-aware beta-binomial Empirical Bayes
posterior with partial pooling, not a raw positivity rate, so a thinly-sampled
establishment is shrunk toward the peer rate and carries a wide credible
interval rather than topping or bottoming the list spuriously.

S03 reuses the base platform's vocabulary and data contract and does not replace
or weaken any existing analysis, artifact, or test.

## Glossary

- **S03_Monitor**: The persistent-establishment-surveillance component added by this module.
- **Establishment**: An FSIS-regulated plant identified by `establishment_id` (with `establishment_number` / `establishment_name` / `establishment_state` as published by FSIS). A sampling location, never a product destination or an illness location.
- **Eligible_Sample**: A valid diagnostic test for the pathogen at an establishment (positive or negative; non-diagnostic excluded), using the S01 tri-state classification.
- **EB_Posterior**: A beta-binomial Empirical Bayes posterior positivity estimate for an establishment, partially pooled toward the pathogen's population (peer) rate; the beta prior is estimated from the pathogen's establishment distribution at development time.
- **Credible_Interval**: The 95% posterior credible interval on the EB_Posterior; wide when support is low, narrow when support is high.
- **Partial_Pooling**: Shrinkage of each establishment's observed rate toward the peer rate in inverse proportion to its sample support, so low-support establishments do not produce extreme rankings.
- **Persistence_Evidence**: The combination of repeated-positive periods, recent support, and sampling-gap awareness used to describe how consistently and recently an establishment has been elevated.
- **Sample_Support**: The eligible-sample count behind an establishment's estimate; the basis for the low-support honesty rule.
- **Low_Support**: An establishment whose eligible-sample count is below a fixed minimum; reported as uncertain, never as "normal" or "safe".
- **Known_Establishment / Unseen_Establishment**: In any evaluation, establishments present before a cutoff (known) versus appearing only after it (unseen), reported separately.
- **Verified_Coordinates**: Latitude/longitude that are actually present and validated in the source data; S03 never fabricates establishment coordinates.
- **OBSERVED / PREDICTED / SIMULATED**: Status tags from the base platform's data contract. S03 emits OBSERVED (descriptive surveillance) and, only where a defensible establishment forecast is validated, PREDICTED; never SIMULATED.
- **establishment_surveillance.json**: The typed artifact S03 exports, registered in the exporter and manifest.
- **EstablishmentSurveillanceRecord**: The TypedDict (Python) / interface (TS) for one record of `establishment_surveillance.json`.

## Requirements

### Requirement 1: Uncertainty-aware establishment ranking

**User Story:** As the Food Safety Operations Director, I want establishments
ranked by a statistically honest positivity estimate, so that a plant that was
simply tested a lot is not confused with a plant that is genuinely elevated, and
a barely-tested plant is not mistaken for safe.

#### Acceptance Criteria

1. S03 SHALL estimate each establishment's positivity as an EB_Posterior with a 95% Credible_Interval, computed with Partial_Pooling toward the pathogen peer rate.
2. WHEN an establishment has low Sample_Support THEN its EB_Posterior SHALL be shrunk toward the peer rate and its Credible_Interval SHALL be correspondingly wide.
3. S03 SHALL rank establishments by the EB_Posterior (not the raw rate) and SHALL NOT emit any fabricated or ad-hoc rank score.
4. The S03_Monitor SHALL NOT present an establishment with few tests and no positives as "safe", "clean", or equivalent; it SHALL present it as low-support / uncertain.

### Requirement 2: Persistence evidence, not a single spike

**User Story:** As a reviewer, I want "persistent" to mean repeatedly and
recently elevated, so that one old positive does not brand a plant a chronic
offender.

#### Acceptance Criteria

1. S03 SHALL build an establishment × program × period history of positive and Eligible_Sample counts.
2. S03 SHALL record, per establishment, the number of repeated-positive periods, the recency of support, and any sampling gaps as Persistence_Evidence.
3. WHEN an establishment's positives are old and it has no recent support THEN S03 SHALL distinguish it from a currently-supported persistently-elevated establishment rather than ranking them identically.

### Requirement 3: Leakage-safe, dev-fixed method

**User Story:** As a data scientist, I want the prior and any thresholds fixed
from development-time evidence and no future data used, so the analysis is
honest and reproducible.

#### Acceptance Criteria

1. The beta prior and all thresholds SHALL be fixed from development-time evidence and recorded in the artifact method metadata.
2. WHEN S03 computes any period-specific or predictive quantity THEN it SHALL use only observations available at or before that period.
3. The S03_Monitor SHALL NOT use any future-period observation when computing a current estimate, threshold, or flag.

### Requirement 4: Per-pathogen confidence and optional forecast

**User Story:** As the Director, I want each pathogen handled at the confidence
its data supports, with no forced facility forecast where events are too rare.

#### Acceptance Criteria

1. S03 SHALL compute the descriptive EB surveillance layer for Salmonella, Listeria, and STEC.
2. IF a pathogen's establishment-level events are too rare for a defensible forecast THEN S03 SHALL provide the descriptive layer only and SHALL mark the predictive layer unavailable with a reason, never a fabricated forecast.
3. IF an establishment forecast is produced THEN it SHALL be validated (calibration and future-positive capture, familiar vs. unseen establishments separately) and beat the equal-effort and EB-persistence baselines, else it SHALL be omitted and recorded as not shown.
4. S03 SHALL NOT drop a pathogen from the artifact for lack of predictive signal.

### Requirement 5: Anonymization and no fabricated relationships

**User Story:** As a responsible publisher, I want establishment surveillance
shown without unnecessary personal/contact detail and without implying any
commercial relationship that is not in the data.

#### Acceptance Criteria

1. The artifact SHALL identify an establishment only by `establishment_id` and the already-public FSIS identity fields (number, name, state) and SHALL NOT include contact details such as address or phone.
2. The S03_Monitor SHALL NOT claim or imply that any establishment is a supplier to any retailer or to the Decision_Maker.
3. The S03_Monitor SHALL NOT synthesize any establishment-to-retailer or establishment-to-product-destination relationship.

### Requirement 6: Typed, provenance-bearing artifact

**User Story:** As a frontend developer, I want S03's output as a versioned,
schema-validated artifact consistent with the existing contract.

#### Acceptance Criteria

1. S03 SHALL export `establishment_surveillance.json` validated against an `EstablishmentSurveillanceRecord` TypedDict before writing.
2. Each record SHALL carry schema/method version, provenance, pathogen, commodity, region (state), establishment identity (anonymized per Req 5), Sample_Support, observed positivity, EB_Posterior and Credible_Interval, Persistence_Evidence, descriptive/predictive status, status tag, availability_status, and unavailable_reason; fields MAY be null with a reason.
3. WHEN an establishment or pathogen cannot support the analysis THEN S03 SHALL emit an explicit unavailable record with a reason and null numerics, never fabricated values.
4. S03 SHALL register the artifact in the exporter and manifest and SHALL NOT read from any hardcoded legacy directory.
5. The TypeScript interface SHALL mirror the Python TypedDict and be covered by the existing schema parity mechanism.

### Requirement 7: Supplier Monitor interaction

**User Story:** As the Director, I want to browse establishments by pathogen and
region, see each one's honest estimate and uncertainty, and only see map points
where real coordinates exist.

#### Acceptance Criteria

1. The Web_App SHALL present a Supplier Monitor view fed by `establishment_surveillance.json` with a pathogen selector (all three first-class) and a region filter.
2. The view SHALL show each establishment's EB_Posterior with its Credible_Interval, its Sample_Support, and its Persistence_Evidence, with a plain-language "how to read this" explanation of why low support is uncertain, not safe.
3. The view SHALL place a facility map point only for an establishment with Verified_Coordinates, and SHALL show an explicit "coordinates not available" state otherwise, never a fabricated point.
4. WHEN the artifact is missing or an establishment/pathogen is unavailable THEN the Web_App SHALL show an explicit not-available / empty state and other panels SHALL continue to render.
5. The Web_App SHALL preserve the existing navy/teal theme and restrict orange/red to active elevated-establishment indicators.

### Requirement 8: Tests and no regression

**User Story:** As a maintainer, I want S03 covered by tests that lock its
honesty rules and leave existing tests intact.

#### Acceptance Criteria

1. Tests SHALL assert no sample is double-counted across the establishment × program × period history.
2. Tests SHALL assert posterior smoothing: a low-support establishment's EB_Posterior lies between its raw rate and the peer rate, with a wider Credible_Interval than a high-support establishment.
3. Tests SHALL assert anonymization: no contact-detail field appears in the artifact.
4. Tests SHALL assert known vs. unseen establishment separation in any evaluation output.
5. Tests SHALL assert no synthetic supplier/retailer relationship is present.
6. Tests SHALL assert leakage-safety (no future-period data in a current estimate) and denominator conservation (positive_n ≤ sample_n; rates and intervals in [0,1]).
7. S03 SHALL NOT replace or weaken any existing passing test; the full suite SHALL pass after S03 lands.

## Constraints and Assumptions

- **Terminal**: Kiro's integrated PowerShell is non-functional this session; all Python/npm/file-write commands run in an external CMD and file contents are hand-pasted.
- **Frontend target**: A new Supplier Monitor tab this milestone; the full facility map page (Page 06) is deferred to the Page-06 build and noted in the UI. The map in this milestone shows verified coordinates if present, else an honest unavailable state.
- **Coordinates**: FSIS sampling data carries `establishment_state` but is not assumed to carry verified latitude/longitude; if none are present, the facility map reports coordinates unavailable rather than fabricating points (confirmed during the inspect step).
- **No fabrication (from source safety checklist)**: FSIS facility geography ≠ product destination ≠ county human illness; model risk never confirms contamination; no invented facility→retailer links, county forecasts, pregnancy counts, verified recalls, or simulated outcomes. If no predictive signal exists, ship the descriptive layer with stated uncertainty.
- **Reuse**: S03 reuses the S01 readers, the status-tag vocabulary, Positivity/Program_Denominator semantics, the period machinery introduced in S04, and the schema/parity mechanism; it introduces no new legacy-directory reads.
- **Per-pathogen expectation**: Salmonella is expected to carry the strongest establishment signal; Listeria and STEC are expected to be descriptive-only given rare-event sparsity (confirmed empirically during implementation).
