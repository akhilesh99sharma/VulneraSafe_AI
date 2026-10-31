# Requirements Document

## Introduction

**S05 — Food Surveillance vs. Human Outbreaks Comparison.** S05 is an expansion
module for VulneraSafe AI. It brings in the challenge's required **human-health
surveillance stream** — real CDC National Outbreak Reporting System (NORS)
foodborne-outbreak data — and compares it against FSIS pathogen-surveillance
history, per pathogen × state × year, strictly as **corroboration**. It closes
the previously-placeholder human-health gap and completes the One Health picture
(human + food/animal + environment).

The governing science specification is
`VulneraSafe_Kiro_Ready_to_Use_Packets/03_Scientific_Research_Modules/S05_food_surveillance-human_outbreaks_comparison.docx`
(extracted text reviewed). Where this document and that spec conflict, the spec
governs and the conflict is recorded in Constraints and Assumptions.

The single hardest rule in S05 — and the challenge brief's central guardrail —
is **non-causality**: FSIS food-surveillance positivity and CDC human-outbreak
reports may be shown side by side as corroborating One Health context, but S05
SHALL NEVER assert a same-strain link, a food-testing-to-illness causal
relationship, or any human county-case forecast. Temporal or geographic
similarity is not proof of causation.

S05 reuses the base platform's data contract and FSIS readers and does not
replace or weaken any existing analysis, artifact, or test.

## Glossary

- **S05_Comparison**: The FSIS-vs-NORS corroboration component added by this module.
- **NORS**: CDC National Outbreak Reporting System; the public foodborne-outbreak dataset (data.cdc.gov dataset 5xkq-dg7x), downloaded to `data/raw/cdc_nors_outbreaks.csv`. One row per reported outbreak with Year, Month, State, Primary Mode, Etiology, Illnesses, Hospitalizations, Deaths.
- **Foodborne_Outbreak**: A NORS row with `Primary Mode == "Food"`; only these are compared against FSIS food surveillance.
- **Etiology_Standardization**: Conservative mapping of the free-text, sometimes multi-valued `Etiology` field to one of Salmonella / Listeria / STEC (STEC includes E. coli / O157 / Shiga-toxin variants); unmatched etiologies are excluded, never force-fit.
- **Comparison_Cell**: A (pathogen, state, year) unit carrying the FSIS surveillance summary and the NORS outbreak/illness counts for that cell.
- **Availability_Lag**: A modeled 365-day delay applied to NORS so an outbreak reported for year Y is treated as knowable no earlier than ~1 year later; this guarantees NORS is never used as a leading predictor of FSIS.
- **Overlap_Window**: The calendar years where both FSIS (≈2013–2026) and NORS (1998–2023) have data, i.e. ≈2013–2023; comparison is reported only within it, and FSIS years with no NORS counterpart are shown as NORS-not-available.
- **Coverage_Limited**: A pathogen or state-year with too few NORS foodborne outbreaks to support a meaningful comparison (e.g. Listeria, 144 outbreaks / 21 states); shown with an explicit limited-coverage flag, never silently treated as zero human burden.
- **Lead_Lag_Summary**: An EXPLORATORY descriptive lead–lag correlation between the FSIS and NORS series with permutation/bootstrap uncertainty; never a causal or predictive claim.
- **CORROBORATION**: The comparison status tag for S05 records — the two surveillance systems corroborate one another as One Health context, which is distinct from OBSERVED data and from a PREDICTED model output, and carries a mandatory no-causal-link warning.
- **one_health_human_comparison.json**: The typed artifact S05 exports, registered in the exporter and manifest.
- **HumanOutbreakComparison**: The TypedDict (Python) / interface (TS) for one record of the artifact.

## Requirements

### Requirement 1: Real human-health surveillance integrated as corroboration

**User Story:** As a judge assessing One Health integration, I want a real CDC
human-health signal compared against FSIS food surveillance, so the tool
connects the human and food/animal domains rather than analyzing food data in
isolation.

#### Acceptance Criteria

1. S05 SHALL ingest the real CDC NORS foodborne-outbreak data from `data/raw/cdc_nors_outbreaks.csv` and SHALL NOT use any placeholder or fabricated human-health values.
2. S05 SHALL compare, per Comparison_Cell, the FSIS surveillance summary against the NORS outbreak count and illness count for the same pathogen, state, and year.
3. Every S05 comparison record SHALL carry the CORROBORATION status and a plain-language no-causal-link warning.
4. S05 SHALL filter NORS to Foodborne_Outbreak rows and SHALL exclude non-food transmission modes from the comparison.

### Requirement 2: Non-causality and no fabricated human inference

**User Story:** As a reviewer, I want the comparison to never overclaim, so a
viewer cannot mistake corroboration for proof of linkage.

#### Acceptance Criteria

1. The S05_Comparison SHALL NOT assert a same-strain or genomic link between any FSIS sample and any NORS outbreak.
2. The S05_Comparison SHALL NOT assert that FSIS positivity caused, or is caused by, human illness.
3. The S05_Comparison SHALL NOT produce any human county-level case forecast or any sub-state human-illness estimate.
4. WHEN any lead–lag correlation is reported THEN it SHALL be labeled EXPLORATORY with permutation/bootstrap uncertainty and SHALL NOT be described as predictive or causal.

### Requirement 3: Leakage-safe 365-day availability lag

**User Story:** As a data scientist, I want NORS treated as information that
arrives late, so it can never act as a leading predictor of FSIS.

#### Acceptance Criteria

