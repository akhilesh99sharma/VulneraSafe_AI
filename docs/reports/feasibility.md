# Multi-Factor Feasibility Assessment

Generated 2026-10-28T19:13:55. Every factor below is measured from the real FSIS laboratory-sampling archives (FY2014-FY2026). Feasibility is the conjunction of the required factors — never a single positive-count threshold (Req 3.5). Temporal resolution is chosen independently per pathogen from that pathogen's own sample availability (Req 3.6).

Chronological split: train = FY2014-FY2023, test = FY2024-FY2026.

## Summary

| Pathogen | Classification | Resolution | Train pos | Test pos | Prevalence |
|---|:--:|:--:|---:|---:|---:|
| Salmonella | predictive | monthly | 30,370 | 7,315 | 11.60% |
| Listeria | predictive | quarterly | 1,185 | 414 | 0.61% |
| STEC | predictive | quarterly | 486 | 178 | 0.29% |

## Salmonella

**Classification:** `predictive`  
**Temporal resolution:** `monthly`

### Factors

| Factor | Value | Threshold | Passed | Required |
|---|---:|---:|:--:|:--:|
| train_positives | 3.037e+04 | 30 | ✓ | yes |
| test_positives | 7315 | 10 | ✓ | yes |
| temporal_coverage | 1 | 0.6 | ✓ | yes |
| geographic_coverage | 0.9592 | 0.25 | ✓ | yes |
| stability | 0.6045 | 0.35 | ✓ | yes |
| calibration | deferred (post-validation) | n/a | ✓ | no |
| prevalence | 0.116 | 0 | ✓ | no |
| positive_rate | 0.116 | 0 | ✓ | no |

**Resolution evidence:** median positives per active cell: monthly=3.00 (over 6499 active monthly cells), quarterly=10.00 (over 2208 active quarterly cells); rule: choose monthly iff monthly median >= 1.00, else quarterly. Selected: monthly.

**Rationale:** Salmonella is classified PREDICTIVE: all required factors pass the conjunction. Chosen resolution: monthly (prevalence 11.60%). Required factors [train_positives=3.04e+04✓(thr 30), test_positives=7.32e+03✓(thr 10), temporal_coverage=1✓(thr 0.6), geographic_coverage=0.959✓(thr 0.25), stability=0.604✓(thr 0.35)]. Calibration is deferred to post-modeling validation and is not treated as decisive now. Classification is the conjunction of the required factors, not any single positive-count threshold (Req 3.5).

**Recommended prediction target:** Binary target at the monthly Modeling_Unit (pathogen x commodity x state x monthly period): next-period positivity rate exceeds the trailing >=12-month baseline for that (state-level) unit. Prevalence 11.60% is above the 10% rare-event line, so standard class weighting suffices.

**Recommended validation design:** PRIMARY chronological rolling-origin with >=3 origins (train timestamps strictly before test timestamps), the final 20% of periods held untouched (excluded from train and tuning). SECONDARY and reported separately: Establishment_Holdout_Validation (withhold all observations of held-out establishments) as a generalization check. Metrics disaggregated by region and period with 95% intervals; rare-event pathogens emphasise PR-AUC, Brier, and calibration over accuracy.

## Listeria

**Classification:** `predictive`  
**Temporal resolution:** `quarterly`

### Factors

| Factor | Value | Threshold | Passed | Required |
|---|---:|---:|:--:|:--:|
| train_positives | 1185 | 30 | ✓ | yes |
| test_positives | 414 | 10 | ✓ | yes |
| temporal_coverage | 1 | 0.6 | ✓ | yes |
| geographic_coverage | 0.8519 | 0.25 | ✓ | yes |
| stability | 0.7212 | 0.35 | ✓ | yes |
| calibration | deferred (post-validation) | n/a | ✓ | no |
| prevalence | 0.006055 | 0 | ✓ | no |
| positive_rate | 0.006055 | 0 | ✓ | no |

