/**
 * Python-to-React data contract for VulneraSafe AI (web side).
 *
 * These interfaces EXACTLY mirror the Python `TypedDict`s in
 * `src/artifacts/schemas.py`. Field names are `snake_case` because the JSON
 * artifacts under `web/public/data` are serialized verbatim from Python and
 * must validate identically on both sides. A parity test keeps the two
 * definitions from silently drifting.
 *
 * Design reference: design.md section "Python-to-React Data Contract".
 *
 * Interface -> consuming panel(s):
 *   Manifest             -> App shell, all panels (gating)
 *   ModuleStatus         -> App shell, multi-pathogen explorer, model-status displays
 *   RiskTimeseriesPoint  -> Current Risk Overview, historical forecast replay
 *   RiskMapFeature       -> Current Risk Overview, multi-pathogen explorer, Vulnerable Population Lens
 *   AttentionQueueItem   -> Prioritized Attention Queue
 *   Recommendation       -> Recommended Action Panel, Explanation/Evidence Panel
 *   RegulatoryAlert      -> Regulatory Alerts strip
 *   ScenarioMetric       -> Policy comparison, what-if simulator, Scenario Builder
 *   AblationResult       -> Explanation/Evidence Panel, policy comparison
 *   ModelMetric          -> Explanation/Evidence Panel, Current Risk Overview
 *   CalibrationPoint     -> Explanation/Evidence Panel (calibration plot)
 *   EvidenceGraphNode    -> Evidence-to-action graph
 *   EvidenceGraphEdge    -> Evidence-to-action graph
 *   ProvenanceEntry      -> Explanation/Evidence Panel
 *   EquityTest           -> Recommended Action Panel / Explanation/Evidence Panel
 *   FeasibilityReport    -> Multi-pathogen explorer, model-status displays
 */

// --------------------------------------------------------------------------
// Shared literal unions
// --------------------------------------------------------------------------

/** Provenance tag attached to every displayed value-bearing field (Req 14.3). */
export type StatusTag = "OBSERVED" | "PREDICTED" | "SIMULATED";

/** Distinguishes a model-derived alert from a verified regulatory recall. */
export type AlertSource = "MODEL" | "REGULATORY";

/** Whether a pathogen module supports defensible prediction (Req 6). */
export type ModuleClassification = "predictive" | "non_predictive";

/** Per-pathogen temporal resolution selected from sample availability. */
export type TemporalResolution = "monthly" | "quarterly";

/** Validation protocol a model metric was computed under (Req 8). */
export type ValidationKind = "chronological" | "establishment_holdout";

/** Policy under comparison (A, B, C) (Req 11). */
export type Policy = "A" | "B" | "C";

/** Ablation configuration over data sources (Req 9.3). */
export type AblationConfig = "fsis_only" | "fsis_cdc" | "fsis_noaa" | "full";

/** Evidence-graph node kinds Data->Model->Alert->Evidence->Decision->Impact. */
export type EvidenceNodeKind =
  | "Data"
  | "Model"
  | "Alert"
  | "Evidence"
  | "Decision"
  | "Impact";

// --------------------------------------------------------------------------
// Feasibility primitives
// --------------------------------------------------------------------------

export interface FeasibilityFactor {
  name: string;
  value: number;
  threshold: number;
  passed: boolean;
}

// --------------------------------------------------------------------------
// manifest.json
// --------------------------------------------------------------------------

export interface ModuleStatus {
  pathogen: string;
  status: ModuleClassification;
  feasibility_factors: FeasibilityFactor[];
  temporal_resolution: TemporalResolution;
}

export interface Manifest {
  artifact_version: string; // semver
  generated_at: string; // ISO 8601
  pathogens: Record<string, ModuleStatus>;
  data_freshness: Record<string, string>;
}

// --------------------------------------------------------------------------
// risk_timeseries
// --------------------------------------------------------------------------

export interface RiskTimeseriesPoint {
  pathogen: string;
  commodity: string;
  region: string;
  period: string;
  value: number;
  ci_low: number;
  ci_high: number;
  status: StatusTag;
}

// --------------------------------------------------------------------------
// risk_map
// --------------------------------------------------------------------------

export interface RiskMapFeature {
  region: string;
  pathogen: string;
  period: string;
  risk: number;
  uncertainty: number;
  status: StatusTag;
  data_freshness: string;
}

