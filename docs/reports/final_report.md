&nbsp;

# VulneraSafe AI - Final Report

### NAFSI Hub SENS-D Data Challenge, 2026

**Predict the Hazard. Protect the Vulnerable.**

A proactive One Health food-safety decision-support tool for the Food Safety Operations Director of a regional grocery retail chain. This report is self-contained: it answers all ten required questions and documents methods, results, validation, scenarios, limitations, and team science, with every reported number drawn from the project's real data and exported predictions.

> **Responsible-use notice.** This is a decision-support prototype - not a regulatory determination, an outbreak declaration, or a substitute for epidemiologic investigation. Every displayed value is tagged OBSERVED, PREDICTED, or SIMULATED. The tool never labels a food, establishment, or shipment safe or unsafe from a model alone.

**Live application:** https://akhilesh99sharma.github.io/VulneraSafe_AI/
**Repository:** https://github.com/akhilesh99sharma/VulneraSafe_AI


## Executive summary

VulneraSafe AI integrates five One Health data pathways - human-health surveillance (CDC NORS), food/animal regulatory surveillance (USDA FSIS laboratory sampling for three pathogens), environmental conditions (NOAA nClimDiv climate), and community food-security/vulnerability (US Census ACS, USDA Food Access Research Atlas) - into a reproducible, leakage-safe spatiotemporal pipeline. From that pipeline it trains per-pathogen next-period risk models, validates them with time-aware methods, and converts their output into safety-constrained, equity-aware, human-reviewed retailer actions. Confirmed official recalls (real openFDA food-enforcement data) enter as independent regulatory evidence that model uncertainty can never suppress.

The honest headline: the models give a useful risk-prioritization signal (Listeria strongest, PR-AUC 0.736; Salmonella moderate, 0.516; STEC weak, 0.434) whose lift over a strong transparent baseline is modest, and which chiefly captures persistent high-risk ranking rather than emerging-spike prediction. The operational value is the translation layer: it turns that signal into transparent, constrained, reviewable decisions that weigh food safety against food availability and equitable access.


## 1. Decision-maker, decision, and horizon

**Decision-maker.** The Food Safety Operations Director of a regional grocery retail chain, held as the single primary actor across the analytics, decision logic, and interface.

**Decision supported.** Where to focus limited food-safety attention next period, and which safe operational action to take: prioritize supplier verification or targeted testing, hold a lot for human review, isolate a confirmed-recall lot, and allocate compliant replacement supply - while protecting access for high-need communities. These are retailer actions, never government inspection orders.

**Horizon.** One period ahead - monthly for Salmonella, quarterly for Listeria and STEC - matching how a retailer schedules supplier verification and testing. The per-pathogen resolution is chosen by a multi-factor feasibility assessment of each pathogen's sample availability and positive counts, not by one arbitrary threshold.

## 2. One Health contribution of each core dataset

Five pathways feed the tool. Each is labeled by integration status so no signal is overstated.

| Pathway | Dataset(s) | Role | Status |
|---|---|---|---|
| Human health | CDC NORS foodborne outbreaks (data.cdc.gov 5xkq-dg7x) | Corroboration | Integrated (S05), lagged ~365 days, non-causal, not a model feature |
| Food / animal | USDA FSIS lab sampling: Raw Poultry (Salmonella), RTE (Listeria), Raw Beef (STEC), FY2014-2026 | Primary risk signal | Complete (~823K records) |
| Environmental | NOAA nClimDiv statewide monthly climate | Context feature | Integrated, national (~87% state-periods) |
| Supply chain | SIMULATED operational network + REAL openFDA recalls | Decision inputs | Synthetic network SIMULATED; recalls real (FDA jurisdiction) |
| Food security | US Census ACS 2022, USDA Food Access Research Atlas 2019 | Equity context | Complete (state-level) |