**Resolution evidence:** median positives per active cell: monthly=0.00 (over 7834 active monthly cells), quarterly=0.00 (over 2673 active quarterly cells); rule: choose monthly iff monthly median >= 1.00, else quarterly. Selected: quarterly.

**Rationale:** Listeria is classified PREDICTIVE: all required factors pass the conjunction. Chosen resolution: quarterly (prevalence 0.61%). Required factors [train_positives=1.18e+03✓(thr 30), test_positives=414✓(thr 10), temporal_coverage=1✓(thr 0.6), geographic_coverage=0.852✓(thr 0.25), stability=0.721✓(thr 0.35)]. Calibration is deferred to post-modeling validation and is not treated as decisive now. Classification is the conjunction of the required factors, not any single positive-count threshold (Req 3.5).

**Recommended prediction target:** Binary rare-event target at the quarterly Modeling_Unit (state-level, quarterly): next-period elevated-rate indicator (positivity exceeds the trailing >=12-month baseline), trained with rare-event handling (class weighting / scale_pos_weight) because prevalence is 0.61% (< 10%). Report under PR-AUC and calibration, not accuracy.

**Recommended validation design:** PRIMARY chronological rolling-origin with >=3 origins (train timestamps strictly before test timestamps), the final 20% of periods held untouched (excluded from train and tuning). SECONDARY and reported separately: Establishment_Holdout_Validation (withhold all observations of held-out establishments) as a generalization check. Metrics disaggregated by region and period with 95% intervals; rare-event pathogens emphasise PR-AUC, Brier, and calibration over accuracy.

## STEC

**Classification:** `predictive`  
**Temporal resolution:** `quarterly`

### Factors

| Factor | Value | Threshold | Passed | Required |
|---|---:|---:|:--:|:--:|
| train_positives | 486 | 30 | ✓ | yes |
| test_positives | 178 | 10 | ✓ | yes |
| temporal_coverage | 1 | 0.6 | ✓ | yes |
| geographic_coverage | 0.9259 | 0.25 | ✓ | yes |
| stability | 0.7277 | 0.35 | ✓ | yes |
| calibration | deferred (post-validation) | n/a | ✓ | no |
| prevalence | 0.002858 | 0 | ✓ | no |
| positive_rate | 0.002858 | 0 | ✓ | no |

**Resolution evidence:** median positives per active cell: monthly=0.00 (over 7742 active monthly cells), quarterly=0.00 (over 2612 active quarterly cells); rule: choose monthly iff monthly median >= 1.00, else quarterly. Selected: quarterly.

**Rationale:** STEC is classified PREDICTIVE: all required factors pass the conjunction. Chosen resolution: quarterly (prevalence 0.29%). Required factors [train_positives=486✓(thr 30), test_positives=178✓(thr 10), temporal_coverage=1✓(thr 0.6), geographic_coverage=0.926✓(thr 0.25), stability=0.728✓(thr 0.35)]. Calibration is deferred to post-modeling validation and is not treated as decisive now. Classification is the conjunction of the required factors, not any single positive-count threshold (Req 3.5).

**Recommended prediction target:** Binary rare-event target at the quarterly Modeling_Unit (state-level, quarterly): next-period elevated-rate indicator (positivity exceeds the trailing >=12-month baseline), trained with rare-event handling (class weighting / scale_pos_weight) because prevalence is 0.29% (< 10%). Report under PR-AUC and calibration, not accuracy.

**Recommended validation design:** PRIMARY chronological rolling-origin with >=3 origins (train timestamps strictly before test timestamps), the final 20% of periods held untouched (excluded from train and tuning). SECONDARY and reported separately: Establishment_Holdout_Validation (withhold all observations of held-out establishments) as a generalization check. Metrics disaggregated by region and period with 95% intervals; rare-event pathogens emphasise PR-AUC, Brier, and calibration over accuracy.

