"""Python-to-React data contract for VulneraSafe AI.

This module is the single coordination point between the Python analysis layer
(``src/``) and the React/TypeScript web app (``web/``). Every artifact the
exporter writes to ``web/public/data`` is described here as a ``TypedDict``.
The exporter validates each artifact against its TypedDict before writing, and
the web loader validates the same JSON against a mirrored TypeScript interface
in ``web/src/types/artifacts.ts`` after reading. A parity test on both sides
guarantees the two definitions cannot silently drift.

Design reference: design.md section "Python-to-React Data Contract".

Field names use ``snake_case`` because they are serialized verbatim into JSON
artifacts, and the TypeScript interfaces use the same ``snake_case`` names so
the on-disk JSON validates identically on both sides.

Status tagging (Req 14.3): every value-bearing artifact carries exactly one
status tag in {OBSERVED, PREDICTED, SIMULATED}.

TypedDict -> consuming panel(s) map (from the design artifact table):

    Manifest             -> App shell, all panels (gating)
    ModuleStatus         -> App shell, multi-pathogen explorer, model-status displays
    RiskTimeseriesPoint  -> Current Risk Overview, historical forecast replay
    RiskMapFeature       -> Current Risk Overview, multi-pathogen explorer, Vulnerable Population Lens
    AttentionQueueItem   -> Prioritized Attention Queue
    Recommendation       -> Recommended Action Panel, Explanation/Evidence Panel
    RegulatoryAlert      -> Regulatory Alerts strip
    ScenarioMetric       -> Policy comparison, what-if simulator, Scenario Builder
    AblationResult       -> Explanation/Evidence Panel, policy comparison
    ModelMetric          -> Explanation/Evidence Panel, Current Risk Overview
    CalibrationPoint     -> Explanation/Evidence Panel (calibration plot)
    EvidenceGraphNode    -> Evidence-to-action graph
    EvidenceGraphEdge    -> Evidence-to-action graph
    ProvenanceEntry      -> Explanation/Evidence Panel
    EquityTest           -> Recommended Action Panel / Explanation/Evidence Panel
    FeasibilityReport    -> Multi-pathogen explorer, model-status displays
"""

from __future__ import annotations

from typing import Literal, Optional, TypedDict

# --------------------------------------------------------------------------- #
# Shared literal unions
# --------------------------------------------------------------------------- #

#: Provenance tag attached to every displayed value-bearing field (Req 14.3).
StatusTag = Literal["OBSERVED", "PREDICTED", "SIMULATED"]

#: Distinguishes a model-derived alert from a verified regulatory recall.
AlertSource = Literal["MODEL", "REGULATORY"]

#: Whether a pathogen module supports defensible prediction (Req 6).
ModuleClassification = Literal["predictive", "non_predictive"]

#: Per-pathogen temporal resolution selected from sample availability (Req 6.4).
TemporalResolution = Literal["monthly", "quarterly"]

#: Validation protocol a model metric was computed under (Req 8).
ValidationKind = Literal["chronological", "establishment_holdout"]

#: Policy under comparison (A = business-as-usual, B = model-guided safety,
#: C = model-guided safety + food-access-aware) (Req 11).
Policy = Literal["A", "B", "C"]

#: Ablation configuration over data sources (Req 9.3).
AblationConfig = Literal["fsis_only", "fsis_cdc", "fsis_noaa", "full"]

#: Node kinds in the evidence-to-action graph Data->Model->Alert->Evidence->Decision->Impact.
EvidenceNodeKind = Literal["Data", "Model", "Alert", "Evidence", "Decision", "Impact"]


# --------------------------------------------------------------------------- #
# Feasibility primitives (shared by manifest and feasibility_report)
# --------------------------------------------------------------------------- #

class FeasibilityFactor(TypedDict):
    """One factor in the multi-factor feasibility assessment (Req 3.5, 6.2)."""

    name: str
    value: float
    threshold: float
    passed: bool


# --------------------------------------------------------------------------- #
# manifest.json  -> App shell, all panels (gating)
# --------------------------------------------------------------------------- #

class ModuleStatus(TypedDict):
    """Per-pathogen module status record carried in the manifest."""

    pathogen: str
    status: ModuleClassification
    feasibility_factors: list[FeasibilityFactor]
    temporal_resolution: TemporalResolution


