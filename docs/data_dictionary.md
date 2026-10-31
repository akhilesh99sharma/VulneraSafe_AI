# VulneraSafe AI — Data Dictionary

Every column in the harmonized per-pathogen analytic tables (`data/processed/harmonized_<pathogen>.parquet`). Each row lists the column name, type, units, source, and the explicit lag it carries relative to the modeling period (Req 1.1, 2.7).

> LIMITATION: FSIS laboratory-sampling records carry a collection_date but no publication/release date (audit gap). availability_date is therefore derived as collection_date + REPORTING_LAG_DAYS (assumed 30 days), NOT an observed availability date. Consequently this platform must not claim true historical real-time forecasting: the lag is a stated assumption and a documented limitation. Backtests reflect assumed-availability timing, not verified real-time data releases.

> CLIMATE: Weather columns come from NOAA nClimDiv statewide monthly climate (REAL national state-level coverage, 49 states). Hawaii has no nClimDiv statewide series and is left MISSING (documented gap, never fabricated). `weather_availability_date` = end-of-period + 7 days, matching nClimDiv's first-week-of-following-month publication; this is an observed publication lag, not an assumption.

> CDC NORS: The `cdc_*` columns carry CDC National Outbreak Reporting System (NORS) state×period foodborne-outbreak counts. NORS is LAGGED CORROBORATION / historical One Health human-health evidence, NOT a model predictor on its own merits. NORS records outbreak dates (not report dates) and finalised data commonly lags the outbreak by a year or more; `cdc_availability_date` therefore applies a large +365-day availability lag so any cutoff-t view uses only outbreaks plausibly available by t. Where a (state, period) cell has no NORS coverage, the `cdc_*` values are blank (missing), never zero-filled.

