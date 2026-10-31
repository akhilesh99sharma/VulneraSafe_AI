# Requirements Document

## Introduction

The Facility Map is a new first-class web tab for VulneraSafe AI (a 2026 NAFSI Hub SENS-D Data Challenge submission) that geographically visualizes FSIS-sampled establishments carrying an elevated surveillance signal, as a sourcing-scrutiny reference layer for the retailer's Food Safety Operations Director. It is decision support only, never a directive.

The feature introduces no new modeling and performs no model training. It is a deterministic join and offline geocode over data that already exists in the project: the S03 establishment-surveillance scan (`src/analysis/establishment_surveillance.py`, `load_cache()`) and the existing `action_queue.json` (module ACTIONQ). The map shows only signal-bearing establishments — those that carry an elevated S03 signal (support_status "ok" with an elevated eb_posterior) and/or appear as an establishment-targeted action in the action queue — not every sampled establishment.

To place a pin, each signal-bearing establishment is joined to the FSIS Meat, Poultry & Egg Product Inspection (MPI) Directory by FSIS establishment number to obtain a real published address, geocoded once offline, and cached as a committed artifact. Establishments that lack an address, are absent from the directory, or do not geocode cleanly are never approximated; they are listed explicitly in an unplaced-establishments panel with a stated reason, and the geocode coverage percentage is reported honestly.

The feature follows the project's existing module and data-contract conventions: a new Python module produces a cache; `src/artifacts/exporter.py` gains a `build_facility_map()` that reads that cache, validates rows against a new TypedDict in `src/artifacts/schemas.py`, stamps a deterministic `generated_at`, and writes `web/public/data/facility_map.json` with a manifest entry; a mirrored TypeScript interface is appended to `web/src/types/artifacts.ts`; and a new `FacilityMap.tsx` tab is wired into `web/src/App.tsx`.

All three pathogens (Salmonella, Listeria, STEC) are first-class. Only Salmonella is forecastable at establishment grain; Listeria and STEC are descriptive only. An empty set of signal-bearing establishments for a pathogen is an honest result and is displayed as such, never fabricated.

The Facility Map is distinct from two existing surfaces: the base platform's SIMULATED optimizer Recommended Action Panel (a simulated supply network), and the state-level PREDICTED risk_map choropleth. The Facility Map presents OBSERVED establishment-level surveillance geography.

## Glossary

