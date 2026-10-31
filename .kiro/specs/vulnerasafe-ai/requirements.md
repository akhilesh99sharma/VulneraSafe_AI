# Requirements Document

## Introduction

VulneraSafe AI ("Predict the Hazard. Protect the Vulnerable.") is a multi-pathogen, vulnerability-aware, One Health food-safety early-warning and operational decision-support platform built for the 2026 NAFSI Hub SENS-D Data Challenge (a 48-hour hackathon). The deliverable is a reproducible analysis plus a React/TypeScript/Vite web application deployable to GitHub Pages, a PDF report, and the AWS Kiro development artifacts (specs, steering files, prompts, hooks).

The authoritative source for scope is the official SENS-D challenge brief in the workspace (`NAFSI Data Challenge.docx.pdf`). Where the user's project prompt and the brief conflict, the brief governs; such conflicts are captured explicitly in the Constraints and Assumptions section.

The primary decision-maker is the Food Safety Operations Director of a regional grocery retail chain. The brief permits a team-selected supply-chain actor and lists "retailer" as a valid choice, so this actor is confirmed and held consistent across every requirement. Food safety is the hard constraint; food availability, equitable access, and minimizing avoidable food loss are secondary objectives that may never override a food-safety constraint.

Requirements are organized so they trace to the brief's five tasks (One Health data integration, predictive ML, operational decision support, the Kiro web application, and team science) and to the brief's five weighted evaluation criteria: Data science rigor and validation (25%), Operational decision support (25%), One Health multi-source integration (20%), Kiro implementation and usability (15%), and Team science, reproducibility, and communication (15%).

## Glossary

- **VulneraSafe_System**: The complete VulneraSafe AI platform, comprising the analysis pipeline, the predictive models, the decision-support optimizer, and the web application.
- **Data_Pipeline**: The reproducible ingestion, harmonization, and alignment component that produces the harmonized analytic tables.
- **Risk_Model**: The predictive modeling component that estimates near-term elevated food-safety surveillance risk at a decision-relevant unit.
- **Baseline_Model**: A transparent reference model (historical/seasonal baseline and a regularized logistic/statistical model) used for comparison against integrated models.
- **Decision_Engine**: The safety-constrained optimization component that converts risk estimates into recommended operational actions.
- **Web_App**: The React/TypeScript/Vite decision-support application deployed via GitHub Pages.
- **Decision_Maker**: The Food Safety Operations Director of a regional grocery retail chain; the single primary actor for the platform.
- **One Health**: An approach that connects signals across human-health, animal/food-production, and environmental domains rather than analyzing any single dataset in isolation.
- **FSIS**: USDA Food Safety and Inspection Service; publisher of establishment-specific laboratory sampling data and a Recall/Public Health Alert API.
- **PulseNet**: The CDC national laboratory network and database used by public-health and food-regulatory laboratories to detect outbreaks; direct access is limited to participating laboratories.
- **PulseNet_Stream**: The required human-health surveillance input, provided as an organizer PulseNet-derived extract, or a documented public CDC human-illness substitute dataset when the extract is unavailable.
- **CDC_Substitute**: A public CDC human-illness surveillance dataset (for example NORS or FoodNet) used in place of a PulseNet extract, with documented justification.
- **NOAA_CDO**: NOAA/NCEI Climate Data Online v2 API, providing weather and climate data; free access that requires a token.
- **ACS**: US Census American Community Survey, providing age distributions, socioeconomic, and geographic data.
- **Food_Access_Atlas**: The USDA Food Access Research Atlas, providing food-access and food-insecurity indicators.
- **SVI**: CDC/ATSDR Social Vulnerability Index (optional added dataset).
- **STEC**: Shiga toxin-producing Escherichia coli, a pathogen monitored in raw beef.
- **Listeria**: Listeria monocytogenes, a pathogen monitored in ready-to-eat (RTE) meat and poultry.
- **Salmonella**: A pathogen monitored in raw poultry and other FSIS-regulated commodities; the anchor hazard of the challenge.
- **RTE**: Ready-to-eat meat and poultry products.
- **Modeling_Unit**: The decision-relevant analytic unit, defined as pathogen x commodity x region x time (monthly or quarterly selected after sample-size evaluation).
- **Prediction_Horizon**: The future reporting period for which elevated risk is estimated, fixed before any model tuning.
- **Positivity_Rate**: The number of pathogen-positive samples divided by the correct program denominator for a given Modeling_Unit and period.
- **Program_Denominator**: The count of samples attributable to a specific FSIS sampling program, used as the denominator for a positivity rate.
- **Leakage**: Use of information at training time that would not be available at the Prediction_Horizon, producing optimistic and invalid performance.
- **Rolling-origin validation**: A time-aware validation scheme that repeatedly trains on past periods and evaluates on the next future period, advancing the cutoff forward.
- **Establishment_Holdout_Validation**: A validation in which all observations of a set of establishments are withheld from training to assess geographic/establishment generalization, run as a secondary check alongside the primary chronological validation.
- **PR-AUC**: Area under the precision-recall curve; a discrimination metric suited to rare-event (imbalanced) targets.
- **ROC-AUC**: Area under the receiver operating characteristic curve.
- **Brier score**: A measure of probabilistic forecast accuracy (mean squared error of predicted probabilities).
- **Calibration**: The agreement between predicted probabilities and observed outcome frequencies, assessed with calibration plots.
- **Ablation**: A controlled comparison that adds or removes a data source or domain to measure its marginal contribution to model performance.
- **SHAP**: SHapley Additive exPlanations; a method for attributing a model prediction to its input features.
- **Non-Predictive_Module**: A pathogen module that lacks sufficient independent positives for defensible prediction and therefore presents historical surveillance with uncertainty instead of predictions.
- **Feasibility_Assessment**: A multi-factor evaluation of whether a pathogen/Modeling_Unit can support valid forecasting, considering training and test positive counts, temporal coverage, geographic coverage, calibration, and prediction stability — not a single positive-count threshold.
- **OBSERVED**: A data value recorded from a real empirical source (surveillance, testing, weather, demographics).
- **PREDICTED**: A value produced by a validated Risk_Model for a future period.
- **SIMULATED**: A value produced from a clearly documented synthetic operational network or what-if scenario, never implying a real observed transaction.
- **Synthetic_Operational_Network**: A clearly documented synthetic retail shipment/inventory dataset used for decision-support demonstration, kept isolated from real observational data.
- **High_Need_Community**: A geography flagged by food-access and vulnerability indicators as having elevated food-security need.
- **Vulnerable_Population_Lens**: A view that filters or weights risk by population groups at elevated health risk (pregnancy and newborns, children under 5, adults 65 and older).
- **Human_Review**: A required step in which a person evaluates a high-consequence recommendation before action.
- **Provenance_Record**: A documented entry capturing a dataset's source, access date, license, geography, time coverage, update frequency, transformations, and known limitations.

