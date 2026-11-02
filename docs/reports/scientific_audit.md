# VulneraSafe AI - Scientific Audit (pre-expansion review)

All numbers below were read directly from on-disk artifacts this session:
`data/interim/provenance_ingest.json`, `data/interim/scientific_audit.json`,
`data/processed/models/{baseline_metrics,integrated_metrics}.json`, the saved
out-of-time predictions `data/processed/models/preds_*.parquet`, and
`data/interim/fsis_columns.json`. Nothing is estimated where a measurement exists.

## (a) Actual fiscal-year coverage - CORRECTED

The inventory's "FY2014/2019/2023/2026" was the sample my column-scan happened to
print, NOT the ingested set. The ingest provenance and the ZIPs on disk show
**all 13 consecutive fiscal years FY2014-FY2026 were ingested for all three
programs**:

- Raw Poultry (Salmonella): FY2014..FY2026, 7,354 -> 21,102 rows/yr (325,123 total)
- RTE (Listeria): FY2014..FY2026 (266,031 total)
- Raw Beef (STEC): FY2014..FY2026 (232,363 total)

Timeline continuity (from the processed MODEL tables, i.e. the actual modeling cells):

| Pathogen | Resolution | Periods | Span | Gaps |
|---|---|---|---|---|
| Salmonella | monthly | 153 | 2013-10 -> 2026-06 | ZERO |
| Listeria | quarterly | 51 | 2013-10 -> 2026-04 | ZERO |
| STEC | quarterly | 51 | 2013-10 -> 2026-04 | ZERO |

There are **no missing interior periods**, so lagged/trailing features never
bridge a multi-year gap. The chronological split and v2 results remain valid on
this point. One caveat to carry forward: at the state x month grain some
Salmonella cells have 0 routine samples; the target module already marks cells
unlabelable when next-period samples are below the minimum, so zero-sample cells
are excluded rather than scored as negatives (verify retained in any new target).

## (b) Model-feature reconciliation - EXACT

Measured from the parquet tables + `src.pipeline.target.feature_columns`:

- feature table columns: **51**; model table columns: **61**
- actual predictors fed to every model: **39** (34 numeric + 5 categorical),
  confirmed identical in `baseline_metrics.json` and `integrated_metrics.json`
- the dictionary's "48 feature fields / 37 predictors" was an estimate; the
  measured predictor count is 39.

Leakage scan over the 39 predictors returned **zero** matches for any
`outcome_*`, `next_*`, `y_elevated*`, `smoothed_next*`, same-sample
`*_analysis`/`mpn`/`cfu`/`pcr_*`, or `*_canceled` token. The three CDC
placeholder columns are **excluded** from predictors. Excluded sets:

- keys: pathogen, state, period, period_start, cutoff, resolution
- current outcomes: outcome_routine_{samples,positives,positivity_rate}
- labels/support: baseline, y_next_positivity, next_routine_{samples,positives},
  next_period, smoothed_next_positivity, v2_threshold, labelable[_v2],
  exclusion_reason[_v2], y_elevated, y_elevated_v2

Pooling: the model table has **one row per (state, period)** (0 duplicate
state-period rows). Within that cell the FSIS sampling programs/products ARE
aggregated into routine vs for-cause vs exploratory streams (by design); no
product-type or program split is currently modeled. That is the main feature-
engineering headroom (see (d)).

## (c) Reliable v2 validation - reproduced from saved predictions

Recomputed from `preds_*.parquet` (untouched out-of-time test), compared against
BOTH baselines from `baseline_metrics.json`:

Salmonella (monthly; test 2024-05..2026-05; n=962, 268 pos, base 27.9%)
| Model | ROC-AUC | PR-AUC |
|---|---|---|
| seasonal-naive baseline | 0.712 | 0.465 |
| regularized logistic baseline | 0.773 | 0.559 |
| XGBoost | 0.760 | 0.524 |
| LightGBM | 0.769 | 0.529 |
| RandomForest (best) | 0.783 | 0.567 |

