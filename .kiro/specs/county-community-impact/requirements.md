# Requirements Document

## Introduction

This feature adds **S07 — County Community Impact**, a finer-geographic-resolution companion to the existing state-level S06 "Vulnerable Communities" module. S07 produces a per-**county** vulnerability-aware priority ranking per pathogen (Salmonella, Listeria, STEC), exported as a first-class schema-validated artifact plus a web view, as **decision support** for the Food Safety Operations Director of a regional grocery retail chain (the Retailer).

S07 is a **new module** (`module_id` **"S07"**) that does not modify, weaken, or depend on the internal state of the existing state-level S06 module (`src/analysis/community_impact.py`), its cache, its artifact, or its tests. S07 reuses the same honesty posture as S06 at county grain.

The central honest constraint of this feature is that the two sides of the ranking join have **different native resolutions**:

- The **vulnerability side can be county-level.** The US Census ACS 5-year API resolves at county grain, and the USDA Food Access Research Atlas (the Atlas) is census-tract-level at source and can be re-aggregated to county (county FIPS = state 2 digits + county 3 digits).
- The **hazard side is state-only.** FSIS laboratory-sampling positivity carries establishment state, not county. There is no honest sub-state hazard.

Therefore a county priority ranking combines **county vulnerability** with the county's **state-level hazard**, and this mismatch is labeled explicitly on every record and in the UI as "county vulnerability x state-level hazard." Consequently, every county in a given state shares that state's single hazard value; S07 never implies county-level contamination, county-level infection, or a county-measured hazard. A county in a state with no hazard for a pathogen is honestly unavailable. All outputs are decision support, never directives and never infection or illness claims.

## Glossary

- **S07 / County_Community_Impact**: The new module introduced by this feature; produces the per-county vulnerability-aware priority ranking per pathogen. `module_id` is "S07".
- **S06 / Community_Impact**: The existing, unchanged state-level module (`src/analysis/community_impact.py`) that S07 is a companion to.
- **Retailer**: The regional grocery retail chain whose Food Safety Operations Director is the primary actor and consumer of S07 outputs.
- **County**: A US county identified by its 5-digit county FIPS code (2-digit state FIPS + 3-digit county FIPS).
- **County_State**: The state that a given county belongs to; the source of that county's state-level hazard.
- **Hazard**: The READ-ONLY per-(pathogen, state) observed FSIS sampling positivity, reused unchanged from the existing hazard source (`fsis_state_year()`), expressed as a value in [0,1]. Surfaced on a county record as `hazard_positivity`.
- **Hazard_Component**: The hazard positivity min-max normalized to [0,1] over the state Normalization_Scope.
- **Vulnerability**: County-level community context from Census ACS and the USDA Atlas: elderly 65+ share (ACS), low-income share (Atlas), low-access share (Atlas).
- **Vulnerability_Component**: A vulnerability lens value min-max normalized to [0,1] over the county Normalization_Scope.
- **Lens**: A single population-vulnerability view (`elderly_65plus`, `low_income`, `low_access`) used to re-order the priority ranking. Switching lens never changes the hazard.
- **Unavailable_Lens**: A lens whose source data does not exist at county grain in this feature (`under5`, `pregnancy`); shown explicitly unavailable, never fabricated.
- **Priority_Score**: A documented multi-criteria score in [0,1] = `round(0.6 x Hazard_Component + 0.4 x Vulnerability_Component, 6)`, under the disclosed default weights (0.6 hazard, 0.4 vulnerability).
- **Default_Weights**: The documented default weighting (0.6 hazard, 0.4 vulnerability), reused from S06 `DEFAULT_WEIGHTS`; weights sum to 1.0 and are exposed as documented constants.
- **Normalization_Scope**: The set over which a component's min-max normalization to [0,1] is computed, exposed as a documented, testable constant: Hazard_Component is normalized over the STATE set (its native state-level grain); Vulnerability_Component is normalized over the county set.
- **Affected_Population_Context**: An illustrative count = low-access share x county population; the number of people who COULD be affected IF exposed. Never an observed exposure, infection, or illness count.
- **Availability_Status**: Per-record status, exactly one of "available" or "unavailable", with a stated reason when unavailable.
- **ACS_Vintage / Atlas_Vintage**: The disclosed data vintages for the Census ACS pull and the USDA Atlas file used for a vulnerability value.
- **CENSUS_API_KEY**: The environment variable required to pull county-grain ACS data; absent, S07 degrades honestly.
- **Committed_County_Vulnerability_Input**: A committed, reviewer-visible county vulnerability table (keyed on 5-digit county FIPS) produced once with a key, so a reviewer without a key still sees the real county vulnerability.
- **Status_Tag**: The displayed provenance label; S07 values are "OBSERVED" (measured/published surveillance + census), never "PREDICTED" or "SIMULATED".
- **Artifact**: The schema-validated S07 payload exported to the web build with a manifest entry.