class Manifest(TypedDict):
    """Top-level manifest gating every panel.

    ``pathogens`` maps a pathogen name to its :class:`ModuleStatus` record.
    ``data_freshness`` maps a source identifier to an ISO 8601 date string.
    """

    artifact_version: str          # semver, e.g. "0.1.0"
    generated_at: str              # ISO 8601 timestamp
    pathogens: dict[str, ModuleStatus]
    data_freshness: dict[str, str]


# --------------------------------------------------------------------------- #
# risk_timeseries -> Current Risk Overview, historical forecast replay
# --------------------------------------------------------------------------- #

class RiskTimeseriesPoint(TypedDict):
    """One risk value for a Modeling_Unit at a period, with a 95% interval."""

    pathogen: str
    commodity: str
    region: str
    period: str
    value: float
    ci_low: float
    ci_high: float
    status: StatusTag


# --------------------------------------------------------------------------- #
# risk_map -> Current Risk Overview, multi-pathogen explorer, Vulnerable Population Lens
# --------------------------------------------------------------------------- #

class RiskMapFeature(TypedDict):
    """Per-region risk feature with the labels required by Req 14.1."""

    region: str
    pathogen: str
    period: str
    risk: float
    uncertainty: float
    status: StatusTag
    data_freshness: str


# --------------------------------------------------------------------------- #
# vulnerability -> Vulnerable Population Lens (Layer 2)
# --------------------------------------------------------------------------- #

class VulnerabilityProfile(TypedDict):
    """Per-state community vulnerability + food-access context (Layer 2).

    Values are REAL ACS / USDA Food Access Atlas fields (status OBSERVED). Fields
    that the source data does not provide (e.g. a direct pregnancy count, or an
    under-5 count when absent) are recorded as ``None`` and surfaced in the UI as
    "not available" — NEVER fabricated. This context describes population
    vulnerability and access, which is SEPARATE from actual exposure: regional
    demographics cannot establish who consumed a product or became ill.
    """

    region: str
    total_population: Optional[float]
    elderly_65plus_share: Optional[float]
    under5_share: Optional[float]
    low_income_tract_share: Optional[float]
    low_access_tract_share: Optional[float]
    acs_vintage: Optional[str]
    atlas_vintage: Optional[str]
    status: StatusTag


# --------------------------------------------------------------------------- #
# attention_queue -> Prioritized Attention Queue
# --------------------------------------------------------------------------- #

class AttentionQueueItem(TypedDict):
    """A ranked item in the prioritized attention queue (high -> low)."""

    rank: int
    target_id: str
    target_type: str
    region: str
    pathogen: str
    risk: float
    triggering_condition: str
    status: StatusTag


# --------------------------------------------------------------------------- #
# recommendations -> Recommended Action Panel, Explanation/Evidence Panel
# --------------------------------------------------------------------------- #

class Recommendation(TypedDict):
    """A recommended action with its evidence and human-review gate (Req 16).

    ``uncertainty`` is ``None`` only for REGULATORY-sourced actions where a
    model uncertainty does not apply; MODEL recommendations lacking uncertainty
    or evidence are withheld by the exporter and never reach this artifact.
    """

    action: str
    target_id: str
    rationale: str
    constraints: list[str]
    human_review_required: bool
    evidence_refs: list[str]
    uncertainty: Optional[float]
    alert_source: AlertSource
    status: StatusTag


# --------------------------------------------------------------------------- #
# regulatory_alerts -> Regulatory Alerts strip (independent track, Req 16.5)
# --------------------------------------------------------------------------- #

class RegulatoryAlert(TypedDict):
    """A verified official recall. ``alert_source`` is always "REGULATORY" and
    ``status`` is always "OBSERVED"; this track never depends on model state."""

    recall_id: str
    product: str
    lot_ids: list[str]
    classification: str
    date: str
    source_url: str
    alert_source: Literal["REGULATORY"]
    status: Literal["OBSERVED"]


# --------------------------------------------------------------------------- #
# scenario_results -> Policy comparison, what-if simulator, Scenario Builder
# --------------------------------------------------------------------------- #

class ScenarioMetric(TypedDict):
    """One policy x scenario x metric cell.

    ``value``/``diff_vs_a``/``ci_low``/``ci_high`` are ``None`` and ``valid``
    is ``False`` when the metric cannot be validly computed for the pair
    (Req 11.5)."""

    policy: Policy
    scenario: str
    metric: str
    value: Optional[float]
    diff_vs_a: Optional[float]
    ci_low: Optional[float]
    ci_high: Optional[float]
    valid: bool
    status: StatusTag