## Requirements

### Requirement 1: Decision context and consistent primary actor (Task 1; Operational decision support)

**User Story:** As the Food Safety Operations Director of a regional grocery retail chain, I want the platform built around my specific decision, horizon, and authority, so that every analysis and recommendation maps to an operational choice I can actually make.

#### Acceptance Criteria

1. THE VulneraSafe_System SHALL record a decision statement that names the Decision_Maker, the specific decision being supported, the geography, the commodity scope, and the Prediction_Horizon, and SHALL reject the decision statement with an error indication identifying each missing element if any of these five elements is absent.
2. THE VulneraSafe_System SHALL use the Food Safety Operations Director of a regional grocery retail chain as the single primary actor across the Data_Pipeline, the Risk_Model, the Decision_Engine, and the Web_App.
3. IF the primary actor referenced by any of the Data_Pipeline, the Risk_Model, the Decision_Engine, or the Web_App differs from the Food Safety Operations Director of a regional grocery retail chain, THEN THE VulneraSafe_System SHALL flag the inconsistency with an error indication naming the component and the conflicting actor.
4. WHERE food availability, equitable access, or minimizing food loss conflicts with a food-safety constraint, THE VulneraSafe_System SHALL treat the food-safety constraint as the governing requirement and SHALL record which competing objective was overridden.
5. THE VulneraSafe_System SHALL document the Decision_Maker's operational constraints, decision authority, and acceptable actions in a single stored record that is retrievable by both the Decision_Engine and the Web_App.

### Requirement 2: One Health core-dataset integration (Task 1; One Health multi-source integration)

**User Story:** As the Decision_Maker, I want human illness, food/animal testing, environmental, supply-chain, and vulnerability signals connected in one reproducible pipeline, so that risk reflects the whole food system rather than one dataset.

#### Acceptance Criteria

1. THE Data_Pipeline SHALL ingest the three core streams: FSIS laboratory sampling and recall data, the PulseNet_Stream human-health surveillance signal, and NOAA_CDO weather and climate data, recording for each stream the source identifier, retrieval timestamp, and record count ingested.
2. IF the PulseNet_Stream organizer extract is unavailable, THEN THE Data_Pipeline SHALL ingest a CDC_Substitute human-illness dataset and SHALL record the justification for the substitution in the provenance table.
3. IF ingestion of the FSIS stream or the NOAA_CDO stream fails or returns zero records, THEN THE Data_Pipeline SHALL halt the affected stream, retain any already-ingested data for the other streams, and record an error indication identifying the failed stream and the failure reason in the missingness report.
4. THE Data_Pipeline SHALL integrate at least two added datasets, including at least one food-security or population-vulnerability dataset selected from ACS and Food_Access_Atlas.
5. THE Data_Pipeline SHALL produce a One Health system diagram that includes all five pathways (human, food/animal, environmental, supply-chain, and food-security) and labels, for each pathway, the specific dataset(s) that supply it.
6. THE Data_Pipeline SHALL produce harmonized analytic tables accompanied by a data dictionary that defines every column, its data type, and its units.
7. THE Data_Pipeline SHALL produce a provenance and licensing table identifying, for each source, its origin, retrieval date, and license terms; a missingness report quantifying the proportion of missing values per field; and a temporal and spatial alignment report stating the common time granularity and geographic unit to which sources were aligned.
8. WHEN the ingestion scripts are executed against the recorded sources, THE Data_Pipeline SHALL regenerate harmonized analytic tables whose schema and row-level contents match the originally produced tables, or SHALL record each deviation and its cause.