- **Human health.** The brief permits a public CDC human-illness dataset in place of PulseNet while retaining a human-health surveillance signal. NORS is joined at (state, period) with a 365-day availability lag reflecting reporting delay and used as historical corroboration (module S05), deliberately NOT as a real-time predictive feature - so a lagged signal can never leak into a forecast.
- **Food / animal.** FSIS establishment laboratory sampling is the surveillance backbone of the risk model: binary result plus quantitative MPN/CFU, no serotype or WGS, so no strain-level attribution is claimed.
- **Environmental.** NOAA nClimDiv statewide monthly temperature and precipitation with anomalies, lagged so only fully-published months are used at a given cutoff.
- **Supply chain.** Confirmed recalls are real openFDA food-enforcement records (FDA jurisdiction); the USDA FSIS meat/poultry recall feed is WAF-blocked (HTTP 403) here and recorded as an honest gap. The operational lot/route network is SIMULATED (no real retailer data exists).
- **Food security.** ACS and the Food Access Atlas supply community vulnerability and access context that drives the equity-aware allocation policy and the vulnerability lens.


## 3. Added datasets, why, and what changed

Two external datasets were added beyond the three required core sources (the brief requires at least two, with at least one food-security or vulnerability dataset):

1. **US Census ACS (2022)** - total population and elderly-65+ share per state.
2. **USDA Food Access Research Atlas (2019)** - low-income and low-income-and-low-access tract shares per state.

**Why.** They supply the food-security and vulnerability dimension the challenge requires. They drive the food-access-aware allocation policy (Policy C) and the vulnerable-population lens, so safety actions can be evaluated for equity.

**What changed.** By design they do NOT change the hazard model - vulnerability must never alter a hazard estimate. They add a distinct decision layer: equity-weighted replacement allocation and a disaggregated equity test. The quantitative effect of the environmental added-data stream is measured directly in the ablation in Section 5. After the NOAA source was upgraded from a single demo station to nationwide nClimDiv statewide monthly climate, weather gives a small real lift for Salmonella (+0.0211 PR-AUC) and STEC (+0.0050) and a slight negative for Listeria (-0.0076) - reported with real signs rather than hidden.

## 4. Modeled signal and why it suits proactive support

**Target.** Future elevated routine-surveillance positivity at a (state, period) cell: an empirical-Bayes / beta-binomial-smoothed next-period positivity at or above a fixed, training-derived tail threshold (75th percentile) within comparable FSIS sampling programs. The target is denominator-aware, so low-sample cells are not forced to negative merely for lack of evidence. A secondary anomaly-above-local-baseline indicator captures emerging increases.

**Why appropriate.** It is forward-looking (next period), leakage-safe (features use only data at or before the cutoff), and actionable at the grain a retailer plans around. It is explicitly a surveillance-risk prioritization - never a claim that a specific product is contaminated. STEC is treated as surveillance-only (non-predictive gating): reported, but not relied on as a forecaster.


## 5. Performance vs baseline, calibration, time and geography

All metrics are computed only from exported predictions on an untouched chronological test split (train periods strictly before test), compared against a persistence/seasonal-naive baseline AND a regularized-logistic baseline. Best integrated model per pathogen: lightgbm for Salmonella, random_forest for Listeria and STEC. Validation is primarily chronological (an untouched final ~20% test split plus rolling-origin with at least 3 origins); a state-level geographic holdout is a secondary check reported separately.

### Headline: integrated model vs baselines (PR-AUC)

| Pathogen | Seasonal-naive | Logistic baseline | Best model | Best-model ROC-AUC |
|---|---|---|---|---|
| Salmonella (monthly) | 0.465 | 0.559 | 0.516 | 0.764 |
| Listeria (quarterly) | 0.660 | 0.711 | 0.736 | 0.838 |
| STEC (quarterly) | 0.355 | 0.380 | 0.434 | 0.650 |

**Honest reading.** The lift over a strong transparent baseline is at most a small margin. For Salmonella the integrated model is roughly on par with the regularized-logistic baseline rather than clearly ahead; for Listeria it is a small margin ahead; STEC stays weak and is treated as surveillance-only. These scores mostly reflect PERSISTENT high-risk ranking, which the baselines already capture - not a demonstration of strong emerging-spike prediction. The target was redesigned after seeing v1 results, so this is an informed re-evaluation on a held-out window, not a fully independent confirmatory test - stated plainly.

### Per-pathogen validation detail (point estimate [95% bootstrap interval])

