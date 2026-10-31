# VulneraSafe AI - Data Provenance

Per-source origin, retrieval method, vintage, license, and known limitations.
All data is real and either manually supplied by the project owner or retrieved from
public providers. No records are fabricated. Synthetic data, where used downstream, is
isolated under `data/synthetic/` and labeled SIMULATED.

| Source | Origin (URL) | Retrieval | Access date (ISO 8601) | Vintage / coverage | License / terms | Update frequency | Limitations |
|---|---|---|---|---|---|---|---|
| FSIS Raw Poultry (Salmonella) | USDA FSIS establishment-specific laboratory sampling, raw poultry product — https://www.fsis.usda.gov/science-data/data-sets-visualizations/laboratory-sampling-data | Zipped JSON per fiscal year (loaded locally; FSIS host returns HTTP 403 here) | 2026-10-28 | FY2014, FY2019, FY2023, FY2026; US state + establishment | US Government public domain (USDA FSIS) | Updated by FSIS on a rolling/periodic basis (not specified by source) | Binary result + MPN/CFU only; no serotype/WGS |
| FSIS RTE (Listeria) | USDA FSIS establishment-specific laboratory sampling, ready-to-eat product — https://www.fsis.usda.gov/science-data/data-sets-visualizations/laboratory-sampling-data | Zipped JSON per fiscal year (loaded locally; FSIS host returns HTTP 403 here) | 2026-10-28 | FY2014, FY2019, FY2023, FY2026; US state + establishment | US Government public domain (USDA FSIS) | Updated by FSIS on a rolling/periodic basis (not specified by source) | Very low positivity (0.61%); no serotype |
| FSIS Raw Beef (STEC) | USDA FSIS establishment-specific laboratory sampling, raw beef product — https://www.fsis.usda.gov/science-data/data-sets-visualizations/laboratory-sampling-data | Zipped JSON per fiscal year (loaded locally; FSIS host returns HTTP 403 here) | 2026-10-28 | FY2014, FY2019, FY2023, FY2026; US state + establishment | US Government public domain (USDA FSIS) | Updated by FSIS on a rolling/periodic basis (not specified by source) | Lowest positivity (0.29%); PCR virulence genes but no serotype |
| FSIS Recalls / PHAs | FSIS Recall & Public Health Alert API — https://www.fsis.usda.gov/fsis/api/recall/v/1 | Attempted; blocked | 2026-10-28 (access attempt) | n/a (not ingested); United States | US Government public domain (USDA FSIS) | Updated as recalls/alerts are issued (event-driven) | HTTP 403 firewall in this environment; not ingested — documented GAP, regulatory-evidence track pending |
| CDC NORS | CDC National Outbreak Reporting System, data.cdc.gov dataset `5xkq-dg7x` — https://data.cdc.gov/resource/5xkq-dg7x | Socrata API / dataset export; aggregated to (state, period) | 2026-10-28 | 2014-01 to 2023-12; 52 states/territories; 6,902 outbreaks | US Government public domain (CDC) | Updated as outbreaks are finalised (long reporting delay, often >1 year) | LAGGED CORROBORATION, not a model predictor. Outbreak dates (not report dates); joined with a +365-day availability lag so cutoff-t views use only plausibly-available outbreaks. PulseNet-organizer substitute (justification per Req 2.2). |
| NOAA nClimDiv climate | NOAA NCEI nClimDiv statewide monthly climate division data — https://www.ncei.noaa.gov/access/monitoring/nclimdiv/ | API / bulk nClimDiv statewide monthly series | 2026-10-28 | 1895-01 to 2026-12; 49 states (statewide monthly) | US Government public domain (NOAA NCEI) | Published monthly, in the first week of the following month (+7d availability) | REAL national state-level coverage. Hawaii has no nClimDiv statewide series → left MISSING (documented gap, never fabricated). Anomalies are within-sample vs each state's long-run mean. |
| Census ACS 5-year | US Census Bureau American Community Survey 5-year — https://api.census.gov/data/2022/acs/acs5 | Live Census API with CENSUS_API_KEY | 2026-10-28 | 2022 vintage; US county aggregated to state | US Government public domain (US Census Bureau) | Released annually (new 5-year vintage each year) | County-level aggregated to state; survey estimates carry margins of error, small areas noisier |
| USDA Food Access Research Atlas (FARA) | USDA Economic Research Service (ERS), LRAM/FARA 2019 — https://www.ers.usda.gov/media/5626/2019-large-retailer-access-map-lram-formerly-known-as-the-food-access-research-atlas-fara-data.xlsx | Downloaded xlsx (lram_2019_xlsx.xlsx, 85,803,176 bytes) | 2026-10-28 | 2015/2019 Atlas vintage; US census tracts aggregated to state | US Government public domain (USDA ERS) | Released irregularly per Atlas update cycle (prior vintages 2015, 2019; not specified by source) | Tract-level aggregated to state; access thresholds are policy choices, not ground truth |

## Decision value (how each source informs the Food Safety Operations Director)

One line per source, stating how it supports the Director's resource-allocation and intervention decisions:

- **FSIS Raw Poultry (Salmonella)** — Supplies the routine-sampling positivity signal that the model forecasts, telling the Director where poultry-Salmonella risk is rising so inspection effort can be directed ahead of time.
- **FSIS RTE (Listeria)** — Supplies the ready-to-eat Listeria positivity signal, flagging high-consequence RTE establishments for the Director's vulnerable-population-weighted attention queue.
- **FSIS Raw Beef (STEC)** — Supplies the raw-beef STEC positivity signal, letting the Director prioritise beef sampling where STEC detection is trending upward.
- **FSIS Recalls / PHAs** — (Pending ingestion) Would provide the independent regulatory-evidence track of verified official actions, confirming or escalating model alerts for the Director without being suppressed by model uncertainty.
- **CDC NORS** — Lagged human-health corroboration: lets the Director cross-check whether elevated food-sampling risk coincides with historical human-outbreak burden in the same state, adding One Health context (not a predictive driver).
- **NOAA nClimDiv climate** — Provides state-monthly temperature and precipitation anomalies that help the Director anticipate weather-linked shifts in contamination risk.
- **Census ACS 5-year** — Supplies state population and elderly (65+) share, letting the Director weight risk toward populations most vulnerable to severe foodborne illness.
- **USDA Food Access Research Atlas (FARA)** — Supplies low-income/low-access food-environment shares, letting the Director factor food-security vulnerability into where interventions do the most good.

## Retrieval notes
- FSIS files were delivered as zipped JSON per fiscal year across three sampling programs.
  Counts, columns, and positivity in `complete_data_inventory.md` are measured directly
  from these files.
- Census and Atlas were retrieved live/once and cached under `data/raw/`.
- NOAA nClimDiv and CDC NORS are now genuinely ingested and joined to the harmonized
  tables (nClimDiv statewide monthly climate; NORS state×period outbreak counts with a
  +365-day availability lag). This supersedes earlier notes that described them as thin/
  placeholder gaps.
- CDC NORS stands in for the PulseNet organizer extract; the substitution justification is
  recorded here per Req 2.2 — PulseNet is not publicly exportable, and NORS provides the
  closest public human-health surveillance signal, used only as lagged corroboration.
- The remaining known data-completeness gap is the FSIS Recall / PHA regulatory track
  (HTTP 403 firewall in this environment); it is documented as a GAP rather than backfilled.

## Integrity principles
- No fabricated or inflated records or metrics.
- Low-sample observations are never labeled negative merely for lack of evidence.
- Future-period and same-sample result fields are excluded from predictor matrices
  (see `model_feature_dictionary.csv` leakage classes).