- **Facility_Map**: The new web tab and its backing artifact that plots signal-bearing FSIS-sampled establishments at their real geocoded sampling locations as a sourcing-scrutiny reference layer.
- **Retailer**: A regional grocery retail chain whose Food Safety Operations Director is the primary actor consuming the Facility Map outputs as decision support.
- **Decision_Maker**: The retailer's Food Safety Operations Director interacting with the Facility Map web tab.
- **S03_Module**: The establishment-surveillance module `src/analysis/establishment_surveillance.py`, whose `load_cache()` yields per-pathogen records keyed by establishment id.
- **Signal_Bearing_Establishment**: An FSIS-sampled establishment that either carries an elevated S03 signal (`support_status == "ok"` and an elevated `eb_posterior`) or appears in `action_queue.json` as an establishment-targeted action.
- **Establishment_Number**: The real FSIS establishment number carried in each S03 record as `establishment_id`; the join key to the MPI Directory.
- **Normalized_Establishment_Number**: An Establishment_Number after a documented deterministic normalization (trim surrounding whitespace, remove leading zeros, uppercase) applied identically to both sides before matching.
- **MPI_Directory**: The FSIS Meat, Poultry & Egg Product Inspection Directory, an external FSIS-published dataset that maps an establishment number to a published establishment address.
- **Geocoder**: The offline process that converts an MPI-published address into latitude/longitude exactly once, whose output is committed as the cached geocode artifact.
- **Geocode_Cache**: The committed artifact keyed on Normalized_Establishment_Number that holds each resolved location; the build reads it and never calls a geocoding service.
- **Geocode_Coverage**: The fraction of signal-bearing establishments that were successfully placed at a real geocoded location, reported as a percentage.
- **Unplaced_Establishment**: A signal-bearing establishment that could not be placed (missing from the MPI Directory, missing an address, ambiguous match, or not cleanly geocoded) and is listed with a stated reason rather than approximated.
- **Action_Queue**: The existing `action_queue.json` artifact (module ACTIONQ) carrying per-action `target_type`, `target`, `pathogen`, `source_module`, `evidence_summary`, `human_review`, and `status`.
- **EB_Posterior**: The beta-binomial Empirical Bayes posterior positivity estimate (`eb_posterior`) produced by S03; a surveillance signal, never a contamination or illness claim.
- **Surveillance_Signal**: An observed positivity or EB posterior value; evidence of testing outcomes, never a contamination, supply, or illness claim.
- **Exporter**: The artifact builder `src/artifacts/exporter.py` that validates and writes JSON artifacts to `web/public/data` and records a manifest entry.
- **Facility_Map_Schema**: The new TypedDict added to `src/artifacts/schemas.py` (before the `STATUS_TAGS` anchor) describing one Facility Map row, mirrored by a TypeScript interface in `web/src/types/artifacts.ts`.
- **Generated_At_Policy**: The project's deterministic `generated_at` resolution (`resolve_generated_at`), which is never the wall clock.
- **MapView_Fallback_Grid**: The accessible grid rendering MapView falls back to under jsdom, reused so the Facility Map is deterministically testable.
- **Forbidden_Terms**: The Action_Queue forbidden-terms set ("recall", "contaminated", "unsafe", "seize", "shut down", "destroy", "government order", "mandate"), matched case-insensitively.
- **Status_Tag**: The provenance label in {OBSERVED, PREDICTED, SIMULATED} carried by every value-bearing row; every Facility Map row is OBSERVED.
- **Human_Review_Gate**: The visible indication that every surfaced item is a human-reviewed decision-support suggestion, never an automated directive.
- **TOP_N_S03**: The locked parameter fixed at 12 (from `src/decision/action_queue.py`) that bounds the number of top-eb_posterior establishments selected per pathogen.

## Requirements

### Requirement 1: Select signal-bearing establishments only

**User Story:** As the retailer's Food Safety Operations Director, I want the map to show only FSIS-sampled establishments that carry an elevated surveillance signal, so that I focus sourcing scrutiny on establishments the data flags rather than on every sampled plant.

#### Acceptance Criteria

1. WHEN the Facility_Map artifact is built, THE Facility_Map SHALL classify an establishment as carrying an elevated S03_Module signal WHERE, for its pathogen, the establishment has a support_status of "ok" and a non-null eb_posterior and ranks within the top TOP_N_S03 establishments when all support_status "ok" establishments for that pathogen are ordered by eb_posterior in descending order, where TOP_N_S03 is a locked parameter fixed at 12.
2. WHEN the Facility_Map artifact is built, THE Facility_Map SHALL include an establishment WHERE the establishment carries an elevated S03_Module signal as defined in criterion 1, OR the establishment appears in the Action_Queue with target_type "establishment".
3. WHEN the Facility_Map artifact is built, THE Facility_Map SHALL exclude an establishment WHERE the establishment carries neither an elevated S03_Module signal as defined in criterion 1 nor an Action_Queue entry with target_type "establishment".
4. IF an establishment carries a support_status of "low_support", THEN THE Facility_Map SHALL exclude the establishment from the elevated-signal selection on the basis of insufficient support and SHALL NOT present the establishment as safe or clean.
5. WHEN the Facility_Map includes an establishment, THE Facility_Map SHALL record for that establishment whether it was selected from the S03_Module signal only, from the Action_Queue only, or from both sources.

### Requirement 2: Join each establishment to the MPI Directory by establishment number

**User Story:** As the retailer's Food Safety Operations Director, I want each flagged establishment located by its real FSIS-published address, so that the map reflects verified sampling locations and not guesses.

#### Acceptance Criteria

