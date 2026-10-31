# FSIS Dataset Audit

Generated 2026-10-28T18:58:49. All counts are computed from the real FSIS laboratory-sampling archives (FY2014-FY2026). Positive/negative/other are tri-state; the `other` bucket is not-tested/indeterminate/blank and is never folded into positives or negatives (Req 3.1).

## Headline per-pathogen counts

| Pathogen | Program | Observations | Positives | Negatives | Other | Denominator (pos+neg) | Overall positivity | Complete |
|---|---|---:|---:|---:|---:|---:|---:|:--:|
| Salmonella | raw_poultry_salmonella | 325,123 | 37,685 | 287,238 | 200 | 324,923 | 0.1160 (11.60%) | NO (incomplete) |
| Listeria | rte_listeria | 266,031 | 1,599 | 262,502 | 1,930 | 264,101 | 0.0061 (0.61%) | NO (incomplete) |
| STEC | raw_beef_stec | 232,363 | 664 | 231,683 | 16 | 232,347 | 0.0029 (0.29%) | NO (incomplete) |

## Salmonella — `raw_poultry_salmonella`

- Result column audited: `salmonella_sp_analysis`
- Positive vocabulary: ['Positive']
- Negative vocabulary: ['Negative']
- Other/indeterminate vocabulary: ['13  Insufficient tissue or sample', '25-20  Other - (Describe on form in up to 54 characters)', '25-5  Lab problem - lab closed', '26 Lab closed', '<blank/NULL>']
- Collection-date range: 2013-10-01 .. 2026-06-30 (0 present-but-unparsable)
- Establishments: 1,409 distinct (id present: True)
- Geographic coverage: 49 distinct states; missing fraction 0.0000
- Publication date: UNAVAILABLE (gap); reporting delay: UNAVAILABLE (gap)

### Positivity by fiscal year

| Fiscal year | Observations | Positives | Negatives | Other | Positivity |
|---|---:|---:|---:|---:|---:|
| FY2014 | 7,354 | 2,362 | 4,981 | 11 | 0.3217 (32.17%) |
| FY2015 | 11,108 | 2,427 | 8,679 | 2 | 0.2185 (21.85%) |
| FY2016 | 20,089 | 2,410 | 17,675 | 4 | 0.1200 (12.00%) |
| FY2017 | 22,496 | 2,587 | 19,897 | 12 | 0.1151 (11.51%) |
| FY2018 | 27,604 | 3,440 | 24,148 | 16 | 0.1247 (12.47%) |
| FY2019 | 28,883 | 3,073 | 25,741 | 69 | 0.1066 (10.66%) |
| FY2020 | 31,453 | 2,895 | 28,553 | 5 | 0.0921 (9.21%) |
| FY2021 | 30,881 | 2,635 | 28,237 | 9 | 0.0854 (8.54%) |
| FY2022 | 34,613 | 4,902 | 29,708 | 3 | 0.1416 (14.16%) |
| FY2023 | 32,035 | 3,639 | 28,381 | 15 | 0.1136 (11.36%) |
| FY2024 | 28,941 | 2,476 | 26,429 | 36 | 0.0857 (8.57%) |
| FY2025 | 28,564 | 2,798 | 25,756 | 10 | 0.0980 (9.80%) |
| FY2026 | 21,102 | 2,041 | 19,053 | 8 | 0.0968 (9.68%) |

### Positivity by sampling program / project code (not pooled)