// --------------------------------------------------------------------------
// attention_queue
// --------------------------------------------------------------------------

export interface AttentionQueueItem {
  rank: number;
  target_id: string;
  target_type: string;
  region: string;
  pathogen: string;
  risk: number;
  triggering_condition: string;
  status: StatusTag;
}

// --------------------------------------------------------------------------
// recommendations
// --------------------------------------------------------------------------

export interface Recommendation {
  action: string;
  target_id: string;
  rationale: string;
  constraints: string[];
  human_review_required: boolean;
  evidence_refs: string[];
  uncertainty: number | null;
  alert_source: AlertSource;
  status: StatusTag;
}

// --------------------------------------------------------------------------
// scenario_results (A/B/C policy comparison, Layer 3)
// --------------------------------------------------------------------------

export interface ScenarioPolicyMetric {
  metric: string;
  value: number | null;
  diff_vs_a: number | null;
  ci_low: number | null;
  ci_high: number | null;
  valid: boolean;
  not_valid_reason: string | null;
  status: StatusTag;
}

export interface ScenarioPolicy {
  policy: string; // "A" | "B" | "C"
  status: StatusTag;
  feasible: boolean;
  no_safety_compliant_solution: boolean;
  isolate_lot_ids: string[];
  human_review_required_actions: string[];
  metrics: ScenarioPolicyMetric[];
}

export interface ScenarioEntry {
  scenario_id: string;
  title: string;
  description: string;
  pathogen: string;
  commodity: string;
  verified_recall: boolean;
  live_official_recall: boolean;
  recall_labeling_note?: string;
  policies: ScenarioPolicy[];
}

export interface ScenarioComparison {
  artifact: string;
  artifact_version: string;
  status: StatusTag;
  primary_actor: string;
  metric_names: string[];
  policies: string[];
  notes: string;
  scenarios: ScenarioEntry[];
}

// --------------------------------------------------------------------------
// vulnerability (Vulnerable Population Lens, Layer 2)
// --------------------------------------------------------------------------

export interface VulnerabilityProfile {
  region: string;
  total_population: number | null;
  elderly_65plus_share: number | null;
  under5_share: number | null;
  low_income_tract_share: number | null;
  low_access_tract_share: number | null;
  acs_vintage: string | null;
  atlas_vintage: string | null;
  status: StatusTag;
}

// --------------------------------------------------------------------------
// regulatory_alerts
// --------------------------------------------------------------------------

export interface RegulatoryAlert {
  recall_id: string;
  product: string;
  lot_ids: string[];
  classification: string;
  date: string;
  source_url: string;
  alert_source: "REGULATORY";
  status: "OBSERVED";
}

// --------------------------------------------------------------------------
// scenario_results
// --------------------------------------------------------------------------

export interface ScenarioMetric {
  policy: Policy;
  scenario: string;
  metric: string;
  value: number | null;
  diff_vs_a: number | null;
  ci_low: number | null;
  ci_high: number | null;
  valid: boolean;
  status: StatusTag;
}

// --------------------------------------------------------------------------
// ablation_results
// --------------------------------------------------------------------------

export interface AblationResult {
  config: AblationConfig;
  metric: string;
  value: number;
  marginal_vs_fsis_only: number;
}

// --------------------------------------------------------------------------
// model_metrics
// --------------------------------------------------------------------------

export interface ModelMetric {
  pathogen: string;
  validation: ValidationKind;
  metric: string;
  value: number | null;
  ci_low: number | null;
  ci_high: number | null;
  region: string | null;
  period: string | null;
}

export interface CalibrationPoint {
  pathogen: string;
  bin_mid: number;
  predicted: number;
  observed: number;
}

// --------------------------------------------------------------------------
// evidence_graph
// --------------------------------------------------------------------------

export interface EvidenceGraphNode {
  id: string;
  kind: EvidenceNodeKind;
  label: string;
}

export interface EvidenceGraphEdge {
  source: string;
  target: string;
}

// --------------------------------------------------------------------------
// provenance
// --------------------------------------------------------------------------

export interface ProvenanceEntry {
  source: string;
  url: string;
  access_date: string;
  license: string;
  geographic_coverage: string;
  temporal_coverage: string;
  checksum: string;
  total_samples: number | null;
  positive_count: number | null;
  missingness: Record<string, number>;
  known_biases: string[];
  notes: string;
}