1. WHEN joining a Signal_Bearing_Establishment to the MPI_Directory, THE Geocoder SHALL first derive a Normalized_Establishment_Number by applying a documented deterministic normalization (trim surrounding whitespace, remove leading zeros, uppercase) to both the establishment's Establishment_Number and the MPI_Directory establishment-number field.
2. WHEN matching a Signal_Bearing_Establishment to the MPI_Directory, THE Geocoder SHALL match on exact equality of the Normalized_Establishment_Number and SHALL NOT use establishment-name or any fuzzy matching.
3. IF a Normalized_Establishment_Number matches more than one MPI_Directory record, THEN THE Facility_Map SHALL record the establishment as an Unplaced_Establishment with the reason "ambiguous match in MPI Directory".
4. IF a Normalized_Establishment_Number is absent from the MPI_Directory, THEN THE Facility_Map SHALL record the establishment as an Unplaced_Establishment with the reason "establishment number not found in MPI Directory".
5. IF a matched MPI_Directory record has no published address, THEN THE Facility_Map SHALL record the establishment as an Unplaced_Establishment with the reason "no published address in MPI Directory".
6. WHEN an establishment is placed, THE Facility_Map SHALL record the MPI_Directory-published address used to obtain the location.
7. WHERE the MPI_Directory data has not been obtained, THE Facility_Map SHALL record every selected establishment as an Unplaced_Establishment with a stated reason rather than fabricating a location.

### Requirement 3: Geocode once offline and cache as a committed artifact

**User Story:** As a reviewer reproducing the submission, I want the geocode computed once offline and committed, so that the map is reproducible and makes no network calls at build time.

#### Acceptance Criteria

1. THE Geocoder SHALL resolve each establishment location exactly once, where "offline" means the location is derived either from a committed local gazetteer file or from a one-time manual geocode whose output is committed to the repository, and SHALL write the result to the committed Geocode_Cache keyed on the Normalized_Establishment_Number.
2. IF two or more establishment records resolve to the same Normalized_Establishment_Number, THEN THE Geocoder SHALL write a single Geocode_Cache entry for that key and SHALL record a conflict indication identifying the duplicated key.
3. WHEN the Facility_Map artifact is built, THE Exporter SHALL read establishment locations from the committed Geocode_Cache keyed on Normalized_Establishment_Number and SHALL NOT perform any network geocode request.
4. IF the committed Geocode_Cache is missing an entry for a required Normalized_Establishment_Number when the Facility_Map artifact is built, THEN THE Exporter SHALL fail the build with an error indicating the missing key and SHALL NOT perform a network geocode request to resolve it.
5. THE Facility_Map SHALL stamp its rows with a deterministic generated_at value resolved through the Generated_At_Policy rather than the wall clock.
6. WHEN the Facility_Map artifact is built twice from identical inputs, THE Exporter SHALL produce byte-identical substantive output, excluding only the generated_at field.
7. THE Facility_Map SHALL emit rows in a documented deterministic order, sorted by Normalized_Establishment_Number, so that repeated builds from identical inputs produce an identical ordering.

### Requirement 4: Report geocode coverage honestly and list unplaced establishments

**User Story:** As the retailer's Food Safety Operations Director, I want to see how many flagged establishments were actually placed and which were not, so that I understand the map's completeness and do not mistake a partial map for a complete one.

#### Acceptance Criteria

1. WHILE the total number of selected Signal_Bearing_Establishments for a pathogen is greater than zero, THE Facility_Map SHALL compute Geocode_Coverage as the number of placed Signal_Bearing_Establishments divided by the total number of selected Signal_Bearing_Establishments, expressed as a percentage rounded to one decimal place in the range 0.0 to 100.0.
2. IF the total number of selected Signal_Bearing_Establishments for a pathogen is zero, THEN THE Facility_Map SHALL report Geocode_Coverage as a not-applicable value accompanied by an explicit "no establishments selected" state rather than performing the coverage division.
3. WHEN Geocode_Coverage has been computed or set to the not-applicable state for a pathogen, THE Facility_Map SHALL present that Geocode_Coverage value, the placed count, and the total selected count to the Decision_Maker.
4. WHEN an establishment is an Unplaced_Establishment, THE Facility_Map SHALL list the establishment in the unplaced-establishments panel with its FSIS-published identity and a human-readable reason indicating why it could not be placed.
5. IF no Signal_Bearing_Establishment can be placed for a pathogen while the total selected count is greater than zero, THEN THE Facility_Map SHALL report a Geocode_Coverage of 0.0 percent and list every selected establishment as unplaced rather than presenting an empty map as a successful result.
6. THE Facility_Map SHALL assign each selected Signal_Bearing_Establishment to exactly one of the placed or unplaced categories such that the placed count plus the unplaced count equals the total selected count for the pathogen.

