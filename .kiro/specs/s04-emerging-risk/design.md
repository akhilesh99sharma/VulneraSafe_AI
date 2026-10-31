# Design Document

S04 — Persistent vs. Emerging Risk Detector.

## Overview

S04 adds a state-by-period surveillance-signal detector on top of the existing VulneraSafe analysis layer. For each pathogen it builds a positivity time series per US state, computes a leakage-safe trailing baseline, flags retrospective anomalies (statistically unusual increases, using only data available in or before each period), and scores persistence (how consistently a state has been elevated). A prospective forecast is attempted separately and shipped only if it beats a naive persistence baseline; otherwise S04 is descriptive (retrospective) only, an explicitly allowed outcome.

S04 reuses the raw-FSIS readers from S01 (_iter_raw_records, _classify_result, _primary_records, wilson_ci) and the base platform's temporal vocabulary (period, period_start, cutoff, resolution). It adds one analysis module, one TypedDict plus TS interface, one exporter builder, one manifest entry, and one dashboard view. It changes no existing analysis, artifact, or test.

### Non-goals / honesty boundaries

- Geography is sampling location (establishment_state), never product destination or human-illness location. The UI labels it as such.
- A retrospective anomaly is an OBSERVED description of the past. It is never labeled a forecast, prediction, or early warning (Req 1.4).
- NOAA/CDC are thin/placeholder in this repo (NOAA = 1 station; NORS = placeholder). S04 depends on FSIS counts only; environmental context is out of scope for this module.
- No contamination claims. Positivity is surveillance signal, not product safety.

## Architecture

Data flow (offline scan to cache to artifact to UI):

