# Design Document

S03 — Persistent Establishment Surveillance Monitor.

## Overview

S03 adds an establishment-level persistent-surveillance detector on top of the existing VulneraSafe analysis layer. For each pathogen it builds a per-establishment history of eligible samples and positives, estimates each establishment's positivity with an uncertainty-aware beta-binomial Empirical Bayes posterior that partially pools toward the pathogen's peer rate, attaches a 95% credible interval, and summarizes persistence (repeated-positive periods, recent support, sampling gaps). The central rule is that low testing is never treated as safety: a thinly-sampled establishment is shrunk toward the peer rate and carries a wide interval, rather than appearing either spuriously clean or spuriously worst.

S03 reuses the S01 raw-FSIS readers (_iter_raw_records, _classify_result, _primary_records, wilson_ci) and the period machinery introduced for S04. It adds one analysis module, one TypedDict plus TS interface, one exporter builder, one manifest entry, and one Supplier Monitor dashboard view. It changes no existing analysis, artifact, or test.

### Non-goals / honesty boundaries

- Geography is sampling (establishment) location only, never product destination or human-illness location.
- No establishment is described or implied to be a supplier to any retailer or to the decision-maker; no synthetic supplier/destination relationship is created.
- The artifact carries only FSIS-published identity (establishment_id, establishment_number, establishment_name, establishment_state). No contact details (address, phone).
- The source data carries no verified latitude/longitude, so the facility map reports coordinates unavailable rather than fabricating points. This is the expected outcome, not a failure.
- Positivity is surveillance signal, never a contamination claim. A low-support establishment is uncertain, never "safe".
- Ranking is by the EB posterior with its interval; there is no ad-hoc rank score.

## Architecture

Data flow (offline scan to cache to artifact to UI):

1. S03 reuses the existing src/models/establishment.py: load_establishment_samples(pathogen) for the leakage-safe per-sample table (routine-surveillance cohort) and build_establishment_quarters(frame) for the establishment x quarter panel. It does NOT re-read raw ZIPs or rebuild the panel, and does not edit or weaken that module or its tests.
2. establishment_surveillance.py aggregates the panel to per-establishment totals (eligible_n, positive_n) keyed by establishment_id, carrying FSIS identity (id, name, state) and the quarter rows for persistence evidence.
3. Per pathogen, a beta prior (alpha0, beta0) is estimated from the pathogen's establishment positivity distribution (method of moments on establishments clearing a minimum support), fixed at development time and recorded.
4. Each establishment gets an EB posterior mean and a 95% beta credible interval via partial pooling (observed positives/eligible plus the prior), plus persistence evidence (repeated-positive periods, recent-support recency, sampling-gap count).
5. Results cache to data/interim/s03_establishment_surveillance.json.
6. exporter.build_establishment_surveillance() reads the cache, shapes and validates web/public/data/establishment_surveillance.json.
7. The Supplier Monitor view renders the ranked establishment list plus an honest coordinates-unavailable map panel.

The heavy raw scan runs offline (compute_establishment_surveillance) and caches, exactly as S01 and S04 do.

## Components and Interfaces

### 1. src/analysis/establishment_surveillance.py

Reuses the existing src/models/establishment.py public API: load_establishment_samples, build_establishment_quarters, and its EB pattern / quarter_label helpers. It does not re-read raw ZIPs. S03 applies its OWN locked parameters (per-pathogen method-of-moments beta prior; MIN_SUPPORT_ESTABLISHMENT=20) rather than that module's fixed strong_prior=100 / HISTORY_MIN_SAMPLES=10, and emits the FULL ranked establishment list (not the module's top-20 descriptive summary). The existing module and its tests are left unchanged. Cohort note: load_establishment_samples returns routine-surveillance samples only, so per-establishment counts and the fitted prior are computed on that cohort and reported as such.