## Requirements

### Requirement 1: County vulnerability x state-level hazard labeling

**User Story:** As the Food Safety Operations Director, I want every county ranking to state plainly that its hazard is the county's state-level positivity, so that I never mistake a county ranking for a county-measured hazard.

#### Acceptance Criteria

1. THE County_Community_Impact SHALL combine each County's county-level Vulnerability_Component with that County's County_State Hazard_Component to produce the Priority_Score as a 0.6/0.4 weighted sum, and SHALL set the Priority_Score to None when either component is None.
2. WHERE two county records share the same County_State and pathogen, THE County_Community_Impact SHALL assign them identical `hazard_component` and identical `hazard_positivity` values.
3. THE County_Community_Impact SHALL carry on every county record an explicit resolution label field whose value is "county vulnerability x state-level hazard".
4. THE County_Community_Impact SHALL record on every county record the County_State (2-digit state FIPS or USPS code) whose Hazard was used.
5. WHERE a county record carries a `hazard_positivity` value, THE County_Community_Impact SHALL represent it as the County_State positivity and SHALL NOT represent it as a county-measured hazard.
6. WHEN the County_Community_Impact web view renders the county ranking, THE County_Community_Impact SHALL display the "county vulnerability x state-level hazard" label.

### Requirement 2: No county-level infection, illness, or county-measured hazard claim

**User Story:** As the Food Safety Operations Director, I want a hard guarantee that no output implies county contamination or illness, so that the submission stays honest and defensible.

#### Acceptance Criteria

1. THE County_Community_Impact SHALL NOT emit any record field whose name contains (case-insensitively) any of "county_infection", "tract_infection", "infection", "illness_estimate", "predicted_case", or "human_case".
2. THE County_Community_Impact SHALL NOT emit any county-measured hazard value; the only Hazard present SHALL be the County_State positivity.
3. THE County_Community_Impact SHALL set every county record Status_Tag to "OBSERVED", meaning a measured or published value, and SHALL NOT set it to "PREDICTED" or "SIMULATED".
4. THE County_Community_Impact SHALL represent Affected_Population_Context as a non-negative count of people who could be affected if exposed, kept distinct from any share in [0,1], and SHALL NOT represent it as an observed exposure, infection, or illness count.
5. THE County_Community_Impact SHALL record the geography level as "county" for Vulnerability and "state" for Hazard, and SHALL NOT claim a sub-state hazard resolution.
6. THE County_Community_Impact SHALL constrain every non-None share and component value to the closed interval [0,1].

### Requirement 3: Key-absent honest degradation

**User Story:** As a reviewer without a Census API key, I want S07 to degrade honestly rather than fabricate, so that I can trust that any county vulnerability shown is real.

#### Acceptance Criteria

1. WHEN CENSUS_API_KEY is absent at the start of an S07 run, THE County_Community_Impact SHALL record a gap entry with reason "skipped-no-key" and SHALL set the county Vulnerability field to None (unavailable) for every county unless a Committed_County_Vulnerability_Input is present.
2. IF CENSUS_API_KEY is absent AND no Committed_County_Vulnerability_Input is present, THEN THE County_Community_Impact SHALL set Availability_Status to "unavailable" with a reason string stating the Census key is absent, SHALL NOT write any numeric county vulnerability value, and SHALL complete the export without raising an error.
3. WHEN a Committed_County_Vulnerability_Input (keyed on 5-digit county FIPS, previously produced with a key) is present, THE County_Community_Impact SHALL load that committed input, SHALL populate the county vulnerability table from it, and SHALL set Availability_Status to "available" for counties it covers.
4. WHEN two S07 runs are executed over byte-identical committed inputs, THE County_Community_Impact SHALL produce byte-identical artifact output across those runs.
5. IF the county ACS or Atlas extraction raises an error OR returns zero rows, THEN THE County_Community_Impact SHALL record a gap entry identifying the failed source, SHALL set the county Vulnerability field to None (unavailable) for every affected county, and SHALL continue the export without aborting the remaining output.
6. WHEN a Committed_County_Vulnerability_Input is loaded, THE County_Community_Impact SHALL match each committed row to a county by its 5-digit county FIPS key, and IF a FIPS key is malformed or not 5 digits, THEN THE County_Community_Impact SHALL record a gap entry for that row and SHALL set that county's Vulnerability to None.