1. S05 SHALL apply a modeled 365-day Availability_Lag to every NORS outbreak so its knowledge-availability date is its event date plus 365 days.
2. The S05_Comparison SHALL NOT use any NORS value as a predictor of an FSIS value at or before the NORS value's availability date.
3. Comparison SHALL be reported only within the Overlap_Window; FSIS years with no available NORS counterpart SHALL be shown as NORS-not-available, never zero.

### Requirement 4: Careful pathogen standardization and honest coverage

**User Story:** As a reviewer, I want etiology mapped conservatively and thin
coverage flagged, so sparse human data is never dressed up as a full comparison.

#### Acceptance Criteria

1. S05 SHALL map the free-text NORS Etiology to Salmonella / Listeria / STEC conservatively (STEC covering E. coli / O157 / Shiga-toxin), splitting multi-etiology rows, and SHALL exclude unmatched etiologies rather than force-fitting them.
2. S05 SHALL compute all three pathogens; a pathogen with too few NORS foodborne outbreaks SHALL be marked Coverage_Limited with its real counts, never dropped and never shown as zero human burden.
3. S05 SHALL identify and flag state-years where sub-state or thin coverage does not support a meaningful comparison.
4. S05 SHALL report NORS sample size, missingness, and the publication/availability lag for each comparison.

### Requirement 5: Typed, provenance-bearing artifact

**User Story:** As a frontend developer, I want S05's output as a versioned,
schema-validated artifact consistent with the existing contract.

#### Acceptance Criteria

1. S05 SHALL export `one_health_human_comparison.json` validated against a `HumanOutbreakComparison` TypedDict before writing.
2. Each record SHALL carry schema/method version, data-source provenance (NORS dataset id + access date), pathogen, geography (state), period (year), the FSIS surveillance summary (sample_n / positive_n / positivity), the NORS outbreak_count and illness_count, availability-lag description, coverage flag, comparison status CORROBORATION, the standard status tag, availability_status, and unavailable_reason; fields MAY be null with a reason.
3. WHEN a pathogen/state-year cannot support comparison THEN S05 SHALL emit an explicit limited/unavailable record with a reason and null numerics, never fabricated values.
4. S05 SHALL register the artifact in the exporter and manifest and SHALL NOT read from any hardcoded legacy directory.
5. The TypeScript interface SHALL mirror the Python TypedDict and be covered by the existing schema parity mechanism.

### Requirement 6: One Health Insights interaction

**User Story:** As the Decision_Maker, I want to see the FSIS and human-outbreak
signals side by side over time with clear source labels, so I understand the
broader One Health picture behind a food-safety signal.

#### Acceptance Criteria

1. The Web_App SHALL present a One Health Insights view fed by `one_health_human_comparison.json` with a pathogen selector (all three first-class) and a state filter.
2. The view SHALL show linked FSIS and NORS time series for a selected pathogen/state with distinct source badges (FSIS food surveillance vs. CDC human outbreaks).
3. The view SHALL display a prominent no-causal-link explanation and label the human series as corroborating context, never as caused-by or predictive-of the FSIS series.
4. WHEN a pathogen/state-year is Coverage_Limited or NORS-not-available THEN the view SHALL show an explicit limited/not-available state, never a fabricated value, and other panels SHALL continue to render.
5. The Web_App SHALL preserve the existing navy/teal theme and restrict orange/red to active alert/elevated states.

### Requirement 7: Tests and no regression

**User Story:** As a maintainer, I want S05 covered by tests that lock its
honesty rules and leave existing tests intact.

#### Acceptance Criteria

1. Tests SHALL assert the 365-day Availability_Lag is enforced on NORS knowledge-availability dates.
2. Tests SHALL assert no NORS value is used as a predictor of an FSIS value at or before the NORS availability date (no CDC predictor leakage).
3. Tests SHALL assert a genuine distinction between a true zero (reported zero outbreaks) and missing/unavailable coverage.
4. Tests SHALL assert no record carries a causal label, a same-strain link, or a human county-case forecast.
5. Tests SHALL assert etiology standardization maps only genuine matches and excludes unmatched etiologies.
6. S05 SHALL NOT replace or weaken any existing passing test; the full suite SHALL pass after S05 lands.

## Constraints and Assumptions

- **Terminal**: Kiro's integrated PowerShell is non-functional this session; all Python/npm/file-write commands run in an external CMD and file contents are hand-pasted.
- **Data acquired this module**: CDC NORS was a 0-row placeholder; S05 downloads the real public NORS CSV (data.cdc.gov 5xkq-dg7x, ~66,713 rows, 24,729 foodborne) into `data/raw/`. Provenance (dataset id + access date) is recorded in the artifact.
- **Per-pathogen coverage (measured)**: Salmonella (3,409 foodborne outbreaks, all states) and STEC (873, 48 states) support full comparison; Listeria (144, 21 states) is Coverage_Limited. NORS year range 1998–2023; FSIS ≈2013–2026; the Overlap_Window is ≈2013–2023.
- **Geography/time grain**: NORS carries only Year + Month + State (no sub-state, no day). The comparison is at state × year; no sub-state human geography is produced.
- **Non-causality (brief guardrail)**: FSIS facility geography ≠ product destination ≠ county human illness; NORS history ≠ real-time human detection; model risk never confirms contamination. No same-strain links, county forecasts, or simulated outcomes.
- **Status concept**: CORROBORATION is a comparison-level label distinct from the core StatusTag union (OBSERVED/PREDICTED/SIMULATED), which is left unchanged; underlying NORS counts are OBSERVED facts, while the cross-system linkage is explicitly non-causal corroboration.
- **Reuse**: S05 reuses the FSIS state-period surveillance already produced by S04/S01 where possible and the schema/parity mechanism; it introduces no new legacy-directory reads.
