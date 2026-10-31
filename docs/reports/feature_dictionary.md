# VulneraSafe AI — Feature Dictionary (Task 3.1, Req 7.4–7.6)

Every feature in the leakage-safe per-pathogen feature matrix (`data/processed/features_<pathogen>.parquet`). Each feature is constructed using ONLY information timestamped at or before the horizon cutoff (the start of the predicted period); every contributing source row satisfies `availability_date <= cutoff` and comes from a period strictly earlier than the target period (Req 7.5). Any source row timestamped after the cutoff is excluded and recorded for audit (Req 7.6).

> LIMITATION: FSIS laboratory-sampling records carry a collection_date but no publication/release date (audit gap). availability_date is therefore derived as collection_date + REPORTING_LAG_DAYS (assumed 30 days), NOT an observed availability date. Consequently this platform must not claim true historical real-time forecasting: the lag is a stated assumption and a documented limitation. Backtests reflect assumed-availability timing, not verified real-time data releases.

Routine-surveillance positivity (the target scope per the program taxonomy) and for-cause / exploratory positivity are kept in SEPARATE columns and are never pooled together.

## Feature columns

| Feature | Definition | Lag | Source | Cutoff-safe |
|---|---|---|---|---|
| `routine_positivity_lag{1,2,3}` | Routine-surveillance positivity rate of the state 1/2/3 periods before t | t-1, t-2, t-3 | FSIS routine samples (is_target) | yes |
| `routine_samples_lag{1,2,3}` | Routine-surveillance tested-sample volume 1/2/3 periods before t | t-1, t-2, t-3 | FSIS routine samples | yes |
| `routine_positivity_trailing4_mean` | Mean routine positivity over the trailing 4 available periods before t | trailing 4 periods | FSIS routine samples | yes |
| `routine_positivity_trailing12m_mean` | Mean routine positivity over the trailing 12 months / 4 quarters before t | trailing 12 months | FSIS routine samples | yes |
| `routine_samples_trailing4_mean / routine_samples_trailing12m_mean` | Trailing-window mean routine sample volume (establishment-activity proxy) | trailing 4 / 12 periods | FSIS routine samples | yes |
| `national_routine_positivity_lag1` | National routine positivity across all states in the period before t | t-1 | FSIS routine samples (all states) | yes |
| `context_forcause_positivity_lag1 / _samples_lag1 / _trailing4_mean` | For-cause program positivity/volume — SEPARATE context, never pooled into the routine baseline | t-1 / trailing 4 | FSIS for_cause samples | yes |
| `context_exploratory_positivity_lag1 / _samples_lag1 / _trailing4_mean` | Exploratory program positivity/volume — SEPARATE context, never pooled into the routine baseline | t-1 / trailing 4 | FSIS exploratory samples | yes |
| `season_sin / season_cos` | Sin/cos encoding of the period-of-year (month 1..12 or quarter 1..4) | current period calendar only | derived from period label | yes |
| `period_of_year / calendar_year / calendar_month` | Calendar components of the target period (known in advance) | current period calendar only | derived from period label | yes |
| `geo_state` | State identifier (categorical) | static | FSIS establishment_state | yes |
| `geo_region` | Census region grouping of the state | static | derived crosswalk | yes |
| `weather_{tmax,tmin,prcp}_*_lag1` | NOAA nClimDiv statewide weather means/anomalies (°C, mm) from the latest fully-published period before t — now NON-MISSING for ~all state-periods (48 contiguous states + AK; HI absent, documented gap) | latest published period < t (end-of-month + 7d lag) | NOAA nClimDiv statewide monthly climate | yes |
| `cdc_{outbreaks,illnesses,pathogen_outbreaks}_lag1` | CDC NORS foodborne-outbreak counts / illnesses / this-pathogen outbreaks from the latest NORS period usable at t under a LARGE (~12-month) availability lag; HISTORICAL One Health evidence, sparse, missing=NaN | latest published period < t (end-of-month + ~365d lag) | CDC NORS (dataset 5xkq-dg7x, primary_mode=Food) | yes |
| `static_total_population / static_elderly_65plus_partial / static_elderly_share` | ACS 65+/vulnerability context joined by state (single pre-cutoff vintage) | static (2022 vintage, pre-cutoff) | Census ACS5 2022 | yes |
| `static_lila_tract_share / static_low_income_tract_share / static_atlas_pop_2010` | Food Access Atlas indicators joined by state (single pre-cutoff vintage) | static (2019 vintage, pre-cutoff) | USDA Food Access Research Atlas 2019 | yes |

## Raw current-period outcome (NOT features — for Task 3.3 label)

These columns carry the raw current-period routine outcome. They are kept clearly separate from the feature columns so Task 3.3 can derive the next-period elevated-positivity label from them. They are NOT used as predictors.

| Column | Definition |
|---|---|
| `outcome_routine_samples` | Current-period routine tested-sample volume (NOT a feature) |
| `outcome_routine_positives` | Current-period routine positive count (NOT a feature) |
| `outcome_routine_positivity_rate` | Current-period routine positivity rate — Task 3.3 derives the next-period elevated-positivity label from this; it is NOT a predictor feature |