// --------------------------------------------------------------------------
// equity_test
// --------------------------------------------------------------------------

export interface EquityTest {
  passed: boolean;
  disparity: number;
  threshold: number;
  description: string;
}

// --------------------------------------------------------------------------
// feasibility_report
// --------------------------------------------------------------------------

export interface FeasibilityReport {
  pathogen: string;
  temporal_resolution: TemporalResolution;
  factors: FeasibilityFactor[];
  classification: ModuleClassification;
  rationale: string;
}


// --------------------------------------------------------------------------
// multipathogen_program_product -> Pathogen Explorer (S01)
// --------------------------------------------------------------------------

/**
 * One OBSERVED positivity stratum from the S01 product/program analysis.
 * One record per (pathogen, dimension, category); `dimension` is
 * "program" | "sample_source" | "product" | "overall". `value` is observed
 * positivity (positive_n / sample_n) with a Wilson 95% interval. Always
 * OBSERVED historical surveillance, never a forecast. Mirrors the Python
 * `ProgramProductStratum` TypedDict.
 */
export interface ProgramProductStratum {
  artifact_version: string;
  module_id: string;
  method_version: string;
  pathogen: string;
  commodity: string;
  dimension: string;
  source_column: string | null;
  category: string;
  sample_n: number | null;
  positive_n: number | null;
  value: number | null;
  ci_low: number | null;
  ci_high: number | null;
  ci_method: string;
  units: string;
  status: StatusTag;
  availability_status: string;
  unavailable_reason: string | null;
  fiscal_years: number[];
  generated_at: string;
}

// emerging_risk -> Emerging Signals view (S04)
export interface ProspectiveEval {
  precision: number | null;
  recall: number | null;
  alert_volume: number | null;
  lead_time_periods: number | null;
  availability_lag_note: string;
  beat_persistence: boolean;
}

export interface EmergingRiskStratum {
  artifact_version: string;
  module_id: string;
  method_version: string;
  pathogen: string;
  commodity: string;
  geography_level: string;
  region: string;
  period: string;
  period_start: string;
  sample_n: number | null;
  positive_n: number | null;
  value: number | null;
  ci_low: number | null;
  ci_high: number | null;
  ci_method: string;
  trailing_baseline: number | null;
  baseline_high: number | null;
  persistent_score: number | null;
  retro_anomaly: boolean | null;
  retro_threshold: number | null;
  support_status: string;
  prospective_alert: boolean | null;
  prospective_status: string;
  prospective_eval: ProspectiveEval | null;
  status: StatusTag;
  availability_status: string;
  unavailable_reason: string | null;
  fiscal_years: number[];
  generated_at: string;
}

// establishment_surveillance -> Supplier Monitor view (S03)
export interface PersistenceEvidence {
  repeated_positive_periods: number | null;
  periods_supported: number | null;
  last_supported_period: string | null;
  sampling_gaps: number | null;
}

export interface EstablishmentSurveillanceRecord {
  artifact_version: string;
  module_id: string;
  method_version: string;
  pathogen: string;
  commodity: string;
  geography_level: string;
  region: string;
  establishment_id: string;
  establishment_number: string | null;
  establishment_name: string | null;
  sample_n: number | null;
  positive_n: number | null;
  value: number | null;
  eb_posterior: number | null;
  ci_low: number | null;
  ci_high: number | null;
  ci_method: string;
  peer_rate: number | null;
  persistence: PersistenceEvidence | null;
  support_status: string;
  latitude: number | null;
  longitude: number | null;
  coordinates_status: string;
  predictive_status: string;
  status: StatusTag;
  availability_status: string;
  unavailable_reason: string | null;
  fiscal_years: number[];
  generated_at: string;
}

// one_health_human_comparison -> One Health Insights view (S05)
export interface LeadLagSummary {
  lag_years: number | null;
  correlation: number | null;
  p_value_permutation: number | null;
  ci_low: number | null;
  ci_high: number | null;
  exploratory: boolean;
  note: string;
}

