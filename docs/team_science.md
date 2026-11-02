# Team Science Statement
**VulneraSafe AI | NAFSI SENS-D Data Challenge 2026**

**Team:** Akhilesh Sharma, Hannah Zonnevylle, and Ruth Nichols

## Interdisciplinary Team Composition

VulneraSafe AI was developed by a team representing three complementary scientific backgrounds: artificial intelligence and agricultural technology, environmental science and remote sensing, and mathematical and biological sciences. This combination reflects the interdisciplinary nature of the One Health framework, where understanding food-safety risks requires considering biological, environmental, technological, and societal factors together.

### Members and disciplines (Req 17.1)

| Member | Discipline covered | Genuine contribution |
|---|---|---|
| Akhilesh Sharma | AI / agricultural technology / data science | Project lead: architecture, data integration, pathogen surveillance, predictive modeling, validation, decision-support logic, and the AWS Kiro web application. |
| Hannah Zonnevylle | Environmental science / spatial ecology / remote sensing | Environmental and spatial dimension: geographic variability, environmental conditions, and ecological context of food-safety risk. |
| Ruth Nichols | Mathematical and biological sciences | Quantitative and biological interpretation: complex-systems reasoning, integrating forms of scientific evidence, and recognizing uncertainty in biological observations. |

### Member contributions

**Akhilesh Sharma - Project Lead, Research and Technical Development.** Akhilesh led the conceptualization, research, technical development, and implementation of VulneraSafe AI. Building on his doctoral research at Cornell University and prior industry experience at Bayer, he designed the overall architecture and developed the data integration, pathogen surveillance, predictive modeling, validation, and decision-support components, and implemented the interactive web application using AWS Kiro. A central focus was moving beyond pathogen-risk prediction to actionable recommendations that consider food availability, population vulnerability, and uncertainty.

**Hannah Zonnevylle - Environmental Science and Spatial Ecology.** Hannah is a Ph.D. student and NSF Graduate Research Fellow whose research examines environmental variability and ecological processes using remote sensing. Her expertise anchors the environmental and spatial dimension - geographic variability, environmental conditions, and the broader ecological context of food-safety risk.

**Ruth Nichols - Mathematical and Biological Sciences.** Ruth holds degrees in Mathematical Sciences and Astrobiology from Florida Institute of Technology, with research spanning chemical ecology, astrobiology, and biological systems. Her background anchors the quantitative and biological dimensions - interpreting complex systems, integrating different forms of scientific evidence, and recognizing uncertainty in biological observations.

**Disciplines covered:** AI / data science, environmental science / remote sensing, mathematical and biological sciences. **Honest gaps (not faked):** a practicing retail supply-chain / logistics operations professional, a veterinary / agricultural production specialist, and a credentialed epidemiologist are disciplines the team did not directly cover and are declared as gaps for future collaboration.

## Scientific approach and integration

The central idea was to treat food safety as an interconnected systems problem rather than an isolated prediction task, integrating pathogen surveillance with environmental information, geographic variation, and population vulnerability. Within the compressed timeline, development was primarily led by Akhilesh, which kept the pipeline, modeling framework, decision logic, and application consistent. The interdisciplinary scope shows up in three areas: environmental and spatial context; quantitative and biological interpretation of sampling, uncertainty, and surveillance limits; and applied AI translating results into interventions that weigh food security, equitable access, and food loss.

## Added datasets (Req 17.2)

Two external datasets beyond the FSIS core, with a food-security/vulnerability dataset among them: **US Census ACS** (population, elderly-65+ share) and **USDA Food Access Research Atlas** (low-income / low-access tract shares). Also integrated: **NOAA nClimDiv** statewide monthly climate (environmental leg) and **CDC NORS** human-health outbreak surveillance (S05, lagged corroboration).

## Added-data ablation with quantitative difference (Req 17.3) - REAL numbers

Four configurations per pathogen (FSIS-only, FSIS+CDC, FSIS+NOAA, full), same chronological train split, same untouched test set. Primary metric PR-AUC; marginal contribution is the signed change vs FSIS-only (negatives preserved). Source: docs/reports/ablation.md and web/public/data/ablation_results.json.

Pathogen | FSIS-only PR-AUC | FSIS+NOAA delta | Full PR-AUC | Full delta vs FSIS-only
---|---|---|---|---
Salmonella | 0.5102 | +0.0211 | 0.5172 | +0.0070
Listeria | 0.7437 | -0.0076 | 0.7384 | -0.0053
STEC | 0.4102 | +0.0050 | 0.4329 | +0.0227

Honest findings: NOAA weather helps Salmonella (+0.0211) and STEC (+0.0050) but is slightly negative for Listeria (-0.0076), consistent with RTE Listeria being process-driven; adding every group (full) helps STEC most (+0.0227) but slightly dilutes Salmonella/Listeria vs their best single addition - more features is not always better with limited positives.

## A real decision changed by interdisciplinary input (Req 17.4)

One important decision was to move beyond a system that simply ranks establishments by pathogen-risk estimates. That alone would have overlooked the consequences of restricting or delaying food distribution. Considering the problem from environmental-systems, biological-sciences, and quantitative-modeling perspectives highlighted the need to account for geographic variability, uncertainty in surveillance data, and the vulnerability of communities affected by supply-chain decisions.

As a result the design expanded to incorporate population vulnerability, food-security considerations, and alternative intervention scenarios. Rather than recommending actions from elevated pathogen-risk signals alone, the platform lets users explore how decisions balance food safety, food availability, and equitable access - transforming VulneraSafe AI from a risk-monitoring dashboard into a broader One Health decision-support platform.

Two further evidence-driven reversals: (1) a one-step-ahead emerging-spike forecast (S04/S05) was built, failed to beat a naive persistence baseline (precision 0.03-0.08), and was withheld rather than shipped as an unvalidated PREDICTED layer; (2) establishment and vulnerability rankings moved from raw positivity/shares to a beta-binomial Empirical-Bayes posterior (S03) with the hazard fixed read-only (S06) after the raw approach proved measurably misleading. Choosing a modest honest result over an impressive unvalidated one was a deliberate call.

## Future partner / dataset recommendations (Req 17.5)

1. **PulseNet WGS access via a participating public-health lab** - to replace lagged NORS corroboration with timely, laboratory-confirmed human-health signal.
2. **USDA FSIS Recall / Public Health Alert API** once reliably reachable - the FDA-jurisdiction openFDA food enforcement recall feed is already integrated as real regulatory evidence, but the USDA FSIS meat/poultry recall feed is WAF-blocked (HTTP 403) here; reaching it would fold FSIS-jurisdiction recalls in alongside the FDA ones.
3. **State health-department line-level surveillance** - finer-grained geography and timing than statewide aggregates allow.

---

*All statements are traceable to real people or real project artifacts. Added datasets, ablation numbers, and design decisions are drawn from the actual pipeline and docs/reports/ablation.md. Team roster and contributions are real (Req 17.1, 17.4).*

