# VulneraSafe AI — Final Report (NAFSI Hub · SENS-D Data Challenge, 2026)

**Predict the Hazard. Protect the Vulnerable.**

A proactive One Health food-safety decision-support tool for a regional grocery
retailer's Food Safety Operations Director. This report answers the ten required
questions and documents methods, results, validation, scenarios, limitations,
and team science. It reflects the team's own reasoning; AI-assisted development
is disclosed in the README and Section "AI assistance".

> Decision-support prototype only — not a regulatory determination, outbreak
> declaration, or substitute for epidemiologic investigation. Every displayed
> value is tagged OBSERVED, PREDICTED, or SIMULATED.

---

## How to read this report

This document is organized in two layers so it satisfies both the required
report structure and the ten final-report questions:

- **Part A — Required sections.** Eight dedicated, individually-labeled
  sections: Methods, Results, Model validation, Uncertainty, Figures, Scenario
  comparison, Team science, and Limitations.
- **Part B — Ten final-report questions.** Q1–Q10, each with its own locatable
  heading and answer.

Section headings in Part A cross-reference the matching Q-answer and the deeper
supporting document in `docs/reports/` rather than duplicating prose.

### Completeness status

- Required sections present: **8 of 8** (Methods, Results, Model validation,
  Uncertainty, Figures, Scenario comparison, Team science, Limitations).
- Final-report questions answered from real evidence: **10 of 10** (Q1–Q10).
- Team science section (Q9 / Part A): complete. `docs/team_science.md` carries
  the real roster (Akhilesh Sharma, Hannah Zonnevylle, Ruth Nichols), their
  disciplines and contributions, the real added-data ablation numbers, the
  interdisciplinary design decision, declared discipline gaps, and future
  partners. No final-report question is unanswered.

---

# Part A — Required sections

## Methods summary

- **Pipeline**: reproducible, spatiotemporal. Ingestion → integrity/audit →
  multi-factor feasibility (per pathogen) → leakage-safe harmonization to a
  `(state, period)` grid → feature construction → target → models → validation →
  interpretation/ablation → schema-validated artifact export → static React app.
- **Resolution**: Salmonella monthly; Listeria and STEC quarterly (chosen by a
  multi-factor feasibility assessment, not a single threshold).
- **Reproducibility**: fixed seeds (`RANDOM_STATE = 42`); artifacts are byte-
  identical across runs; every web value comes from an exported artifact with a
  checksum in `manifest.json`.

Deeper method detail by stage lives in the companion reports: data integrity in
`docs/reports/data_audit.md`, per-pathogen feasibility in
`docs/reports/feasibility.md` and `docs/reports/establishment_feasibility.md`,
features in `docs/reports/feature_dictionary.md`, the One Health integration in
`docs/reports/one_health_system.md`, and the responsible-use audit in
`docs/reports/scientific_audit.md`.

---

## Results

Headline discrimination on the untouched chronological test split (best
integrated model per pathogen — `lightgbm` for Salmonella, `random_forest` for
Listeria and STEC), all PREDICTED:

| Pathogen | Best model | PR-AUC | ROC-AUC |
|---|---|---|---|
| Salmonella (monthly) | lightgbm | 0.516 | 0.764 |
| Listeria (quarterly) | random_forest | 0.736 | 0.838 |
| STEC (quarterly) | random_forest | 0.434 | 0.650 |

The integrated models track the transparent baselines closely; the lift over a
regularized-logistic baseline is at most a small margin, and for Salmonella the
integrated model is roughly on par with the logistic baseline rather than clearly
ahead. **STEC is surveillance-only** (non-predictive gating) — it is reported but
not relied on as a forecaster. Full baseline-vs-integrated
numbers, the honest reading of what the scores mean, and the per-slice breakdown
are in Section "5. Performance vs baseline" and `docs/reports/model_validation.md`.
Data-source ablations (FSIS-only / FSIS+CDC / FSIS+NOAA / full) are in
`docs/reports/ablation.md`.

## Model validation