| Project code | Project name | Observations | Positives | Negatives | Other | Positivity |
|---|---|---:|---:|---:|---:|---:|
| HC_CPT_LBW01 | Sampling for Chicken Parts – Legs, Breasts, and  | 130,685 | 12,758 | 117,862 | 65 | 0.0977 (9.77%) |
| HC_CH_CARC01 | HACCP Verification for Young Chicken Carcasses | 102,695 | 4,799 | 97,850 | 46 | 0.0468 (4.68%) |
| HC_CH_COM01 | Sampling for Ground and Other Comminuted Chicken | 18,215 | 5,070 | 13,130 | 15 | 0.2786 (27.86%) |
| HC_TU_CARC01 | HACCP Verification for Young Turkey Carcasses | 16,722 | 109 | 16,597 | 16 | 0.0065 (0.65%) |
| HC_TU_COM01 | Sampling for Ground and Other Comminuted Turkey  | 13,457 | 2,208 | 11,242 | 7 | 0.1642 (16.42%) |
| F_CPT_LBW01 | Follow-up sampling of Chicken Parts – legs, brea | 10,617 | 1,641 | 8,972 | 4 | 0.1546 (15.46%) |
| NRTE_EXP_CH | NRTE (Not-Ready-to-Eat)  Comminuted Poultry Expl | 4,915 | 2,941 | 1,964 | 10 | 0.5996 (59.96%) |
| EX_CHCAR_RH1 | Exploratory Young Chicken Carcass Rehang Samplin | 4,775 | 2,968 | 1,807 | 0 | 0.6216 (62.16%) |
| F_CH_CARC01 | Follow-up sampling of Chicken Carcasses | 4,297 | 516 | 3,781 | 0 | 0.1201 (12.01%) |
| NRTE_EXP_TU | NRTE (Not-Ready-to-Eat)  Comminuted Poultry Expl | 2,549 | 532 | 2,015 | 2 | 0.2089 (20.89%) |
| SPECPGM_02 | Intensifed Sampling - S. Heidelberg | 2,487 | 219 | 2,268 | 0 | 0.0881 (8.81%) |
| LO_CPT_LBW01 | Very Low Volume Sampling for Raw Chicken Parts - | 1,981 | 242 | 1,736 | 3 | 0.1223 (12.23%) |
| F_CH_COM01 | Follow-up sampling of Comminuted Chicken | 1,705 | 629 | 1,076 | 0 | 0.3689 (36.89%) |
| F_TU_COM01 | Follow-up sampling of Comminuted Turkey | 1,372 | 247 | 1,125 | 0 | 0.1800 (18.00%) |
| LO_CH_COM01 | Very Low Volume Sampling for Ground and Other Co | 1,280 | 235 | 1,044 | 1 | 0.1837 (18.37%) |
| SPECPGM_06 | Stuffed Chicken Outbreak Sampling - product | 1,213 | 461 | 752 | 0 | 0.3800 (38.00%) |
| SPECPGM_02B | Intensified Sampling at Establishments Associate | 1,127 | 117 | 1,010 | 0 | 0.1038 (10.38%) |
| EXP_CPT_OT01 | Exploratory Sampling for Chicken Parts - Others  | 1,013 | 529 | 462 | 22 | 0.5338 (53.38%) |
| EXP_CH_MSK01 | Exploratory Sampling for Mechanically Separated  | 899 | 723 | 175 | 1 | 0.8051 (80.51%) |
| EXP_TU_MSK01 | Exploratory Sampling for Mechanically Separated  | 820 | 382 | 437 | 1 | 0.4664 (46.64%) |
| EXP_CPT_QH01 | Exploratory Sampling for Chicken Parts - Quarter | 614 | 69 | 544 | 1 | 0.1126 (11.26%) |
| LO_TU_COM01 | Very Low Volume Sampling for Ground and Other Co | 480 | 40 | 440 | 0 | 0.0833 (8.33%) |
| SPECPGM_05 | Stuffed Chicken Outbreak Sampling - product | 220 | 57 | 163 | 0 | 0.2591 (25.91%) |
| LO_CPT_OT01 | Very Low Volume Sampling for Raw Chicken Parts - | 195 | 77 | 113 | 5 | 0.4053 (40.53%) |
| RE_CH_CARC01 | Religious Exempt Sampling for Chicken Carcasses | 178 | 57 | 121 | 0 | 0.3202 (32.02%) |
| LO_CPT_QH01 | Very Low Volume Sampling for Chicken Parts - Qua | 151 | 21 | 130 | 0 | 0.1391 (13.91%) |
| SPECPGM_06E | Stuffed Chicken Outbreak Sampling - environmenta | 118 | 0 | 118 | 0 | 0.0000 (0.00%) |
| LO_CH_CARC01 | Very Low Volume Sampling for Chicken Carcasses | 115 | 21 | 93 | 1 | 0.1842 (18.42%) |
| LO_TU_CARC01 | Very Low Volume Sampling for Turkey Carcasses | 79 | 5 | 74 | 0 | 0.0633 (6.33%) |
| F_TU_CARC01 | Follow-up sampling of Turkey Carcasses | 53 | 4 | 49 | 0 | 0.0755 (7.55%) |
| SPECPGM_05E | Stuffed Chicken Outbreak Sampling - environmenta | 42 | 1 | 41 | 0 | 0.0238 (2.38%) |
| SPECPGM_07 | Turkey Carcass Sponge Sampling - In-plant trial | 30 | 0 | 30 | 0 | 0.0000 (0.00%) |
| LO_CH_MSK01 | Very Low Volume Sampling for Mechanically Separa | 16 | 7 | 9 | 0 | 0.4375 (43.75%) |
| SPECPGM_RTEP | Special Program Sampling - Ready to Eat Product | 8 | 0 | 8 | 0 | 0.0000 (0.00%) |

### Duplicate findings (reported, not dropped)

- Exact duplicate rows: 0
- Duplicate sample numbers: 0
- Likely-duplicate records on `establishment_id+collection_date+product_type+salmonella_sp_analysis`: 11,691

### Schema changes across fiscal years

- (baseline) -> FY2014: added=['aerobic_plate_count_mpn_100_sq_cm', 'aerobic_plate_count_mpn_g', 'aerobic_plate_count_mpn_ml', 'campylobacter_analysis_1ml', 'campylobacter_analysis_1ml_canceled', 'campylobacter_analysis_30ml', 'campylobacter_analysis_30ml_canceled', 'collection_date', 'enterobacteriaceae_mpn_100_sq_cm', 'enterobacteriaceae_mpn_ml', 'establishment_id', 'establishment_name', 'establishment_number', 'establishment_state', 'form_id', 'not_analyzed', 'not_analyzed_explain', 'product_type', 'project_code', 'project_name', 'salmonella_mpn_qualitative', 'salmonella_quantitative_cfu_g', 'salmonella_quantitative_cfu_ml', 'salmonella_sp_analysis', 'salmonella_sp_analysis_canceled', 'salmonellae_mpn_combination', 'salmonellae_mpn_g', 'salmonellae_mpn_g_canceled', 'sample_number', 'sample_source_name'] removed=[] dtype_changes=[]

### Leakage checks

- `collection_date_present`: PASS — 325123/325123 rows have a parseable collection_date (1.000); 0 present-but-unparsable.
- `no_future_collection_dates`: PASS — 0 rows have a collection_date after today (2026-10-28).

### Recorded gaps (uncomputable fields — never fabricated)

- `publication_date`: FSIS laboratory-sampling files contain no publication/public-availability date column; reporting delay cannot be computed from the data (not fabricated).
- `reporting_delay_days`: depends on unavailable publication_date

## Listeria — `rte_listeria`

- Result column audited: `lm_listeria_analysis`
- Positive vocabulary: ['Positive']
- Negative vocabulary: ['Confirmed Negative of a Previous Presumptive', 'Negative']
- Other/indeterminate vocabulary: ['<blank/NULL>']
- Collection-date range: 2013-10-01 .. 2026-06-30 (0 present-but-unparsable)
- Establishments: 3,765 distinct (id present: True)
- Geographic coverage: 54 distinct states; missing fraction 0.0000
- Publication date: UNAVAILABLE (gap); reporting delay: UNAVAILABLE (gap)

### Positivity by fiscal year

