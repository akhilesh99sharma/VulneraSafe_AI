# VulneraSafe AI - Complete Data Inventory

Generated from direct inspection of the ingested raw files and processed feature tables.
All figures are measured from the actual files on disk. Nothing here is fabricated or inferred.

Companion machine-readable files in this folder:
- `dataset_summary.csv` - one row per source dataset
- `raw_column_dictionary.csv` - every raw column, its role, and whether it is a target source
- `model_feature_dictionary.csv` - every modeling column with leakage classification

---

## Part 1 - Scope and Provenance

| Source | Provider | Access method | Status |
|---|---|---|---|
| FSIS Raw Poultry (Salmonella) | USDA FSIS | Manually supplied zipped JSON, FY2014-2026 | Fully ingested |
| FSIS RTE (Listeria) | USDA FSIS | Manually supplied zipped JSON, FY2014-2026 | Fully ingested |
| FSIS Raw Beef (STEC) | USDA FSIS | Manually supplied zipped JSON, FY2014-2026 | Fully ingested |
| Census ACS 5-year 2022 | US Census Bureau | Live API (CENSUS_API_KEY) | Fully ingested |
| USDA Food Access Research Atlas 2019 | USDA ERS | Downloaded xlsx | Fully ingested |
| NOAA weather | NOAA NCEI Access | Live API | PARTIAL - single NY station, needs nClimDiv state monthly |
| CDC NORS | data.cdc.gov | Not truly joined | PLACEHOLDER columns only |
| FSIS Recalls / PHAs | FSIS Recall API | Blocked (HTTP 403) | Not ingested |

Fiscal years present in every FSIS program: FY2014, FY2019, FY2023, FY2026 (the years supplied).

---

## Part 2 - Dataset Dimensions (measured)

| Dataset | Rows | Raw columns | Positives | Positivity |
|---|---|---|---|---|
| FSIS Raw Poultry (Salmonella) | 325,123 | 30 | 37,685 | 11.6% |
| FSIS RTE (Listeria) | 266,031 | 28 | 1,599 | 0.61% |
| FSIS Raw Beef (STEC) | 232,363 | 29 | 664 | 0.29% |
| Census ACS 2022 | 3,222 counties | - | - | - |
| Food Access Atlas 2019 | ~72,531 tracts | - | - | - |
| NOAA weather | 7 (thin slice) | 5 | - | - |

Positivity is computed from the primary binary analysis column of each program
(`salmonella_sp_analysis`, `lm_listeria_analysis`, `stec_analysis`).

---

## Part 3 - FSIS Deep Dive (the core One Health signal)

### 3.1 Common structure
Every FSIS program shares the same backbone:
- Identifiers: `form_id`, `sample_number`
- Establishment + geography: `establishment_id`, `establishment_number`, `establishment_name`, `establishment_state`
- Sampling program: `project_code`, `project_name`
- Time: `collection_date`
- Product/context: `sample_source_name`, `product_type` (poultry), `production_alternative` (RTE)
- QA: `not_analyzed`, `not_analyzed_explain`, and per-assay `*_canceled` fields
- Lab results: one or more `*_analysis` (binary Negative/Positive), plus quantitative MPN / CFU / combination fields

### 3.2 CRITICAL FINDING - no serotype or subtyping anywhere
A column-level search across all three programs and all four fiscal years returned
ZERO matches for serotype, serovar, WGS, PFGE, or any isolate-subtyping field.
FSIS establishment sampling records contain only:
- a binary result (Negative / Positive / Confirmed Negative of a Previous Presumptive)
- quantitative enumeration (MPN per g, CFU per g/ml, MPN combination codes) - mostly NULL
- for beef only: `pcr_stx_1_2_analysis` and `pcr_eae_analysis` (virulence-gene PCR, still binary)

Implication: any PulseNet-style serotype linkage or outbreak-strain matching is NOT
possible from this data. The platform must not claim serotype-level attribution.

### 3.3 Per-program result columns
- Poultry (Salmonella): `salmonella_sp_analysis` (primary), plus Campylobacter assays
  (`campylobacter_analysis_1ml`, `campylobacter_analysis_30ml`), MPN/CFU, and indicator
  organisms (aerobic plate count, Enterobacteriaceae).
- RTE (Listeria): `lm_listeria_analysis` (primary, L. monocytogenes), `non_lm_listeria_analysis`,
  plus a Salmonella screen on the same samples.