**Salmonella (lightgbm)** - test units 962 (268 positive, base rate 0.279)
- PR-AUC 0.516 [0.457, 0.583]; ROC-AUC 0.764 [0.732, 0.795]; Brier 0.175 [0.160, 0.192]
- Precision @ 0.5: 0.562; Recall @ 0.5: 0.306
- Calibration error (count-weighted): 0.081
- Rolling-origin (3 origins): PR-AUC 0.452 (delta -0.064 vs single split); ROC-AUC 0.719 (delta -0.045)
- Geographic holdout (11 of 43 states): PR-AUC 0.380, ROC-AUC 0.652
- Inspection budget (top 10%, 97 units): captured 59 of 268 positives; precision@K 0.608, recall@K 0.220
- FP/FN @ 0.5: FP 64 (rate 0.092), FN 186 (rate 0.694)
- Disaggregation: 34 of 41 regions scorable; 25 of 25 periods scored

**Listeria (random_forest)** - test units 435 (114 positive, base rate 0.262)
- PR-AUC 0.736 [0.663, 0.800]; ROC-AUC 0.838 [0.791, 0.879]; Brier 0.124 [0.107, 0.143]
- Precision @ 0.5: 0.794; Recall @ 0.5: 0.474
- Calibration error (count-weighted): 0.031 (best of the three)
- Rolling-origin (3 origins): PR-AUC 0.699 (delta -0.037); ROC-AUC 0.815 (delta -0.023)
- Geographic holdout (13 of 52 states): PR-AUC 0.679, ROC-AUC 0.788
- Inspection budget (top 10%, 44 units): captured 40 of 114 positives; precision@K 0.909, recall@K 0.351
- FP/FN @ 0.5: FP 14 (rate 0.044), FN 60 (rate 0.526)
- Disaggregation: 28 of 51 regions scorable; 9 of 9 periods scored

**STEC (random_forest)** - test units 452 (113 positive, base rate 0.250)
- PR-AUC 0.434 [0.353, 0.528]; ROC-AUC 0.650 [0.590, 0.709]; Brier 0.184 [0.165, 0.205]
- Precision @ 0.5: 0.450; Recall @ 0.5: 0.319
- Calibration error (count-weighted): 0.104
- Rolling-origin (3 origins): PR-AUC 0.464 (delta +0.031); ROC-AUC 0.681 (delta +0.031)
- Geographic holdout (13 of 51 states): PR-AUC 0.399, ROC-AUC 0.709
- Inspection budget (top 10%, 46 units): captured 27 of 113 positives; precision@K 0.587, recall@K 0.239
- FP/FN @ 0.5: FP 44 (rate 0.130), FN 77 (rate 0.681)
- Disaggregation: 42 of 51 regions scorable; 9 of 9 periods scored

### Data-source ablation (marginal value of an added domain)

Four configurations per pathogen, each trained with the pathogen's best model on the same chronological train split and scored on the same untouched test. Primary metric PR-AUC; marginal contribution is the signed change vs FSIS-only (negatives preserved). Values from the live ablation artifact.

| Pathogen | FSIS-only | FSIS+CDC (delta) | FSIS+NOAA (delta) | Full (delta) |
|---|---|---|---|---|
| Salmonella | 0.5102 | 0.5161 (+0.0060) | 0.5313 (+0.0211) | 0.5172 (+0.0070) |
| Listeria | 0.7437 | 0.7455 (+0.0018) | 0.7361 (-0.0076) | 0.7384 (-0.0053) |
| STEC | 0.4102 | 0.4181 (+0.0079) | 0.4151 (+0.0050) | 0.4329 (+0.0227) |

Honest findings: NOAA weather helps Salmonella and STEC but is slightly negative for Listeria (consistent with RTE Listeria being process-driven, not weather-driven). Adding every group (full) clearly helps STEC (+0.0227) but slightly dilutes Salmonella and Listeria versus their best single addition - a reminder that more features is not always better with limited positives.


## 6. Which errors matter most

For a retailer, a missed risk (false negative) is the more consequential error: failing to prioritize verification where positivity truly rises can let unsafe product reach shelves and vulnerable consumers. A false alarm (false positive) costs inspection budget, supplier friction, and potential avoidable food loss or reduced availability. Because the model is a prioritization aid, the app surfaces a ranked queue and a top-K inspection-budget view so the director can tune how many alerts to act on, and pairs every high-consequence action with a human-review gate - keeping recall sensitivity high while bounding false-alarm workload. Concrete FP/FN counts at the 0.5 threshold are in Section 5 (for example, Listeria FP 14 / FN 60; Salmonella FP 64 / FN 186).