### Requirement 3: Dataset audit and feasibility assessment (Task 1; Data science rigor and validation)

**User Story:** As a data scientist on the team, I want a real per-dataset audit before modeling, so that modeling targets rest on verified counts, denominators, and coverage rather than assumptions.

#### Acceptance Criteria

1. WHEN auditing an FSIS dataset, THE Data_Pipeline SHALL record for that dataset the observation count, positive count, negative count, Positivity_Rate computed using the Program_Denominator defined for that dataset's program, yearly and quarterly observation distributions, establishment identifiers, location identifiers, and record timestamps.
2. IF a required audit field in criterion 1 cannot be computed or is absent for a dataset, THEN THE Data_Pipeline SHALL record the affected field, the reason it is unavailable, and SHALL mark that dataset's audit as incomplete rather than omitting the dataset.
3. THE Data_Pipeline SHALL record, per dataset, the sample-collection date range, the public-availability (publication) date, and the reporting delay computed as the difference between publication date and sample-collection date.
4. THE Data_Pipeline SHALL run Leakage checks on each dataset and SHALL record, per dataset, a pass or fail result for each Leakage check and the fields or date relationships that triggered any failure.
5. THE Data_Pipeline SHALL produce a dataset feasibility report that classifies each pathogen as predictive-capable or non-predictive using a Feasibility_Assessment that jointly considers the training-positive count, the test-positive count, temporal coverage, geographic coverage, achievable calibration, and prediction stability, and SHALL record the value of each factor and the rationale for each classification.
6. THE Data_Pipeline SHALL define the Modeling_Unit as pathogen x commodity x region x time and SHALL select the temporal resolution (monthly or quarterly) independently for each pathogen based on that pathogen's actual sample availability and positive counts, recording the selected resolution and the availability evidence per pathogen.
7. WHERE a data source cannot be accessed, THE Data_Pipeline SHALL record the exact error returned by the access attempt and the manual download instructions for that source, and SHALL continue the audit using the independently accessible datasets.

### Requirement 4: Data integrity and authenticity (Task 1; Team science, reproducibility, and communication)

**User Story:** As a judge assessing reproducibility, I want every empirical value traceable to a verified public source, so that I can trust that no data or results were fabricated.

#### Acceptance Criteria

1. WHEN the Data_Pipeline ingests a dataset, THE Data_Pipeline SHALL source it from a verified public source and SHALL record in the Provenance_Record the download URL, the access date in ISO 8601 format (YYYY-MM-DD), and a content checksum computed over the downloaded file.
2. IF a dataset's recorded content checksum does not match the checksum of the file currently in use, THEN THE Data_Pipeline SHALL reject the dataset, SHALL report a verification error identifying the affected dataset, and SHALL NOT include the dataset in any downstream processing.
3. WHEN the Data_Pipeline processes a downloaded dataset, THE Data_Pipeline SHALL inspect the actual columns present in that dataset and SHALL record in the Provenance_Record the total sample count, the positive-label count, the geographic coverage, the temporal coverage, the license identifier, the per-column missingness fraction (0.0 to 1.0), and any known biases.
4. THE VulneraSafe_System SHALL store Synthetic_Operational_Network data in a storage location separate from real observational data such that no record set contains both, and SHALL label every synthetic record with the value SIMULATED.
5. THE VulneraSafe_System SHALL use placeholder values only within datasets labeled as synthetic operational demonstration datasets and SHALL NOT assign placeholder values to any empirical machine-learning label.
6. IF a required empirical value is unavailable, THEN THE VulneraSafe_System SHALL record a gap entry identifying the missing value in the Provenance_Record, SHALL report the gap to the caller, and SHALL NOT substitute a fabricated, estimated, or placeholder value for that empirical value.

### Requirement 5: Predictive target and horizon definition (Task 2; Data science rigor and validation)

**User Story:** As a data scientist, I want the prediction target and horizon fixed before tuning, so that the model is evaluated honestly against a defensible baseline.

#### Acceptance Criteria