### Requirement 5: Enforce identity and framing honesty

**User Story:** As the retailer's Food Safety Operations Director, I want the map to use only FSIS-published identity and to frame establishments as sampled locations with a signal, so that no establishment is implied to be my supplier and no contact detail is exposed.

#### Acceptance Criteria

1. WHEN rendering an establishment's identity, THE Facility_Map SHALL display only the FSIS-published fields establishment number, FSIS-published establishment name, and state, and SHALL NOT display any other identity field.
2. IF an FSIS-published establishment name is absent, THEN THE Facility_Map SHALL display the establishment by its establishment number only and SHALL NOT fabricate, infer, or substitute a name.
3. WHEN labeling the plotted establishments collectively, THE Facility_Map SHALL frame them as "FSIS-sampled establishments with elevated surveillance signal, by location".
4. THE Facility_Map SHALL NOT describe any plotted establishment as the Retailer's supplier, vendor, or source.
5. WHEN presenting a placed location, THE Facility_Map SHALL present it as the establishment's sampling location and SHALL NOT present it as a product destination or an illness location.
6. THE Facility_Map SHALL NOT display any establishment contact detail, including street address beyond what is needed to geocode, phone number, email, or contact-person name.

### Requirement 6: Frame the signal as surveillance, not contamination or illness

**User Story:** As the retailer's Food Safety Operations Director, I want positivity framed as a surveillance signal, so that I do not misread the map as a contamination or illness claim.

#### Acceptance Criteria

1. WHEN displaying an establishment's eb_posterior or observed positivity, THE Facility_Map SHALL label the value as a Surveillance_Signal.
2. THE Facility_Map SHALL NOT describe any establishment value as a contamination level, an illness count, or a food-to-illness link.
3. WHEN displaying an establishment's eb_posterior, THE Facility_Map SHALL present its 95% credible interval as a lower-bound and upper-bound pair shown in the same view as the eb_posterior.
4. THE Facility_Map SHALL NOT characterize any establishment as safe.
5. WHERE an establishment's sample count is below 30 samples, THE Facility_Map SHALL present a low-support indication for that establishment and SHALL NOT present its signal as a settled or confident estimate.

### Requirement 7: Keep all three pathogens first-class with honest empty results

**User Story:** As the retailer's Food Safety Operations Director, I want each pathogen handled consistently, so that Listeria and STEC remain visible even though only Salmonella is forecastable at establishment grain.

#### Acceptance Criteria

1. THE Facility_Map SHALL offer a pathogen filter whose selectable values are exactly Salmonella, Listeria, and STEC.
2. WHEN the Decision_Maker selects a single pathogen in the pathogen filter, THE Facility_Map SHALL display only the Signal_Bearing_Establishments whose pathogen matches the selected value and SHALL exclude every establishment of the other two pathogens.
3. WHERE a pathogen is descriptive only at establishment grain, THE Facility_Map SHALL tag each of its establishments with the Status_Tag OBSERVED and SHALL NOT present a PREDICTED value for any of that pathogen's establishments.
4. IF a pathogen carries an availability_status of "available" in the S03_Module cache but has zero Signal_Bearing_Establishments, THEN THE Facility_Map SHALL present that pathogen with zero plotted establishments and a visible empty-result indication identifying the pathogen, and SHALL NOT add any establishment that is not a Signal_Bearing_Establishment.
5. WHERE the S03_Module cache marks a pathogen's availability_status as "unavailable", THE Facility_Map SHALL present that pathogen with the S03_Module unavailable_reason text and SHALL retain the pathogen as a selectable filter value rather than omitting it.