## 7. Where safety and security conflicted, and how we handled it

The direct tension: isolating or holding product protects health but reduces food availability, which falls hardest on high-need communities. We handle it with a strict lexicographic ordering in an OR-Tools CP-SAT optimizer. Hard food-safety constraints are modeled structurally and are never relaxed: a confirmed-recall lot is never distributed and is always isolated; blocked lots require human review; replacements use only compliant supply. Secondary objectives - availability, cost, and equitable access - are optimized ONLY within the safety-feasible region. Policy C adds a food-access weighting that steers compliant replacement toward high-need-community stores, breaking ties among safety-equivalent options. A disaggregated equity test (four-fifths band) checks that recommendations do not systematically disadvantage high-need communities.

## 8. One realistic scenario (signals to model to action to evidence)

**Scenario: Listeria RTE verified-evidence recall (SIMULATED operational context).**

- **Incoming signals.** FSIS surveillance positivity (real, PREDICTED risk) plus a verified recall flag on a synthetic operational lot (SIMULATED).
- **Model output.** The hazard layer ranks states by predicted Listeria risk, unchanged by any vulnerable-population lens. The optimizer receives the recall as a hard constraint.
- **Recommended action.** Isolate the recalled lot (never distribute), match it against the confirmed-recall record, and allocate compliant replacement supply - with a human-review gate on the high-consequence steps.
- **What the user sees.** The Recommended Action Panel shows each action with its rationale, governing constraints, and the human-review flag; the co-located Explanation / Evidence Panel shows the source dataset, coverage, access date, quantified uncertainty, and limitations; the Policy Comparison shows A/B/C outcomes on identical inputs. The Listeria scenario is dominated by mandatory isolation, so A/B/C tie there (shown and explained); the Salmonella limited-inspection scenario shows B/C diverging from A (inspection workload +16, priority-review coverage +1.0 under the equity-aware policy).

No observed illness reduction is claimed; operational outcomes are SIMULATED because no real retailer data exists.


## 9. How team science changed the analysis

**Team:** Akhilesh Sharma, Hannah Zonnevylle, and Ruth Nichols - three complementary scientific backgrounds spanning AI and agricultural technology, environmental science and remote sensing, and mathematical and biological sciences.

| Member | Discipline | Contribution |
|---|---|---|
| Akhilesh Sharma | AI / agricultural technology / data science | Project lead: architecture, data integration, pathogen surveillance, predictive modeling, validation, decision logic, and the AWS Kiro web application. |
| Hannah Zonnevylle | Environmental science / spatial ecology / remote sensing | Environmental and spatial dimension: geographic variability, environmental conditions, and the ecological context of food-safety risk. |
| Ruth Nichols | Mathematical and biological sciences | Quantitative and biological interpretation: complex-systems reasoning, integrating forms of evidence, and recognizing uncertainty in biological observations. |

**Honest discipline gaps (declared, not faked):** a practicing retail supply-chain / logistics operations professional, a veterinary / agricultural production specialist, and a credentialed epidemiologist are disciplines the team did not directly cover.

**A real decision changed by interdisciplinary input.** The original intent was to rank establishments purely by pathogen-risk estimates. Viewing the problem through environmental-systems, biological, and quantitative lenses highlighted that this ignores the consequences of restricting or delaying food distribution - geographic variability, surveillance uncertainty, and the vulnerability of affected communities. As a result the design expanded to incorporate population vulnerability, food-security considerations, and alternative intervention scenarios, turning a risk-monitoring dashboard into a broader One Health decision-support platform.

Two further evidence-driven reversals: (1) a one-step-ahead emerging-spike forecast (modules S04/S05) was built, failed to beat a naive persistence baseline (precision 0.03-0.08), and was withheld rather than shipped as an unvalidated PREDICTED layer; (2) establishment and vulnerability rankings moved from raw positivity/shares to a beta-binomial Empirical-Bayes posterior (S03) with the hazard fixed read-only (S06) after the raw approach proved measurably misleading. Choosing a modest honest result over an impressive unvalidated one was a deliberate call.