1. THE Risk_Model SHALL define the prediction target as a binary indicator of whether pathogen-positive sampling in the next Prediction_Horizon exceeds a documented baseline computed over a fixed lookback window of at least 12 months or a stated program-specific threshold, at the Modeling_Unit.
2. IF a Modeling_Unit has fewer than the lookback window's required periods of history, THEN THE Risk_Model SHALL exclude that Modeling_Unit from labeling and SHALL record the exclusion reason.
3. THE Risk_Model SHALL fix the Prediction_Horizon to a single stated value before any model tuning begins and SHALL NOT alter it after tuning has started.
4. THE Risk_Model SHALL evaluate at least one count or rate formulation and at least one binary formulation of the target and SHALL record the selected formulation, the rationale, and the comparison metrics used.
5. THE Risk_Model SHALL state that the modeled target is surveillance risk at the Modeling_Unit and SHALL NOT state or imply that a specific shipment is contaminated.

### Requirement 6: Multi-pathogen modeling with suitability gating (Task 2; Data science rigor and validation)

**User Story:** As the Decision_Maker, I want predictions only where the data support them and clearly marked historical views elsewhere, so that I am never misled by a model trained on too few positives.

#### Acceptance Criteria

1. THE Risk_Model SHALL build a Salmonella in raw poultry module as the primary predictive module that produces predictive output for its Modeling_Units.
2. IF the Feasibility_Assessment classifies the Salmonella module as non-predictive, THEN THE Risk_Model SHALL mark the Salmonella module as a Non-Predictive_Module and SHALL present historical surveillance with uncertainty instead of predictions.
3. WHERE the Feasibility_Assessment classifies a Listeria in RTE meat and poultry module or a STEC in raw beef module as predictive-capable, THE Risk_Model SHALL build a predictive module for that pathogen.
4. IF the Feasibility_Assessment classifies a Listeria or STEC module as non-predictive, THEN THE Risk_Model SHALL mark that module as a Non-Predictive_Module and SHALL present historical surveillance with uncertainty instead of predictions.
5. WHEN a pathogen module is built or updated, THE Risk_Model SHALL expose that module's status (predictive or Non-Predictive_Module) and the Feasibility_Assessment factor values to the Web_App.

### Requirement 7: Features, baselines, and integrated models (Task 2; Data science rigor and validation)

**User Story:** As a data scientist, I want transparent baselines and integrated models built from leakage-safe features, so that any performance gain is attributable and defensible.

#### Acceptance Criteria

1. THE Risk_Model SHALL build a Baseline_Model comprising both a historical or seasonal baseline and a regularized logistic or statistical model, and SHALL record each Baseline_Model's configuration and evaluation metrics for comparison against integrated models.
2. THE Risk_Model SHALL build at least one integrated model using a gradient-boosting method (XGBoost, LightGBM, or CatBoost) and at least one Random Forest model, and SHALL record each integrated model's configuration and evaluation metrics.
3. WHERE the target exhibits class imbalance with a positive-class prevalence below 10 percent or a defined hierarchical structure, THE Risk_Model SHALL apply a rare-event or hierarchical method to that target.
4. THE Risk_Model SHALL derive features from historical FSIS outcomes, positivity rates, and sampling counts, from CDC signals available at or before the Prediction_Horizon cutoff, from NOAA weather anomalies, and from seasonal and geographic attributes.
5. THE Risk_Model SHALL construct every feature using only information timestamped at or before the Prediction_Horizon cutoff, with no Leakage.
6. IF any feature's source data is timestamped after the Prediction_Horizon cutoff, THEN THE Risk_Model SHALL exclude that data from feature construction and record the excluded source so that the exclusion is auditable.

### Requirement 8: Time-aware validation and uncertainty (Task 2; Data science rigor and validation)

**User Story:** As a judge assessing rigor, I want chronological validation, rare-event-appropriate metrics, calibration, and uncertainty, so that reported performance reflects real forecasting ability over time and geography.

#### Acceptance Criteria

1. THE Risk_Model SHALL use chronological validation as the primary evaluation, with all training timestamps strictly earlier than all test timestamps, rolling-origin validation using at least 3 origins, and the most recent 20 percent of periods reserved as an untouched final test period excluded from training and tuning.
2. WHERE sufficient establishments are available, THE Risk_Model SHALL additionally run Establishment_Holdout_Validation as a secondary check that withholds all observations of a held-out set of establishments from training, and SHALL report its results separately from the chronological results to characterize geographic or establishment generalization.
3. THE Risk_Model SHALL report PR-AUC, ROC-AUC, precision, recall, and Brier score as numeric values, a calibration plot, and 95 percent uncertainty intervals for each reported metric.
4. THE Risk_Model SHALL report each metric in criterion 3 disaggregated as one value per region and one value per time period.
5. THE Risk_Model SHALL report false-positive and false-negative counts and rates, and performance under a limited inspection-budget condition defined as top-K prioritization for at least one stated value of K.
6. WHEN a validation run completes, THE Risk_Model SHALL export the model artifacts, figures, and predictions produced by that run, and SHALL report only metric values computed from those exported predictions.
7. IF a required metric cannot be computed for a configuration, THEN THE Risk_Model SHALL omit that metric and record that it was unavailable rather than reporting a fabricated or placeholder value.

