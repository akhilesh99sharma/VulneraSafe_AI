# VulneraSafe AI - Scientific Audit

All numbers below were read directly from on-disk artifacts:
`data/interim/provenance_ingest.json`, `data/interim/scientific_audit.json`,
`data/processed/models/baseline_metrics.json`,
`data/processed/models/integrated_metrics.json`, the saved out-of-time
predictions `data/processed/models/preds_*.parquet`, and
`data/interim/fsis_columns.json`. Nothing is estimated where a measurement exists.

## (a) Fiscal-year coverage - complete FY2014-FY2026

The earlier inventory line "FY2014/2019/2023/2026" was only the subset a column
scan printed, NOT the ingested set. The ingest provenance and the ZIPs on disk
confirm all 13 consecutive fiscal years FY2014-FY2026 were ingested for all
three programs:

- Raw Poultry (Salmonella): FY2014..FY2026, 325,123 rows total
- RTE (Listeria): FY2014..FY2026, 266,031 rows total
- Raw Beef (STEC): FY2014..FY2026, 232,363 rows total

Timeline continuity, measured from the processed model tables (the actual
modeling cells):

| Pathogen | Resolution | Periods | Span | Interior gaps |
|---|---|---|---|---|
| Salmonella | monthly | 153 | 2013-10 -> 2026-06 | 0 |
| Listeria | quarterly | 51 | 2013-10 -> 2026-04 | 0 |
| STEC | quarterly | 51 | 2013-10 -> 2026-04 | 0 |

No missing interior periods, so lagged/trailing features never bridge a
multi-year gap and the chronological split is valid on that point. Caveat to
carry forward: at the state x month grain some Salmonella cells have 0 routine
samples; the target module marks a cell unlabelable when next-period samples are
below the minimum, so zero-sample cells are excluded rather than scored negative.

## (b) Model-feature reconciliation - exact

Measured from the parquet tables and `src.pipeline.target.feature_columns`:

- feature table columns: 51; model table columns: 61
- actual predictors fed to every model: 39 (34 numeric + 5 categorical),
  identical in baseline_metrics.json and integrated_metrics.json
- the dictionary's "48 feature fields / 37 predictors" was an estimate; the
  measured predictor count is 39

Leakage scan over the 39 predictors returned zero matches for any `outcome_*`,
`next_*`, `y_elevated*`, `smoothed_next*`, same-sample
`*_analysis`/`mpn`/`cfu`/`pcr_*`, or `*_canceled` token. The three CDC
placeholder columns are excluded from predictors.

Excluded sets:
- keys: pathogen, state, period, period_start, cutoff, resolution
- current outcomes: outcome_routine_samples, outcome_routine_positives,
  outcome_routine_positivity_rate
- labels/support: baseline, y_next_positivity, next_routine_samples,
  next_routine_positives, next_period, smoothed_next_positivity, v2_threshold,
  labelable, labelable_v2, exclusion_reason, exclusion_reason_v2, y_elevated,
  y_elevated_v2

Pooling: one row per (state, period) (0 duplicate state-period rows). Within the
cell the FSIS sampling programs are aggregated into routine / for-cause /
exploratory streams by design; product-type and program are NOT currently split.
That pooling is the main feature-engineering headroom.

## (c) v2 validation vs strong baselines

**Primary (exported chronological source of truth).** The headline model-
performance figures below are the exported chronological, best-model-per-pathogen
values from `web/public/data/model_metrics.json` (region=null, period=null),
cross-checked against `docs/reports/model_validation.md`. These are the numbers
every reporting doc aligns to.

| Pathogen | Best model | PR-AUC | ROC-AUC |
|---|---|---|---|
| Salmonella | lightgbm | 0.516 | 0.764 |
| Listeria | random_forest | 0.736 | 0.838 |
| STEC | random_forest | 0.434 | 0.650 |

### State-level integrated split (secondary protocol — NOT the exported chronological values)

The tables in this subsection come from the state-level v2 integrated-split
protocol (`preds_*.parquet`, compared against BOTH baselines in
`baseline_metrics.json`). They are reported separately and are **not** the
exported chronological source-of-truth values above; do not treat them as such.

Salmonella (monthly; test 2024-05..2026-05; n=962, 268 pos, base rate 27.9%)

| Model | ROC-AUC | PR-AUC |
|---|---|---|
| seasonal-naive baseline | 0.712 | 0.465 |
| regularized logistic baseline | 0.773 | 0.559 |
| XGBoost | 0.760 | 0.524 |
| LightGBM | 0.769 | 0.529 |
| RandomForest (best) | 0.783 | 0.567 |

