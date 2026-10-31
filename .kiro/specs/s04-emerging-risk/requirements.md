# Requirements Document

## Introduction

**S04 — Persistent vs. Emerging Risk Detector.** S04 is an expansion module for VulneraSafe AI. It adds a new analytical
capability on top of the completed base platform: distinguishing **persistent**
elevated food-safety surveillance (categories/regions that have been high for a
long time) from **emerging** signals (a statistically unusual *new* increase),
across all three pathogens (Salmonella in raw poultry, Listeria in RTE, STEC in
raw beef).

The governing science specification is
`VulneraSafe_Kiro_Ready_to_Use_Packets/03_Scientific_Research_Modules/S04_persistent_versus_emerging_risk_detector.docx`
(extracted text reviewed). Where this requirements document and that spec
conflict, the spec governs and the conflict is recorded in Constraints and
Assumptions.

The single hardest rule in S04, stated repeatedly in the source spec, is a
**claims-discipline rule**: an observed retrospective change must never be
presented as an early prediction/forecast. Retrospective anomaly and (optional,
separately validated) prospective forecast are first-class, separately labeled
concepts. This document treats that rule as a requirement, not a design detail.

S04 reuses the base platform's vocabulary and data contract. It does not
replace or weaken any existing analysis, artifact, or test.

## Glossary

- **S04_Detector**: The persistent-vs-emerging analytical component added by this module.
- **Modeling_Unit**: As in the base platform — pathogen × commodity × region × period. S04's labeled unit is **state × period** per pathogen.
- **Period**: A fiscal-period bucket (monthly or quarterly) selected per pathogen from sample availability; the unit of the time series.
- **Positivity_Rate**: Pathogen-positive samples ÷ the correct program denominator for a Modeling_Unit and period (same definition as the base platform).
- **Trailing_Baseline**: A smoothed expectation for a unit's positivity computed **only** from that unit's periods strictly before the period under evaluation, with a minimum-support requirement.
- **Minimum_Support**: The minimum sample denominator (n) a unit-period must have before S04 will assign it a baseline, a flag, or a rate; below it the cell is `low_support`, never silently treated as zero/negative.
- **Persistent_Score**: A measure of how consistently a unit's positivity has sat above its peer/historical baseline over the observed window (long-run elevation), computed retrospectively.
- **Retrospective_Anomaly**: A period flagged, using only data available in or before that period, as a statistically unusual increase relative to the Trailing_Baseline. Status OBSERVED. Never labeled a forecast.
- **Prospective_Forecast_Alert**: An OPTIONAL, separately trained alert that a future period will be anomalous, trained strictly before a cutoff and tested only on later data. Status PREDICTED. Produced only if it passes validation against persistence; otherwise omitted entirely.
- **Change_Detector**: The sequential method (EWMA / CUSUM / posterior exceedance) that converts a unit's running observations into Retrospective_Anomaly flags.
- **Persistence_Baseline**: The naive reference "the next period looks like the last period(s)" against which any Prospective_Forecast_Alert's precision/recall and lead time must be compared before it may be shown.
- **Lead_Time**: For a validated prospective alert, how many periods ahead of a statistically supported future change the alert fired, reported with availability-lag assumptions.
- **Availability_Lag**: The real delay between a sample's collection and when its result would actually be available; used so a prospective alert is never credited with data it could not have had in time.
- **Leakage**: Use of any information from the evaluated period or later when computing that period's baseline, threshold, or forecast (same definition as the base platform; forbidden).
- **OBSERVED / PREDICTED / SIMULATED**: Status tags from the base platform's data contract. S04 emits only OBSERVED (retrospective) and, if validated, PREDICTED (prospective). Never SIMULATED.
- **emerging_risk.json**: The typed artifact S04 exports, registered in the exporter and manifest.
- **EmergingRiskStratum**: The TypedDict (Python) / interface (TS) describing one record of `emerging_risk.json`.

## Requirements

### Requirement 1: Honest persistent vs. emerging distinction

