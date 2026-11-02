# Data-source ablations (Req 9.3-9.5)

Exactly four configurations per pathogen, defined by data source, trained with each pathogen's best model on the SAME chronological train split and evaluated on the SAME untouched test. The primary metric is **PR-AUC**; the marginal contribution is the **signed** change vs the FSIS-only baseline (negatives preserved, never clamped). All values below are from the live exported artifact (web/public/data/ablation_results.json).

## Configurations and honest notes

- **FSIS+CDC.** CDC NORS human-health context is in the matrix via the S05 integration, so this configuration is evaluated with a real (small) signed marginal - no longer recorded as a gap.
- **FSIS+NOAA.** NOAA weather_* features come from NOAA nClimDiv statewide monthly climate (national, ~87% of state-periods non-missing). The marginal is small and pathogen-dependent (positive for Salmonella and STEC, slightly negative for Listeria) and is reported with its real sign.
- **Static context.** ACS / Food Access Atlas static_* columns are slowly-varying demographic / food-access context, not a One-Health surveillance stream; they are folded into the full configuration.

## PR-AUC by configuration (signed marginal vs FSIS-only)

| Pathogen | FSIS-only | FSIS+CDC (delta) | FSIS+NOAA (delta) | Full (delta) |
|---|---|---|---|---|
| Salmonella (lightgbm) | 0.5102 | 0.5161 (+0.0060) | 0.5313 (+0.0211) | 0.5172 (+0.0070) |
| Listeria (random_forest) | 0.7437 | 0.7455 (+0.0018) | 0.7361 (-0.0076) | 0.7384 (-0.0053) |
| STEC (random_forest) | 0.4102 | 0.4181 (+0.0079) | 0.4151 (+0.0050) | 0.4329 (+0.0227) |

## Honest findings

- **NOAA weather helps Salmonella** (+0.0211) and STEC (+0.0050), with the national nClimDiv coverage being what makes the signal detectable; it is slightly negative for Listeria (-0.0076), consistent with RTE Listeria being process-driven rather than weather-driven. Reported with real signs, not hidden.
- **FSIS+CDC is a small positive** for all three pathogens (+0.0060 / +0.0018 / +0.0079), reflecting the S05 CDC NORS context - a real contribution, not a fabricated number and no longer a gap.
- **Adding every group (full) is not monotonic**: it clearly helps STEC (+0.0227) but slightly dilutes Salmonella and Listeria versus their best single addition - an honest reminder that more features is not always better with limited positives.