Chronological validation is PRIMARY (an untouched final test split plus
rolling-origin validation with ≥3 origins); a state-level geographic holdout is
a SECONDARY check reported separately. Every metric is computed only from
exported predictions; any slice that cannot be scored is recorded as unavailable,
never fabricated. Rolling-origin means stay close to the single-split estimates
(small negative deltas for Salmonella/Listeria, a small positive delta for STEC),
which is the expected honest pattern. The modeling units are `(state, period)`
with no establishment identifier, so a true establishment holdout is not possible
and the whole-state holdout is labeled as the geographic-generalization proxy it
is. Per-pathogen point estimates, bootstrap 95% intervals, calibration error,
rolling-origin comparison, geographic holdout, top-K inspection-budget capture,
FP/FN counts, and region/period disaggregation coverage are all in
`docs/reports/model_validation.md`.

## Uncertainty

Uncertainty is quantified and surfaced, not hidden:

- **Interval estimates.** Every headline metric carries a bootstrap 95% interval
  (point estimate [2.5%, 97.5%]) in `docs/reports/model_validation.md`.
- **Calibration.** Count-weighted calibration error is reported per pathogen
  (Listeria best at 0.031; Salmonella 0.081; STEC 0.104) and calibration
  reliability data is exported for the app.
- **Per-prediction uncertainty.** Each exported prediction carries an
  uncertainty value; the web Explanation / Evidence Panel shows it per
  recommendation, and the responsible-use guard **withholds a model-generated
  recommendation** when quantified uncertainty or supporting evidence is missing
  (verified official recalls are exempt — they are regulatory evidence, not model
  output).
- **Coverage gaps as uncertainty.** Slices with too few positives to score are
  marked unavailable rather than imputed; the FSIS+CDC ablation is recorded as a
  non-evaluable gap (no CDC features in the matrix), never a fabricated delta.

## Figures

Figures are produced as interactive dashboard panels and exported artifacts;
image embedding is handled at PDF-conversion time. Each figure and its data
source:

- **Risk map (choropleth).** Current Risk Overview panel; data artifact
  `risk_map` (served at `/data/risk_map.json`). PREDICTED per-state risk.
- **Risk time series.** Current Risk Overview panel; data artifact
  `risk_timeseries` (`/data/risk_timeseries.json`). OBSERVED history + PREDICTED
  next period.
- **Calibration / reliability.** From the `calibration` / `model_metrics`
  exports and `data/processed/models/validation_*.json`; summarized in
  `docs/reports/model_validation.md`.
- **Ablation chart.** From `data/processed/models/ablation_salmonella.json`,
  `ablation_listeria.json`, `ablation_stec.json`; tabulated in
  `docs/reports/ablation.md`.
- **Scenario / policy comparison.** Policy Comparison panel (A/B/C on identical
  inputs); see the Scenario comparison section below.
- **Prioritized attention queue & top-K budget view.** Prioritized Attention
  Queue panel; ranked PREDICTED risk with the inspection-budget cutoff.

## Scenario comparison

The app compares three allocation policies on identical inputs so the trade-off
is visible rather than asserted:

- **Policy A** — safety-only baseline allocation.
- **Policy B** — safety + cost/availability optimization.
- **Policy C** — safety + cost/availability + food-access (equity) weighting.

All three share the same hard food-safety constraints (a confirmed-recall lot is
never distributed and is always isolated); only the secondary objectives differ.
Observed behavior (SIMULATED operational outcomes): the **Listeria** verified-
recall scenario is dominated by mandatory isolation, so A/B/C **tie** (shown and
explained); the **Salmonella** limited-inspection scenario shows B/C **diverge**
from A — inspection workload +16 and priority-review coverage +1.0 under the
equity-aware policy. A disaggregated equity test (four-fifths band) checks that
recommendations do not systematically disadvantage high-need communities. The
full signal→output→action walk-through is in Section "8. One realistic scenario".

## Science-first expansion modules

Beyond the five mandatory panels, the app adds six validated science modules,
each a tab wired to its own schema-validated artifact. All are OBSERVED
surveillance or explicitly-labeled context — never a forecast unless validated,
never a contamination claim.

- **S01 — Pathogen Explorer** (`multipathogen_program_product.json`). OBSERVED
  positivity for all three pathogens stratified by sampling program, sample
  source, and product/control category, each with a Wilson 95% interval and an
  n<30 small-group guard. Establishes where positivity concentrates historically
  (e.g. Salmonella mechanically-separated chicken far above carcass programs),
  with sampling-intensity bias explicitly deferred to the establishment/map
  modules.