- Beef (STEC): `stec_analysis` (primary), `stec_o157_h7_mpn`, PCR virulence genes
  (`pcr_stx_1_2_analysis`, `pcr_eae_analysis`), plus a Salmonella screen.

### 3.4 CRITICAL FINDING - CDC NORS columns are placeholders
The feature tables carry `cdc_outbreaks_lag1`, `cdc_illnesses_lag1`, and
`cdc_pathogen_outbreaks_lag1`. These are PLACEHOLDER columns - NORS was not truly
joined, so they are currently constant and carry no signal. They are documented here
so no reader mistakes them for a working human-illness linkage. Completing the honest
NORS join (with reporting-lag handling) is a named next step.

### 3.5 Quality / leakage notes
- `*_canceled` fields describe lab cancellations and can reflect information not known at
  prediction time; they are excluded from features.
- Same-sample result fields (`*_analysis`, MPN, CFU, PCR) are the outcome source and must
  never enter the predictor matrix for the same observation.
- Next-period fields (`y_next_positivity`, `next_routine_*`, `smoothed_next_positivity`) are
  the forecasting target and are excluded from X.

---

## Part 4 - Processed Model Tables

For each pathogen the pipeline produces `features_{pathogen}.parquet` (51 columns) and
`model_{pathogen}.parquet` (61 columns = features + targets + support/meta).

| Pathogen | Model rows | Feature cols | Model cols |
|---|---|---|---|
| Salmonella | 7,497 | 51 | 61 |
| Listeria | 2,754 | 51 | 61 |
| STEC | 2,754 | 51 | 61 |

Approx. 39 of the 51 feature-table columns are usable predictors (the rest are identity
keys and current-period outcomes that are not fed to the model). Full per-column leakage
classification is in `model_feature_dictionary.csv`.

### 4.1 Targets
- `y_elevated` (v1, DEPRECATED): next positivity above the cell's own trailing mean.
  Measured as near-noise (Salmonella ROC-AUC 0.586) and retired.
- `y_elevated_v2` (ACTIVE): empirical-Bayes / beta-binomial smoothed next positivity at or
  above a fixed, training-derived tail threshold (75th percentile) within comparable FSIS
  sampling programs. Denominator-aware; low-sample cells are not forced to negative.
- Secondary anomaly indicator: emerging increases above local historical baselines.

### 4.2 Measured v2 model performance (untouched chronological test split)
Exported chronological, best-model-per-pathogen values from
`web/public/data/model_metrics.json` (region=null, period=null), cross-checked
against `docs/reports/model_validation.md`.

| Pathogen | Best model | PR-AUC | ROC-AUC | Base rate |
|---|---|---|---|---|
| Salmonella | lightgbm | 0.516 | 0.764 | 27.9% |
| Listeria | random_forest | 0.736 | 0.838 | 26.2% |
| STEC | random_forest | 0.434 | 0.650 | 25.0% (weak - surveillance-only candidate) |

---

## Part 5 - Summary Table

See `dataset_summary.csv` for the machine-readable one-row-per-dataset summary (source,
rows, columns, date range, geography, ingestion status, join keys).

---

## Part 6 - Research Opportunities and Unused Fields

Unused but available fields worth exploiting:
- `product_type` (poultry) and `sample_source_name` (all programs): product-mix context that
  could sharpen establishment- and state-level risk without leakage.
- `production_alternative` (RTE): Listeria control-alternative category, a plausible risk modifier.
- Quantitative enumeration (`salmonellae_mpn_g`, `salmonella_quantitative_cfu_*`, `stec_o157_h7_mpn`):
  mostly NULL, but where present could support a severity/load signal distinct from presence.
- Indicator organisms (aerobic plate count, Enterobacteriaceae): process-hygiene proxies.
- Beef virulence-gene PCR (`pcr_stx_1_2_analysis`, `pcr_eae_analysis`): pathogenicity context for STEC.

Columns that MUST stay out of the predictor matrix (future leakage):
- every `*_canceled` field
- same-sample result/subresult/MPN/CFU/PCR fields for the observation being predicted
- all next-period count and smoothed-target fields

Named data-completion next steps:
1. Replace the thin single-station NOAA feed with NOAA nClimDiv state-level monthly climate.
2. Perform an honest CDC NORS join with explicit reporting-lag handling (replace the placeholders).
3. Revisit the firewalled FSIS Recall feed for an independent regulatory-alert channel.
