# Requirements Document

## Introduction

S02 — Seasonal / Temporal Hazard Patterns is an additive analytical module for the existing VulneraSafe AI platform. It gives the Food Safety Operations Director a new analytical lens, surfaced in a new web tab, that decomposes each FSIS-monitored pathogen's historical positivity time series into month-of-year and quarter seasonality plus a long-run trend, using only the FSIS laboratory sampling history already ingested in this project. It answers one operational question: in which parts of the year is each hazard (Salmonella in raw poultry, Listeria in RTE, STEC in raw beef) most elevated, so that inspection and testing cadence can be planned seasonally.

This module is strictly additive. It does not modify, re-run, or re-key any existing module (S01, S03–S07), and it leaves every existing web tab untouched. It reads existing harmonized FSIS data read-only through the same helpers the sibling modules use and never mutates shared inputs.

The module performs no new modeling and trains no model. It is a descriptive decomposition of historical OBSERVED positivity only. It never predicts future contamination, never implies that any shipment is contaminated, and always labels seasonality as a historical pattern. Every value the module reports is OBSERVED (measured or published FSIS surveillance); there is no PREDICTED, SIMULATED, placeholder, or synthetic data in this module. Where a pathogen, region, or period lacks enough samples to compute a seasonal statistic honestly, the module records an explicit availability status with a reason instead of fabricating a value.

The module mirrors the established identity and honesty conventions of its sibling modules: a fixed `MODULE_ID`, a fixed `METHOD_VERSION`, a dedicated cache artifact, a single source file, explicit and testable minimum-sample gates, explicit normalization/decomposition scopes, and flow through the shared exporter with a TypedDict schema, a mirrored TypeScript type, a parity test, and a forbidden-field guard. The module supports the brief's Task 2 (data-science rigor, validation, reproducibility) and Task 1 (One Health, operational relevance) framing. Food safety is the hard constraint; food availability and access are secondary and never override it.

## Glossary

- **S02_Module**: The seasonal/temporal hazard-patterns module defined by this document, identified by `MODULE_ID = "S02"` and `METHOD_VERSION = "s02.v1"`, implemented in `src/analysis/seasonal_hazard_patterns.py`, caching to `data/interim/s02_seasonal_hazard_patterns.json`.
- **Positivity_Rate**: The number of pathogen-positive samples divided by the FSIS program denominator for a given pathogen and period, as already defined and computed by the project's harmonized FSIS data.
- **Positivity_Series**: The ordered historical sequence of OBSERVED Positivity_Rate values for one pathogen over the available FSIS reporting periods.
- **Seasonal_Decomposition**: The separation of a Positivity_Series into a seasonal component (recurring within-year pattern), a trend component (long-run level change), and a residual component, computed from OBSERVED history only.
- **Month_Of_Year_Positivity**: The OBSERVED positivity statistic aggregated by calendar month (January–December) across all available years for one pathogen.
- **Quarter_Positivity**: The OBSERVED positivity statistic aggregated by calendar quarter (Q1–Q4) across all available years for one pathogen.
- **Seasonality**: A recurring within-year pattern in Month_Of_Year_Positivity or Quarter_Positivity; a historical description, never a forecast.
- **Trend**: The long-run direction and magnitude of change in the Positivity_Series level across years, computed from OBSERVED history only.
- **Peak_Season**: The month or quarter whose OBSERVED positivity statistic is the highest for a pathogen, reported only when the Minimum_Sample_Gate is satisfied.
- **Minimum_Sample_Gate**: A documented, testable minimum underlying sample count that a pathogen, period bucket, or decomposition component must meet before its seasonal statistic is reported; otherwise the statistic is marked unavailable with the count that was found.
- **Availability_Status**: An explicit per-lens status in {available, unavailable} recorded for every seasonal statistic, accompanied by an `unavailable_reason` string whenever the status is unavailable.
- **S02_Cache**: The module's cache artifact at `data/interim/s02_seasonal_hazard_patterns.json`.
- **S02_Artifact**: The exporter-produced web artifact derived from the S02_Cache, described by a TypedDict in `src/artifacts/schemas.py` and a mirrored TypeScript type in `web/src/types/artifacts.ts`.
- **S02_Tab**: The new web tab in the React/TypeScript/Vite application that presents the S02 seasonal lens; distinct from, and not a drill-down into, any existing tab.
- **OBSERVED**: A data value recorded from a real empirical FSIS surveillance source; the only provenance class this module produces.
- **Exporter**: The shared artifact exporter in `src/artifacts/exporter.py` that validates each artifact against its TypedDict and applies the forbidden-field guard before writing.

## Requirements