1. Raw FSIS per-FY JSON ZIPs under data/raw/*_sampling_data/ are read by the reused S01 readers (_iter_raw_records / _classify_result / wilson_ci).
2. emerging_risk.py aggregates records into a state-by-period positivity series.
3. For each state series: a trailing baseline with prior-only seasonal adjustment, then a change detector (EWMA / posterior exceedance) producing retrospective anomaly flags, then a persistence score.
4. Separately and optionally, a prospective forecast trained strictly before a cutoff and tested after it.
5. Results cache to data/interim/s04_emerging_risk.json.
6. exporter.build_emerging_risk() reads the cache, shapes and validates web/public/data/emerging_risk.json.
7. The Risk Dashboard "Emerging Signals" view renders the trend, a persistent/emerging toggle, and a time scrubber.

The heavy raw scan runs offline (compute_emerging_risk) and caches to data/interim/s04_emerging_risk.json. The exporter reads the cache and shapes the public emerging_risk.json, exactly as S01 does.

## Components and Interfaces

### 1. src/analysis/emerging_risk.py

Reuses from src/analysis/program_product.py: _iter_raw_records, _classify_result, _primary_records, wilson_ci.

New constants:
- MODULE_ID = "S04", METHOD_VERSION = "s04.v1".
- MIN_SUPPORT — minimum per-(state, period) denominator (fixed in the Support-audit step below; placeholder 30, revised from the audit).
- BASELINE_WINDOW — number of prior same-season periods used for the trailing baseline (default: all prior periods, EWMA-weighted; see Algorithm).
- RESOLUTION per pathogen — "quarterly" default (monthly is sparse at the state level; confirmed in the Support audit).

Key functions:
- _record_state(rec) -> Optional[str] — read establishment_state, uppercase plus strip; empty/NULL to None (dropped from state series, counted as state_missing).
- _record_period(rec, resolution) -> Optional[str] — parse collection_date; bucket to YYYY-Qn (quarterly) or YYYY-MM (monthly); unparseable to None (counted as date_unparsable, never assigned a period).
- _build_series(records, analysis_col, resolution) — returns {state: [(period, period_start, n, pos), ... ordered by period_start]}.
- trailing_baseline(series_for_state) — see Algorithm; returns per-period (baseline_rate, expected_low, expected_high) using only strictly-earlier periods.
- detect_retrospective(series_for_state, baselines) — EWMA/posterior exceedance flag per period; returns retro_anomaly (bool) and retro_threshold.
- persistent_score(series_for_state, baselines) — fraction of supported periods whose observed rate sat above the trailing expected-high band (long-run elevation), in [0,1].
- forecast_prospective(series_for_state, cutoff) — OPTIONAL; trains a one-step-ahead anomaly rule on periods before cutoff, evaluates on periods at/after cutoff, returns precision/recall/lead-time vs a persistence baseline, or None when support is insufficient.
- compute_emerging_risk(resolution_by_pathogen=None, round_to=6) — orchestrates all pathogens, writes the cache, returns the cache dict.
- load_cache() — mirrors S01.

### 2. Support audit (pre-design-lock step, run once)

Before locking MIN_SUPPORT, RESOLUTION, and BASELINE_WINDOW, run a one-off audit (a __main__-guarded report in emerging_risk.py) that prints, per pathogen: number of distinct states, median per-(state, quarter) and per-(state, month) denominators, and the share of state-periods that would clear candidate thresholds (20 / 30 / 50). The chosen values are recorded in the cache's method metadata and quoted in the completion report. This satisfies the source spec's "compact inspect report before writing a model" and Req 3.4 (threshold fixed from development-time evidence).

### 3. Frontend — Risk Dashboard "Emerging Signals" view

New component web/src/components/panels/EmergingSignals.tsx, added as a tab in App.tsx (Tab union extended with "emerging"). Uses useArtifact<EmergingRiskStratum[]>("emerging_risk"), StatusTag, EmptyState, PanelShell/ArtifactBody, consistent with PathogenExplorer.

Controls:
- pathogen selector (3 pathogens, all first-class);
- persistent / emerging toggle — persistent view ranks states by persistent_score; emerging view lists states with a retro_anomaly in the scrubbed period;
- trend chart — positivity per period for the selected state, with the trailing-baseline band overlaid and anomaly periods marked; time scope labeled;
- time scrubber — selects a period; the state list and markers reflect only information available in or before that period (Req 7.4).

Honesty UI:
- A "How to read this" box distinguishing persistent (long-standing) from emerging (new increase) and stating geography = sampling location.
- low_support state-periods are shown de-emphasized and never as "normal".
- If prospective_status is not "validated" for a pathogen, the view shows a plain note that no forward-looking signal beat a naive guess, and presents the retrospective layer only (Req 4.3, 6.2).
- Theme: navy/teal; orange/red only on active anomaly markers (Req 7.6).
- Multi-Map surface deferred to the Page-04 build; a one-line note says so.

### 4. Exporter — build_emerging_risk()

In src/artifacts/exporter.py, mirroring build_multipathogen_program_product(): reads the cache via from src.analysis.emerging_risk import load_cache, flattens to a list[EmergingRiskStratum], validates with validate_payload(..., EmergingRiskStratum, label="emerging_risk"), returns the keyed payload from build_all_artifacts(), and is written to web/public/data/emerging_risk.json. A manifest entry records the artifact and its per-pathogen prospective_status.

## Data Models

### EmergingRiskStratum (Python) plus TS mirror

Added to src/artifacts/schemas.py next to ProgramProductStratum (before the STATUS_TAGS anchor), and mirrored in web/src/types/artifacts.ts. One record per (pathogen, state, period).

Helper TypedDict ProspectiveEval — separately-labeled forecast evaluation, present only when a prospective forecast beat persistence; otherwise the parent record's prospective_alert is None and prospective_status explains why. Fields:
- precision: Optional[float]
- recall: Optional[float]
- alert_volume: Optional[int]
- lead_time_periods: Optional[float]
- availability_lag_note: str
- beat_persistence: bool

Main TypedDict EmergingRiskStratum fields:
- artifact_version: str
- module_id: str  ("S04")
- method_version: str
- pathogen: str
- commodity: str
- geography_level: str  ("state (sampling location)")
- region: str  (state code)
- period: str  ("YYYY-Qn" or "YYYY-MM")
- period_start: str  (ISO date, temporal ordering key)
- sample_n: Optional[int]
- positive_n: Optional[int]
- value: Optional[float]  (observed positivity this state-period)
- ci_low: Optional[float]
- ci_high: Optional[float]
- ci_method: str  ("wilson_95")
- trailing_baseline: Optional[float]  (expected rate from prior periods)
- baseline_high: Optional[float]  (upper expected band)
- persistent_score: Optional[float]  ([0,1], per state, repeated per row)
- retro_anomaly: Optional[bool]  (OBSERVED retrospective flag)
- retro_threshold: Optional[float]
- support_status: str  ("ok" | "low_support")
- prospective_alert: Optional[bool]  (PREDICTED, only if validated)
- prospective_status: str  ("validated" | "not_shown_did_not_beat_persistence" | "insufficient_support" | "not_attempted")
- prospective_eval: Optional[ProspectiveEval]
- status: StatusTag  (OBSERVED for retro rows; PREDICTED only on a validated prospective alert)
- availability_status: str  ("available" | "unavailable")
- unavailable_reason: Optional[str]
- fiscal_years: list[int]
- generated_at: str

Status-tag discipline (Req 1.4, 4.2, 8.3): status is OBSERVED for every retrospective row. PREDICTED appears only on a row carrying a validated prospective_alert. A retrospective anomaly can never carry PREDICTED; a test enforces this.

## Algorithm detail

Period series. For each (pathogen, state), order periods by period_start. Each period cell has n (valid tests) and pos (positives), classified by the S01 tri-state rule (non-diagnostic excluded; "Confirmed Negative of a Previous Presumptive" = negative).

Trailing baseline (leakage-safe). For period t, the baseline uses only periods before t of the same state. To respect seasonality without a future peek, the baseline is an EWMA of prior-period positivity plus a prior-only seasonal offset (mean deviation of same-season prior periods from their EWMA). The expected band is a Wilson interval widened by the baseline's prior-period dispersion. When fewer than BASELINE_WINDOW_MIN prior supported periods exist, the baseline is None and no anomaly is emitted for t (it is low_support for baseline purposes, not "normal").

Retrospective anomaly. Period t (with support at least MIN_SUPPORT and a defined baseline) is flagged when its observed rate exceeds the upper expected band by a sequential rule (EWMA control limit / posterior exceedance probability at or above a fixed threshold). Both the band and the threshold use only data at or before t. Flag is a retrospective, OBSERVED statement.

Persistent score. Over a state's supported periods, the fraction whose observed rate sat above the trailing expected-high band. High = chronically elevated. This is deliberately distinct from the retrospective-anomaly flag: a state can be persistent without a new anomaly, and vice versa (Req 1.2).

Prospective forecast (optional, gated). Fix a cutoff (for example, last 20% of periods held out). Train a one-step-ahead anomaly rule on periods before cutoff; predict anomaly for each test period using only its own past; compare precision/recall against the persistence baseline ("next period anomalous iff last period anomalous"). Report Lead_Time with an availability-lag note (FSIS collection-to-availability delay). If it does not beat persistence, set prospective_status = "not_shown_did_not_beat_persistence" and emit no prospective_alert (Req 4.3). Evaluation on the threshold-selection data is labeled exploratory (Req 4.5).

## Correctness Properties

The S04 tests (in tests/test_emerging_risk.py, Python; and web/src/components/panels/__tests__/EmergingSignals.test.tsx, web) assert:

### Property 1: No future threshold / baseline
**Validates: Requirements 2.3, 8.2**
For a synthetic series, the baseline and threshold at period t are invariant to any mutation of periods at or after t.

### Property 2: Low-n not flagged negative
**Validates: Requirements 3.1, 8.1**
A state-period with n below MIN_SUPPORT has support_status = "low_support" and retro_anomaly is not False-by-default (it is None/unflagged).

### Property 3: No retrospective row labeled forecast
**Validates: Requirements 1.4, 8.3**
Every row with retro_anomaly=True and no validated prospective alert has status = "OBSERVED"; no row carries PREDICTED unless prospective_alert is set and prospective_eval.beat_persistence is true.

### Property 4: State-by-period uniqueness
**Validates: Requirements 8.4**
(pathogen, region, period) is unique across the artifact.

### Property 5: Denominator conservation
**Validates: Requirements 8.5**
positive_n at most sample_n; value, ci_low, ci_high, trailing_baseline in [0,1] when not None.

### Property 6: Persistence not equal to anomaly
**Validates: Requirements 1.2**
A constructed chronically-high, no-new-increase series yields high persistent_score and no current-period retro_anomaly.



Existing Python (pytest) and web (vitest) suites must remain green (Req 8.6); S04 adds files and one schema entry and does not modify existing modules beyond appending the exporter builder plus manifest entry.

## Error Handling

- A pathogen/state/period with no diagnostic rows — no row emitted for that cell (not fabricated).
- A pathogen whose state-by-period series cannot support the detector at all — a single availability_status = "unavailable" record with a plain reason and null numerics (Req 5.3). Expected to be rare given row counts, but handled.
- Missing establishment_state or unparsable collection_date — the record is excluded from the series and counted in method metadata (state_missing, date_unparsable), surfaced in the completion report; never silently zeroed.

## Testing Strategy

- Python: tests/test_emerging_risk.py with the six properties above, using small hand-built synthetic series (no raw-data dependency) so tests are fast and deterministic. Property 1 (no-future-leakage) uses a mutation check.
- Web: EmergingSignals.test.tsx asserts the persistent/emerging toggle, the scrubber restricting to at-or-before period, the low-support de-emphasis, and the "no prospective signal" note render from a small fixture.
- Full suite (pytest + vitest) run in external CMD after implementation; counts recorded in the completion report.