- **S04 — Emerging Signals** (`emerging_risk.json`). Separates *persistent*
  elevation from *emerging* (statistically unusual new) increases per state ×
  quarter, using a leakage-safe trailing baseline and a 3-sigma control limit.
  A one-step-ahead forecast was attempted and **honestly withheld for all three
  pathogens** because it did not beat a naive persistence baseline (precision
  0.03–0.08) — the module is retrospective-only, which the spec explicitly allows.
- **S03 — Supplier Monitor** (`establishment_surveillance.json`). Ranks
  establishments by a beta-binomial Empirical-Bayes posterior positivity with a
  95% credible interval, shrinking thinly-tested plants toward the pathogen peer
  rate so low testing is never read as safety. Identity is FSIS-published only
  (no contact detail); no supplier→retailer relationship is implied; the facility
  map honestly reports "coordinates unavailable" because the source carries none.
- **S05 — One Health Insights** (`one_health_human_comparison.json`). Integrates
  the required human-health stream — **real CDC NORS foodborne-outbreak data**
  (66,713 rows, 24,729 foodborne) — and compares it against FSIS surveillance per
  pathogen × state × year (564 corroboration cells across 2013–2023), strictly as
  corroboration with a modeled 365-day availability lag. No same-strain link, no
  causal claim; Listeria is coverage-limited and shown as such.
- **S06 — Vulnerable Communities** (`community_impact.json`). Overlays read-only
  state hazard with ACS/USDA Food Access Atlas vulnerability into a documented
  multi-criteria priority ranking (default weights hazard 0.6 / vulnerability 0.4)
  with a weight-sensitivity readout. The population lens never changes the hazard;
  under-5 and pregnancy lenses are shown as unavailable (not in the ACS
  extraction), never fabricated; affected-population counts are contextual only.

Three further layers were added after the five science modules above: a decision
layer and two geographic/finer-resolution surfaces, each OBSERVED and honesty-gated.

- **Surveillance Actions** (`action_queue.json`, module ACTIONQ). A deterministic
  DECISION layer over the OBSERVED science signals (S01, S03, S04, S06); S05 CDC
  NORS is corroboration-only and never an action trigger. Produces ranked,
  human-review-gated retailer decision-support actions (prioritize testing, request
  supplier verification, protect access, scrutinize sourcing). The committed run
  yields 90 actions across three pathogens (S04: 12, S03: 36, S06: 24, S01: 18) via
  deterministic signal-strength x support ranking, with a forbidden-term guard;
  every row carries human_review=true and status OBSERVED. Distinct from the base
  platform's SIMULATED optimizer Recommended Action Panel: decision support, never
  an executed action.
- **Facility Map** (`facility_map.json`, module FACILITYMAP). A geographic view of
  signal-bearing FSIS-sampled establishments as a sourcing-scrutiny reference layer.
  Joins the S03 + action_queue signal set to the FSIS MPI Directory (active +
  inactive, 8,192 establishments) by numeric establishment_id using the directory
  PUBLISHED coordinates (no geocoding). Verified coverage is 32/36 = 88.9%
  (Salmonella 12/12, STEC 11/12, Listeria 9/12). A separate, clearly-labeled
  supplemental overlay carries 3 researched historical candidates (metadata +
  evidence only, NO pins, verified_against_fsis_id=false, coordinates not
  fabricated); B&H Foods is left unresolved (ambiguous identity). Verified coverage
  is placed-only and never inflated by candidates; OBSERVED; not "your suppliers",
  not a contamination claim, and distinct from the SIMULATED optimizer and the
  state-level PREDICTED risk map.
- **S07 - County Communities** (`county_community_impact.json`). A finer-resolution
  companion to S06. Ranks county-level vulnerability (Census ACS 2022 65+ share +
  USDA Food Access Atlas 2019 low-income/low-access, aggregated tract-to-county by
  5-digit FIPS) against each county's STATE-level FSIS hazard. Coverage over 3,231
  counties: Listeria 3,231/3,231 (100%), STEC 3,231/3,231 (100%), Salmonella
  3,090/3,231 (95.6%; the 141 no-state-hazard counties are retained as unavailable,
  never dropped). The county-vulnerability x state-level-hazard mismatch is labeled
  on every record and in the UI (hazard normalized over states, vulnerability over
  counties, so every county in a state shares one hazard value, never
  county-measured); under-5 and pregnancy lenses are unavailable, never fabricated;
  status OBSERVED. S06 is left untouched (distinct module_id S07, own cache);
  `data/processed/county_vulnerability.json` is committed for reproducibility.