New constants:
- MODULE_ID = "S03", METHOD_VERSION = "s03.v1".
- MIN_SUPPORT_ESTABLISHMENT — minimum eligible samples before an establishment is ranked rather than shown low-support (fixed from the Task-1 inventory; placeholder 20).
- PRIOR_FIT_MIN_SUPPORT — minimum eligible samples for an establishment to contribute to the beta-prior fit (so the prior is estimated from establishments with real signal; placeholder 30).
- RESOLUTION = "quarterly" (reused from S04's audit finding).

Key functions:
- _record_establishment(rec) -> Optional[dict] — read establishment_id, establishment_number, establishment_name, establishment_state; drop records with no establishment_id (counted as establishment_missing).
- _build_history(records, analysis_col) -> {est_id: {"identity": {...}, "periods": {period: {n, pos}}, "n": int, "pos": int}} — establishment x quarter counts; each eligible sample counted exactly once.
- fit_beta_prior(establishments) -> (alpha0, beta0) — method-of-moments beta prior from the positivity rates of establishments with eligible_n >= PRIOR_FIT_MIN_SUPPORT; recorded in metadata.
- eb_posterior(pos, n, alpha0, beta0) -> (mean, ci_low, ci_high) — posterior Beta(alpha0+pos, beta0+n-pos); mean and 95% equal-tailed credible interval.
- persistence_evidence(periods) -> {repeated_positive_periods, periods_supported, last_supported_period, sampling_gaps} — all descriptive, prior-independent.
- compute_establishment_surveillance(round_to=6) -> dict — orchestrates all pathogens, writes cache; marks a pathogen/establishment unavailable with a reason when unsupported.
- load_cache() — mirrors S01/S04.

### 2. Inventory / prior-fit audit (Task 1, run once)

A __main__-guarded report that prints, per pathogen: distinct establishments, the eligible-sample support distribution (median, quartiles, share clearing 10/20/30), the fitted beta prior (alpha0, beta0) and implied peer rate, and how many establishments clear MIN_SUPPORT_ESTABLISHMENT. Confirms the counts against the spec's earlier audit (Salmonella ~1,409; Listeria ~3,765; STEC ~2,524), fixes MIN_SUPPORT_ESTABLISHMENT and PRIOR_FIT_MIN_SUPPORT, and confirms there is no latitude/longitude column. Satisfies the spec's "compact inspect report before writing a model" and Req 3.1.

### 3. Frontend — Supplier Monitor view

New component web/src/components/panels/SupplierMonitor.tsx, added as a tab in App.tsx (Tab union extended with "supplier"). Uses useArtifact<EstablishmentSurveillanceRecord[]>("establishment_surveillance"), StatusTag, EmptyState, PanelShell/ArtifactBody.

Controls and panels:
- pathogen selector (3 pathogens, all first-class) and a region (state) filter;
- ranked establishment list sorted by EB posterior, each row showing the EB posterior with its credible interval, the raw positives/eligible and support, and a compact persistence summary (repeated-positive periods, recency);
- a "How to read this" box explaining that the shown rate is a shrinkage estimate and that low support means uncertain, not safe;
- low-support establishments shown de-emphasized in a separate "insufficient testing" group, never ranked as clean;
- a facility-map panel that renders points only for establishments with verified coordinates, and otherwise shows an explicit "establishment coordinates are not available in the source data" state;
- navy/teal theme; orange/red only on active elevated-establishment indicators; a Page-06-deferred note.

### 4. Exporter — build_establishment_surveillance()

In src/artifacts/exporter.py, mirroring build_emerging_risk(): reads the cache via from src.analysis.establishment_surveillance import load_cache, flattens to a list[EstablishmentSurveillanceRecord], validates with validate_payload(..., EstablishmentSurveillanceRecord, label="establishment_surveillance"), returns the keyed payload from build_all_artifacts() (auto-written and manifest-registered). The flattener emits only the four identity fields and never any contact field.

## Data Models

### EstablishmentSurveillanceRecord (Python) plus TS mirror

Added to src/artifacts/schemas.py next to EmergingRiskStratum (before the STATUS_TAGS anchor), mirrored in web/src/types/artifacts.ts. One record per (pathogen, establishment).

Helper TypedDict PersistenceEvidence fields:
- repeated_positive_periods: Optional[int]
- periods_supported: Optional[int]
- last_supported_period: Optional[str]
- sampling_gaps: Optional[int]

Main TypedDict EstablishmentSurveillanceRecord fields:
- artifact_version: str
- module_id: str  ("S03")
- method_version: str
- pathogen: str
- commodity: str
- geography_level: str  ("establishment (sampling location)")
- region: str  (establishment_state)
- establishment_id: str
- establishment_number: Optional[str]
- establishment_name: Optional[str]
- sample_n: Optional[int]  (eligible samples)
- positive_n: Optional[int]
- value: Optional[float]  (raw observed positivity)
- eb_posterior: Optional[float]  (shrunk estimate; ranking key)
- ci_low: Optional[float]  (95% credible interval)
- ci_high: Optional[float]
- ci_method: str  ("beta_eb_95")
- peer_rate: Optional[float]  (pathogen pooled rate the prior centers on)
- persistence: Optional[PersistenceEvidence]
- support_status: str  ("ok" | "low_support")
- latitude: Optional[float]  (null; no verified coordinates in source)
- longitude: Optional[float]  (null; no verified coordinates in source)
- coordinates_status: str  ("unavailable")
- predictive_status: str  ("descriptive_only" | "validated" | "not_shown" | "insufficient_support")
- status: StatusTag  (OBSERVED for descriptive rows; PREDICTED only on a validated forecast)
- availability_status: str  ("available" | "unavailable")
- unavailable_reason: Optional[str]
- fiscal_years: list[int]
- generated_at: str

Status-tag discipline: status is OBSERVED for every descriptive surveillance row. PREDICTED appears only if a validated establishment forecast is produced (not expected in the current data). No contact-detail field exists on the record by construction.

## Algorithm detail

Establishment history. For each (pathogen, establishment_id), accumulate eligible samples (S01 tri-state valid tests) and positives by quarter. Each sample is counted once; the establishment totals equal the sum over its periods (a test enforces this).

Beta prior (partial pooling). Fit a Beta(alpha0, beta0) to the distribution of per-establishment positivity among establishments with eligible_n >= PRIOR_FIT_MIN_SUPPORT, by method of moments (match the mean and variance of those rates). The prior's mean is the pathogen peer rate. Fixed at development time, recorded in metadata. For very rare pathogens (STEC) the prior is strong (large beta0), which is exactly the desired heavy shrinkage. The prior is fit on the routine-surveillance cohort returned by load_establishment_samples (not the all-program raw counts used in the Task-1 scoping audit), and the actual fitted alpha0/beta0/peer_rate are recorded in metadata and the completion report.


EB posterior and interval. For an establishment with pos positives in n eligible samples, the posterior is Beta(alpha0 + pos, beta0 + n - pos). The reported estimate is the posterior mean; the 95% credible interval is the equal-tailed beta interval. Low n keeps the posterior near the peer rate with a wide interval; high n lets the data dominate with a narrow interval. Ranking uses the posterior mean, so no low-support establishment can reach the top on a spurious 100 percent.

Persistence evidence. Descriptive and prior-independent: count the quarters with at least one positive (repeated_positive_periods), the number of supported quarters, the most recent supported quarter, and the number of gaps (supported quarters missing between first and last support). These let the UI distinguish a currently-active elevated establishment from one whose positives are old.

Optional forecast. The spec permits an establishment forecast only where rare-event coverage is adequate and it beats equal-effort and EB-persistence baselines, evaluated on familiar vs unseen establishments separately. Given establishment-level sparsity (especially Listeria/STEC), the expected and honest outcome is descriptive_only. If attempted and it does not clear the bar, predictive_status is not_shown and no PREDICTED row is emitted.

## Correctness Properties

The S03 tests (tests/test_establishment_surveillance.py, Python; and web/src/components/panels/__tests__/SupplierMonitor.test.tsx, web) assert the following.

### Property 1: No double-counted samples
**Validates: Requirements 8.1, 2.1**
For a synthetic record set, each establishment's total eligible_n and positive_n equal the sums over its per-quarter cells, and equal the count of its input eligible records.

### Property 2: Posterior smoothing
**Validates: Requirements 8.2, 1.2**
A low-support establishment's EB posterior lies strictly between its raw rate and the peer rate, and its credible interval is wider than that of a high-support establishment with the same raw rate.

### Property 3: Low support is not safety
**Validates: Requirements 1.4, 8.2**
An establishment with few eligible samples and zero positives is marked support_status low_support and is not ranked or labeled as clean/safe.

### Property 4: Anonymization
**Validates: Requirements 5.1, 8.3**
No artifact record contains any contact-detail field (address, phone, email); only establishment_id, number, name, state identity fields are present.

### Property 5: No synthetic supplier relationship
**Validates: Requirements 5.2, 5.3, 8.5**
No record or field asserts an establishment-to-retailer or establishment-to-destination relationship.

### Property 6: Known vs unseen separation
**Validates: Requirements 4.3, 8.4**
Any evaluation output reports familiar (pre-cutoff) and unseen (post-cutoff) establishments as separate groups, never pooled.

### Property 7: Leakage-safety and denominator conservation
**Validates: Requirements 3.2, 3.3, 8.6**
No current estimate uses a future-period observation; positive_n is at most sample_n; value, eb_posterior, ci_low, ci_high, peer_rate lie in [0,1] when not null.

## Error Handling

- An establishment/pathogen with no eligible samples produces no row (never fabricated).
- A pathogen whose establishment series cannot support the analysis produces a single availability_status unavailable record with a reason and null numerics.
- Records missing establishment_id are excluded and counted (establishment_missing) in method metadata, surfaced in the completion report, never silently zeroed.
- No verified coordinates exist in the source, so every record carries coordinates_status unavailable and null latitude/longitude; the map renders an honest unavailable state.

## Testing Strategy

- Python: tests/test_establishment_surveillance.py with the seven properties above on small hand-built synthetic record sets (no raw-data dependency), fast and deterministic.
- Web: SupplierMonitor.test.tsx asserts the ranked list renders EB posterior with interval, low-support establishments are separated and not ranked as clean, the coordinates-unavailable map state renders, and the artifact-missing empty state renders.
- Full suite (pytest plus vitest plus build) run in external CMD after implementation; counts recorded in the completion report.