### Requirement 1: Module identity and additive isolation (Task 1; Team science, reproducibility, and communication)

**User Story:** As a judge assessing the platform, I want S02 to be a clearly identified, self-contained additive module that never alters existing modules, so that I can trust it extends the platform without regressing any prior result.

#### Acceptance Criteria

1. THE S02_Module SHALL declare `MODULE_ID` equal to "S02" and `METHOD_VERSION` equal to "s02.v1" and SHALL record both values in the S02_Cache.
2. THE S02_Module SHALL be implemented in `src/analysis/seasonal_hazard_patterns.py` and SHALL write its cache exclusively to `data/interim/s02_seasonal_hazard_patterns.json`.
3. THE S02_Module SHALL NOT write to, delete, or modify any cache artifact, source file, or web file belonging to modules S01 or S03 through S07.
4. THE S02_Module SHALL read existing harmonized FSIS data read-only and SHALL NOT mutate any shared input it reads.
5. IF the S02_Module detects that a shared FSIS input it read has been modified by the module, THEN THE S02_Module SHALL halt and record an error indication identifying the mutated input rather than continuing.

### Requirement 2: FSIS-only read-only input scope (Task 1; One Health multi-source integration)

**User Story:** As a data scientist, I want S02 to draw solely on FSIS laboratory sampling history already ingested in this project, so that the seasonal lens introduces no new data source and stays reproducible from recorded inputs.

#### Acceptance Criteria

1. THE S02_Module SHALL derive every seasonal statistic exclusively from the FSIS laboratory sampling history already ingested in this project, read through the same read-only helpers used by the sibling FSIS modules.
2. THE S02_Module SHALL NOT ingest, download, or reference any data source that is not already part of the project's ingested FSIS sampling history.
3. THE S02_Module SHALL record in the S02_Cache, for each pathogen, the identifier of the FSIS input used and the set of reporting periods read.
4. IF a required FSIS input is absent or unreadable for a pathogen, THEN THE S02_Module SHALL mark that pathogen's seasonal statistics unavailable with an `unavailable_reason` identifying the missing input and SHALL continue with the pathogens whose inputs are available.

### Requirement 3: Seasonal and trend decomposition of OBSERVED positivity (Task 2; Data science rigor and validation)

**User Story:** As the Food Safety Operations Director, I want each pathogen's historical positivity separated into month-of-year and quarter seasonality plus a long-run trend, so that I can see when in the year each hazard is most elevated.

#### Acceptance Criteria

1. THE S02_Module SHALL compute, for each of Salmonella in raw poultry, Listeria in RTE, and STEC in raw beef, a Month_Of_Year_Positivity statistic for each calendar month and a Quarter_Positivity statistic for each calendar quarter from the OBSERVED Positivity_Series.
2. THE S02_Module SHALL compute a Seasonal_Decomposition of each pathogen's Positivity_Series into a seasonal component, a trend component, and a residual component, using OBSERVED history only.
3. THE S02_Module SHALL record, for each reported seasonal statistic, the underlying OBSERVED sample count and positive count on which the statistic was computed.
4. WHEN the Month_Of_Year_Positivity and Quarter_Positivity statistics for a pathogen are available, THE S02_Module SHALL record that pathogen's Peak_Season as the month and the quarter with the highest OBSERVED positivity statistic.
5. THE S02_Module SHALL label every seasonal and trend statistic as OBSERVED and as a historical pattern.

### Requirement 4: Minimum-sample gating with explicit availability (Task 2; Data science rigor and validation)

**User Story:** As a data scientist, I want a seasonal statistic reported only when its underlying sample counts meet a documented minimum, so that no seasonal pattern rests on too few samples.

#### Acceptance Criteria

1. THE S02_Module SHALL define a documented Minimum_Sample_Gate specifying the minimum underlying OBSERVED sample count required per pathogen, per month bucket, and per quarter bucket before the corresponding seasonal statistic is reported.
2. WHEN a pathogen, a month bucket, or a quarter bucket satisfies the Minimum_Sample_Gate, THE S02_Module SHALL set that statistic's Availability_Status to available and report the computed value.
3. IF a pathogen, a month bucket, or a quarter bucket does not satisfy the Minimum_Sample_Gate, THEN THE S02_Module SHALL set that statistic's Availability_Status to unavailable, record an `unavailable_reason` naming the unmet gate, and record the actual sample count that was found, and SHALL NOT report a computed value for that statistic.
4. THE S02_Module SHALL define the minimum number of distinct years of history required to report a Trend component and SHALL mark the Trend unavailable with an `unavailable_reason` and the number of years found when that minimum is not met.
5. THE S02_Module SHALL NOT substitute a fabricated, estimated, interpolated, or placeholder value for any seasonal or trend statistic whose Availability_Status is unavailable.