### Requirement 9: Interpretation and ablations (Task 2; One Health multi-source integration)

**User Story:** As the Decision_Maker, I want to know which signals drive predictions and what each data domain adds, so that I understand and trust the risk estimates.

#### Acceptance Criteria

1. WHEN a predictive module completes training, THE Risk_Model SHALL produce, for that module, a permutation importance ranking of all input features and SHAP attribution values for each input feature.
2. WHEN a predictive module completes training, THE Risk_Model SHALL produce an error analysis for that module that reports at least one accuracy metric and at least one calibration or error-distribution metric on a held-out evaluation set.
3. THE Risk_Model SHALL run exactly four ablation configurations: FSIS-only, FSIS plus CDC, FSIS plus NOAA, and the full integrated configuration combining FSIS, CDC, and NOAA.
4. WHEN all four ablation configurations have been evaluated on the same held-out evaluation set using the same evaluation metric, THE Risk_Model SHALL report the marginal contribution of each configuration relative to the FSIS-only baseline, expressed as the signed change in that evaluation metric.
5. IF the marginal contribution of a configuration is negative, THEN THE Risk_Model SHALL report that contribution with its negative sign rather than omitting, clamping to zero, or suppressing it.

### Requirement 10: Safety-constrained decision actions (Task 3; Operational decision support)

**User Story:** As the Decision_Maker, I want model risk translated into concrete actions bounded by hard safety rules, so that I can act proactively without ever trading safety for cost or availability.

#### Acceptance Criteria

1. THE Decision_Engine SHALL support at least six distinct recommended actions: prioritize additional testing or inspection; request supplier documentation or review; escalate concerning shipments for human assessment; match verified product or lot identifiers against confirmed recalls; isolate inventory under confirmed recall or safety requirements; and allocate compliant replacement inventory to minimize interruption to food access.
2. WHEN the Decision_Engine generates a recommendation, THE Decision_Engine SHALL return each recommended action with the affected product or lot identifier, the triggering risk condition, and a priority rank ordered from highest to lowest.
3. THE Decision_Engine SHALL treat food-safety rules as hard constraints that are never relaxed to improve any secondary objective, including cost or availability.
4. THE Decision_Engine SHALL optimize secondary objectives, including inspection resource allocation, delivery continuity, minimizing preventable shortages, transport and delay reduction, and equitable access for High_Need_Communities, only within the food-safety constraints, such that no secondary-objective gain is produced by violating a food-safety constraint.
5. IF two or more candidate recommendations are feasible within the food-safety constraints, THEN THE Decision_Engine SHALL select the recommendation that best satisfies the secondary objectives and SHALL retain all food-safety constraints as satisfied.
6. THE Decision_Engine SHALL NOT recommend distributing inventory under a confirmed recall.
7. IF inventory is under a confirmed recall, THEN THE Decision_Engine SHALL recommend isolating that inventory and SHALL indicate the confirmed-recall condition as the basis for the action.
8. THE Decision_Engine SHALL compute recommendations using an optimization method (OR-Tools or equivalent) and SHALL report only computed result values.
9. IF the optimization method cannot produce a feasible solution within the food-safety constraints, THEN THE Decision_Engine SHALL return no distribution recommendation and SHALL return an indication that no safety-compliant solution was found.

### Requirement 11: Policy comparison and scenarios (Task 3; Operational decision support)

**User Story:** As the Decision_Maker, I want three policies compared across realistic scenarios with quantified trade-offs, so that I can see what model-guided, access-aware decisions change.

#### Acceptance Criteria

1. THE Decision_Engine SHALL compare exactly three policies within a single evaluation run using identical scenario inputs and the same evaluation metrics: policy A (business-as-usual), policy B (model-guided safety prioritization), and policy C (model-guided safety plus food-access-aware optimization).
2. THE Decision_Engine SHALL evaluate at least three scenarios: a Listeria RTE recall with replacement-inventory allocation; an elevated Salmonella signal with limited inspection resources; and a STEC concern with limited supply and High_Need_Community requirements.
3. WHEN a policy is evaluated for a scenario, THE Decision_Engine SHALL produce for that policy-scenario pair a numeric value for each of the following metrics: inspection workload, priority-review coverage, retrospective positive-test capture, inventory availability, compliant food delivered, supply disruptions, and service to High_Need_Communities.
4. WHEN a policy is evaluated for a scenario, THE Decision_Engine SHALL report, for each metric in criterion 3, the difference relative to policy A and an uncertainty estimate expressed as a range or interval for that metric.
5. IF retrospective positive-test capture cannot be validly computed for a policy-scenario pair, THEN THE Decision_Engine SHALL omit the numeric value for that metric and SHALL record an indicator stating that the metric is not valid for that pair.
6. WHERE real retail shipment or inventory data are unavailable, THE Decision_Engine SHALL use the Synthetic_Operational_Network and SHALL label the affected outputs as SIMULATED.
7. IF a recommendation is a high-consequence decision, THEN THE Decision_Engine SHALL block the recommended action from execution until a Human_Review step is completed.