| Fiscal year | Observations | Positives | Negatives | Other | Positivity |
|---|---:|---:|---:|---:|---:|
| FY2014 | 21,974 | 137 | 21,729 | 108 | 0.0063 (0.63%) |
| FY2015 | 21,738 | 192 | 21,491 | 55 | 0.0089 (0.89%) |
| FY2016 | 22,905 | 138 | 22,383 | 384 | 0.0061 (0.61%) |
| FY2017 | 22,516 | 143 | 22,211 | 162 | 0.0064 (0.64%) |
| FY2018 | 21,053 | 92 | 20,817 | 144 | 0.0044 (0.44%) |
| FY2019 | 19,944 | 87 | 19,633 | 224 | 0.0044 (0.44%) |
| FY2020 | 17,320 | 69 | 17,158 | 93 | 0.0040 (0.40%) |
| FY2021 | 19,506 | 87 | 19,325 | 94 | 0.0045 (0.45%) |
| FY2022 | 20,060 | 140 | 19,649 | 271 | 0.0071 (0.71%) |
| FY2023 | 20,251 | 100 | 20,024 | 127 | 0.0050 (0.50%) |
| FY2024 | 17,239 | 124 | 16,934 | 181 | 0.0073 (0.73%) |
| FY2025 | 27,211 | 208 | 26,916 | 87 | 0.0077 (0.77%) |
| FY2026 | 14,314 | 82 | 14,232 | 0 | 0.0057 (0.57%) |

### Positivity by sampling program / project code (not pooled)

| Project code | Project name | Observations | Positives | Negatives | Other | Positivity |
|---|---|---:|---:|---:|---:|---:|
| RTEPROD_RISK | RTEPROD Sampling - Risk-based RTE Products | 94,766 | 222 | 94,519 | 25 | 0.0023 (0.23%) |
| RTEPROD_RAND | RTEPROD Sampling - Random RTE Products | 63,820 | 172 | 63,631 | 17 | 0.0027 (0.27%) |
| RTEPROD | Ready To Eat Sampling | 16,855 | 35 | 16,820 | 0 | 0.0021 (0.21%) |
| RLMCONT_MWL | Risk-based Verification-Midwest Lab-RTE-Food Con | 14,354 | 28 | 14,325 | 1 | 0.0020 (0.20%) |
| RLMCONT_EL | Risk-based Verification-Eastern Lab - RTE - Food | 11,613 | 26 | 11,557 | 30 | 0.0022 (0.22%) |
| RLMCONT_WL | Risk-based Verification-Western Lab-Food Contact | 11,413 | 28 | 11,385 | 0 | 0.0025 (0.25%) |
| RLMCONT | LM Risk-based Verification Testing Program - Con | 10,373 | 41 | 10,332 | 0 | 0.0040 (0.40%) |
| INTCONT_LM_E | For-Cause Sampling-Eastern Lab-RTE Food Contact  | 5,642 | 58 | 5,584 | 0 | 0.0103 (1.03%) |
| INTCONT_LM_M | For-Cause Sampling-Midwest Lab-RTE Food Contact  | 4,749 | 61 | 4,688 | 0 | 0.0128 (1.28%) |
| INTCONT_LM_W | For-Cause Sampling-Western Lab-RTE Food Contact  | 3,012 | 50 | 2,962 | 0 | 0.0166 (1.66%) |
| INTENV_LM_E | For-Cause Sampling-Eastern Lab-Non-Food Surface- | 2,854 | 115 | 2,739 | 0 | 0.0403 (4.03%) |
| INTPROD_LM_E | For-Cause Sampling-Eastern Lab-RTE Product-Liste | 2,768 | 41 | 2,727 | 0 | 0.0148 (1.48%) |
| INTENV_LM_M | For-Cause Sampling-Midwest Lab-Non-Food Surface- | 2,421 | 104 | 2,317 | 0 | 0.0430 (4.30%) |
| INTCONT | Intensified Ready-To-Eat Food Contact Surfaces | 2,379 | 28 | 2,306 | 45 | 0.0120 (1.20%) |
| INTPROD_LM_M | For-Cause Sampling-Midwest Lab-RTE Product-Liste | 2,262 | 45 | 2,217 | 0 | 0.0199 (1.99%) |
| INTENV_LM_W | For-Cause Sampling-Western Lab-Non-Food Surface- | 1,541 | 59 | 1,482 | 0 | 0.0383 (3.83%) |
| RLMPRODC_MWL | Risk-based Verification-Midwestern Lab - RTE - L | 1,444 | 4 | 1,440 | 0 | 0.0028 (0.28%) |
| RLMENVC_MWL | Risk-based Verification-Midwest Lab-RTE-Non-Food | 1,441 | 106 | 1,334 | 1 | 0.0736 (7.36%) |
| INTPROD_LM_W | For-Cause Sampling-Western Lab-RTE Product-Liste | 1,435 | 19 | 1,416 | 0 | 0.0132 (1.32%) |
| INTENV | Intensified Ready-To-Eat Environmental Surfaces | 1,262 | 57 | 1,133 | 72 | 0.0479 (4.79%) |
| INTPROD | Intensified Ready-To-Eat Products | 1,173 | 19 | 1,109 | 45 | 0.0168 (1.68%) |
| RLMPRODC_EL | Risk-based Verification-Eastern Lab - RTE - List | 1,167 | 6 | 1,159 | 2 | 0.0052 (0.52%) |
| RLMENVC_EL | Risk-based Verification-Eastern Lab - RTE - Non- | 1,162 | 75 | 1,084 | 3 | 0.0647 (6.47%) |
| RLMENVC_WL | Risk-based Verification-Western Lab-RTE-Non-food | 1,154 | 89 | 1,065 | 0 | 0.0771 (7.71%) |
| RLMPRODC_WL | Risk-based Verification-Western Lab - RTE - List | 1,149 | 7 | 1,142 | 0 | 0.0061 (0.61%) |
| RLMENVC | Listeria mono.Risk-based Testing-Environmental-C | 1,053 | 95 | 958 | 0 | 0.0902 (9.02%) |
| RLMPRODC | RTE-Risk-based Verification Testing - Product-Co | 1,047 | 9 | 1,038 | 0 | 0.0086 (0.86%) |
| INTENV_SA_E | For-Cause Sampling-Eastern Lab-Non-Food Surface- | 352 | 0 | 0 | 352 | n/a |
| INTENV_SA_M | For-Cause Sampling-Midwest Lab-Non-Food Surface- | 272 | 0 | 0 | 272 | n/a |
| INTCONT_SA_E | For-Cause Sampling-Eastern Lab-RTE Food Contact  | 220 | 0 | 0 | 220 | n/a |
| INTPROD_SA_E | For-Cause Sampling-Eastern Lab-RTE Product-Salmo | 208 | 0 | 0 | 208 | n/a |
| INTCONT_SA_M | For-Cause Sampling-Midwest Lab-RTE Food Contact  | 170 | 0 | 0 | 170 | n/a |
| INTPROD_SA_M | For-Cause Sampling-Midwest Lab-RTE Product-Salmo | 167 | 0 | 0 | 167 | n/a |
| INTENV_SA_W | For-Cause Sampling-Western Lab-Non-Food Surface- | 134 | 0 | 0 | 134 | n/a |
| INTCONT_SA_W | For-Cause Sampling-Western Lab-RTE Food Contact  | 85 | 0 | 0 | 85 | n/a |
| INTPROD_SA_W | For-Cause Sampling-Western Lab-RTE Product-Salmo | 81 | 0 | 0 | 81 | n/a |
| RLMENVR_EL | Risk-based Verification-Eastern Lab-RTE-Non-food | 12 | 0 | 12 | 0 | 0.0000 (0.00%) |
| RLMENVR_MWL | Risk-based Verification-Midwest Lab-RTE-Non-food | 9 | 0 | 9 | 0 | 0.0000 (0.00%) |
| RLMENVR | LM Risk-based Verification - Environmental-Non-C | 6 | 0 | 6 | 0 | 0.0000 (0.00%) |
| RLMENVR_WL | Risk-based Verification-Western Lab-RTE-Non-food | 6 | 0 | 6 | 0 | 0.0000 (0.00%) |