# --------------------------------------------------------------------------- #
# ablation_results -> Explanation/Evidence Panel, policy comparison
# --------------------------------------------------------------------------- #

class AblationResult(TypedDict):
    """A single ablation configuration's metric and signed marginal
    contribution versus the FSIS-only baseline (Req 9.4, sign preserved)."""

    config: AblationConfig
    metric: str
    value: float
    marginal_vs_fsis_only: float


# --------------------------------------------------------------------------- #
# model_metrics -> Explanation/Evidence Panel, Current Risk Overview
# --------------------------------------------------------------------------- #

class ModelMetric(TypedDict):
    """A model performance metric, optionally disaggregated by region/period.

    ``value``/``ci_low``/``ci_high`` are ``None`` when the metric is
    unavailable (Req 8.7). ``region``/``period`` are ``None`` for the
    aggregate (non-disaggregated) metric."""

    pathogen: str
    validation: ValidationKind
    metric: str
    value: Optional[float]
    ci_low: Optional[float]
    ci_high: Optional[float]
    region: Optional[str]
    period: Optional[str]


# --------------------------------------------------------------------------- #
# model_metrics (calibration plot points)
# --------------------------------------------------------------------------- #

class CalibrationPoint(TypedDict):
    """One point on a reliability/calibration curve (Req 8.3)."""

    pathogen: str
    bin_mid: float
    predicted: float
    observed: float


# --------------------------------------------------------------------------- #
# evidence_graph -> Evidence-to-action graph
# --------------------------------------------------------------------------- #

class EvidenceGraphNode(TypedDict):
    """A node in the Data->Model->Alert->Evidence->Decision->Impact graph."""

    id: str
    kind: EvidenceNodeKind
    label: str


class EvidenceGraphEdge(TypedDict):
    """A directed edge between two evidence-graph nodes by id."""

    source: str
    target: str


# --------------------------------------------------------------------------- #
# provenance -> Explanation/Evidence Panel
# --------------------------------------------------------------------------- #

class ProvenanceEntry(TypedDict):
    """A per-source provenance record (Req 4.3).

    ``missingness`` maps a column name to its missingness fraction (0.0-1.0).
    ``total_samples``/``positive_count`` are ``None`` when unavailable."""

    source: str
    url: str
    access_date: str
    license: str
    geographic_coverage: str
    temporal_coverage: str
    checksum: str
    total_samples: Optional[int]
    positive_count: Optional[int]
    missingness: dict[str, float]
    known_biases: list[str]
    notes: str


# --------------------------------------------------------------------------- #
# audit_report -> dataset audit stage (Req 3.1-3.4)
# --------------------------------------------------------------------------- #

class LeakageCheck(TypedDict):
    """One leakage check result recorded per dataset (Req 3.4).

    ``passed`` is the pass/fail outcome; ``triggering_fields`` names the fields
    or date relationships that triggered a failure (empty when passed)."""

    name: str
    passed: bool
    triggering_fields: list[str]
    detail: str


class ProgramPositivity(TypedDict):
    """Positivity broken out by a single sampling program/project code so that
    programs with differing definitions are never silently pooled (Req 3.1).

    ``positivity_rate`` is ``None`` when the per-code denominator is zero (never
    fabricated)."""

    project_code: str
    project_name: str
    observations: int
    positives: int
    negatives: int
    other: int
    denominator: int
    positivity_rate: Optional[float]


class DuplicateFindings(TypedDict):
    """Duplicate-detection counts; records are reported, never silently dropped
    (Req audit integrity)."""

    exact_duplicate_rows: int
    duplicate_sample_numbers: int
    likely_duplicate_records: int
    likely_duplicate_key: str


class SchemaChange(TypedDict):
    """A fiscal-year-to-fiscal-year schema diff for one program (Req 3.* /
    FSIS schema drift). Columns added/removed and dtype changes between a prior
    FY and this FY."""

    from_fy: Optional[int]
    to_fy: int
    added_columns: list[str]
    removed_columns: list[str]
    dtype_changes: list[str]


