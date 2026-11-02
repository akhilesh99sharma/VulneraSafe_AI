# VulneraSafe AI - One Health System

VulneraSafe AI frames food-safety early warning as a One Health problem: pathogen risk at
the retail level emerges from the interaction of microbial surveillance, human illness,
the environment, the supply chain, and community food security. The platform wires real
datasets to each pathway and makes explicit where a pathway is complete, thin, or pending.

Decision-maker throughout: the retailer Food Safety Operations Director. Recommended
actions are retailer actions (supplier verification, targeted testing, human review,
recall response, replacement allocation) - never government inspection orders.

## The five pathways and their datasets

### 1. Human health pathway
- Signal: reported foodborne outbreaks and illnesses.
- Dataset: CDC NORS (National Outbreak Reporting System).
- Status: INTEGRATED as corroboration (S05 One Health Insights). Real CDC NORS
  foodborne-outbreak data is compared against FSIS surveillance per pathogen x state x
  year with a modeled ~365-day availability lag. It is corroboration only, never a
  real-time predictive feature and never a causal link, so the human-illness signal is
  not overstated.

### 2. Food / animal pathway (core signal)
- Signal: pathogen positivity in food-production establishments.
- Datasets: USDA FSIS establishment sampling - Raw Poultry (Salmonella), RTE (Listeria),
  Raw Beef (STEC). ~823K sampling records FY2014-2026.
- Status: COMPLETE and primary. Binary result + quantitative MPN/CFU. No serotype/WGS,
  so no strain-level attribution is claimed.

### 3. Environmental pathway
- Signal: climate conditions associated with pathogen growth/survival.
- Dataset: NOAA nClimDiv statewide monthly climate (temperature, precipitation, anomalies).
- Status: INTEGRATED with national coverage (~87% of state-periods non-missing), upgraded
  from the earlier single-station demo. Measured marginal value in the ablation: a small
  real lift for Salmonella (+0.0211 PR-AUC) and STEC (+0.0050), slightly negative for
  Listeria (-0.0076) - modest and honestly reported, not a headline driver.

### 4. Supply-chain pathway
- Signal: product movement, lot isolation, and replacement allocation.
- Dataset: seeded Synthetic_Operational_Network (isolated under `data/synthetic/`, every
  record labeled SIMULATED) plus REAL openFDA food-enforcement recalls (FDA jurisdiction)
  as an independent regulatory-evidence channel.
- Status: synthetic network drives the decision optimizer (SIMULATED); recalls are
  integrated from a committed openFDA cache (50 of 382 ongoing listeria/salmonella/E.coli
  recalls). The USDA FSIS meat/poultry recall feed remains WAF-blocked (HTTP 403) here and
  is recorded as an honest gap, not fabricated.

### 5. Food-security pathway
- Signal: community vulnerability and access, so safety actions do not disproportionately
  harm High-Need Communities.
- Datasets: US Census ACS 2022 (population, elderly share) and USDA Food Access Research
  Atlas 2019 (low-income / low-access tract shares).
- Status: COMPLETE as static state-level context features.

## Pathway completeness summary

| Pathway | Dataset(s) | State |
|---|---|---|
| Human health | CDC NORS | PLACEHOLDER (join pending) |
| Food / animal | FSIS (3 programs) | COMPLETE - primary signal |
| Environmental | NOAA weather | THIN (nClimDiv pending) |
| Supply chain | Synthetic network + FSIS recalls | synthetic active; recalls pending |
| Food security | ACS + Food Access Atlas | COMPLETE |

## How the pathways combine
State-and-period surveillance from the food/animal pathway is the prediction backbone.
Environmental and food-security pathways add context features. The human-health pathway
is reserved for honest corroboration once NORS is joined. The supply-chain pathway turns a
risk signal into a constrained, retailer-facing action set, with confirmed recalls acting
as hard constraints independent of model uncertainty, and food-security context ensuring
recommendations remain equitable.