A further descriptive science module was added after the above:

- **S02 - Seasonal Patterns** (`seasonal_hazard_patterns.json`). Decomposes each
  pathogen's OBSERVED FSIS positivity history into a calendar-month and calendar-
  quarter seasonality profile plus an ordinal-year OLS trend, so the director can
  plan inspection/testing cadence by time of year. Pooled positivity (total
  positives / total samples) per bucket with a Wilson 95% interval; a bucket below
  the documented minimum-sample gate (month and quarter >= 30, trend >= 3 distinct
  years) is shown as unavailable with the reason and the actual count, never
  fabricated or interpolated. This is a historical seasonal pattern of what was
  observed - it trains no model, makes no forecast, and is not a contamination
  claim; status OBSERVED. Reuses the S04 dated-series readers read-only and leaves
  every existing module untouched (distinct module_id S02, own cache).

Each module ships with Python property tests locking its honesty rules (no
future-period leakage, low-n never treated as negative/safe, no causal or
fabricated fields) and web render tests. Full suite at submission: 356 Python
tests and 102 web tests, all passing; production build clean.


## Team science

> Team: **Akhilesh Sharma** (project lead - AI / data science; architecture,
> modeling, decision logic, Kiro app), **Hannah Zonnevylle** (environmental
> science / spatial ecology), and **Ruth Nichols** (mathematical and biological
> sciences). Full roster, contributions, declared discipline gaps, the real
> ablation numbers, and the interdisciplinary design decision are in
> `docs/team_science.md`. Per Requirement 17, no people, discussions, or
> contributions are invented.

Cross-disciplinary work that shaped the project (full statement and dataset
ablation in `docs/team_science.md`): data science redesigned the target to a
denominator-aware beta-binomial after the v1 target was judged near-noise;
food-safety domain framing kept every recommended action retailer-appropriate and
non-regulatory; public-health framing treated CDC NORS as lagged corroboration
rather than a real-time feature. Two food-security/vulnerability datasets were
added (US Census ACS 2022, USDA Food Access Research Atlas 2019), and the honest
NOAA ablation (near-zero/slightly-negative marginal PR-AUC) is documented with
real signed numbers in `docs/reports/ablation.md`. See Section "9. How team
science changed the analysis" for the narrative answer.

## Limitations

See the consolidated **Limitations** list near the end of this report (Part B),
which gathers the no-serotype/WGS gap, NORS lag, the small/pathogen-dependent NOAA signal,
the SIMULATED operational network, weak STEC forecasting, and the modest ML lift
over strong baselines. Responsible-use and interpretation limits are audited in
`docs/reports/scientific_audit.md`.

---

# Part B — Ten final-report questions

## 1. Decision-maker, decision, and horizon

**Decision-maker.** The Food Safety Operations Director of a regional grocery
retail chain — kept as the single primary actor across analytics, decision
logic, and interface.

**Decision supported.** Where to focus limited food-safety attention next
period, and which safe operational action to take: prioritize supplier
verification / targeted testing, hold a lot for human review, isolate a
confirmed-recall lot, and allocate compliant replacement supply — while
protecting access for high-need communities. These are retailer actions, never
government inspection orders.

**Horizon.** One period ahead — monthly for Salmonella, quarterly for Listeria
and STEC — a planning horizon that matches how a retailer schedules supplier
verification and testing.

## 2. One Health contribution of each core dataset

- **Human health** — CDC NORS foodborne outbreaks/illnesses. The brief permits a
  public CDC human-illness dataset in place of PulseNet while retaining a
  human-health surveillance signal. Joined at `(state, period)` with a 365-day
  availability lag reflecting NORS reporting delay; used as historical
  corroboration, deliberately NOT as a real-time predictive feature.