Listeria (quarterly; test 2024-Q1..2026-Q1; n=435, 114 pos, base 26.2%)
| Model | ROC-AUC | PR-AUC |
|---|---|---|
| seasonal-naive baseline | 0.794 | 0.660 |
| regularized logistic baseline | 0.822 | 0.711 |
| RandomForest (best) | 0.836 | 0.744 |

STEC (quarterly; n=452, 113 pos, base 25.0%)
| Model | ROC-AUC | PR-AUC |
|---|---|---|
| seasonal-naive baseline | 0.594 | 0.355 |
| regularized logistic baseline | 0.622 | 0.380 |
| RandomForest (best) | 0.650 | 0.414 |

Honest reading:
- The headline "RF 0.783/0.567 (Salmonella), 0.836/0.744 (Listeria)" numbers are
  REAL and reproduce exactly from the exported predictions.
- But the ML LIFT over a strong transparent baseline is small: Salmonella RF
  beats regularized logistic by only +0.008 PR-AUC (and XGB/LGBM LOSE to it);
  Listeria RF beats logistic by +0.033 PR-AUC. STEC stays weak for every model.
- These scores mostly reflect **persistent high-risk ranking** (states that are
  chronically elevated), which the logistic/persistence baselines already
  capture. They are NOT yet a demonstrated early warning of EMERGING change.
  The emerging-change (anomaly) question needs its own metric and is not
  established by these AUCs.
- Provenance of the evaluation: the v2 target was redesigned AFTER seeing v1 test
  results, so this is an informed re-evaluation on a held-out period, NOT a fully
  independent untouched confirmatory test. Treat it as such in the report.

## (d) Top feasible unused feature groups + missingness (from fsis_columns.json counts)

Ranked by coverage x plausibility, all strictly leakage-safe only when used as
LAGGED predictors of a FUTURE period (never same-sample):

1. **Lagged Campylobacter positivity (poultry) -> future Salmonella risk.**
   `campylobacter_analysis_30ml` is well populated in recent years (FY2019 ~90%,
   FY2023 ~91% filled; FY2026 partial). Strong candidate: co-contamination signal
   on the same poultry lines, available at t to predict t+1.
2. **Product-type / sample-source split within the Salmonella state-period.**
   `product_type` and `sample_source_name` are populated across years (categorical,
   low-missingness in the raw records). Lets the cell carry product-mix context
   instead of a single pooled rate - the biggest structural headroom found.
3. **Lagged beef virulence-gene PCR (`pcr_stx_1_2_analysis`, `pcr_eae_analysis`)
   for STEC context**, but only FY2019-FY2025: coverage is ~20% (FY2014), ~75%
   (FY2019), ~100% (FY2023), and 100% NULL again at FY2026. Usable as a lagged
   contextual feature on the covered window with an explicit availability flag.

Rejected as too sparse / unusable:
- `non_lm_listeria_analysis`: ~100% NULL every year -> drop.
- MPN/CFU enumeration fields (`salmonellae_mpn_g`, `salmonella_quantitative_cfu_*`,
  `lm_listeria_mpn`): >95% NULL -> no stable signal.
- `production_alternative` (Listeria): present but low cardinality; keep as a
  minor candidate, not top-3.

Every proposed group must be evaluated by controlled ablation against the current
39-feature model on the SAME chronological split, reporting delta-PR-AUC with the
baseline comparison, before adoption.

## (e) Required final deliverables - status

Done: data acquisition+audit (all FY), harmonization, target v1->v2, baselines,
integrated models, validation, interpret/ablation, responsible-use, React panels
+ regulatory strip + theming, full data inventory + dictionaries + provenance +
One Health report.

Status of the challenge-mandatory items (all but the PDF are DONE):
1. DONE - NOAA nationwide nClimDiv statewide-monthly climate integrated.
2. DONE - CDC NORS integrated as S05 human-health corroboration (lagged, non-causal); not forced into the hazard model as a predictive feature.
3. DONE - decision optimizer (OR-Tools CP-SAT) + SIMULATED synthetic network.
4. DONE - three operational scenarios (policies A/B/C) on identical inputs.
5. DONE - exported dashboard artifacts + GitHub Pages deploy (live).
6. PENDING - PDF export of this final report.