### Requirement 12: Web application core interface (Task 4; Kiro implementation and usability)

**User Story:** As the Decision_Maker, I want a responsive command center with the five mandatory panels, so that I can see risk, triage attention, test scenarios, review recommended actions, and inspect the evidence.

#### Acceptance Criteria

1. THE Web_App SHALL provide a Current Risk Overview panel presenting both an interactive geography view and an interactive time-series view driven by dated surveillance data and validated predictions.
2. WHEN the Decision_Maker selects a geographic region in the Current Risk Overview, THE Web_App SHALL update the time-series view to reflect the selected region.
3. IF the Current Risk Overview has no dated surveillance data or no validated predictions available for the selected region and time range, THEN THE Web_App SHALL display an empty-state indication identifying the missing data rather than rendering an empty or misleading view.
4. THE Web_App SHALL provide a Prioritized Attention Queue that lists items ordered from highest to lowest priority.
5. THE Web_App SHALL provide a Scenario Builder with user-adjustable controls for inspection budget, inventory supply, delays, and food-access settings.
6. WHEN the Decision_Maker submits a Scenario Builder control value outside its defined valid range, THE Web_App SHALL reject the submission and display an indication identifying the invalid control and its accepted range, retaining the previously valid values.
7. THE Web_App SHALL provide a Recommended Action Panel that shows, for each recommended action, the action, its rationale, the governing constraints, and the Human_Review requirement.
8. THE Web_App SHALL provide an Explanation and Evidence Panel that shows, for each recommendation, the source data, the uncertainty, and the limitations.
9. THE Web_App SHALL use the technology stack React, TypeScript, Vite, Tailwind CSS, a map library (MapLibre or equivalent), a charting library (ECharts or Recharts), and React Flow.

### Requirement 13: Web application analytical features (Task 4; Kiro implementation and usability)

**User Story:** As the Decision_Maker, I want multi-pathogen, vulnerability, replay, what-if, policy-comparison, and evidence-graph views, so that I can explore risk and reasoning from multiple angles.

#### Acceptance Criteria

1. WHEN the Decision_Maker switches the selected pathogen among Salmonella, Listeria, and STEC, THE Web_App SHALL update the maps, trends, evidence, and model-status displays to reflect the selected pathogen within 3 seconds.
2. THE Web_App SHALL provide a Vulnerable_Population_Lens with selectable views for pregnancy and newborns, children under 5, and adults 65 and older.
3. WHEN the Decision_Maker submits a cutoff date to the historical forecast replay, THE Web_App SHALL display only information available at or before that cutoff date and SHALL then reveal later observed outcomes alongside the predicted values for that cutoff.
4. IF a submitted replay cutoff date is outside the available data range, THEN THE Web_App SHALL reject it and display an indication of the accepted date range, retaining the prior valid cutoff.
5. THE Web_App SHALL provide a what-if intervention simulator and a side-by-side comparison of policies A, B, and C on a common set of metrics.
6. THE Web_App SHALL provide an evidence-to-action graph with connected nodes tracing Data to Model to Alert to Evidence to Decision to Expected impact.
7. THE Web_App SHALL provide a supply-chain network view and an export control that produces a downloadable file of the currently displayed results.
8. IF an export is requested when no results are currently displayed, THEN THE Web_App SHALL decline the export and display an indication that there are no results to export.

### Requirement 14: Labeling, provenance presentation, and status distinction (Task 4; Kiro implementation and usability)

**User Story:** As the Decision_Maker, I want every map and figure labeled and every value tagged by its nature, so that I never confuse observed data, predictions, and simulations.

#### Acceptance Criteria

1. WHEN the Web_App renders a risk map, THE Web_App SHALL label that map with the pathogen, geography, reporting period, model or surveillance status, uncertainty, and data freshness, leaving none of these fields blank.
2. IF a required map label value is unavailable, THEN THE Web_App SHALL display an explicit not-available indicator for that field rather than omitting the field.
3. THE Web_App SHALL tag every displayed value as OBSERVED, PREDICTED, or SIMULATED according to the value's provenance, assigning exactly one tag to each displayed value.
4. THE Web_App SHALL render orange or red only on elements that represent an active alert condition.
5. THE Web_App SHALL use a scientific light theme with white or off-white backgrounds and navy and teal accents.
6. THE Web_App SHALL NOT display any metric that is decorative or that is not derived from OBSERVED, PREDICTED, or SIMULATED data.

### Requirement 15: GitHub Pages deployment with precomputed artifacts (Task 4; Kiro implementation and usability)

**User Story:** As a judge, I want the app to run on GitHub Pages with no paid services, so that I can review a working, reproducible tool.

#### Acceptance Criteria