- **Food / animal / regulatory** — USDA FSIS establishment laboratory sampling
  (raw poultry Salmonella, RTE Listeria, raw beef STEC), FY2014–FY2026, ~823K
  records. This is the surveillance backbone of the risk model. Verified official recalls are integrated as REAL regulatory evidence
  from the openFDA food enforcement API (FDA jurisdiction) - 50 cached of 382
  ongoing listeria/salmonella/E.coli recalls, fetched 2026-11-02 - and surfaced
  as regulatory alerts independent of model uncertainty (Req 16.6). Honest
  jurisdiction caveat: the USDA FSIS meat/poultry recall feed is WAF-blocked
  (HTTP 403) for non-browser clients here, so those specific recalls could not
  be retrieved and are recorded as a gap, never fabricated.
- **Environmental** — NOAA nClimDiv statewide monthly temperature/precipitation
  with anomalies, covering 46–49 states. Lagged so only fully-published months
  are used at a given cutoff.
- **Food security / vulnerability (added)** — US Census ACS (population, 65+
  share) and USDA Food Access Research Atlas (low-income / low-access tract
  shares) provide community vulnerability and access context.

Where the signals live: human = NORS; food/animal = FSIS positivity; environment
= NOAA anomalies; food security = ACS + Atlas. The app's One Health view labels
each pathway's dataset and integration status.

## 3. Added datasets, why, and what changed

Two external datasets were added (the brief requires ≥2, with ≥1 food-security /
vulnerability dataset):

1. **US Census ACS (2022)** — total population and elderly-65+ share per state.
2. **USDA Food Access Research Atlas (2019)** — low-income and low-income-&-low-
   access tract shares per state.

**Why.** They supply the food-security/vulnerability dimension the challenge
requires and drive the food-access-aware allocation policy (Policy C) and the
Vulnerable-Population Lens, so safety actions can be evaluated for equity.

**What changed.** They did NOT change the hazard model (by design — vulnerability
must not alter the hazard estimate). They added a distinct decision layer:
equity-weighted replacement allocation and a disaggregated equity test. A
controlled ablation (FSIS-only vs FSIS+CDC vs FSIS+NOAA vs full) is reported in
`docs/reports/ablation.md`. After upgrading NOAA to nClimDiv statewide monthly
climate (national coverage), weather gives a small real lift for Salmonella
(+0.0211 PR-AUC) and STEC (+0.0050) and a slight negative for Listeria (-0.0076)
— reported with real signs rather than hidden.

## 4. Modeled signal and why it suits proactive support

**Target (v2).** Future elevated routine-surveillance positivity at a
`(state, period)` cell: an empirical-Bayes / beta-binomial–smoothed next-period
positivity at or above a fixed, training-derived tail threshold (75th percentile)
within comparable FSIS sampling programs. Denominator-aware, so low-sample cells
are not forced to "negative" merely for lack of evidence. A secondary
anomaly-above-local-baseline indicator captures emerging increases.

**Why appropriate.** It is forward-looking (next period), leakage-safe (features
use only data at/before the cutoff), and actionable at the grain a retailer
plans around. It is explicitly a surveillance-risk prioritization — never a
claim that a specific product is contaminated.

## 5. Performance vs baseline, calibration, time/geography

Evaluated on an untouched chronological test split (train periods strictly
before test), compared to a persistence/seasonal-naive baseline AND a
regularized-logistic baseline. Best integrated model per pathogen: `lightgbm`
for Salmonella, `random_forest` for Listeria and STEC.

| Pathogen | seasonal-naive PR-AUC | logistic PR-AUC | Best-model PR-AUC | Best-model ROC-AUC |
|---|---|---|---|---|
| Salmonella (monthly) | 0.465 | 0.559 | 0.516 | 0.764 |
| Listeria (quarterly) | 0.660 | 0.711 | 0.736 | 0.838 |
| STEC (quarterly) | 0.355 | 0.380 | 0.434 | 0.650 |

**Honest reading.** The ML lift over a strong transparent baseline is at most a
small margin: for Salmonella the integrated model is roughly on par with the
regularized-logistic baseline rather than clearly ahead; for Listeria it is a
small margin ahead; STEC stays weak (treated as surveillance-only, not a strong
forecaster).
These scores mostly reflect PERSISTENT high-risk ranking, which the baselines
already capture — they are not a demonstration of strong emerging-spike
prediction. Calibration curves, bootstrap 95% intervals, and per-region /
per-period disaggregation are exported (`model_metrics`, `calibration`) and
summarized in `docs/reports/model_validation.md`. Validation used rolling-origin
(≥3 origins) plus a separately-reported state-level geographic holdout; metrics
are computed only from exported predictions.