class AuditReport(TypedDict):
    """Per-dataset audit (Req 3.1-3.4).

    A dataset here is one FSIS program (pathogen). ``complete`` is ``False``
    when any required audit field could not be computed; the dataset is marked
    incomplete and never omitted (Req 3.2). Uncomputable fields are recorded in
    ``gaps`` (Req 3.2/4.6) rather than fabricated.
    """

    dataset: str                              # program id, e.g. raw_poultry_salmonella
    pathogen: str                             # Salmonella | Listeria | STEC
    commodity: str                            # raw_poultry | rte | raw_beef
    result_column: str                        # the pathogen result column audited
    positive_labels: list[str]                # detected positive vocabulary
    negative_labels: list[str]                # detected negative vocabulary
    other_labels: list[str]                   # not-tested/indeterminate vocabulary
    observation_count: int
    positive_count: int
    negative_count: int
    other_count: int                          # tri-state: not forced into pos/neg
    program_denominator: int                  # observations attributable to a program
    positivity_rate: Optional[float]          # positives / program_denominator
    positivity_by_program: list[ProgramPositivity]
    pathogen_by_fiscal_year: dict[str, dict[str, Optional[float]]]
    yearly_distribution: dict[str, int]
    quarterly_distribution: dict[str, int]
    commodity_distribution: dict[str, int]
    establishment_id_present: bool
    establishment_count: int
    collection_date_range: list[Optional[str]]   # [min, max] ISO; None when unparsable
    collection_date_parse_failures: int
    publication_date: Optional[str]           # None when absent from the data
    reporting_delay_days: Optional[int]       # None when publication date unavailable
    state_coverage_count: int
    state_coverage_missing_fraction: float
    leakage_checks: list[LeakageCheck]
    duplicates: DuplicateFindings
    schema_changes: list[SchemaChange]
    gaps: list[dict]                          # structured gap entries (Req 3.2/4.6)
    complete: bool


# --------------------------------------------------------------------------- #
# equity_test -> Recommended Action Panel / Explanation/Evidence Panel
# --------------------------------------------------------------------------- #

class EquityTest(TypedDict):
    """Result of the equity disparity test (Req 16.9)."""

    passed: bool
    disparity: float
    threshold: float
    description: str


# --------------------------------------------------------------------------- #
# feasibility_report -> Multi-pathogen explorer, model-status displays
# --------------------------------------------------------------------------- #

class FeasibilityReport(TypedDict):
    """Per-pathogen multi-factor feasibility assessment with rationale."""

    pathogen: str
    temporal_resolution: TemporalResolution
    factors: list[FeasibilityFactor]
    classification: ModuleClassification
    rationale: str


# --------------------------------------------------------------------------- #
# multipathogen_program_product -> Pathogen Explorer (S01)
# --------------------------------------------------------------------------- #

class ProgramProductStratum(TypedDict):
    """One OBSERVED positivity stratum for the S01 product/program analysis.

    One record per (pathogen, dimension, category). ``dimension`` is one of
    "program" | "sample_source" | "product" | "overall". ``value`` is observed
    positivity (positive_n / sample_n) with a Wilson 95% interval. These are
    historical surveillance figures, never a model forecast or contamination
    claim, so ``status`` is always OBSERVED. When a dimension is unavailable for
    a pathogen (e.g. STEC has no product category) a single record carries
    ``availability_status="unavailable"`` with a reason and null counts.
    """

    artifact_version: str
    module_id: str
    method_version: str
    pathogen: str
    commodity: str
    dimension: str
    source_column: Optional[str]
    category: str
    sample_n: Optional[int]
    positive_n: Optional[int]
    value: Optional[float]
    ci_low: Optional[float]
    ci_high: Optional[float]
    ci_method: str
    units: str
    status: StatusTag
    availability_status: str
    unavailable_reason: Optional[str]
    fiscal_years: list[int]
    generated_at: str


# --------------------------------------------------------------------------- #
# establishment_surveillance -> Supplier Monitor view (S03)
# --------------------------------------------------------------------------- #

class PersistenceEvidence(TypedDict):
    """Descriptive, prior-independent persistence summary for an establishment.

    All fields are counts/labels derived only from the establishment's own
    quarter history (repeated-positive quarters, how many quarters carried
    samples, the most recent supported quarter, and gaps). None when the
    establishment has no supported quarters."""

    repeated_positive_periods: Optional[int]
    periods_supported: Optional[int]
    last_supported_period: Optional[str]
    sampling_gaps: Optional[int]