### Requirement 4: Lens never changes the hazard (invariant)

**User Story:** As the Food Safety Operations Director, I want switching the population lens to re-order priorities only, so that I know the underlying hazard is one fixed observed value.

#### Acceptance Criteria

1. THE County_Community_Impact SHALL compute exactly one Hazard value and exactly one Hazard_Component, each in the range 0.0 to 1.0, per (pathogen, County).
2. WHEN the Lens changes for a given (pathogen, County), THE County_Community_Impact SHALL return the same Hazard value and the same Hazard_Component as before the Lens change (equal after rounding to 6 decimal places).
3. WHEN a Lens is applied to a (pathogen, County) record whose Hazard_Component and that Lens Vulnerability_Component are both present and in the range 0.0 to 1.0, THE County_Community_Impact SHALL set that Lens Priority_Score to round((0.6 x Hazard_Component) + (0.4 x Vulnerability_Component), 6) using the Default_Weights.
4. IF the Hazard_Component is missing for a (pathogen, County), THEN THE County_Community_Impact SHALL set every Lens Priority_Score for that record to None and SHALL NOT substitute a hazard-only or vulnerability-only score.
5. IF a given Lens Vulnerability_Component is missing, THEN THE County_Community_Impact SHALL set that Lens Priority_Score to None and SHALL NOT substitute a hazard-only score.

### Requirement 5: All three pathogens first-class with honest availability

**User Story:** As the Food Safety Operations Director, I want Salmonella, Listeria, and STEC all treated as first-class, so that no pathogen is silently dropped.

#### Acceptance Criteria

1. THE County_Community_Impact SHALL produce exactly three ranking sections, one each for Salmonella, Listeria, and STEC, in every output.
2. THE County_Community_Impact SHALL set each County record Availability_Status to exactly one of "available" or "unavailable".
3. IF a pathogen has no County_State Hazard for a County, THEN THE County_Community_Impact SHALL set that County record Availability_Status to "unavailable" with a reason stating the state has no hazard for the pathogen, and SHALL retain the County record without dropping or fabricating it.
4. IF a County has no county Vulnerability profile, THEN THE County_Community_Impact SHALL set that County record Availability_Status to "unavailable" with a reason stating no vulnerability profile exists for the County, and SHALL retain the County record without dropping or fabricating it.
5. THE County_Community_Impact SHALL include every unavailable County in the output with its Availability_Status and reason rather than omitting it.

### Requirement 6: Documented, deterministic multi-criteria Priority_Score

**User Story:** As a reviewer, I want the Priority_Score method documented and deterministic, so that I can reproduce and audit the ranking.

#### Acceptance Criteria

1. THE County_Community_Impact SHALL compute Priority_Score as a weighted sum of the Hazard_Component and the Vulnerability_Component, using Default_Weights that sum to 1.0 and are exposed as documented constants.
2. THE County_Community_Impact SHALL normalize the Hazard_Component over the STATE set (its native state-level grain) and the Vulnerability_Component over the county set, applying min-max normalization to the interval [0,1], and SHALL expose each Normalization_Scope as a documented, testable constant.
3. WHEN either the Hazard_Component or Vulnerability_Component value for a county is None, THE County_Community_Impact SHALL exclude that value from min-max normalization, SHALL keep the component None in the output, and SHALL NOT impute or substitute any value.
4. THE County_Community_Impact SHALL constrain every non-None Hazard_Component, Vulnerability_Component, and Priority_Score value to the closed interval [0,1].
5. IF both the Hazard_Component and Vulnerability_Component for a county are None, THEN THE County_Community_Impact SHALL set that county's Priority_Score to None and SHALL NOT assign it a numeric rank.
6. WHEN two Priority_Score computations are executed over identical inputs, THE County_Community_Impact SHALL produce identical Priority_Score values and identical county ordering across those runs.

### Requirement 7: Weight-sensitivity reporting

**User Story:** As a reviewer, I want the ranking's sensitivity to weighting disclosed, so that no single weighting is presented as definitive.

#### Acceptance Criteria