### Duplicate findings (reported, not dropped)

- Exact duplicate rows: 0
- Duplicate sample numbers: 0
- Likely-duplicate records on `establishment_id+collection_date+sample_source_name+lm_listeria_analysis`: 75,468

### Schema changes across fiscal years

- (baseline) -> FY2014: added=['collection_date', 'establishment_id', 'establishment_name', 'establishment_number', 'establishment_state', 'form_id', 'lm_listeria_analysis', 'lm_listeria_analysis_canceled', 'lm_listeria_mpn', 'lm_listeria_mpn_canceled', 'lm_listeria_mpn_combination', 'lm_listeria_mpn_combination_canceled', 'non_lm_listeria_analysis', 'non_lm_listeria_analysis_canceled', 'not_analyzed', 'not_analyzed_explain', 'production_alternative', 'project_code', 'project_name', 'salmonella_mpn_qualitative', 'salmonella_sp_analysis', 'salmonella_sp_analysis_canceled', 'salmonellae_mpn_combination', 'salmonellae_mpn_combination_canceled', 'salmonellae_mpn_g', 'salmonellae_mpn_g_canceled', 'sample_number', 'sample_source_name'] removed=[] dtype_changes=[]

### Leakage checks

- `collection_date_present`: PASS — 266031/266031 rows have a parseable collection_date (1.000); 0 present-but-unparsable.
- `no_future_collection_dates`: PASS — 0 rows have a collection_date after today (2026-10-28).

### Recorded gaps (uncomputable fields — never fabricated)

- `publication_date`: FSIS laboratory-sampling files contain no publication/public-availability date column; reporting delay cannot be computed from the data (not fabricated).
- `reporting_delay_days`: depends on unavailable publication_date

## STEC — `raw_beef_stec`

- Result column audited: `stec_analysis`
- Positive vocabulary: ['Positive']
- Negative vocabulary: ['Confirmed Negative of a Previous Presumptive', 'Negative']
- Other/indeterminate vocabulary: ['<blank/NULL>']
- Collection-date range: 2013-10-01 .. 2026-06-30 (0 present-but-unparsable)
- Establishments: 2,524 distinct (id present: True)
- Geographic coverage: 54 distinct states; missing fraction 0.0000
- Publication date: UNAVAILABLE (gap); reporting delay: UNAVAILABLE (gap)

### Positivity by fiscal year

| Fiscal year | Observations | Positives | Negatives | Other | Positivity |
|---|---:|---:|---:|---:|---:|
| FY2014 | 17,765 | 52 | 17,713 | 0 | 0.0029 (0.29%) |
| FY2015 | 17,871 | 55 | 17,815 | 1 | 0.0031 (0.31%) |
| FY2016 | 17,894 | 49 | 17,845 | 0 | 0.0027 (0.27%) |
| FY2017 | 17,455 | 53 | 17,402 | 0 | 0.0030 (0.30%) |
| FY2018 | 17,916 | 31 | 17,885 | 0 | 0.0017 (0.17%) |
| FY2019 | 17,964 | 59 | 17,905 | 0 | 0.0033 (0.33%) |
| FY2020 | 18,162 | 54 | 18,106 | 2 | 0.0030 (0.30%) |
| FY2021 | 18,197 | 39 | 18,153 | 5 | 0.0021 (0.21%) |
| FY2022 | 17,923 | 40 | 17,882 | 1 | 0.0022 (0.22%) |
| FY2023 | 18,025 | 54 | 17,965 | 6 | 0.0030 (0.30%) |
| FY2024 | 18,741 | 61 | 18,680 | 0 | 0.0033 (0.33%) |
| FY2025 | 19,089 | 64 | 19,025 | 0 | 0.0034 (0.34%) |
| FY2026 | 15,361 | 53 | 15,307 | 1 | 0.0035 (0.35%) |

### Positivity by sampling program / project code (not pooled)