**Next partner / dataset that would most help.** PulseNet WGS access via a participating public-health lab, to replace lagged NORS corroboration with a timely laboratory-confirmed human-health signal; and reaching the USDA FSIS recall feed (WAF-blocked here) to fold meat/poultry recalls in alongside the FDA-jurisdiction openFDA recalls already integrated.

## 10. What the tool can and cannot support, and what deployment needs

**Can support today.** Proactive prioritization of where a retailer should focus verification and testing next period; transparent, uncertainty-aware, safety-constrained action recommendations; equity-aware allocation trade-offs; a fully reproducible static application.

**Must never claim.** It must never declare a specific product contaminated or safe, assert a causal link between FSIS sampling and human illness, present a scenario-generated recall as a verified regulatory alert, or claim an observed reduction in illness.

**Needed for real deployment.** A timely human-health feed (PulseNet or an approved near-real-time CDC source) rather than lagged NORS; a live USDA FSIS Recall/PHA integration (WAF-blocked here, so only FDA-jurisdiction openFDA recalls are currently integrated); real retailer operational data (shipments, lots, inventory, routes) in place of the SIMULATED network; independent prospective validation on a truly untouched future period; and a formal fairness and equity review with stakeholders.


## Methods summary

- **Pipeline.** Reproducible and spatiotemporal: ingestion, integrity/audit, per-pathogen multi-factor feasibility, leakage-safe harmonization to a (state, period) grid, feature construction, target definition, models, validation, interpretation/ablation, schema-validated artifact export, and a static React application.
- **Resolution.** Salmonella monthly; Listeria and STEC quarterly (chosen by multi-factor feasibility, not a single threshold).
- **Reproducibility.** Fixed seeds (RANDOM_STATE = 42); artifacts are byte-identical across runs; every web value comes from an exported artifact with a checksum recorded in manifest.json. The openFDA recall cache is committed so the regulatory artifact rebuilds offline.

## Science modules beyond the five mandatory panels

The app ships the five required panels (current-risk view, prioritized attention queue, scenario builder, recommended-action panel, explanation/evidence panel) plus validated science modules, each wired to its own schema-validated artifact and each OBSERVED surveillance or explicitly-labeled context: Pathogen Explorer (S01), Supplier Monitor (S03, beta-binomial Empirical-Bayes), Emerging Signals (S04, retrospective - forecast honestly withheld), One Health Insights (S05, real CDC NORS corroboration), Vulnerable Communities (S06) and County Communities (S07), Seasonal Patterns (S02), a Surveillance Actions decision layer, and a Facility Map (FSIS MPI Directory published coordinates, verified coverage reported, never fabricated). Every module ships property tests locking its honesty rules.

## Limitations (consolidated)

- No serotype/WGS in FSIS establishment sampling - no strain-level attribution.
- CDC NORS is integrated as lagged corroboration (~365 days), non-causal, and never a real-time predictor or forecasting feature.
- NOAA weather (nClimDiv, national) gives a small, pathogen-dependent lift (Salmonella +0.0211, STEC +0.0050, Listeria -0.0076 PR-AUC) - modest and honest, not a headline driver.
- Regulatory recalls are real openFDA food-enforcement records (FDA jurisdiction); the USDA FSIS meat/poultry recall feed is WAF-blocked (HTTP 403) here - an honest gap.
- The operational network and all operational outcomes are SIMULATED.
- STEC forecasting is weak; it is treated as surveillance-only.
- ML lift over strong baselines is modest; persistent-risk ranking is not the same as emerging-spike prediction.
- County Communities (S07) ranks county-level vulnerability against a state-level FSIS hazard; the resolution mismatch is labeled on every record and in the UI.

## AI assistance

Development was AI-assisted (AWS Kiro agentic workflow with spec, steering, and hook files). Substantial manual review and corrections were applied. All reported numbers come from real data and exported predictions.

## Deliverables mapping

1. Reproducible scripts - src/, tests/, pipeline modules.
2. Kiro artifacts - .kiro/specs/ (base vulnerasafe-ai spec plus per-module expansion specs).
3. Decision-support app - web/ (React + Vite), deployed to GitHub Pages via GitHub Actions; seven top-level sections including a guided three-step Decision Actions flow (Act / Decide / Plan).
4. Data dictionary and provenance - docs/data_dictionary.md, docs/provenance.md.
5. PDF report - this document.
6. README and requirements - README.md, requirements.txt, web/package.json.