class EstablishmentSurveillanceRecord(TypedDict):
    """One OBSERVED establishment-level surveillance record for S03.

    One record per (pathogen, establishment). ``value`` is the raw observed
    positivity; ``eb_posterior`` is the beta-binomial Empirical Bayes estimate
    partially pooled toward ``peer_rate`` (the ranking key), with a 95% beta
    credible interval ``ci_low``/``ci_high`` that is wide when ``sample_n`` is
    small. A low-support establishment carries ``support_status="low_support"``
    and is NEVER presented as safe/clean. Identity is FSIS-published only
    (``establishment_id``, optional ``establishment_number``/``establishment_name``,
    state); there is no contact-detail field by construction. Geography is the
    sampling (establishment) location, never a product destination or illness
    location, and no supplier/retailer relationship is implied.

    The source data carries no verified coordinates, so ``latitude``/``longitude``
    are null and ``coordinates_status`` is "unavailable". ``status`` is OBSERVED
    for every descriptive row (establishment forecasting is not supported in the
    current data; ``predictive_status="descriptive_only"``). When a pathogen
    cannot support the analysis a single record carries
    ``availability_status="unavailable"`` with a reason and null numerics.
    """

    artifact_version: str
    module_id: str                 # "S03"
    method_version: str
    pathogen: str
    commodity: str
    geography_level: str           # "establishment (sampling location)"
    region: str                    # establishment state
    establishment_id: str
    establishment_number: Optional[str]
    establishment_name: Optional[str]
    sample_n: Optional[int]
    positive_n: Optional[int]
    value: Optional[float]
    eb_posterior: Optional[float]
    ci_low: Optional[float]
    ci_high: Optional[float]
    ci_method: str                 # "beta_eb_95"
    peer_rate: Optional[float]
    persistence: Optional[PersistenceEvidence]
    support_status: str            # "ok" | "low_support"
    latitude: Optional[float]
    longitude: Optional[float]
    coordinates_status: str        # "unavailable"
    predictive_status: str         # "descriptive_only" | "validated" | "not_shown" | "insufficient_support"
    status: StatusTag
    availability_status: str       # "available" | "unavailable"
    unavailable_reason: Optional[str]
    fiscal_years: list[int]
    generated_at: str

# --------------------------------------------------------------------------- #
# one_health_human_comparison -> One Health Insights view (S05)
# --------------------------------------------------------------------------- #

class LeadLagSummary(TypedDict):
    """EXPLORATORY national lead-lag correlation between the FSIS annual
    positivity series and the NORS annual outbreak-count series. Descriptive
    only — never causal or predictive. ``exploratory`` is always True."""

    lag_years: Optional[int]
    correlation: Optional[float]
    p_value_permutation: Optional[float]
    ci_low: Optional[float]
    ci_high: Optional[float]
    exploratory: bool
    note: str

class HumanOutbreakComparison(TypedDict):
    """One (pathogen, state, year) CORROBORATION cell comparing FSIS food
    surveillance with CDC NORS human foodborne-outbreak reports.

    The FSIS fields are OBSERVED surveillance; the NORS fields are OBSERVED
    human-outbreak counts. The two are shown side by side as One Health
    corroboration ONLY: ``comparison_status`` is always "CORROBORATION" and
    ``no_causal_link_note`` is always present. This record asserts NO same-strain
    link, NO food-to-illness causation, and NO sub-state/county human estimate.
    NORS is modeled as available ``nors_available_from_year`` (= period year + 1,
    the 365-day lag), so it can never be a leading predictor of FSIS.

    ``coverage_status`` distinguishes a genuine reported zero ("ok" with
    ``nors_outbreak_count`` 0) from missing/thin coverage ("coverage_limited"
    with null NORS counts) and from years beyond NORS ("nors_not_available").
    ``status`` is OBSERVED; the core StatusTag union is unchanged.
    """

    artifact_version: str
    module_id: str                 # "S05"
    method_version: str
    dataset_sources: str
    source_accessed_at: str
    pathogen: str
    commodity: str
    geography_level: str           # "state"
    region: str                    # state abbreviation
    period: str                    # year, "YYYY"
    fsis_sample_n: Optional[int]
    fsis_positive_n: Optional[int]
    fsis_positivity: Optional[float]
    fsis_ci_low: Optional[float]
    fsis_ci_high: Optional[float]
    nors_outbreak_count: Optional[int]
    nors_illness_count: Optional[int]
    nors_available_from_year: Optional[int]
    availability_lag_days: int     # 365
    lead_lag: Optional[LeadLagSummary]
    coverage_status: str           # "ok" | "coverage_limited" | "nors_not_available"
    comparison_status: str         # "CORROBORATION"
    no_causal_link_note: str
    units: str
    status: StatusTag              # OBSERVED
    availability_status: str       # "available" | "unavailable"
    unavailable_reason: Optional[str]
    fiscal_years: list[int]
    generated_at: str