1. WHEN the Web_App initializes, THE Web_App SHALL load model outputs exclusively from precomputed reproducible CSV, JSON, or Parquet artifacts and SHALL NOT issue requests to a live backend.
2. THE Web_App SHALL operate as a static client-side application that makes no server-side API requests at runtime.
3. IF a required precomputed artifact is missing, unreadable, or invalid at load time, THEN THE Web_App SHALL display an error indication identifying the failed artifact and SHALL render the portions of the interface whose artifacts loaded successfully.
4. THE Web_App SHALL be deployable to GitHub Pages using only free-tier services with no paid dependency.
5. WHEN the analysis pipeline completes, THE VulneraSafe_System SHALL generate the Web_App artifacts such that identical pipeline inputs produce identical artifacts.

### Requirement 16: Responsible interpretation constraints (Guardrails; Operational decision support)

**User Story:** As a judge assessing responsible use, I want the platform to refuse unsupported claims and surface uncertainty and human review, so that it supports rather than replaces regulatory and operational judgment.

#### Acceptance Criteria

1. THE VulneraSafe_System SHALL present itself as decision support and SHALL NOT present itself as a regulatory determination, outbreak declaration, or substitute for epidemiologic investigation.
2. THE VulneraSafe_System SHALL NOT infer contamination from a model alone and SHALL NOT declare a product safe or unsafe solely from predicted risk.
3. THE VulneraSafe_System SHALL NOT infer causal outbreak linkage from genomic or temporal similarity alone.
4. WHEN a recommendation is displayed, THE VulneraSafe_System SHALL display, alongside that recommendation, the supporting evidence, the uncertainty expressed as a quantified measure (a confidence interval, probability, or confidence score with its defined scale), and an indication that human review is required before acting.
5. IF a MODEL-GENERATED recommendation is displayed without an available quantified uncertainty measure or without supporting evidence, THEN THE VulneraSafe_System SHALL withhold that model-generated recommendation and display an indication that it cannot be shown because required supporting evidence or uncertainty is unavailable.
6. THE VulneraSafe_System SHALL present verified official recall or public-health alerts as regulatory evidence independently of any model-generated uncertainty estimate, and SHALL NOT suppress a verified official alert because a predictive uncertainty estimate is unavailable, while visually distinguishing regulatory evidence from model-generated alerts.
7. THE VulneraSafe_System SHALL NOT infer individual medical status from regional demographics.
8. THE VulneraSafe_System SHALL distinguish historical associations from prospective predictive performance by labeling each reported performance measure as either historical or prospective, and SHALL NOT report a measured benefit that exceeds the value computed on the evaluation data.
9. WHEN recommendations are generated, THE VulneraSafe_System SHALL test whether those recommendations systematically disadvantage High_Need_Communities and SHALL display the result of that test as a pass or fail outcome with the measured disparity value.

### Requirement 17: Team science and added data value (Task 5; Team science, reproducibility, and communication)

**User Story:** As a judge assessing team science, I want documented roles, a genuine added-data ablation, and a real decision changed by interdisciplinary input, so that the multi-source value and collaboration are evidenced rather than asserted.

#### Acceptance Criteria

1. THE VulneraSafe_System SHALL document the actual team members and their genuine contributions, mapping each real contribution to the discipline(s) it covered among food-safety science, epidemiology, agriculture and environment, machine learning and data science, geospatial analysis, retail supply-chain operations, and food access and equity, and SHALL identify any discipline not covered by the team as a gap rather than attributing it to a fabricated specialist.
2. THE VulneraSafe_System SHALL document at least two added external datasets, each identified by source and the domain it represents.
3. THE VulneraSafe_System SHALL document a genuine added-data ablation comparing at least one baseline configuration without the added dataset or domain against the configuration with it added, reporting at least one quantitative metric for each configuration and the measured difference.
4. THE VulneraSafe_System SHALL document at least one actual team decision that changed because of input from a real team member's discipline or a real stakeholder, recording the input source, the prior decision, and the revised decision.
5. IF any team member, discipline coverage, discussion, stakeholder participation, or team decision cannot be traced to a real recorded source, THEN THE VulneraSafe_System SHALL exclude it from the team science documentation rather than represent it as having occurred.
6. THE VulneraSafe_System SHALL document at least one recommendation for a future partner or dataset and a team science statement not exceeding one page.

### Requirement 18: Final submission package (Submission; Team science, reproducibility, and communication)

**User Story:** As a judge, I want all six submission components and answers to all ten final-report questions, so that the submission is complete and fully reproducible.

#### Acceptance Criteria