**User Story:** As the Food Safety Operations Director, I want to tell apart a
problem that has been bad for a long time from one that just started getting
worse, so that I direct new attention to genuinely new signals and do not
mistake a long-standing issue for a fresh emergency.

#### Acceptance Criteria

1. WHEN S04 reports a unit THEN it SHALL present a Persistent_Score and a Retrospective_Anomaly state as two distinct, separately labeled fields.
2. WHEN a unit has been elevated for a long time but has no new increase THEN S04 SHALL classify it as persistent and SHALL NOT flag it as an emerging anomaly for the current period.
3. WHEN a unit shows a statistically unusual new increase THEN S04 SHALL flag it as a Retrospective_Anomaly for the period(s) in which the increase is supported.
4. The S04_Detector SHALL NOT describe any Retrospective_Anomaly as an early prediction, forecast, or early warning in any field, label, or UI string.

### Requirement 2: Leakage-safe retrospective anomaly detection

**User Story:** As a data scientist reviewing the method, I want every
retrospective flag to use only information available in or before its own
period, so that the analysis is honest and reproducible.

#### Acceptance Criteria

1. WHEN S04 computes a Trailing_Baseline for a period THEN it SHALL use only observations from strictly earlier periods of the same unit.
2. WHEN S04 flags a Retrospective_Anomaly for a period THEN the threshold and baseline used SHALL be derived only from data in or before that period.
3. The S04_Detector SHALL NOT use any future-period value when computing a current-period baseline, threshold, or flag.
4. S04 SHALL apply a seasonal adjustment computed only from prior periods, and SHALL record the adjustment method.

### Requirement 3: Minimum support and honest low-n handling

**User Story:** As a reviewer, I want thinly sampled cells to be marked as
low-support rather than reported as safe, so that absence of evidence is never
shown as evidence of absence.

#### Acceptance Criteria

1. WHEN a unit-period has a denominator below Minimum_Support THEN S04 SHALL label it `low_support` and SHALL NOT assign it a Retrospective_Anomaly flag of "normal/negative".
2. The S04_Detector SHALL NOT treat a low-support unit-period as a non-anomaly by default.
3. WHEN S04 omits or de-emphasizes a unit for low support THEN it SHALL record the support value and the Minimum_Support threshold used.
4. The Minimum_Support threshold SHALL be fixed from development-time evidence and recorded in the artifact method metadata.

### Requirement 4: Optional, separately validated prospective forecast

**User Story:** As the Director, I want any forward-looking alert to be clearly
separated from retrospective findings and only shown if it actually beats a
naive guess, so that I am not misled by a dressed-up description of the past.

#### Acceptance Criteria

1. IF S04 produces a Prospective_Forecast_Alert THEN it SHALL be trained strictly on data before a fixed cutoff and evaluated only on later data.
2. IF a Prospective_Forecast_Alert is produced THEN it SHALL carry status PREDICTED and SHALL be stored and labeled separately from Retrospective_Anomaly fields.
3. IF a Prospective_Forecast_Alert does not beat the Persistence_Baseline on precision/recall THEN S04 SHALL omit the prospective alert entirely and SHALL record that prediction did not improve on persistence.
4. WHEN S04 reports any Prospective_Forecast_Alert performance THEN it SHALL report precision, recall, alert volume, and Lead_Time with Availability_Lag assumptions stated.
5. The S04_Detector SHALL NOT present a Prospective_Forecast_Alert whose evaluation was performed on data used for its own threshold selection without labeling that evaluation as exploratory.

### Requirement 5: Typed, provenance-bearing artifact

**User Story:** As a frontend developer, I want S04's output as a versioned,
schema-validated artifact consistent with the existing contract, so that the web
app renders it safely and the parity test protects it.

#### Acceptance Criteria