1. THE County_Community_Impact SHALL compute the top-ranked counties under the Default_Weights and at least one alternative weighting.
2. THE County_Community_Impact SHALL report whether the top set is stable across the default and alternative weightings.
3. THE County_Community_Impact SHALL disclose the default and alternative weight values with the sensitivity result.
4. THE County_Community_Impact SHALL state that the ranking is weight-dependent and that no single weighting is definitive.

### Requirement 8: Affected_Population_Context as an illustrative count

**User Story:** As the Food Safety Operations Director, I want the affected-population figure clearly framed as "could be affected if exposed," so that I never read it as an observed count.

#### Acceptance Criteria

1. THE County_Community_Impact SHALL compute Affected_Population_Context as the county low-access share multiplied by the county population.
2. WHEN either the county low-access share or the county population is missing, THE County_Community_Impact SHALL set Affected_Population_Context to None, and SHALL NOT impute a value.
3. THE County_Community_Impact SHALL keep Affected_Population_Context (a non-negative count) distinct from the shares (values in [0,1]).
4. THE County_Community_Impact SHALL carry a note stating Affected_Population_Context is an illustrative count of people who could be affected if exposed, never an observed exposure or illness count.

### Requirement 9: Disclosed vintages on available vulnerability values

**User Story:** As a reviewer, I want data vintages disclosed on every available vulnerability value, so that I can judge recency and provenance.

#### Acceptance Criteria

1. WHEN a county record has an available ACS-derived vulnerability value, THE County_Community_Impact SHALL disclose the ACS_Vintage on that record.
2. WHEN a county record has an available Atlas-derived vulnerability value, THE County_Community_Impact SHALL disclose the Atlas_Vintage on that record.
3. WHERE a vulnerability value is unavailable, THE County_Community_Impact SHALL null the corresponding vintage rather than fabricate one.

### Requirement 10: County vulnerability lenses and unavailable lenses

**User Story:** As the Food Safety Operations Director, I want only genuinely available county lenses used, with the rest shown explicitly unavailable, so that nothing is invented.

#### Acceptance Criteria

1. THE County_Community_Impact SHALL support the `elderly_65plus` lens from county ACS when the county ACS pull includes the 65+ variables.
2. THE County_Community_Impact SHALL support the `low_income` and `low_access` lenses from the county-aggregated USDA Atlas.
3. THE County_Community_Impact SHALL mark the `under5` and `pregnancy` lenses as unavailable with a stated reason for every county record, and SHALL set their Vulnerability_Component and Priority_Score to None.
4. THE County_Community_Impact SHALL aggregate the tract-level USDA Atlas to county by 5-digit county FIPS, and SHALL NOT use the existing S06 state aggregation as the county vulnerability source.

### Requirement 11: Independence from the existing S06 module

**User Story:** As a maintainer, I want S07 to leave S06 untouched, so that the locked state-level guarantees and tests keep passing.

#### Acceptance Criteria

1. THE County_Community_Impact SHALL NOT modify `src/analysis/community_impact.py`, its cache file, its artifact, or its tests.
2. THE County_Community_Impact SHALL use `module_id` "S07" distinct from S06.
3. THE County_Community_Impact SHALL write its own interim cache under `data/interim/` without overwriting the S06 cache.
4. WHERE S07 reads the FSIS state-level hazard, THE County_Community_Impact SHALL read it without mutating the shared hazard source used by S06.

### Requirement 12: First-class schema-validated artifact and web view

**User Story:** As a reviewer, I want S07 exported as a validated artifact with a web view, so that the county ranking is a first-class, inspectable deliverable.

#### Acceptance Criteria

1. THE County_Community_Impact SHALL define a new county-record TypedDict in the Python schema module and a mirrored type in the web types module with identical snake_case field names.
2. THE County_Community_Impact SHALL provide an exporter builder that writes the county artifact to the web public data directory with a manifest entry recording its checksum and record count.
3. THE County_Community_Impact SHALL validate the county artifact payload against its schema before export and SHALL raise a validation error before writing when a record is invalid.
4. WHEN a WebGL map canvas is unavailable, THE County_Community_Impact web view SHALL render the county ranking reusing the maplibre fallback-grid county pattern as an accessible grid so it is testable under jsdom.
5. THE County_Community_Impact web view SHALL display the Status_Tag "OBSERVED" on hazard and vulnerability values, and SHALL NOT display "PREDICTED" or "SIMULATED" for S07 values.