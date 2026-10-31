# Team Science Statement

> STATUS: Team-member identities and any stakeholder attribution are **clearly
> flagged placeholders pending real team input** (kept honest per Req 17.5 — do
> not fabricate people). Added datasets, the added-data ablation numbers, and the
> future-partner recommendations below are **real, project-traceable facts** drawn
> from the actual pipeline and `docs/reports/ablation.md` /
> `web/public/data/ablation_results.json`.
>
> UPDATE: this statement now also reflects the science-first expansion modules
> (S01/S03/S04/S05/S06); the dataset, ablation, and decision facts below are real
> and project-traceable. Only team-member identities remain placeholders.

## Team members and disciplines (Req 17.1) — PLACEHOLDER, pending real info

The real team roster and contribution mapping has not yet been supplied, so it is
left as placeholders rather than invented. Replace each bracketed field with a
real person and their genuine contribution before submission.

| Member | Discipline covered | Genuine contribution |
|---|---|---|
| [Member 1 — name/discipline TBD] | [machine learning / data science?] | [specific contribution TBD] |
| [Member 2 — name/discipline TBD] | [food-safety science?] | [specific contribution TBD] |
| [Member 3 — name/discipline TBD] | [epidemiology / public health?] | [specific contribution TBD] |
| [Member 4 — name/discipline TBD] | [software / frontend?] | [specific contribution TBD] |

Disciplines in scope for this challenge: food-safety science, epidemiology,
agriculture and environment, machine learning and data science, geospatial
analysis, retail supply-chain operations, and food access and equity.

**Uncovered-discipline gaps (flagged, not faked):** until the real roster is
provided, every discipline above is treated as an **open gap**. Disciplines most
likely to be genuinely uncovered and that should be declared as gaps include a
practicing **retail supply-chain / logistics operations** professional, a
**veterinary / agricultural production** specialist, and a credentialed
**epidemiologist** — these must be listed as gaps, not attributed to a
fabricated specialist.

## Added datasets (Req 17.2 — two real, beyond FSIS core)

Both are real streams integrated into the pipeline beyond the minimal FSIS core:

1. **NOAA nClimDiv — statewide monthly climate** (NOAA/NCEI). Domain:
   environment. Added to test whether temperature/precipitation signals improve
   near-term pathogen-risk prediction (the environmental leg of One Health). What
   it changed: it is the source of the `weather_*` features whose marginal value
   is measured directly in the ablation below.
2. **US Census ACS 5-year** (American Community Survey). Domain: food access and
   equity / demographics. Added to supply the vulnerable-population context
   (elderly-65+ share, socioeconomic indicators) used for equity-aware allocation
   and folded into the `full` configuration as `static_*` features.

Also integrated: **CDC NORS** human-health outbreak surveillance (lagged
corroboration, honestly reported as a feature gap — see ablation) and the **USDA
Food Access Research Atlas** (low-income/low-access tract shares, part of the
`static_*` context block).

**Update (science-first expansion):** CDC NORS moved from a declared feature-gap
to a **real, integrated comparison** in S05 (One Health Insights): the public CDC
NORS foodborne-outbreak dataset (data.cdc.gov `5xkq-dg7x`) was downloaded and
compared against FSIS surveillance at state x year as lagged corroboration. It is
still NOT a predictive feature in the hazard model — the integration is honest
corroboration, closing the human-health leg of One Health that was previously a
placeholder.

## Added-data ablation with a quantitative difference (Req 17.3) — REAL numbers

Exactly four configurations per pathogen (FSIS-only, FSIS+CDC, FSIS+NOAA, full),
each trained with the pathogen's best model on the **same** chronological train
split and scored on the **same** untouched held-out test set. Primary metric:
**PR-AUC**; marginal contribution is the **signed** change vs FSIS-only (negatives
preserved, never clamped). Source:
`docs/reports/ablation.md` / `web/public/data/ablation_results.json`.

| Pathogen | FSIS-only PR-AUC | FSIS+NOAA Δ | Full PR-AUC | Full Δ vs FSIS-only |
|---|---|---|---|---|
| Salmonella | 0.5208 | +0.0000 | 0.5484 | **+0.0276** |
| Listeria | 0.3218 | −0.0120 | 0.3396 | **+0.0178** |
| STEC | 0.3011 | −0.0028 | 0.3114 | **+0.0103** |

Honest findings from the real measurement:
- Adding **all** context (full) improved PR-AUC for every pathogen, most for
  Salmonella (+0.0276).
- **NOAA weather alone did not help** — its marginal PR-AUC was 0.0000
  (Salmonella) or slightly **negative** (Listeria −0.0120, STEC −0.0028), caused
  by thin ingested station coverage leaving `weather_*` mostly NaN.
- **FSIS+CDC is a declared gap**: no CDC human-health features were joined into
  the feature matrix, so its contribution is **not evaluable** and is recorded as
  a gap (n/a) rather than a fabricated delta.

## A real decision changed by a team member/stakeholder (Req 17.4) — PLACEHOLDER

A genuine design decision was made during the project, but it **cannot yet be
attributed to a named real team member or stakeholder**, so the attribution is
left as a flagged placeholder rather than fabricated:

- **Input source:** [stakeholder/team-member role TBD — pending real team input]
- **Prior decision:** the added `weather_*` (NOAA) features were assumed to carry
  predictive value and were slated to stay in the headline model.
- **Revised decision:** after the ablation measured a near-zero / negative NOAA
  marginal (above), NOAA weather was demoted from a claimed predictive driver to
  an honestly-reported non-contributor, and the thin-coverage limitation was
  documented rather than hidden.

A second, independent evidence-driven reversal came from the expansion modules:
- **Prior decision:** S04 (Emerging Signals) and S05 were expected to deliver a
  forward-looking forecast of emerging pathogen spikes.
- **Revised decision:** a one-step-ahead forecast was built and evaluated against
  a naive persistence baseline. It did not beat persistence (precision 0.03–0.08
  across pathogens), so the PREDICTED forecast layer was **withheld entirely**
  and both modules were shipped as rigorous retrospective/descriptive layers with
  stated uncertainty. Choosing to publish a modest honest result over an
  impressive unvalidated one is itself a deliberate, evidence-driven call.
- **Prior decision:** establishment and vulnerability rankings would use raw
  positivity / raw shares.
- **Revised decision:** after seeing how thinly-sampled establishments produced
  spurious extremes, S03 switched to a beta-binomial Empirical-Bayes posterior
  (shrinkage toward the peer rate) and S06 fixed the hazard as read-only so a
  vulnerability lens can never distort it — both changes made because the raw
  approach was measurably misleading.

This decision is real and traceable to the ablation artifact; only the
person/role behind it is a placeholder until the real roster is supplied.

## Future partner / dataset recommendations (Req 17.5) — real, traceable gaps

1. **PulseNet WGS access via a participating public-health lab** — to replace the
   lagged NORS corroboration with timely, laboratory-confirmed human-health
   signal (closes the FSIS+CDC ablation gap above).
2. **FSIS Recall / Public Health Alert API** once reliably reachable — to fold
   verified regulatory recalls in as independent evidence.
3. **State health-department line-level surveillance** — finer-grained geography
   and timing than statewide aggregates allow.

---

*Within one page (Req 17.6). Only statements traceable to a real source or real
project artifact are stated as fact; team-member identities and the stakeholder
attribution above are explicitly flagged placeholders pending real team input.*