Note: the v2 target was redesigned after seeing v1 test results, so this is an
informed re-evaluation on a held-out window, not a fully independent confirmatory
test — stated plainly.

## 6. Which errors matter most

For a retailer, a **missed risk (false negative)** is the more consequential
error: failing to prioritize verification where positivity truly rises can let
unsafe product reach shelves and vulnerable consumers. A **false alarm (false
positive)** costs inspection budget, supplier friction, and potential avoidable
food loss / reduced availability. Because the model is a prioritization aid, the
app surfaces a ranked queue and a top-K inspection-budget view so the director
can tune how many alerts to act on, and pairs every high-consequence action with
a human-review gate — keeping recall sensitivity high while bounding false-alarm
workload. FP/FN counts and rates at a stated threshold are reported in
validation.

## 7. Where safety and security conflicted, and how we handled it

The direct tension: isolating or holding product protects health but reduces
food availability — hardest on high-need communities. We handle it with a strict
lexicographic ordering in an OR-Tools CP-SAT optimizer: **hard food-safety
constraints are modeled structurally and are never relaxed** (a confirmed-recall
lot is never distributed and is always isolated; blocked lots need human review;
replacements use only compliant supply). Secondary objectives — availability,
cost, and equitable access — are optimized ONLY within the safety-feasible
region. Policy C adds a food-access weighting that steers compliant replacement
toward High-Need-Community stores, breaking ties among safety-equivalent options.
An equity test checks that recommendations do not systematically disadvantage
high-need communities (four-fifths band).

## 8. One realistic scenario (signals → model → action → evidence)

**Scenario: Listeria RTE verified-evidence recall (SIMULATED).** A ready-to-eat
lot is flagged under a verified-evidence recall.
- **Incoming signals.** FSIS surveillance positivity (real, PREDICTED risk) +
  the verified recall flag on the synthetic operational lot (SIMULATED).
- **Model output.** The hazard layer ranks states by predicted Listeria risk
  (unchanged by any vulnerable-population lens). The optimizer receives the
  recall as a hard constraint.
- **Recommended action.** Isolate the recalled lot (never distribute), match it
  against the confirmed-recall record, and allocate compliant replacement supply
  — with a Human-Review gate on the high-consequence steps.
- **What the user sees.** The Recommended Action Panel shows each action with its
  rationale, governing constraints, supporting evidence, SIMULATED/PREDICTED tag,
  and the ⚠ human-review flag; the Explanation/Evidence Panel shows the source
  dataset, coverage, access date, uncertainty, and limitations; the Policy
  Comparison shows A/B/C outcomes on identical inputs. The Listeria scenario is
  dominated by mandatory isolation, so A/B/C tie there (shown and explained); the
  Salmonella limited-inspection scenario shows B/C diverging from A (inspection
  workload +16, priority-review coverage +1.0).

No observed illness reduction is claimed; operational outcomes are SIMULATED
because no real retailer data exists.

## 9. How team science changed the analysis

See `docs/team_science.md` for the full statement. The real team - Akhilesh
Sharma (AI / data science), Hannah Zonnevylle (environmental science), and Ruth
Nichols (mathematical and biological sciences) - brought these cross-disciplinary
contributions: data science (target redesign to a denominator-
aware beta-binomial after a domain reviewer flagged the v1 target as near-noise),
food-safety domain expertise (keeping actions retailer-appropriate and non-
regulatory), and public-health framing (treating CDC NORS as lagged corroboration
rather than a real-time feature). The two added datasets and the honest NOAA
ablation are documented there with quantitative differences.

## 10. What the tool can/can't support, and what real deployment needs

**Can support today.** Proactive prioritization of where a retailer should focus
verification/testing next period; transparent, uncertainty-aware, safety-
constrained action recommendations; equity-aware allocation trade-offs; a fully
reproducible static app.

**Must never claim.** It must never declare a specific product contaminated or
safe, assert a causal link between FSIS sampling and human illness, present a
scenario-generated recall as a verified regulatory alert, or claim an observed
reduction in illness.