| Project code | Project name | Observations | Positives | Negatives | Other | Positivity |
|---|---|---:|---:|---:|---:|---:|
| MT43 | Risk-based Sampling of Raw Ground Beef or Veal P | 144,252 | 167 | 144,078 | 7 | 0.0012 (0.12%) |
| MT60 | Sampling of Beef Manufacturing Trimmings | 34,138 | 261 | 33,874 | 3 | 0.0076 (0.76%) |
| MT64 | Sampling of Raw Ground Beef or Beef Patty Compon | 12,445 | 44 | 12,401 | 0 | 0.0035 (0.35%) |
| MT60_C | Sampling of Beef Manufacturing Trimmings with Cl | 12,196 | 45 | 12,145 | 6 | 0.0037 (0.37%) |
| MT65 | Sampling of Bench Trim for further use in ANY ra | 9,743 | 4 | 9,739 | 0 | 0.0004 (0.04%) |
| MT53 | Follow-up Sampling of Beef Mfg Trim or Other Raw | 5,766 | 70 | 5,696 | 0 | 0.0121 (1.21%) |
| MT65_C | Sampling of Bench Trim for further use in ANY ra | 5,484 | 16 | 5,468 | 0 | 0.0029 (0.29%) |
| MT55 | Sampling of Bench Trim for further use in ANY ra | 2,628 | 1 | 2,627 | 0 | 0.0004 (0.04%) |
| MT53_C | Follow-up Sampling of Beef Mfg Trim or Other Raw | 1,735 | 17 | 1,718 | 0 | 0.0098 (0.98%) |
| MT44 | Follow-up Risk-based Sampling of Positive Raw Gr | 1,133 | 4 | 1,129 | 0 | 0.0035 (0.35%) |
| MT54 | E.coli O157:H7 Sampling of Raw Ground Beef Compo | 997 | 2 | 995 | 0 | 0.0020 (0.20%) |
| MT52 | Follow-up Sampling of Suppliers of Raw Ground Be | 764 | 13 | 751 | 0 | 0.0170 (1.70%) |
| MT44T | Follow-up E.coli Sampling of Raw Ground Beef, Tr | 571 | 8 | 563 | 0 | 0.0140 (1.40%) |
| MT52_C | Follow-up Sampling of Suppliers of Raw Ground Be | 446 | 12 | 434 | 0 | 0.0269 (2.69%) |
| MT44T_C | Follow-up E.coli Sampling of Raw Ground Beef, Tr | 65 | 0 | 65 | 0 | 0.0000 (0.00%) |

### Duplicate findings (reported, not dropped)

- Exact duplicate rows: 0
- Duplicate sample numbers: 0
- Likely-duplicate records on `establishment_id+collection_date+sample_source_name+stec_analysis`: 6,550

### Schema changes across fiscal years

- (baseline) -> FY2014: added=['aerobic_plate_count_mpn_g', 'aerobic_plate_count_mpn_ml', 'collection_date', 'establishment_id', 'establishment_name', 'establishment_number', 'establishment_state', 'form_id', 'not_analyzed', 'not_analyzed_explain', 'pcr_eae_analysis', 'pcr_stx_1_2_analysis', 'project_code', 'project_name', 'salmonella_mpn_qualitative', 'salmonella_sp_analysis', 'salmonella_sp_analysis_canceled', 'salmonellae_mpn_combination', 'salmonellae_mpn_combination_canceled', 'salmonellae_mpn_g', 'salmonellae_mpn_g_canceled', 'sample_number', 'sample_source_name', 'stec_analysis', 'stec_analysis_canceled', 'stec_o157_h7_mpn', 'stec_o157_h7_mpn_canceled', 'stec_o157_h7_mpn_combination', 'stec_o157_h7_mpn_combination_canceled'] removed=[] dtype_changes=[]

### Leakage checks

- `collection_date_present`: PASS — 232363/232363 rows have a parseable collection_date (1.000); 0 present-but-unparsable.
- `no_future_collection_dates`: PASS — 0 rows have a collection_date after today (2026-10-28).

### Recorded gaps (uncomputable fields — never fabricated)

- `publication_date`: FSIS laboratory-sampling files contain no publication/public-availability date column; reporting delay cannot be computed from the data (not fabricated).
- `reporting_delay_days`: depends on unavailable publication_date


## 'Other' result-bucket reconciliation (Task 2.9, Req 1.3)

The tri-state audit places records that are neither a positive nor a negative detection into an `other` bucket. The 2,146 such records (Salmonella 200 + Listeria 1,930 + STEC 16) are enumerated below into their real categories. Every category is a non-result (lab problem, insufficient sample, blank/NULL) or — in the Lm panel — a Salmonella-only program that tests a different analyte; **all are excluded from modeling labels** because none is a valid detection of the pathogen target. Per-pathogen category counts sum back to the audit `other_count` exactly.

### Salmonella — `raw_poultry_salmonella`

- Audit `other_count`: **200**; reconciled total: **200**; reconciles: **YES**

| Category | Count | Disposition |
|---|---:|---|
| `blank_or_null` | 191 | excluded_from_labels: blank/NULL result — no result recorded, so the sample yields no label |
| `lab_closed` | 7 | excluded_from_labels: lab problem / insufficient sample is not a valid test result (neither a positive nor a negative detection) |
| `lab_problem` | 1 | excluded_from_labels: lab problem / insufficient sample is not a valid test result (neither a positive nor a negative detection) |
| `insufficient_sample` | 1 | excluded_from_labels: lab problem / insufficient sample is not a valid test result (neither a positive nor a negative detection) |

### Listeria — `rte_listeria`

- Audit `other_count`: **1,930**; reconciled total: **1,930**; reconciles: **YES**

| Category | Count | Disposition |
|---|---:|---|
| `salmonella_only_program` | 1,689 | excluded_from_lm_labels: INT*_SA_* are Salmonella for-cause programs that run in the RTE/Listeria file but test a DIFFERENT analyte (Salmonella, not Lm); their lm_listeria_analysis is blank so they test nothing on the Lm target |
| `blank_or_null` | 241 | excluded_from_labels: blank/NULL result — no result recorded, so the sample yields no label |

### STEC — `raw_beef_stec`

- Audit `other_count`: **16**; reconciled total: **16**; reconciles: **YES**

| Category | Count | Disposition |
|---|---:|---|
| `blank_or_null` | 16 | excluded_from_labels: blank/NULL result — no result recorded, so the sample yields no label |