# --------------------------------------------------------------------------- #
# community_impact -> Vulnerable Communities view (S06)
# --------------------------------------------------------------------------- #

class LensPriority(TypedDict):
    """One population-lens priority for a state. ``available`` is False for a lens
    the source data does not support (under-5, pregnancy) or a state missing the
    field; its ``vulnerability_component`` and ``priority_score`` are then None
    with a reason — never fabricated. ``weights`` documents the hazard/vulnerability
    weighting used."""

    lens: str
    available: bool
    vulnerability_component: Optional[float]
    priority_score: Optional[float]
    weights: str
    unavailable_reason: Optional[str]

class WeightSensitivity(TypedDict):
    """Top-ranked states under the default weighting vs an alternative, so no
    single weighting is presented as definitive (Req 2.3)."""

    default_top: list[str]
    alt_top: list[str]
    rank_stable: bool
    note: str

class CommunityImpactRecord(TypedDict):
    """One (pathogen, state) vulnerability-aware impact record (S06).

    ``hazard_component``/``hazard_positivity`` are the READ-ONLY food-safety
    signal (reused from S04); they are a pure function of surveillance and are
    identical regardless of which lens or weighting is applied — only each
    lens ``priority_score`` varies. Vulnerability context (ACS 2022 / USDA Atlas
    2019) reprioritizes attention; it never changes the hazard. Geography is
    state level only: there is NO county/tract pathogen or infection estimate.
    ``affected_population_context`` is a contextual/illustrative count (a
    population that could be affected IF exposed), never an observed exposure or
    illness count, and is reported separately from the shares. The under-5 and
    pregnancy lenses are unavailable (not in the current ACS extraction) and are
    never fabricated. ``status`` is OBSERVED (the inputs are real observations).
    """

    artifact_version: str
    module_id: str                 # "S06"
    method_version: str
    pathogen: str
    commodity: str
    geography_level: str           # "state"
    region: str
    hazard_component: Optional[float]
    hazard_positivity: Optional[float]
    total_population: Optional[float]
    affected_population_context: Optional[float]
    elderly_65plus_share: Optional[float]
    low_income_tract_share: Optional[float]
    low_access_tract_share: Optional[float]
    under5_share: Optional[float]
    acs_vintage: Optional[str]
    atlas_vintage: Optional[str]
    lenses: list[LensPriority]
    weight_sensitivity: Optional[WeightSensitivity]
    contextual_count_note: str
    status: StatusTag
    availability_status: str
    unavailable_reason: Optional[str]
    generated_at: str


# --------------------------------------------------------------------------- #
# action_queue -> Surveillance Actions view (decision layer over S01/S03/S04/S06)
# --------------------------------------------------------------------------- #

class ActionQueueItem(TypedDict):
    """One suggested, human-review-gated operational action derived from an
    OBSERVED surveillance signal (S01/S03/S04/S06). Decision support only:
    retailer-appropriate (prioritize testing, request supplier verification,
    protect access, scrutinize sourcing, gather information), never a recall,
    contamination, or regulatory directive. ``human_review`` is always True and
    ``status`` is always OBSERVED. ``corroboration_note`` carries optional,
    explicitly NON-CAUSAL CDC NORS context (S05) and is None when absent; S05
    never generates an action. No field encodes contamination or human illness.
    """

    artifact_version: str
    module_id: str                 # "ACTIONQ"
    method_version: str
    rank: int
    pathogen: str
    commodity: str
    action: str
    action_category: str           # prioritize_testing | request_supplier_verification | protect_access | scrutinize_sourcing | gather_information
    target_type: str               # state | establishment | product_category
    target: str
    source_module: str             # S01 | S03 | S04 | S06
    triggering_signal: str
    evidence_summary: str
    corroboration_note: Optional[str]
    human_review: bool             # always True
    status: StatusTag              # OBSERVED
    availability_status: str
    generated_at: str