1. THE VulneraSafe_System SHALL deliver all six submission components: (a) reproducible analysis notebooks or scripts; (b) the Kiro development artifacts comprising specs, steering files, prompts, hooks, and disclosed manual changes; (c) a runnable web application with build and deploy instructions; (d) a data dictionary and provenance file; (e) a PDF report; and (f) a README with a reproducibility requirements list.
2. IF any of the six submission components in criterion 1 is absent, THEN THE VulneraSafe_System SHALL identify the missing component rather than present the package as complete.
3. THE PDF report SHALL include a dedicated section for each of methods, results, model validation, uncertainty, figures, scenario comparison, team science, and limitations.
4. THE PDF report SHALL provide an identifiable response to each of the ten final-report questions: (1) the decision-maker, decision, and horizon; (2) how each core dataset contributes to the One Health picture; (3) which additional datasets were added and what changed; (4) the outcome or risk signal modeled and why; (5) integrated versus baseline performance including calibration and performance over time and geography; (6) which errors matter most and the consequences of false positives versus false negatives; (7) where food safety and food security conflicted and how the trade-off was handled; (8) a walk-through of one realistic scenario from signal to model to action to evidence; (9) how team science changed the work; and (10) what the tool can support today, what it should never claim, and what data and validation real deployment would require.
5. IF any of the ten final-report questions lacks an identifiable response, THEN THE VulneraSafe_System SHALL flag that question as unanswered rather than present the report as complete.
6. WHERE AI assistance contributed to analysis, code, or report content, THE VulneraSafe_System SHALL disclose that AI-assisted work.
7. IF deployment has not been verified, THEN THE VulneraSafe_System SHALL NOT claim that the application is deployed.

## Constraints and Assumptions

This section records decisions and the points where the user's project prompt and the authoritative brief interact. Where a conflict exists, the brief governs.

1. **Team-selected actor confirmed as retailer.** The brief names the primary decision-maker as a team-selected supply-chain actor and lists "retailer" as a valid option. The project selects the Food Safety Operations Director of a regional grocery retail chain. This is consistent with the brief, not a conflict.
2. **Salmonella is the only reliably predictive pathogen expected.** The brief anchors on Salmonella in FSIS-regulated poultry and allows broadening "when justified by the data." Listeria and STEC modules are therefore gated on real data suitability and may be marked Non-Predictive_Module (Requirement 6).
3. **PulseNet substitution.** The brief states PulseNet access is limited to participating laboratories and permits a public CDC human-illness substitute when an organizer extract is unavailable, provided a human-health surveillance signal is retained and the substitution is justified (Requirement 2, AC 2).
4. **Synthetic operational network isolation.** The brief does not supply retailer shipment/inventory data. A Synthetic_Operational_Network is used for decision-support demonstration and is kept isolated from real observational data and labeled SIMULATED (Requirement 4, AC 3; Requirement 11, AC 4).
5. **GitHub Pages precomputed-artifact architecture.** The brief recommends React and permits precomputing model outputs as CSV/JSON artifacts when a live backend is impractical, requiring no AWS service beyond Kiro. The platform therefore uses a static, precomputed-artifact architecture (Requirement 15).
6. **48-hour time box.** The work is produced within a 48-hour hackathon. Scope decisions (pathogen gating, synthetic operational data, precomputed artifacts) reflect this constraint while preserving the brief's required rigor and guardrails.
7. **FSIS causal-linkage caution.** The brief warns that FSIS sampling and WGS identifiers alone cannot establish causal linkage to human illness; this is enforced as a responsible-interpretation constraint (Requirement 16, AC 3).
8. **Food safety as the hard constraint.** Across all requirements, food availability, equitable access, and minimizing food loss are secondary objectives that never override a food-safety constraint (Requirement 1, AC 3; Requirement 10, AC 2).
9. **Multi-factor feasibility replaces the single positive-count threshold.** Pathogen forecasting feasibility is determined by a multi-factor Feasibility_Assessment (training-positive count, test-positive count, temporal coverage, geographic coverage, calibration, and prediction stability) rather than a single ≥30 independent-positive threshold (Requirement 3, AC 5; Requirement 6, AC 2–5).
10. **Per-pathogen temporal resolution.** Monthly versus quarterly temporal resolution is selected independently for each pathogen from that pathogen's actual sample availability and positive counts, not by requiring every geographic Modeling_Unit to meet an arbitrary positive count (Requirement 3, AC 6).
11. **Chronological validation primary, establishment-holdout secondary.** Chronological (time-aware) validation is the primary evaluation; Establishment_Holdout_Validation runs as a separate secondary check where sufficient establishments are available, rather than folding establishment grouping into every chronological split (Requirement 8, AC 1–2).
12. **Verified official recalls are regulatory evidence independent of model uncertainty.** Verified official recall or public-health alerts are presented as regulatory evidence and are never suppressed by a missing model-generated uncertainty estimate; only model-generated recommendations are withheld when quantified uncertainty or supporting evidence is unavailable (Requirement 16, AC 5–6).
13. **Team science documents only real members and contributions.** The team science documentation records the actual team members and their genuine contributions mapped to the disciplines they covered, identifies uncovered disciplines as gaps, and never fabricates people, discussions, stakeholders, or decisions (Requirement 17, AC 1, 4, 5).