### Requirement 8: Validate against the data contract and write the artifact

**User Story:** As a maintainer, I want the Facility Map to follow the existing artifact contract, so that the Python and TypeScript definitions cannot silently drift.

#### Acceptance Criteria

1. WHEN building the Facility_Map artifact, THE Exporter SHALL validate every Facility_Map row against the Facility_Map_Schema before writing any byte of the artifact.
2. IF one or more Facility_Map rows fail validation against the Facility_Map_Schema, THEN THE Exporter SHALL raise a schema validation error that identifies each failing row and field, and SHALL leave the existing `web/public/data/facility_map.json` unchanged.
3. WHEN all Facility_Map rows pass validation, THE Exporter SHALL write the validated rows to `web/public/data/facility_map.json`.
4. WHEN the Facility_Map artifact is written, THE Exporter SHALL record a Facility_Map manifest entry containing the artifact's sha256 checksum computed over its substantive bytes and the count of written Facility_Map rows.
5. THE Facility_Map_Schema SHALL have a mirrored TypeScript interface in `web/src/types/artifacts.ts` whose field names are identical to the serialized snake_case field names of the Facility_Map_Schema.
6. THE Facility_Map SHALL tag every value-bearing row with exactly the Status_Tag OBSERVED and SHALL NOT assign PREDICTED or SIMULATED to any Facility_Map row.

### Requirement 9: Render the Facility Map web tab

**User Story:** As the retailer's Food Safety Operations Director, I want a dedicated map tab, so that I can explore flagged establishments geographically with filters and an evidence-backed list.

#### Acceptance Criteria

1. THE Facility_Map SHALL render as a selectable tab registered in the web application's top navigation, and WHEN the Decision_Maker selects that tab THE Facility_Map SHALL become the active view.
2. WHEN the Facility_Map tab becomes active, THE Facility_Map SHALL load its data through the existing useArtifact hook from the facility_map artifact.
3. WHILE the facility_map artifact load is in progress, THE Facility_Map SHALL render a loading indication and SHALL NOT render the ranked list, the map view, or the unplaced-establishments panel.
4. IF the facility_map artifact fails to load, THEN THE Facility_Map SHALL render an empty-state that names the failed artifact, and the failure SHALL NOT prevent other tabs or panels from rendering their own successfully-loaded data.
5. THE Facility_Map SHALL provide a pathogen filter whose options are exactly the distinct pathogens present in the loaded facility_map data plus an all-pathogens option, and a source filter whose options are exactly S03_Module-selected, Action_Queue-selected, and an all-sources option; and WHEN the Decision_Maker changes either filter THE Facility_Map SHALL restrict the ranked list, the map view, and the unplaced-establishments count to establishments matching both active filter selections.
6. THE Facility_Map SHALL render a geographic map view that reuses the MapView_Fallback_Grid pattern such that, when a WebGL map canvas is unavailable, THE Facility_Map SHALL render an accessible grid fallback exposing one selectable element per placed establishment.
7. THE Facility_Map SHALL render a list of elevated establishments ordered by descending Surveillance_Signal, and for each listed establishment THE Facility_Map SHALL display the establishment's FSIS-published identity, its Surveillance_Signal accompanied by that signal's credible interval shown as a lower-bound and upper-bound pair, and its evidence summary.
8. WHERE the filtered facility_map data contains no elevated establishments, THE Facility_Map SHALL render an empty-state in place of the ranked list rather than an empty container.
9. THE Facility_Map SHALL render the unplaced-establishments panel displaying the Geocode_Coverage as a percentage between 0 and 100 inclusive and the count of establishments that could not be placed on the map view.
10. THE Facility_Map SHALL display a Human_Review_Gate indication on every surfaced establishment such that each surfaced item reads as decision support requiring human review rather than as a directive action.

### Requirement 10: Forbid directive, recall, and contamination language

**User Story:** As a compliance reviewer, I want the Facility Map to use only permitted decision-support language, so that it never reads as a recall or a regulatory directive.

#### Acceptance Criteria