# --------------------------------------------------------------------------- #
# facility_map -> Facility Map view (deterministic join + offline geocode over
# S03 establishment surveillance + the action_queue)
# --------------------------------------------------------------------------- #

class FacilityMapCoverage(TypedDict):
    """Per-pathogen geocode-coverage summary carried in each row so the web
    component does not recompute it (Req 4.1-4.3). ``coverage_pct`` is None with
    ``coverage_state="not_applicable"`` when ``total_selected`` is 0 (Req 4.2);
    otherwise ``coverage_state="computed"`` and ``coverage_pct`` is in [0.0, 100.0].

    ``coverage_pct`` is the VERIFIED headline: it counts ONLY MPI-verified placements
    (``placement_status == "placed"``) over ``total_selected`` and is NEVER inflated by
    the supplemental historical-candidate overlay (Req 4). The invariant
    ``placed + unplaced == total_selected`` still holds because ``unplaced`` is defined
    as ``total_selected - placed`` and therefore INCLUDES every row that is not a
    verified placement. ``historical_candidate`` and ``unresolved`` are informational
    sub-counts OF that ``unplaced`` total: ``historical_candidate`` counts rows whose
    ``placement_status == "historical_candidate"`` (a supplemental overlay candidate),
    and ``unresolved`` counts the remaining unplaced rows (neither verified-placed nor a
    historical candidate). Thus ``historical_candidate + unresolved == unplaced`` and
    they surface how many of the unplaced establishments are historical candidates vs
    truly unresolved without touching the verified headline percentage.
    """

    pathogen: str
    total_selected: int
    placed: int
    unplaced: int
    historical_candidate: int
    unresolved: int
    coverage_pct: Optional[float]
    coverage_state: str            # "computed" | "not_applicable"


class FacilityMapItem(TypedDict):
    """One OBSERVED signal-bearing FSIS-sampled establishment plotted (or listed as
    unplaced) on the Facility Map. Decision-support reference layer only: identity is
    FSIS-published (number, optional published name, state) with NO contact detail;
    the location is the establishment's SAMPLING location, never a product destination
    or illness location, and no supplier/retailer relationship is implied. The value is
    a Surveillance_Signal (eb_posterior), never a contamination or illness claim.
    ``human_review`` is always True and ``status`` is always OBSERVED (never
    PREDICTED/SIMULATED). A placed row carries a real lat/lon/address from the committed
    Geocode_Cache; an unplaced row carries lat/lon/address=None and a non-empty
    ``unplaced_reason``. ``coverage`` repeats the per-pathogen coverage block so the UI
    reads it without recomputing. The optional ``establishment_number``/``county``/
    ``fips_code`` display fields are surfaced from the enriched Geocode_Cache for placed
    rows and are None on unplaced/action-queue-only rows.

    ``location_status`` is the richer placement dimension distinguishing the MPI-verified
    overlay from the supplemental historical-candidate overlay: "mpi_verified" rows are
    matched against the FSIS MPI Directory, "historical_candidate" rows are a supplemental
    overlay matched only by historical name/state/address heuristics, and "unresolved"
    rows could not be placed. ``verified_against_fsis_id`` is True ONLY for MPI-directory
    matches; for historical candidates it is False because the establishment identity is
    NOT confirmed against an FSIS establishment id. The ``historical_*`` fields and
    ``historical_inspection_number`` carry the supplemental historical overlay's own
    attributes and are NEVER asserted as linked to the numeric establishment id. These
    overlay fields are all Optional so MPI-verified rows and unresolved rows still
    validate.
    """

    artifact_version: str
    module_id: str                 # "FACILITYMAP"
    method_version: str            # "fm.v1"
    pathogen: str
    normalized_establishment_number: str
    establishment_id: str
    establishment_number: Optional[str]
    establishment_name: Optional[str]
    state: str
    county: Optional[str]
    fips_code: Optional[str]
    eb_posterior: Optional[float]
    ci_low: Optional[float]
    ci_high: Optional[float]
    sample_n: int
    positive_n: int
    support_status: str            # "ok" | "low_support"
    source_selection: str          # "s03" | "action_queue" | "both"
    placement_status: str          # "placed" | "unplaced"
    location_status: str           # "mpi_verified" | "historical_candidate" | "unresolved"
    match_method: Optional[str]    # e.g. "fsis_mpi_establishment_id" | "historical_name_state_address"
    match_confidence: Optional[str]  # e.g. "verified" | "probable" | None
    verified_against_fsis_id: bool  # True only for MPI-directory matches; False for historical candidates
    historical_inspection_number: Optional[str]  # e.g. "M44857 / P44857"; NEVER asserted as linked to the numeric id
    historical_address: Optional[str]
    coordinate_source: Optional[str]  # e.g. "FSIS MPI Directory (published)" | "external geocode" | None
    evidence_urls: list[str]       # may be empty
    lat: Optional[float]
    lon: Optional[float]
    address: Optional[str]
    unplaced_reason: Optional[str]
    evidence_summary: str
    coverage: FacilityMapCoverage
    human_review: bool             # always True
    status: StatusTag              # OBSERVED
    generated_at: str