Listeria (quarterly; test 2024-Q1..2026-Q1; n=435, 114 pos, base rate 26.2%)

| Model | ROC-AUC | PR-AUC |
|---|---|---|
| seasonal-naive baseline | 0.794 | 0.660 |
| regularized logistic baseline | 0.822 | 0.711 |
| RandomForest (best) | 0.836 | 0.744 |

STEC (quarterly; test 2024-Q1..2026-Q1; n=452, 113 pos, base rate 25.0%)

| Model | ROC-AUC | PR-AUC |
|---|---|---|
| seasonal-naive baseline | 0.594 | 0.355 |
| regularized logistic baseline | 0.622 | 0.380 |
| RandomForest (best) | 0.650 | 0.414 |

Honest reading:
- The exported chronological source-of-truth headline figures are Salmonella
  0.516/0.764 (lightgbm), Listeria 0.736/0.838 (random_forest), and STEC
  0.434/0.650 (random_forest) — see the primary table above. The
  RandomForest numbers in the state-level tables (Salmonella 0.783/0.567;
  Listeria 0.836/0.744) are the state-level integrated-split protocol, not the
  exported chronological values, and are reported separately.
- The ML LIFT over a strong transparent baseline is at most a small margin: on
  the exported chronological split the integrated Salmonella model is roughly on
  par with the regularized-logistic baseline rather than clearly ahead, and
  Listeria is a small margin ahead. STEC stays weak for every model.
- These scores mostly reflect PERSISTENT high-risk ranking (chronically elevated
  states), which the logistic/persistence baselines already capture. They do NOT
  by themselves demonstrate early warning of EMERGING spikes. Persistent
  high-risk identification and true anomaly forecasting are separate claims; only
  the former is supported here.
- Evaluation provenance: the v2 target was redesigned AFTER seeing v1 test
  results, so this is an informed re-evaluation on a held-out period, NOT a fully
  independent untouched confirmatory test. It is reported as such.

## (d) Availability assumptions and data-stream limitations

- NOAA weather in the current feature matrix is a thin single-station slice;
  the nationwide nClimDiv state-month integration is a mandatory next step. Until
  then, weather features are flagged "safe but sparse".
- CDC NORS columns (cdc_outbreaks_lag1, cdc_illnesses_lag1,
  cdc_pathogen_outbreaks_lag1) are placeholders, not a real join, and are
  excluded from predictors. NORS also carries real publication delay; if it
  cannot supply a timely predictive signal it will be integrated for historical
  corroboration rather than forced into the ML model.
- FSIS Recalls/PHAs are firewalled (HTTP 403) in this environment and are not
  ingested; the regulatory-evidence channel is documented as pending.
- No serotype/serovar/WGS/PFGE field exists in any FSIS program; no strain-level
  attribution is claimed.

## (e) Top feasible unused feature groups (from fsis_columns.json counts)

Usable only as LAGGED predictors of a FUTURE period (never same-sample):

1. Lagged Campylobacter positivity (poultry) -> future Salmonella risk.
   `campylobacter_analysis_30ml` is well populated recently (FY2019 ~90%, FY2023
   ~91% filled; FY2026 partial). Co-contamination signal on the same lines.
2. Product-type / sample-source split within the Salmonella state-period.
   `product_type` and `sample_source_name` are populated across years, low
   missingness. Lets the cell carry product mix instead of one pooled rate -
   the biggest structural headroom.
3. Lagged beef virulence-gene PCR (pcr_stx_1_2_analysis, pcr_eae_analysis) for
   STEC context, but only FY2019-FY2025: ~20% (FY2014), ~75% (FY2019), ~100%
   (FY2023), 100% NULL (FY2026). Usable on the covered window with an explicit
   availability flag.

Rejected as too sparse: non_lm_listeria_analysis (~100% NULL every year),
MPN/CFU enumeration fields (>95% NULL). production_alternative (Listeria) is a
minor candidate, not top-3.

Every proposed group must be evaluated by controlled ablation against the current
39-feature model on the SAME chronological split, reporting delta-PR-AUC with the
baseline comparison, before adoption. These experiments are SECONDARY to the
mandatory deliverables.

## Integrity notes

- Verified baseline results and existing model artifacts are preserved.
- The small integrated-model improvement over baselines is NOT claimed as proof
  of strong emerging-spike prediction.
- If NOAA/CDC integration changes the feature matrix, validation and ablations
  will be rerun before attributing any gain to those streams.
- No observations, predictive improvements, regulatory alerts or operational
  outcomes are fabricated.
