# Design Document

S05 — Food Surveillance vs. Human Outbreaks Comparison.

## Overview

S05 integrates the challenge's required human-health surveillance stream — real CDC NORS foodborne-outbreak data — and compares it against FSIS pathogen-surveillance history per pathogen x state x year, strictly as corroboration. It closes the previously-placeholder human-health gap. The FSIS side is produced by aggregating the existing S04 state x quarter series to state x year; the NORS side is ingested fresh from data/raw/cdc_nors_outbreaks.csv, standardized to the three pathogens, filtered to foodborne outbreaks, and lagged by a modeled 365 days so it can never act as a leading predictor of FSIS.

The central rule, and the challenge brief's core guardrail, is non-causality: the two systems are shown side by side as corroborating One Health context; S05 never asserts a same-strain link, a food-to-illness causal relationship, or any human county-case forecast. Temporal or geographic similarity is not proof of causation.

S05 reuses the S01/S04 FSIS readers and series builder and the schema/parity mechanism. It adds one analysis module, one TypedDict plus TS interface, one exporter builder, one manifest entry, and one One Health Insights dashboard view. It changes no existing analysis, artifact, or test.

### Non-goals / honesty boundaries

- No same-strain or genomic linkage between any FSIS sample and any NORS outbreak.
- No causal claim in either direction between FSIS positivity and human illness.
- No human county-level or sub-state case estimate or forecast; NORS grain is state x year only.
- Lead-lag correlation is EXPLORATORY descriptive only, with permutation/bootstrap uncertainty.
- NORS counts are OBSERVED facts; the cross-system comparison is labeled CORROBORATION (a separate field), and the core StatusTag union is left unchanged.
- A true reported zero is distinguished from missing/unavailable coverage; thin pathogens/state-years are Coverage_Limited, never zeroed.

## Architecture

Data flow (offline scan to cache to artifact to UI):

1. FSIS side: reuse src/analysis/emerging_risk.py (_build_series + readers) to get per-pathogen state x quarter (n, pos); aggregate to state x year (sum n, sum pos) within the FSIS window.
2. NORS side: read data/raw/cdc_nors_outbreaks.csv; keep Primary Mode == Food; standardize Etiology to Salmonella / Listeria / STEC (split multi-etiology; exclude unmatched); aggregate to (pathogen, state, year) outbreak_count and illness_count.
3. Apply the 365-day availability lag to NORS (knowledge-availability = event year + 1).
4. Join FSIS and NORS on (pathogen, state, year) within the Overlap_Window; flag Coverage_Limited and NORS-not-available cells honestly.
5. Compute an EXPLORATORY lead-lag summary (national per-pathogen series) with permutation/bootstrap uncertainty.
6. Cache to data/interim/s05_human_comparison.json.
7. exporter.build_human_outbreak_comparison() reads the cache, shapes and validates web/public/data/one_health_human_comparison.json.
8. The One Health Insights view renders linked FSIS/CDC timelines with source badges and the no-causal-link explanation.

## Components and Interfaces

### 1. src/analysis/human_comparison.py

Reuses from src/analysis/emerging_risk.py: _build_series, _PATHOGEN_CONFIG, _iter_raw_records (indirectly), and the readers. Reuses src/analysis/program_product.wilson_ci for the FSIS positivity interval.

New constants:
- MODULE_ID = "S05", METHOD_VERSION = "s05.v1".
- NORS_PATH = data/raw/cdc_nors_outbreaks.csv.
- NORS_DATASET_ID = "5xkq-dg7x"; NORS_SOURCE_URL recorded for provenance.
- AVAILABILITY_LAG_DAYS = 365.
- COVERAGE_MIN_OUTBREAKS — a pathogen/state-year with fewer NORS foodborne outbreaks than this across the window is Coverage_Limited (fixed from the probe; placeholder set per pathogen from the inventory).
- OVERLAP_MIN_YEAR / OVERLAP_MAX_YEAR — the FSIS-NORS overlap window (approx 2013..2023), computed from the data, not hardcoded blindly.