### Requirement 5: No prediction and no contamination implication (Guardrails; Operational decision support)

**User Story:** As a judge assessing responsible use, I want S02 to stay descriptive and never imply prediction or contamination, so that a historical seasonal pattern is not mistaken for a forecast or a safety determination.

#### Acceptance Criteria

1. THE S02_Module SHALL present every output as a historical description of OBSERVED positivity and SHALL NOT produce any PREDICTED, SIMULATED, placeholder, or synthetic value.
2. THE S02_Module SHALL NOT state or imply that positivity in any future period will occur, that any shipment or lot is contaminated, or that a product is safe or unsafe.
3. THE S02_Module SHALL train no model and SHALL perform no new modeling, limiting its computation to descriptive decomposition and aggregation of OBSERVED history.
4. WHEN the S02_Tab presents a Peak_Season or seasonal pattern, THE S02_Tab SHALL label it as a historical seasonal pattern and SHALL NOT label it as a prediction or a risk forecast.

### Requirement 6: Exporter, schema, and forbidden-field compliance (Task 4; Kiro implementation and usability)

**User Story:** As a developer maintaining the data contract, I want the S02 artifact to flow through the shared exporter with a validated schema and a forbidden-field guard, so that the new artifact matches the platform's contract and cannot carry fabricated fields.

#### Acceptance Criteria

1. THE S02_Module SHALL define a TypedDict for the S02_Artifact in `src/artifacts/schemas.py` and a mirrored TypeScript type for the same artifact in `web/src/types/artifacts.ts`.
2. THE Exporter SHALL produce the S02_Artifact from the S02_Cache and SHALL validate the S02_Artifact against its TypedDict before writing, rejecting the artifact with a schema validation error that identifies the offending field if validation fails.
3. THE Exporter SHALL apply a forbidden-field guard to the S02_Artifact that rejects the artifact with a schema validation error when any field name contains a banned fabrication token, and SHALL write nothing when the guard is triggered.
4. THE S02_Artifact SHALL tag every value-bearing field as OBSERVED and SHALL carry, for each seasonal statistic, its Availability_Status and, when unavailable, its `unavailable_reason`.
5. THE S02_Module SHALL include a parity test verifying that the Python TypedDict for the S02_Artifact and the mirrored TypeScript type define the same field names, reporting a failure that identifies any field present on only one side.

### Requirement 7: New seasonal web tab (Task 4; Kiro implementation and usability)

**User Story:** As the Food Safety Operations Director, I want a dedicated seasonal tab that shows each pathogen's month-of-year and quarter positivity, trend, and peak season, so that I can plan inspection and testing cadence by time of year without disturbing the existing views.

#### Acceptance Criteria

1. THE Web_App SHALL provide the S02_Tab as a new tab that is distinct from, and not a drill-down into, any existing tab, and SHALL leave all existing tabs unchanged.
2. WHEN the S02_Tab loads the S02_Artifact, THE S02_Tab SHALL present, per pathogen, the Month_Of_Year_Positivity, the Quarter_Positivity, the Trend, and the Peak_Season for statistics whose Availability_Status is available.
3. IF a seasonal statistic's Availability_Status is unavailable, THEN THE S02_Tab SHALL display an explicit not-available indication showing the `unavailable_reason` rather than rendering a blank or fabricated value.
4. WHEN the Food Safety Operations Director selects a pathogen among Salmonella, Listeria, and STEC on the S02_Tab, THE S02_Tab SHALL update the displayed seasonal statistics to reflect the selected pathogen.
5. IF the S02_Artifact is missing, unreadable, or invalid at load time, THEN THE S02_Tab SHALL display an error indication identifying the S02_Artifact and SHALL NOT render fabricated seasonal content.

### Requirement 8: Reproducibility of the cache from recorded FSIS inputs (Task 5; Team science, reproducibility, and communication)

**User Story:** As a judge assessing reproducibility, I want the S02 build to regenerate identical cache contents from the recorded FSIS inputs, so that the seasonal results are verifiable and deterministic.

#### Acceptance Criteria

1. WHEN the S02 build script is executed against the recorded FSIS inputs, THE S02_Module SHALL regenerate an S02_Cache whose contents match the previously produced S02_Cache, or SHALL record each deviation and its cause.
2. THE S02_Module SHALL record in the S02_Cache the `MODULE_ID`, the `METHOD_VERSION`, and the set of FSIS reporting periods read, such that the inputs to each run are auditable.
3. THE S02_Module SHALL compute all seasonal and trend statistics deterministically, such that identical recorded FSIS inputs produce identical S02_Cache contents.