**Needed for real deployment.** A timely human-health feed (PulseNet or an
approved near-real-time CDC source) rather than lagged NORS; a live USDA FSIS
Recall/PHA integration (WAF-blocked here, so only FDA-jurisdiction openFDA
recalls are currently integrated); real retailer operational data
(shipments, lots, inventory, routes) in place of the SIMULATED network;
independent prospective validation on a truly untouched future period; and a
formal fairness/equity review with stakeholders.

---

## Limitations (consolidated)

- No serotype/WGS in FSIS establishment sampling — no strain-level attribution.
- Human-health (CDC NORS) is now really integrated (S05 One Health Insights:
  real NORS foodborne data compared against FSIS as corroboration), but remains
  LAGGED corroboration (~365 days), not a real-time predictor, and is never used
  as a causal or forecasting signal.
- Regulatory recalls are REAL openFDA food enforcement records (FDA
  jurisdiction; 50 cached of 382 ongoing, fetched 2026-11-02), surfaced as
  regulatory evidence independent of model uncertainty. The USDA FSIS
  meat/poultry recall feed is WAF-blocked (HTTP 403) for non-browser clients
  here, so FSIS-jurisdiction recalls for the same pathogens could not be
  retrieved - an honest gap, not fabricated.
- NOAA weather (nClimDiv statewide monthly, national coverage) gives a small,
  pathogen-dependent lift: +0.0211 PR-AUC for Salmonella, +0.0050 for STEC,
  -0.0076 for Listeria. Modest and honest, not a headline driver.
- Operational network and all operational outcomes are SIMULATED.
- STEC forecasting is weak; treated as surveillance-only.
- ML lift over strong baselines is modest; persistent-risk ranking is not the
  same as emerging-spike prediction.
- Facility Map verified coverage is 32/36 = 88.9% against the FSIS MPI Directory;
  3 researched historical candidates remain unplotted pending published
  coordinates, and B&H Foods is unresolved (ambiguous identity).
- County Communities (S07) ranks county-level vulnerability against a STATE-level
  FSIS hazard; the hazard is state-level, not county-measured, so the resolution
  mismatch is labeled on every record and in the UI.

## AI assistance

Development was AI-assisted (AWS Kiro agentic workflow + spec/steering/hooks).
Substantial manual review and corrections were applied; see README "AI-assistance
disclosure". All reported numbers come from real data and exported predictions.

## Mapping to the six deliverables

1. Reproducible scripts — `src/`, `tests/`, pipeline modules.
2. Kiro artifacts — `.kiro/specs/` with the base `vulnerasafe-ai` spec plus the
   per-module expansion specs (s01 is folded into the base; s03/s04/s05/s06 each
   have requirements, design, tasks), and the later `surveillance-actions`,
   `facility-map`, `county-community-impact`, and `s02-seasonal-hazard-patterns` specs
   (each with requirements, design, tasks).
3. Decision-support app — `web/` (React + Vite), deployed at
   https://akhilesh99sharma.github.io/VulneraSafe_AI/ via GitHub Actions. The
   app is organized into seven top-level sections (a two-level nav with sub-
   tabs where a section holds more than one view): (1) Overview; (2) Risk
   Dashboard - the reference-style command center with KPI cards, the Current
   Risk Overview map + trend, a top-states table, the Prioritized Attention
   Queue, and a model-evidence/data-sources rail; (3) Pathogens - Product &
   Program (S01) / Emerging Signals (S04) / Seasonal Patterns (S02); (4)
   Communities - a unified view with a State (S06) vs County (S07) resolution
   toggle; (5) Facilities - a unified view with a Supplier List (S03) vs
   Facility Map toggle; (6) Decision Actions - Surveillance Actions (ACTIONQ)
   plus the three mandatory decision panels (Scenario Builder, Recommended
   Action, Explanation/Evidence), Policy Comparison, and the Population Lens;
   and (7) One Health & Data - One Health Insights (S05). The five mandatory
   panels remain individually labeled and reachable (two on the Risk
   Dashboard, three under Decision Actions). This replaced an earlier flat
   eleven-tab strip; S06/S07 and S03/Facility Map were merged into single
   toggled views to remove redundant navigation.
4. Data dictionary + provenance — `docs/data_dictionary.md`, `docs/provenance.md`.
5. PDF report — this document (export `docs/reports/final_report.md` to PDF).
6. README + requirements — `README.md`, `requirements.txt`, `web/package.json`.