1. S04 SHALL export `emerging_risk.json` validated against an `EmergingRiskStratum` TypedDict before writing.
2. Each record SHALL carry: artifact_version, module_id ("S04"), method_version, pathogen, commodity, geography_level, region, period, sample_n, positive_n, value, ci_low, ci_high, ci_method, trailing_baseline, persistent_score, retro_anomaly (bool), retro_threshold, prospective_alert (nullable), status, availability_status, unavailable_reason, fiscal_years, generated_at.
3. WHEN a pathogen or unit cannot support the analysis THEN S04 SHALL emit a record with availability_status="unavailable" and a plain-language unavailable_reason and null numeric fields, never fabricated numbers.
4. S04 SHALL register `emerging_risk.json` in the exporter and in the manifest, and SHALL NOT read from any hardcoded legacy directory.
5. The TypeScript interface for `EmergingRiskStratum` SHALL mirror the Python TypedDict and SHALL be covered by the existing schema parity mechanism.

### Requirement 6: All three pathogens remain first-class

**User Story:** As a reviewer, I want all three pathogens represented honestly,
with weaker ones shown as surveillance-only rather than dropped.

#### Acceptance Criteria

1. S04 SHALL compute the detector for Salmonella, Listeria, and STEC.
2. IF a pathogen's state×period series is too sparse for a defensible prospective forecast THEN S04 SHALL still provide the retrospective descriptive layer with explicit uncertainty, and SHALL mark the prospective layer unavailable with a reason.
3. S04 SHALL NOT drop a pathogen from the artifact for lack of predictive signal.

### Requirement 7: Dashboard interaction (trend + persistent/emerging states + time scrubber)

**User Story:** As the Director, I want to switch between persistent and emerging
views, see a trend over time, and scrub through periods, so that I can explore
where and when signals appear.

#### Acceptance Criteria

1. The Web_App SHALL present a selectable persistent / emerging view fed by `emerging_risk.json`.
2. The Web_App SHALL render a trend chart of positivity over periods for a selected unit, labeling the time scope.
3. The Web_App SHALL provide a time scrubber that selects a period and updates the displayed state to that period's values.
4. WHEN scrubbed to a given period THEN the view SHALL show only information available in or before that period for any anomaly state, consistent with Requirement 2.
5. WHEN the artifact is missing or a unit is unavailable THEN the Web_App SHALL show an explicit not-available / empty state, never a fabricated value, and other panels SHALL continue to render.
6. The Web_App SHALL preserve the existing navy/teal scientific light theme and SHALL restrict orange/red to active anomaly/alert states.

### Requirement 8: Tests and no regression

**User Story:** As a maintainer, I want S04 covered by tests that lock its
honesty rules and leave existing tests intact.

#### Acceptance Criteria

1. Tests SHALL assert a low-support unit-period is not flagged as a non-anomaly ("not flag low n as negative").
2. Tests SHALL assert no baseline/threshold uses a future period ("no future threshold").
3. Tests SHALL assert no Retrospective_Anomaly record is labeled as a forecast/PREDICTED.
4. Tests SHALL assert state×period records contain no duplicates for a given pathogen.
5. Tests SHALL assert denominator conservation (positive_n ≤ sample_n; rates in [0,1]).
6. S04 SHALL NOT replace or weaken any existing passing Python or web test; the full suite SHALL pass after S04 lands.

## Constraints and Assumptions

- **Terminal**: Kiro's integrated PowerShell is non-functional this session; all Python/npm/file-write commands run in an external CMD and file contents are hand-pasted into the editor.
- **Frontend target**: The source spec names "Risk Dashboard and Multi-Map." The Multi-Map page (Page 04) does not yet exist. S04 wires into the existing Risk Dashboard this milestone; the Multi-Map surface is deferred to the Page-04 build and noted in the UI.
- **No fabrication (from source safety checklist)**: FSIS facility geography ≠ product destination ≠ county human illness; model risk never confirms contamination; no invented county forecasts, facility→retailer links, pregnancy counts, verified recalls, or simulated lives saved. If no predictive signal exists, ship the descriptive retrospective layer with stated uncertainty.
- **Reuse**: S04 reuses the base platform's status tags, Modeling_Unit definition, Positivity_Rate/Program_Denominator semantics, and the schema/parity mechanism; it introduces no new legacy-directory reads.
- **Resolution**: monthly vs. quarterly period is selected per pathogen from sample availability, consistent with the base platform's feasibility logic, and the choice is recorded.