**Grand total reconciled:** 2,146 (all pathogens reconcile: YES).


## 'Other' result-bucket reconciliation (Task 2.9, Req 1.3)

The tri-state audit places records that are neither a positive nor a negative detection into an `other` bucket. The 2,146 such records (Salmonella 200 + Listeria 1,930 + STEC 16) are enumerated below into their real categories. Every category is a non-result (lab problem, insufficient sample, blank/NULL) or — in the Lm panel — a Salmonella-only program that tests a different analyte; **all are excluded from modeling labels** because none is a valid detection of the pathogen target. Per-pathogen category counts sum back to the audit `other_count` exactly.

### Salmonella — `raw_poultry_salmonella`

- Audit `other_count`: **200**; reconciled total: **200**; reconciles: **YES**

| Category | Count | Disposition |
|---|---:|---|
| `blank_or_null` | 191 | excluded_from_labels: blank/NULL result — no result recorded, so the sample yields no label |
| `lab_closed` | 7 | excluded_from_labels: lab problem / insufficient sample is not a valid test result (neither a positive nor a negative detection) |
| `lab_problem` | 1 | excluded_from_labels: lab problem / insufficient sample is not a valid test result (neither a positive nor a negative detection) |
| `insufficient_sample` | 1 | excluded_from_labels: lab problem / insufficient sample is not a valid test result (neither a positive nor a negative detection) |

### Listeria — `rte_listeria`

- Audit `other_count`: **1,930**; reconciled total: **1,930**; reconciles: **YES**

| Category | Count | Disposition |
|---|---:|---|
| `salmonella_only_program` | 1,689 | excluded_from_lm_labels: INT*_SA_* are Salmonella for-cause programs that run in the RTE/Listeria file but test a DIFFERENT analyte (Salmonella, not Lm); their lm_listeria_analysis is blank so they test nothing on the Lm target |
| `blank_or_null` | 241 | excluded_from_labels: blank/NULL result — no result recorded, so the sample yields no label |

### STEC — `raw_beef_stec`

- Audit `other_count`: **16**; reconciled total: **16**; reconciles: **YES**

| Category | Count | Disposition |
|---|---:|---|
| `blank_or_null` | 16 | excluded_from_labels: blank/NULL result — no result recorded, so the sample yields no label |

**Grand total reconciled:** 2,146 (all pathogens reconcile: YES).


## 'Other' result-bucket reconciliation (Task 2.9, Req 1.3)

The tri-state audit places records that are neither a positive nor a negative detection into an `other` bucket. The 2,146 such records (Salmonella 200 + Listeria 1,930 + STEC 16) are enumerated below into their real categories. Every category is a non-result (lab problem, insufficient sample, blank/NULL) or — in the Lm panel — a Salmonella-only program that tests a different analyte; **all are excluded from modeling labels** because none is a valid detection of the pathogen target. Per-pathogen category counts sum back to the audit `other_count` exactly.

### Salmonella — `raw_poultry_salmonella`

- Audit `other_count`: **200**; reconciled total: **200**; reconciles: **YES**

| Category | Count | Disposition |
|---|---:|---|
| `blank_or_null` | 191 | excluded_from_labels: blank/NULL result — no result recorded, so the sample yields no label |
| `lab_closed` | 7 | excluded_from_labels: lab problem / insufficient sample is not a valid test result (neither a positive nor a negative detection) |
| `lab_problem` | 1 | excluded_from_labels: lab problem / insufficient sample is not a valid test result (neither a positive nor a negative detection) |
| `insufficient_sample` | 1 | excluded_from_labels: lab problem / insufficient sample is not a valid test result (neither a positive nor a negative detection) |

### Listeria — `rte_listeria`

- Audit `other_count`: **1,930**; reconciled total: **1,930**; reconciles: **YES**

| Category | Count | Disposition |
|---|---:|---|
| `salmonella_only_program` | 1,689 | excluded_from_lm_labels: INT*_SA_* are Salmonella for-cause programs that run in the RTE/Listeria file but test a DIFFERENT analyte (Salmonella, not Lm); their lm_listeria_analysis is blank so they test nothing on the Lm target |
| `blank_or_null` | 241 | excluded_from_labels: blank/NULL result — no result recorded, so the sample yields no label |

### STEC — `raw_beef_stec`

- Audit `other_count`: **16**; reconciled total: **16**; reconciles: **YES**

| Category | Count | Disposition |
|---|---:|---|
| `blank_or_null` | 16 | excluded_from_labels: blank/NULL result — no result recorded, so the sample yields no label |

**Grand total reconciled:** 2,146 (all pathogens reconcile: YES).


## 'Other' result-bucket reconciliation (Task 2.9, Req 1.3)

The tri-state audit places records that are neither a positive nor a negative detection into an `other` bucket. The 2,146 such records (Salmonella 200 + Listeria 1,930 + STEC 16) are enumerated below into their real categories. Every category is a non-result (lab problem, insufficient sample, blank/NULL) or — in the Lm panel — a Salmonella-only program that tests a different analyte; **all are excluded from modeling labels** because none is a valid detection of the pathogen target. Per-pathogen category counts sum back to the audit `other_count` exactly.

### Salmonella — `raw_poultry_salmonella`

- Audit `other_count`: **200**; reconciled total: **200**; reconciles: **YES**

| Category | Count | Disposition |
|---|---:|---|
| `blank_or_null` | 191 | excluded_from_labels: blank/NULL result — no result recorded, so the sample yields no label |
| `lab_closed` | 7 | excluded_from_labels: lab problem / insufficient sample is not a valid test result (neither a positive nor a negative detection) |
| `lab_problem` | 1 | excluded_from_labels: lab problem / insufficient sample is not a valid test result (neither a positive nor a negative detection) |
| `insufficient_sample` | 1 | excluded_from_labels: lab problem / insufficient sample is not a valid test result (neither a positive nor a negative detection) |

### Listeria — `rte_listeria`

- Audit `other_count`: **1,930**; reconciled total: **1,930**; reconciles: **YES**