#: All status-bearing literal values, re-exported for lightweight validation.
STATUS_TAGS: frozenset[str] = frozenset(("OBSERVED", "PREDICTED", "SIMULATED"))

# --------------------------------------------------------------------------- #
# emerging_risk -> Emerging Signals view (S04)
# --------------------------------------------------------------------------- #

class ProspectiveEval(TypedDict):
    """Separately-labeled prospective-forecast evaluation (Req 4.4).

    Present (non-null) whenever S04 attempted a forecast for the pathogen,
    regardless of outcome, so the honest "we tried, here is how it did" result
    is recorded. ``beat_persistence`` is True only when the forecast cleared the
    absolute precision/recall skill floor AND beat the naive persistence
    baseline; only then may a row carry a PREDICTED prospective alert. A forecast
    that did not clear the bar is reported here but produces no alert.
    """

    precision: Optional[float]
    recall: Optional[float]
    alert_volume: Optional[int]
    lead_time_periods: Optional[float]
    availability_lag_note: str
    beat_persistence: bool

class EmergingRiskStratum(TypedDict):
    """One OBSERVED state x period surveillance-signal record for S04.

    One record per (pathogen, region, period). ``value`` is observed positivity
    for that state-quarter with a Wilson 95% interval. ``trailing_baseline`` and
    ``baseline_high`` are the LEAKAGE-SAFE prior-only expectation and 3-sigma
    control limit; ``retro_anomaly`` is True when observed exceeded the control
    limit. ``retro_anomaly`` is ``None`` (unflagged) for a low-support cell or
    one without enough prior history — never False-by-default. ``persistent_score``
    is the state-level chronic-elevation fraction (``None`` when the state has
    fewer than the minimum supported quarters), repeated on each of the state's
    rows. Geography is SAMPLING LOCATION only.

    ``status`` is OBSERVED for every retrospective row. A row carries PREDICTED
    only when ``prospective_alert`` is True, which happens only for a validated
    forecast (``prospective_status == "validated"``). A retrospective anomaly is
    never labeled a forecast.

    When a pathogen's series cannot support the detector at all, a single record
    carries ``availability_status="unavailable"`` with a reason and null numerics.
    """

    artifact_version: str
    module_id: str                 # "S04"
    method_version: str
    pathogen: str
    commodity: str
    geography_level: str           # "state (sampling location)"
    region: str                    # state code
    period: str                    # "YYYY-Qn"
    period_start: str              # ISO date (temporal ordering key)
    sample_n: Optional[int]
    positive_n: Optional[int]
    value: Optional[float]
    ci_low: Optional[float]
    ci_high: Optional[float]
    ci_method: str
    trailing_baseline: Optional[float]
    baseline_high: Optional[float]
    persistent_score: Optional[float]
    retro_anomaly: Optional[bool]
    retro_threshold: Optional[float]
    support_status: str            # "ok" | "low_support"
    prospective_alert: Optional[bool]
    prospective_status: str        # validated | not_shown_did_not_beat_persistence | insufficient_support | not_attempted
    prospective_eval: Optional[ProspectiveEval]
    status: StatusTag
    availability_status: str       # "available" | "unavailable"
    unavailable_reason: Optional[str]
    fiscal_years: list[int]
    generated_at: str


#: All alert-source literal values.
ALERT_SOURCES: frozenset[str] = frozenset(("MODEL", "REGULATORY"))
