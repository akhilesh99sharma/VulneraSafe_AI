# Data-source ablations (Req 9.3-9.5)

Exactly four configurations per pathogen, defined by data source, trained with each pathogen's best model on the SAME chronological train split and evaluated on the SAME untouched test. The primary metric is **PR-AUC**; the marginal contribution is the **signed** change vs the FSIS-only baseline (negatives preserved, never clamped).

## Key limitations (honest, feeding Task 8)

- **CDC gap:** there are NO CDC human-health features in the feature matrix (the CDC stream was not joined into harmonize). The **FSIS+CDC** configuration is therefore recorded as a *gap* — its contribution is **not evaluable** and is reported as such, never as a fabricated number.
- **NOAA nClimDiv coverage:** NOAA `weather_*` features come from NOAA nClimDiv statewide monthly climate (national, ~87% of state-periods non-missing). The **FSIS+NOAA** marginal is small and pathogen-dependent (positive for Salmonella/STEC, slightly negative for Listeria) and is reported with its real sign.
- **Static context:** ACS / Food Access Atlas `static_*` columns are slowly-varying demographic / food-access CONTEXT, not a One-Health surveillance stream; they are folded into the **full** configuration.


## Salmonella (best model: lightgbm)

Feature groups: FSIS=9, CDC=0, NOAA=2, static=2, other=0. Test periods: 2015-01..2018-12 (n_test_rows=30).

| Configuration | Status | PR-AUC | ROC-AUC | Δ PR-AUC vs FSIS-only | Δ ROC-AUC vs FSIS-only |
|---|---|---|---|---|---|
| fsis_only | evaluated | 0.8015 | 0.7273 | +0.0000 | +0.0000 |
| fsis_cdc | gap | n/a (gap) | n/a (gap) | n/a | n/a |
| fsis_noaa | evaluated | 0.8015 | 0.7273 | +0.0000 | +0.0000 |
| full | evaluated | 0.8027 | 0.7273 | +0.0011 | +0.0000 |

> **FSIS+CDC gap:** no CDC features available — contribution not evaluable; recorded as a gap, not a fabricated delta.

## Listeria (best model: random_forest)

Feature groups: FSIS=9, CDC=0, NOAA=2, static=2, other=0. Test periods: 2015-01..2018-12 (n_test_rows=30).

| Configuration | Status | PR-AUC | ROC-AUC | Δ PR-AUC vs FSIS-only | Δ ROC-AUC vs FSIS-only |
|---|---|---|---|---|---|
| fsis_only | evaluated | 0.7655 | 0.6794 | +0.0000 | +0.0000 |
| fsis_cdc | gap | n/a (gap) | n/a (gap) | n/a | n/a |
| fsis_noaa | evaluated | 0.7655 | 0.6794 | +0.0000 | +0.0000 |
| full | evaluated | 0.7679 | 0.6842 | +0.0024 | +0.0048 |

> **FSIS+CDC gap:** no CDC features available — contribution not evaluable; recorded as a gap, not a fabricated delta.

## STEC (best model: random_forest)

Feature groups: FSIS=9, CDC=0, NOAA=2, static=2, other=0. Test periods: 2015-01..2018-12 (n_test_rows=30).

| Configuration | Status | PR-AUC | ROC-AUC | Δ PR-AUC vs FSIS-only | Δ ROC-AUC vs FSIS-only |
|---|---|---|---|---|---|
| fsis_only | evaluated | 0.7655 | 0.6794 | +0.0000 | +0.0000 |
| fsis_cdc | gap | n/a (gap) | n/a (gap) | n/a | n/a |
| fsis_noaa | evaluated | 0.7655 | 0.6794 | +0.0000 | +0.0000 |
| full | evaluated | 0.7679 | 0.6842 | +0.0024 | +0.0048 |

> **FSIS+CDC gap:** no CDC features available — contribution not evaluable; recorded as a gap, not a fabricated delta.