| Category | Count | Disposition |
|---|---:|---|
| `salmonella_only_program` | 1,689 | excluded_from_lm_labels: INT*_SA_* are Salmonella for-cause programs that run in the RTE/Listeria file but test a DIFFERENT analyte (Salmonella, not Lm); their lm_listeria_analysis is blank so they test nothing on the Lm target |
| `blank_or_null` | 241 | excluded_from_labels: blank/NULL result — no result recorded, so the sample yields no label |

### STEC — `raw_beef_stec`

- Audit `other_count`: **16**; reconciled total: **16**; reconciles: **YES**

| Category | Count | Disposition |
|---|---:|---|
| `blank_or_null` | 16 | excluded_from_labels: blank/NULL result — no result recorded, so the sample yields no label |

**Grand total reconciled:** 2,146 (all pathogens reconcile: YES).


## 'Other' result-bucket reconciliation (Task 2.9, Req 1.3)

The tri-state audit places records that are neither a positive nor a negative detection into an `other` bucket. The 2,146 such records (Salmonella 200 + Listeria 1,930 + STEC 16) are enumerated below into their real categories. Every category is a non-result (lab problem, insufficient sample, blank/NULL) or — in the Lm panel — a Salmonella-only program that tests a different analyte; **all are excluded from modeling labels** because none is a valid detection of the pathogen target. Per-pathogen category counts sum back to the audit `other_count` exactly.

### Salmonella — `raw_poultry_salmonella`

- Audit `other_count`: **200**; reconciled total: **200**; reconciles: **YES**

| Category | Count | Disposition |
|---|---:|---|
| `blank_or_null` | 191 | excluded_from_labels: blank/NULL result — no result recorded, so the sample yields no label |
| `lab_closed` | 7 | excluded_from_labels: lab problem / insufficient sample is not a valid test result (neither a positive nor a negative detection) |
| `lab_problem` | 1 | excluded_from_labels: lab problem / insufficient sample is not a valid test result (neither a positive nor a negative detection) |
| `insufficient_sample` | 1 | excluded_from_labels: lab problem / insufficient sample is not a valid test result (neither a positive nor a negative detection) |

### Listeria — `rte_listeria`

- Audit `other_count`: **1,930**; reconciled total: **1,930**; reconciles: **YES**

| Category | Count | Disposition |
|---|---:|---|
| `salmonella_only_program` | 1,689 | excluded_from_lm_labels: INT*_SA_* are Salmonella for-cause programs that run in the RTE/Listeria file but test a DIFFERENT analyte (Salmonella, not Lm); their lm_listeria_analysis is blank so they test nothing on the Lm target |
| `blank_or_null` | 241 | excluded_from_labels: blank/NULL result — no result recorded, so the sample yields no label |

### STEC — `raw_beef_stec`

- Audit `other_count`: **16**; reconciled total: **16**; reconciles: **YES**

| Category | Count | Disposition |
|---|---:|---|
| `blank_or_null` | 16 | excluded_from_labels: blank/NULL result — no result recorded, so the sample yields no label |

**Grand total reconciled:** 2,146 (all pathogens reconcile: YES).


## 'Other' result-bucket reconciliation (Task 2.9, Req 1.3)

The tri-state audit places records that are neither a positive nor a negative detection into an `other` bucket. The 2,146 such records (Salmonella 200 + Listeria 1,930 + STEC 16) are enumerated below into their real categories. Every category is a non-result (lab problem, insufficient sample, blank/NULL) or — in the Lm panel — a Salmonella-only program that tests a different analyte; **all are excluded from modeling labels** because none is a valid detection of the pathogen target. Per-pathogen category counts sum back to the audit `other_count` exactly.

### Salmonella — `raw_poultry_salmonella`

- Audit `other_count`: **200**; reconciled total: **200**; reconciles: **YES**

| Category | Count | Disposition |
|---|---:|---|
| `blank_or_null` | 191 | excluded_from_labels: blank/NULL result — no result recorded, so the sample yields no label |
| `lab_closed` | 7 | excluded_from_labels: lab problem / insufficient sample is not a valid test result (neither a positive nor a negative detection) |
| `lab_problem` | 1 | excluded_from_labels: lab problem / insufficient sample is not a valid test result (neither a positive nor a negative detection) |
| `insufficient_sample` | 1 | excluded_from_labels: lab problem / insufficient sample is not a valid test result (neither a positive nor a negative detection) |

### Listeria — `rte_listeria`

- Audit `other_count`: **1,930**; reconciled total: **1,930**; reconciles: **YES**

| Category | Count | Disposition |
|---|---:|---|
| `salmonella_only_program` | 1,689 | excluded_from_lm_labels: INT*_SA_* are Salmonella for-cause programs that run in the RTE/Listeria file but test a DIFFERENT analyte (Salmonella, not Lm); their lm_listeria_analysis is blank so they test nothing on the Lm target |
| `blank_or_null` | 241 | excluded_from_labels: blank/NULL result — no result recorded, so the sample yields no label |

### STEC — `raw_beef_stec`

- Audit `other_count`: **16**; reconciled total: **16**; reconciles: **YES**

| Category | Count | Disposition |
|---|---:|---|
| `blank_or_null` | 16 | excluded_from_labels: blank/NULL result — no result recorded, so the sample yields no label |

**Grand total reconciled:** 2,146 (all pathogens reconcile: YES).


## 'Other' result-bucket reconciliation (Task 2.9, Req 1.3)

The tri-state audit places records that are neither a positive nor a negative detection into an `other` bucket. The 2,146 such records (Salmonella 200 + Listeria 1,930 + STEC 16) are enumerated below into their real categories. Every category is a non-result (lab problem, insufficient sample, blank/NULL) or — in the Lm panel — a Salmonella-only program that tests a different analyte; **all are excluded from modeling labels** because none is a valid detection of the pathogen target. Per-pathogen category counts sum back to the audit `other_count` exactly.

### Salmonella — `raw_poultry_salmonella`

- Audit `other_count`: **200**; reconciled total: **200**; reconciles: **YES**