| Column | Type | Units | Source | Lag |
|---|---|---|---|---|
| `pathogen` | string | — | FSIS program metadata | none (key) |
| `commodity` | string | — | FSIS program metadata | none (key) |
| `state` | string | USPS 2-letter code | FSIS establishment_state | none (key) |
| `period` | string | YYYY-MM or YYYY-Qn | derived from collection_date | none (key) |
| `sampling_program` | string | FSIS project_code | FSIS project_code | none (key) |
| `program_category` | string | routine_surveillance|for_cause|exploratory|follow_up|special | tag_program(project_code, project_name) | none |
| `is_target` | bool | — | derived: program_category == routine_surveillance | none |
| `collection_date` | datetime | date (latest sample in the cell) | FSIS collection_date | observed collection date |
| `availability_date` | datetime | date | collection_date + REPORTING_LAG_DAYS | ASSUMED +30d (not observed) |
| `lag_days` | int | days | constant REPORTING_LAG_DAYS | assumed reporting lag (30) |
| `samples` | int | count of tested samples (pos+neg) | FSIS tri-state classification | availability lag |
| `positives` | int | count of positive detections | FSIS tri-state classification | availability lag |
| `positivity_rate` | float | fraction 0..1 (positives/samples) | derived | availability lag |
| `tmax_mean` | float | °C (mean monthly max over period) | NOAA nClimDiv statewide monthly | +7d observed (end-of-month + 7d) |
| `tmin_mean` | float | °C (mean monthly min over period) | NOAA nClimDiv statewide monthly | +7d observed (end-of-month + 7d) |
| `prcp_total` | float | mm (total precip over period) | NOAA nClimDiv statewide monthly | +7d observed (end-of-month + 7d) |
| `tmax_anomaly` | float | °C vs state long-run mean (within-sample) | derived from NOAA nClimDiv | +7d observed |
| `tmin_anomaly` | float | °C vs state long-run mean (within-sample) | derived from NOAA nClimDiv | +7d observed |
| `prcp_anomaly` | float | mm vs state long-run mean (within-sample) | derived from NOAA nClimDiv | +7d observed |
| `noaa_lag_days` | int | days (constant 7) | constant NOAA availability lag | observed nClimDiv publication lag (7) |
| `weather_availability_date` | datetime | date (end-of-period + 7d; blank where state/period has no nClimDiv series) | derived from NOAA nClimDiv | observed weather availability date |
| `cdc_outbreaks` | float | count of CDC NORS foodborne outbreaks for (state, period); blank where no NORS coverage | CDC NORS (data.cdc.gov `5xkq-dg7x`) | +365d assumed availability lag (corroboration, not a predictor) |
| `cdc_illnesses` | float | count of CDC NORS reported illnesses for (state, period); blank where no NORS coverage | CDC NORS (data.cdc.gov `5xkq-dg7x`) | +365d assumed availability lag (corroboration, not a predictor) |
| `cdc_salmonella_outbreaks` | float | count of NORS outbreaks etiology Salmonella; blank where no NORS coverage | CDC NORS (data.cdc.gov `5xkq-dg7x`) | +365d assumed availability lag (corroboration, not a predictor) |
| `cdc_listeria_outbreaks` | float | count of NORS outbreaks etiology Listeria; blank where no NORS coverage | CDC NORS (data.cdc.gov `5xkq-dg7x`) | +365d assumed availability lag (corroboration, not a predictor) |
| `cdc_stec_outbreaks` | float | count of NORS outbreaks etiology STEC/E. coli; blank where no NORS coverage | CDC NORS (data.cdc.gov `5xkq-dg7x`) | +365d assumed availability lag (corroboration, not a predictor) |
| `cdc_pathogen_outbreaks` | float | count of NORS outbreaks matching this table's pathogen; blank where no NORS coverage | CDC NORS (data.cdc.gov `5xkq-dg7x`) | +365d assumed availability lag (corroboration, not a predictor) |
| `cdc_availability_date` | datetime | date (end-of-outbreak-period + 365d); blank where no NORS coverage | derived from CDC NORS | +365d assumed availability date |
| `total_population` | float | persons | Census ACS5 2022 B01001_001E | static (2022 vintage, pre-cutoff) |
| `elderly_65plus_partial` | float | persons (sum of six ingested 65+ bands) | Census ACS5 2022 B01001 | static (2022 vintage, pre-cutoff) |
| `elderly_share` | float | fraction 0..1 | derived from ACS | static (2022 vintage, pre-cutoff) |
| `acs_vintage` | string | — | Census ACS | static |
| `lila_tract_share` | float | fraction of tracts flagged low-income & low-access | USDA Food Access Research Atlas 2019 | static (2019 vintage, pre-cutoff) |
| `low_income_tract_share` | float | fraction of low-income tracts | USDA Food Access Research Atlas 2019 | static (2019 vintage, pre-cutoff) |
| `atlas_pop_2010` | float | persons (tract Pop2010 summed) | USDA Food Access Research Atlas 2019 | static |
| `atlas_vintage` | string | — | USDA ERS Food Access Atlas | static |

## Leakage-safe feature tables (`data/processed/features_<pathogen>.parquet`)

The modeling feature tables derive from the harmonized tables above. Every column, its role, and its leakage class are enumerated in `docs/model_feature_dictionary.csv` (the authoritative, machine-readable feature dictionary); refer to that file for the full per-column catalogue rather than duplicating it here. All predictor columns are constructed strictly from data timestamped at or before the horizon cutoff.

The following CDC NORS lag features appear in the exported feature tables and are **not** yet listed in `model_feature_dictionary.csv`; they are documented here for completeness:

| Column | Type | Units / allowed values | Source | Leakage class |
|---|---|---|---|---|
| `cdc_outbreaks_lag1` | float | count of NORS foodborne outbreaks, one period before the target (blank where no NORS coverage) | CDC NORS (+365d availability lag) | safe (lagged corroboration, sparse) |
| `cdc_illnesses_lag1` | float | count of NORS reported illnesses, one period before the target (blank where no NORS coverage) | CDC NORS (+365d availability lag) | safe (lagged corroboration, sparse) |
| `cdc_pathogen_outbreaks_lag1` | float | count of NORS outbreaks matching this pathogen, one period before the target (blank where no NORS coverage) | CDC NORS (+365d availability lag) | safe (lagged corroboration, sparse) |

CDC NORS features remain lagged corroboration, not a primary signal; their large availability lag and sparsity are documented above and in `docs/provenance.md`.

