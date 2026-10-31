# Model Validation (Task 3.7 — Requirements 8.1-8.7)
Time-aware validation and uncertainty for the per-pathogen risk models. Chronological validation is PRIMARY (an untouched final ~20% test split plus rolling-origin validation with >= 3 origins); a state-level geographic holdout is a SECONDARY check reported separately. Every number below is computed only from exported predictions; any metric that cannot be computed for a slice is recorded as unavailable, never fabricated (Req 8.6-8.7).
> **State-holdout limitation.** The modeling units are aggregated to `(state, period)` with no establishment identifier, so true `Establishment_Holdout_Validation` is not possible on these tables. The secondary check withholds whole states from training as the available geographic-generalization proxy and is labeled as such — an honest limitation, not a claim of establishment-level holdout.

## Salmonella (best model: `lightgbm`)
### Chronological single-split (untouched final ~20%)
- Test units: 962 (positives: 268, base rate: 0.279)
- PR-AUC: 0.516 [0.457, 0.583]
- ROC-AUC: 0.764 [0.732, 0.795]
- Precision @ 0.5: 0.562 [0.476, 0.637]
- Recall @ 0.5: 0.306 [0.252, 0.357]
- Brier: 0.175 [0.160, 0.192]

_(values are point estimate [2.5%, 97.5%] bootstrap interval)_
### Calibration (reliability)
- Calibration error (count-weighted |pred - obs|): 0.081 (lower is better; 0 = perfectly reliable)
### Rolling-origin vs single-split
- Origins produced: 3 (available: 3, warm-up periods: 12)
- PR_AUC: single-split 0.516 vs rolling-origin mean 0.452 (delta -0.064)
- ROC_AUC: single-split 0.764 vs rolling-origin mean 0.719 (delta -0.045)
- BRIER: single-split 0.175 vs rolling-origin mean 0.183 (delta 0.007)
### Secondary: state-level geographic holdout (reported separately)
- Held-out states: AZ, CA, GA, LA, MA, MS, NY, OH, RI, WI, WV (11 of 43)
- PR-AUC: 0.380, ROC-AUC: 0.652, Brier: 0.199
### Inspection budget (top-K) and FP/FN
- Top-K: inspect top 97 of 962 units (top 10%); captured 59 of 268 positives; precision@K 0.608, recall@K 0.220
- FP/FN @ 0.5: FP=64 (rate 0.092), FN=186 (rate 0.694)
### Disaggregation coverage (Req 8.4 / 8.7)
- Regions: 34 of 41 had enough positives to score (7 marked unavailable)
- Periods: 25 of 25 scored (0 marked unavailable)

## Listeria (best model: `random_forest`)
### Chronological single-split (untouched final ~20%)
- Test units: 435 (positives: 114, base rate: 0.262)
- PR-AUC: 0.736 [0.663, 0.800]
- ROC-AUC: 0.838 [0.791, 0.879]
- Precision @ 0.5: 0.794 [0.698, 0.880]
- Recall @ 0.5: 0.474 [0.390, 0.562]
- Brier: 0.124 [0.107, 0.143]

_(values are point estimate [2.5%, 97.5%] bootstrap interval)_
### Calibration (reliability)
- Calibration error (count-weighted |pred - obs|): 0.031 (lower is better; 0 = perfectly reliable)
### Rolling-origin vs single-split
- Origins produced: 3 (available: 3, warm-up periods: 4)
- PR_AUC: single-split 0.736 vs rolling-origin mean 0.699 (delta -0.037)
- ROC_AUC: single-split 0.838 vs rolling-origin mean 0.815 (delta -0.023)
- BRIER: single-split 0.124 vs rolling-origin mean 0.130 (delta 0.006)
### Secondary: state-level geographic holdout (reported separately)
- Held-out states: AZ, CA, GA, LA, MA, MT, NC, NJ, NM, PA, UT, WI, WY (13 of 52)
- PR-AUC: 0.679, ROC-AUC: 0.788, Brier: 0.148
### Inspection budget (top-K) and FP/FN
- Top-K: inspect top 44 of 435 units (top 10%); captured 40 of 114 positives; precision@K 0.909, recall@K 0.351
- FP/FN @ 0.5: FP=14 (rate 0.044), FN=60 (rate 0.526)
### Disaggregation coverage (Req 8.4 / 8.7)
- Regions: 28 of 51 had enough positives to score (23 marked unavailable)
- Periods: 9 of 9 scored (0 marked unavailable)

## STEC (best model: `random_forest`)
### Chronological single-split (untouched final ~20%)
- Test units: 452 (positives: 113, base rate: 0.250)
- PR-AUC: 0.434 [0.353, 0.528]
- ROC-AUC: 0.650 [0.590, 0.709]
- Precision @ 0.5: 0.450 [0.342, 0.558]
- Recall @ 0.5: 0.319 [0.242, 0.403]
- Brier: 0.184 [0.165, 0.205]

_(values are point estimate [2.5%, 97.5%] bootstrap interval)_
### Calibration (reliability)
- Calibration error (count-weighted |pred - obs|): 0.104 (lower is better; 0 = perfectly reliable)
### Rolling-origin vs single-split
- Origins produced: 3 (available: 3, warm-up periods: 4)
- PR_AUC: single-split 0.434 vs rolling-origin mean 0.464 (delta 0.031)
- ROC_AUC: single-split 0.650 vs rolling-origin mean 0.681 (delta 0.031)
- BRIER: single-split 0.184 vs rolling-origin mean 0.173 (delta -0.011)
### Secondary: state-level geographic holdout (reported separately)
- Held-out states: AZ, CA, GA, MA, MT, NC, NJ, NV, PA, TN, UT, WI, WY (13 of 51)
- PR-AUC: 0.399, ROC-AUC: 0.709, Brier: 0.163
### Inspection budget (top-K) and FP/FN
- Top-K: inspect top 46 of 452 units (top 10%); captured 27 of 113 positives; precision@K 0.587, recall@K 0.239
- FP/FN @ 0.5: FP=44 (rate 0.130), FN=77 (rate 0.681)
### Disaggregation coverage (Req 8.4 / 8.7)
- Regions: 42 of 51 had enough positives to score (9 marked unavailable)
- Periods: 9 of 9 scored (0 marked unavailable)