| Category | Count | Disposition |
|---|---:|---|
| `blank_or_null` | 191 | excluded_from_labels: blank/NULL result — no result recorded, so the sample yields no label |
| `lab_closed` | 7 | excluded_from_labels: lab problem / insufficient sample is not a valid test result (neither a positive nor a negative detection) |
| `lab_problem` | 1 | excluded_from_labels: lab problem / insufficient sample is not a valid test result (neither a positive nor a negative detection) |
| `insufficient_sample` | 1 | excluded_from_labels: lab problem / insufficient sample is not a valid test result (neither a positive nor a negative detection) |

### Listeria — `rte_listeria`

- Audit `other_count`: **1,930**; reconciled total: **1,930**; reconciles: **YES**

| Category | Count | Disposition |
|---|---:|---|
| `salmonella_only_program` | 1,689 | excluded_from_lm_labels: INT*_SA_* are Salmonella for-cause programs that run in the RTE/Listeria file but test a DIFFERENT analyte (Salmonella, not Lm); their lm_listeria_analysis is blank so they test nothing on the Lm target |
| `blank_or_null` | 241 | excluded_from_labels: blank/NULL result — no result recorded, so the sample yields no label |

### STEC — `raw_beef_stec`

- Audit `other_count`: **16**; reconciled total: **16**; reconciles: **YES**

| Category | Count | Disposition |
|---|---:|---|
| `blank_or_null` | 16 | excluded_from_labels: blank/NULL result — no result recorded, so the sample yields no label |

**Grand total reconciled:** 2,146 (all pathogens reconcile: YES).


## 'Other' result-bucket reconciliation (Task 2.9, Req 1.3)

The tri-state audit places records that are neither a positive nor a negative detection into an `other` bucket. The 2,146 such records (Salmonella 200 + Listeria 1,930 + STEC 16) are enumerated below into their real categories. Every category is a non-result (lab problem, insufficient sample, blank/NULL) or — in the Lm panel — a Salmonella-only program that tests a different analyte; **all are excluded from modeling labels** because none is a valid detection of the pathogen target. Per-pathogen category counts sum back to the audit `other_count` exactly.

### Salmonella — `raw_poultry_salmonella`

- Audit `other_count`: **200**; reconciled total: **200**; reconciles: **YES**

| Category | Count | Disposition |
|---|---:|---|
| `blank_or_null` | 191 | excluded_from_labels: blank/NULL result — no result recorded, so the sample yields no label |
| `lab_closed` | 7 | excluded_from_labels: lab problem / insufficient sample is not a valid test result (neither a positive nor a negative detection) |
| `lab_problem` | 1 | excluded_from_labels: lab problem / insufficient sample is not a valid test result (neither a positive nor a negative detection) |
| `insufficient_sample` | 1 | excluded_from_labels: lab problem / insufficient sample is not a valid test result (neither a positive nor a negative detection) |

### Listeria — `rte_listeria`

- Audit `other_count`: **1,930**; reconciled total: **1,930**; reconciles: **YES**

| Category | Count | Disposition |
|---|---:|---|
| `salmonella_only_program` | 1,689 | excluded_from_lm_labels: INT*_SA_* are Salmonella for-cause programs that run in the RTE/Listeria file but test a DIFFERENT analyte (Salmonella, not Lm); their lm_listeria_analysis is blank so they test nothing on the Lm target |
| `blank_or_null` | 241 | excluded_from_labels: blank/NULL result — no result recorded, so the sample yields no label |

### STEC — `raw_beef_stec`

- Audit `other_count`: **16**; reconciled total: **16**; reconciles: **YES**

| Category | Count | Disposition |
|---|---:|---|
| `blank_or_null` | 16 | excluded_from_labels: blank/NULL result — no result recorded, so the sample yields no label |

**Grand total reconciled:** 2,146 (all pathogens reconcile: YES).


## 'Other' result-bucket reconciliation (Task 2.9, Req 1.3)

The tri-state audit places records that are neither a positive nor a negative detection into an `other` bucket. The 2,146 such records (Salmonella 200 + Listeria 1,930 + STEC 16) are enumerated below into their real categories. Every category is a non-result (lab problem, insufficient sample, blank/NULL) or — in the Lm panel — a Salmonella-only program that tests a different analyte; **all are excluded from modeling labels** because none is a valid detection of the pathogen target. Per-pathogen category counts sum back to the audit `other_count` exactly.

### Salmonella — `raw_poultry_salmonella`

- Audit `other_count`: **200**; reconciled total: **200**; reconciles: **YES**

| Category | Count | Disposition |
|---|---:|---|
| `blank_or_null` | 191 | excluded_from_labels: blank/NULL result — no result recorded, so the sample yields no label |
| `lab_closed` | 7 | excluded_from_labels: lab problem / insufficient sample is not a valid test result (neither a positive nor a negative detection) |
| `lab_problem` | 1 | excluded_from_labels: lab problem / insufficient sample is not a valid test result (neither a positive nor a negative detection) |
| `insufficient_sample` | 1 | excluded_from_labels: lab problem / insufficient sample is not a valid test result (neither a positive nor a negative detection) |

### Listeria — `rte_listeria`

- Audit `other_count`: **1,930**; reconciled total: **1,930**; reconciles: **YES**

| Category | Count | Disposition |
|---|---:|---|
| `salmonella_only_program` | 1,689 | excluded_from_lm_labels: INT*_SA_* are Salmonella for-cause programs that run in the RTE/Listeria file but test a DIFFERENT analyte (Salmonella, not Lm); their lm_listeria_analysis is blank so they test nothing on the Lm target |
| `blank_or_null` | 241 | excluded_from_labels: blank/NULL result — no result recorded, so the sample yields no label |

### STEC — `raw_beef_stec`

- Audit `other_count`: **16**; reconciled total: **16**; reconciles: **YES**

| Category | Count | Disposition |
|---|---:|---|
| `blank_or_null` | 16 | excluded_from_labels: blank/NULL result — no result recorded, so the sample yields no label |

**Grand total reconciled:** 2,146 (all pathogens reconcile: YES).

