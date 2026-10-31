# Establishment-Level Temporal Feasibility Gate

Establishment-level temporal feasibility: measured counts of establishments/quarters with sufficient trailing history AND an evaluable next-quarter outcome. Forecasting proceeds only where enough TRAINABLE rows exist. Nothing fabricated.

Parameters: cutoffs 2015-Q1..2026-Q1, trailing windows [90, 180, 365, 730] days, evaluable future >= 10 samples, sufficient history >= 10 samples, reporting lag 30 days.

## Per-pathogen verdict

| Pathogen | Establishments | Median pos/est | Trainable est-quarters | Evaluable futures | Consecutive-year est | Verdict |
|---|---:|---:|---:|---:|---:|---|
| Salmonella | 1389 | 4.0 | 9765 | 10235 | 1196 | **forecastable** |
| Listeria | 3752 | 0.0 | 0 | 0 | 3415 | **descriptive_only** |
| STEC | 2481 | 0.0 | 3347 | 3462 | 2252 | **descriptive_only** |

### Salmonella

1389 establishments, median positives/est=4.0, 9765 trainable establishment-quarter rows (history>=10 samples AND next-quarter>=10 samples), 10235 establishment-quarters with an evaluable future outcome. Enough trainable rows and non-zero typical positives -> establishment-level FORECASTS are feasible.

Trailing-history establishments by cutoff (>= sufficient-history samples):

| Cutoff | 90d | 180d | 365d | 730d |
|---|---:|---:|---:|---:|
| 2015-Q1 | 0 | 0 | 0 | 0 |
| 2016-Q1 | 146 | 226 | 261 | 261 |
| 2017-Q1 | 161 | 255 | 366 | 444 |
| 2018-Q1 | 175 | 265 | 373 | 491 |
| 2019-Q1 | 166 | 282 | 418 | 549 |
| 2020-Q1 | 188 | 287 | 499 | 628 |
| 2021-Q1 | 208 | 358 | 502 | 569 |
| 2022-Q1 | 204 | 368 | 528 | 563 |
| 2023-Q1 | 202 | 374 | 535 | 573 |
| 2024-Q1 | 185 | 390 | 536 | 586 |
| 2025-Q1 | 160 | 350 | 551 | 597 |
| 2026-Q1 | 184 | 386 | 522 | 585 |

### Listeria

3752 establishments, median positives/est=0.0, 0 trainable establishment-quarter rows (history>=10 samples AND next-quarter>=10 samples), 0 establishment-quarters with an evaluable future outcome. Too few trainable rows / median 0 positives per establishment -> establishment-level forecasts NOT feasible; descriptive / ranking only.

Trailing-history establishments by cutoff (>= sufficient-history samples):

| Cutoff | 90d | 180d | 365d | 730d |
|---|---:|---:|---:|---:|
| 2015-Q1 | 0 | 0 | 172 | 365 |
| 2016-Q1 | 0 | 0 | 182 | 1487 |
| 2017-Q1 | 0 | 0 | 173 | 1553 |
| 2018-Q1 | 0 | 0 | 463 | 1473 |
| 2019-Q1 | 0 | 0 | 555 | 1361 |
| 2020-Q1 | 0 | 0 | 524 | 1335 |
| 2021-Q1 | 0 | 0 | 488 | 1326 |
| 2022-Q1 | 0 | 0 | 539 | 1320 |
| 2023-Q1 | 0 | 0 | 566 | 1342 |
| 2024-Q1 | 0 | 0 | 527 | 1324 |
| 2025-Q1 | 0 | 0 | 348 | 1097 |
| 2026-Q1 | 0 | 0 | 235 | 960 |

### STEC

2481 establishments, median positives/est=0.0, 3347 trainable establishment-quarter rows (history>=10 samples AND next-quarter>=10 samples), 3462 establishment-quarters with an evaluable future outcome. Too few trainable rows / median 0 positives per establishment -> establishment-level forecasts NOT feasible; descriptive / ranking only.

Trailing-history establishments by cutoff (>= sufficient-history samples):

| Cutoff | 90d | 180d | 365d | 730d |
|---|---:|---:|---:|---:|
| 2015-Q1 | 27 | 191 | 381 | 472 |
| 2016-Q1 | 25 | 210 | 409 | 876 |
| 2017-Q1 | 28 | 232 | 456 | 908 |
| 2018-Q1 | 27 | 141 | 555 | 1025 |
| 2019-Q1 | 29 | 141 | 550 | 1082 |
| 2020-Q1 | 31 | 154 | 575 | 1078 |
| 2021-Q1 | 32 | 147 | 507 | 1055 |
| 2022-Q1 | 32 | 143 | 522 | 1060 |
| 2023-Q1 | 33 | 136 | 467 | 1093 |
| 2024-Q1 | 39 | 156 | 481 | 1047 |
| 2025-Q1 | 32 | 158 | 495 | 1003 |
| 2026-Q1 | 32 | 144 | 494 | 1135 |