1. THE Facility_Map SHALL NOT emit any term from the Forbidden_Terms set, matched case-insensitively, in any string-valued row field or any displayed label.
2. IF a Facility_Map row's text content or displayed label contains any term from the Forbidden_Terms set, THEN THE Exporter SHALL raise a validation error naming the offending field and SHALL NOT write any Facility_Map output.
3. THE Facility_Map SHALL present each surfaced item as a human-review-gated decision-support suggestion and SHALL carry a Human_Review_Gate indication on every surfaced item.
4. WHEN the Facility_Map derives an item from an Action_Queue entry, THE Facility_Map SHALL carry forward the entry's human_review flag with the value true and SHALL carry forward the entry's status value OBSERVED.

### Requirement 11: Keep the Facility Map distinct from other surfaces and theme-compliant

**User Story:** As the retailer's Food Safety Operations Director, I want the Facility Map clearly distinguished from the simulated optimizer and the state-level risk map, so that I do not confuse OBSERVED establishment geography with predicted or simulated outputs.

#### Acceptance Criteria

1. THE Facility_Map SHALL label its content as OBSERVED establishment-level surveillance geography and SHALL NOT render the SIMULATED optimizer Recommended Action Panel or present any of its surfaced items as a SIMULATED recommended action.
2. THE Facility_Map SHALL visibly distinguish its OBSERVED establishment-level geography from the state-level PREDICTED risk_map choropleth such that no element of the Facility_Map is labeled PREDICTED.
3. THE Facility_Map SHALL style all non-alert elements using only the navy, teal, slate, and gray theme tokens.
4. WHERE the Facility_Map applies an alert-family color (orange or red) for elevated-signal emphasis, THE Facility_Map source file SHALL be a member of the theme-discipline static-scan allowlist so that the theme-discipline test passes, and THE Facility_Map SHALL apply that alert-family color only to elements conveying an elevated Surveillance_Signal or a required human review.

### Requirement 12: Provide automated tests mirroring the Surveillance Actions module

**User Story:** As a maintainer, I want Python and web tests for the Facility Map, so that the selection, geocode-coverage, and honesty guarantees are protected against regression.

#### Acceptance Criteria

1. THE Facility_Map SHALL include Python property tests under `tests/` that cover establishment selection, Geocode_Coverage accounting, and the invariant that the count of placed Signal_Bearing_Establishments plus the count of Unplaced_Establishments equals the total count of selected Signal_Bearing_Establishments for every pathogen.
2. THE Facility_Map SHALL include a Python test asserting that every placed row carries an MPI_Directory-published address and a geocoded location sourced from the committed Geocode_Cache, that no placed row carries a fabricated or placeholder location, and that every Unplaced_Establishment carries a non-empty stated reason.
3. THE Facility_Map SHALL include a web component test (vitest) that renders the tab and asserts that the pathogen filter, the source filter, the ranked list, and the unplaced-establishments panel displaying the Geocode_Coverage percentage are each present in the rendered output.
4. THE Facility_Map SHALL include a parity test asserting that the set of serialized snake_case field names of the Facility_Map_Schema and the set of field names of its mirrored TypeScript interface in `web/src/types/artifacts.ts` are equal, so that a field present in one but absent from the other fails the test.

### Requirement 13: Capture the MPI Directory matching risk as an explicit assumption

**User Story:** As a reviewer, I want the open risk about MPI Directory matching stated honestly, so that coverage limits are transparent rather than assumed away.

#### Acceptance Criteria

1. THE Facility_Map SHALL document the assumption that an Establishment_Number must match the MPI_Directory establishment-number field to place an establishment and that any unmatched Establishment_Number yields an Unplaced_Establishment with a stated reason.
2. THE Facility_Map SHALL document that the Geocoder computes each location offline against the committed Geocode_Cache and that Geocode_Coverage is a reported measured percentage rather than an assumed value.
3. IF the computed Geocode_Coverage is below 100 percent, THEN THE Facility_Map SHALL display the actual Geocode_Coverage percentage and the Unplaced_Establishments with their stated reasons, and SHALL NOT present the map as complete coverage.