Key functions:
- standardize_etiology(text) -> set[str] — conservative map of the free-text, semicolon-split Etiology to a subset of {Salmonella, Listeria, STEC}; STEC covers coli / o157 / shiga / stec; unmatched -> empty set (excluded).
- load_nors_foodborne() -> list[dict] — read CSV, keep Primary Mode == Food, parse Year/State/Illnesses, attach standardized pathogens; count and expose excluded/unparsable rows.
- nors_by_cell(rows) -> {(pathogen, state, year): {outbreaks, illnesses}} — aggregate; a multi-pathogen outbreak contributes to each matched pathogen (documented; counts are not invented, only attributed).
- fsis_state_year() -> {pathogen: {(state, year): {n, pos}}} — aggregate the reused S04 quarterly series to years.
- availability_year(event_year) -> event_year + 1 — the modeled 365-day lag.
- lead_lag_summary(fsis_series, nors_series) -> dict — EXPLORATORY national lead-lag correlation with a permutation/bootstrap p-value and CI; labeled exploratory.
- compute_human_comparison(round_to=6) -> dict — orchestrate all pathogens, join, flag coverage, write cache.
- load_cache().

### 2. Inventory step (Task 1)

A __main__-guarded report confirming: NORS foodborne row count, per-pathogen outbreak/illness/state coverage (Salmonella 3409 / Listeria 144 / STEC 873 confirmed by the probe), the computed Overlap_Window, counts of excluded/unmatched etiologies, and the number of joined comparison cells per pathogen. Fixes COVERAGE_MIN_OUTBREAKS and the overlap window from this evidence. Satisfies the spec step 01 inspect-before-model rule.

### 3. Frontend — One Health Insights view

New component web/src/components/panels/OneHealthInsights.tsx, added as a tab in App.tsx (Tab union extended with "onehealth"). Uses useArtifact<HumanOutbreakComparison[]>("one_health_human_comparison"), StatusTag, EmptyState, PanelShell/ArtifactBody.

Controls and panels:
- pathogen selector (3 first-class) and a state filter;
- linked dual time series over years: an FSIS food-surveillance positivity line and a CDC human-outbreak/illness line, each with a distinct source badge (FSIS food surveillance vs CDC human outbreaks);
- a prominent no-causal-link explanation box stating the human series is corroborating context, not caused-by or predictive-of the FSIS series, and that NORS is lagged ~365 days;
- an EXPLORATORY lead-lag summary line, explicitly labeled exploratory with its uncertainty;
- Coverage_Limited / NORS-not-available states rendered explicitly (e.g. Listeria, later FSIS years), never a fabricated value;
- navy/teal theme; orange/red only on active alert states; a note that sub-state human geography is not produced.

### 4. Exporter — build_human_outbreak_comparison()

In src/artifacts/exporter.py, mirroring build_emerging_risk(): reads the cache via from src.analysis.human_comparison import load_cache, flattens to a list[HumanOutbreakComparison], validates with validate_payload(..., HumanOutbreakComparison, label="one_health_human_comparison"), returns the keyed payload from build_all_artifacts() (auto-written and manifest-registered).

## Data Models

### HumanOutbreakComparison (Python) plus TS mirror

Added to src/artifacts/schemas.py next to the other expansion records (before the STATUS_TAGS anchor), mirrored in web/src/types/artifacts.ts. One record per (pathogen, state, year) comparison cell.

Helper TypedDict LeadLagSummary fields:
- lag_years: Optional[int]
- correlation: Optional[float]
- p_value_permutation: Optional[float]
- ci_low: Optional[float]
- ci_high: Optional[float]
- exploratory: bool  (always true)
- note: str

Main TypedDict HumanOutbreakComparison fields:
- artifact_version: str
- module_id: str  ("S05")
- method_version: str
- dataset_sources: str  (NORS dataset id + FSIS)
- source_accessed_at: str
- pathogen: str
- commodity: str
- geography_level: str  ("state")
- region: str  (state)
- period: str  (year as YYYY)
- fsis_sample_n: Optional[int]
- fsis_positive_n: Optional[int]
- fsis_positivity: Optional[float]
- fsis_ci_low: Optional[float]
- fsis_ci_high: Optional[float]
- nors_outbreak_count: Optional[int]
- nors_illness_count: Optional[int]
- nors_available_from_year: Optional[int]  (event year + 1; the 365-day lag)
- availability_lag_days: int  (365)
- lead_lag: Optional[LeadLagSummary]  (national per-pathogen; repeated on rows or null)
- coverage_status: str  ("ok" | "coverage_limited" | "nors_not_available")
- comparison_status: str  ("CORROBORATION")
- no_causal_link_note: str
- units: str
- status: StatusTag  (OBSERVED; underlying counts are observed facts)
- availability_status: str  ("available" | "unavailable")
- unavailable_reason: Optional[str]
- fiscal_years: list[int]
- generated_at: str

Status discipline: status is OBSERVED (the counts are real observations). The cross-system relationship is carried by comparison_status = CORROBORATION plus no_causal_link_note; the core StatusTag union is unchanged. No field encodes a causal or predictive linkage.