export interface HumanOutbreakComparison {
  artifact_version: string;
  module_id: string;
  method_version: string;
  dataset_sources: string;
  source_accessed_at: string;
  pathogen: string;
  commodity: string;
  geography_level: string;
  region: string;
  period: string;
  fsis_sample_n: number | null;
  fsis_positive_n: number | null;
  fsis_positivity: number | null;
  fsis_ci_low: number | null;
  fsis_ci_high: number | null;
  nors_outbreak_count: number | null;
  nors_illness_count: number | null;
  nors_available_from_year: number | null;
  availability_lag_days: number;
  lead_lag: LeadLagSummary | null;
  coverage_status: string;
  comparison_status: string;
  no_causal_link_note: string;
  units: string;
  status: StatusTag;
  availability_status: string;
  unavailable_reason: string | null;
  fiscal_years: number[];
  generated_at: string;
}

// community_impact -> Vulnerable Communities view (S06)
export interface LensPriority {
  lens: string;
  available: boolean;
  vulnerability_component: number | null;
  priority_score: number | null;
  weights: string;
  unavailable_reason: string | null;
}

export interface WeightSensitivity {
  default_top: string[];
  alt_top: string[];
  rank_stable: boolean;
  note: string;
}

export interface CommunityImpactRecord {
  artifact_version: string;
  module_id: string;
  method_version: string;
  pathogen: string;
  commodity: string;
  geography_level: string;
  region: string;
  hazard_component: number | null;
  hazard_positivity: number | null;
  total_population: number | null;
  affected_population_context: number | null;
  elderly_65plus_share: number | null;
  low_income_tract_share: number | null;
  low_access_tract_share: number | null;
  under5_share: number | null;
  acs_vintage: string | null;
  atlas_vintage: string | null;
  lenses: LensPriority[];
  weight_sensitivity: WeightSensitivity | null;
  contextual_count_note: string;
  status: StatusTag;
  availability_status: string;
  unavailable_reason: string | null;
  generated_at: string;
}


// action_queue -> Surveillance Actions view (decision layer over S01/S03/S04/S06)
export interface ActionQueueItem {
  artifact_version: string;
  module_id: string;
  method_version: string;
  rank: number;
  pathogen: string;
  commodity: string;
  action: string;
  action_category: string;
  target_type: string;
  target: string;
  source_module: string;
  triggering_signal: string;
  evidence_summary: string;
  corroboration_note: string | null;
  human_review: boolean;
  status: StatusTag;
  availability_status: string;
  generated_at: string;
}
// facility_map -> Facility Map view (decision layer over S03 + the action_queue)
export interface FacilityMapCoverage {
  pathogen: string;
  total_selected: number;
  placed: number;
  unplaced: number;
  historical_candidate: number; // informational sub-count of unplaced (overlay candidates)
  unresolved: number; // informational sub-count of unplaced (neither placed nor candidate)
  coverage_pct: number | null; // VERIFIED (placed-only); never inflated by candidates
  coverage_state: string; // "computed" | "not_applicable"
}

export interface FacilityMapItem {
  artifact_version: string;
  module_id: string; // "FACILITYMAP"
  method_version: string; // "fm.v1"
  pathogen: string;
  normalized_establishment_number: string;
  establishment_id: string;
  establishment_number: string | null;
  establishment_name: string | null;
  state: string;
  county: string | null;
  fips_code: string | null;
  eb_posterior: number | null;
  ci_low: number | null;
  ci_high: number | null;
  sample_n: number;
  positive_n: number;
  support_status: string; // "ok" | "low_support"
  source_selection: string; // "s03" | "action_queue" | "both"
  placement_status: string; // "placed" | "unplaced"
  location_status: string; // "mpi_verified" | "historical_candidate" | "unresolved"
  match_method: string | null; // e.g. "fsis_mpi_establishment_id" | "historical_name_state_address"
  match_confidence: string | null; // e.g. "verified" | "probable" | null
  verified_against_fsis_id: boolean; // True only for MPI-directory matches; false for historical candidates
  historical_inspection_number: string | null; // e.g. "M44857 / P44857"; NEVER asserted as linked to the numeric id
  historical_address: string | null;
  coordinate_source: string | null; // e.g. "FSIS MPI Directory (published)" | "external geocode" | null
  evidence_urls: string[]; // may be empty
  lat: number | null;
  lon: number | null;
  address: string | null;
  unplaced_reason: string | null;
  evidence_summary: string;
  coverage: FacilityMapCoverage;
  human_review: boolean;
  status: StatusTag;
  generated_at: string;
}