## Algorithm detail

Etiology standardization. The NORS Etiology is free text and may list several agents separated by semicolons (e.g. "Norovirus unknown;Clostridium difficile"). standardize_etiology lowercases, splits on semicolons, and matches each token conservatively: contains "salmonella" -> Salmonella; "listeria" -> Listeria; any of coli / o157 / stec / shiga -> STEC. A row contributes its counts to EACH matched pathogen (documented attribution, not invention); rows matching none of the three are excluded and counted. Suspected vs Confirmed etiology status is retained in the inventory report but both are counted (NORS convention).

FSIS state-year side. Reuse the S04 _build_series per pathogen to get state x quarter (n, pos); sum quarters within a calendar year to (state, year) n and pos; positivity = pos/n with a Wilson interval. Only the FSIS program/result handling already validated in S01/S04 is used; nothing re-derived.

Availability lag. Each NORS outbreak for event year Y is treated as knowable from year Y+1 (365-day modeled lag). The comparison for a given year uses NORS values whose availability year is at or before that year; by construction NORS can never lead FSIS. A test asserts no NORS value with availability_year > the FSIS period year is attached as a predictor.

Join and coverage. Join FSIS and NORS on (pathogen, state, year) within the Overlap_Window. A cell with FSIS data but no NORS outbreaks in a pathogen/state-year that NORS covers is a true zero (nors_outbreak_count = 0); a cell outside NORS coverage (year beyond NORS, or a pathogen/state with no NORS reporting) is coverage_limited or nors_not_available with nulls and a reason. The distinction is explicit (a test enforces it).

Lead-lag (exploratory). For each pathogen, build the national annual FSIS positivity series and the national annual NORS outbreak-count series over the overlap window; compute a descriptive cross-correlation at small integer year lags, with a permutation test (shuffle years) for a p-value and a bootstrap CI. Reported with exploratory = true and a note that it is descriptive only, never causal or predictive.

## Correctness Properties

The S05 tests (tests/test_human_comparison.py, Python; and web/src/components/panels/__tests__/OneHealthInsights.test.tsx, web) assert the following.

### Property 1: 365-day availability lag enforced
**Validates: Requirements 3.1, 7.1**
Every NORS cell's nors_available_from_year equals its event year plus one, and availability_lag_days is 365.

### Property 2: No CDC predictor leakage
**Validates: Requirements 3.2, 7.2**
No comparison attaches a NORS value whose availability year is after the FSIS period year as a predictor of that period's FSIS value.

### Property 3: Zero vs missing distinction
**Validates: Requirements 4.2, 7.3**
A reported zero (nors_outbreak_count = 0 within NORS coverage) is represented differently from missing coverage (coverage_status nors_not_available or coverage_limited with null counts).

### Property 4: No causal or forecast labels
**Validates: Requirements 2.1, 2.2, 2.3, 7.4**
No record contains a causal/same-strain/linkage field or any sub-state or forecast human-case field; comparison_status is CORROBORATION and no_causal_link_note is present.

### Property 5: Conservative etiology standardization
**Validates: Requirements 4.1, 7.5**
standardize_etiology maps known agents correctly (salmonella/listeria/coli-o157-shiga), splits multi-etiology strings, and returns empty for unmatched etiologies (e.g. Norovirus), which are excluded.

### Property 6: All three pathogens first-class with honest coverage
**Validates: Requirements 4.2, 1.2**
All three pathogens appear; a thin pathogen (Listeria) is coverage_limited with its real counts, never dropped and never zeroed.

## Error Handling

- A pathogen/state-year with no FSIS data and no NORS data produces no row.
- A pathogen/state-year outside NORS coverage produces a coverage_limited / nors_not_available record with null NORS counts and a reason, never a fabricated zero.
- NORS rows with unparsable year/state are excluded and counted in method metadata.
- If the NORS CSV is absent, compute_human_comparison emits a per-pathogen unavailable record with a reason (run the documented download), never fabricated human data.

## Testing Strategy

- Python: tests/test_human_comparison.py with the six properties above on small hand-built NORS/FSIS fixtures (no raw-file dependency), fast and deterministic; plus a unit test of standardize_etiology.
- Web: OneHealthInsights.test.tsx asserts the dual FSIS/CDC timelines render with distinct source badges, the no-causal-link explanation is present, a coverage-limited state renders, and the artifact-missing empty state renders.
- Full suite (pytest plus vitest plus build) run in external CMD after implementation; counts recorded in the completion report.
