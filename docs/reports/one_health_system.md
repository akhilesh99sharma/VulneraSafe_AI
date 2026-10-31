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
- Status: PLACEHOLDER. The `cdc_*_lag1` feature columns exist but are not truly joined and
  are currently constant. Honest integration with explicit reporting-lag handling is a
  named next step so the human-illness signal is never overstated.

### 2. Food / animal pathway (core signal)
- Signal: pathogen positivity in food-production establishments.
- Datasets: USDA FSIS establishment sampling - Raw Poultry (Salmonella), RTE (Listeria),
  Raw Beef (STEC). ~823K sampling records FY2014-2026.
- Status: COMPLETE and primary. Binary result + quantitative MPN/CFU. No serotype/WGS,
  so no strain-level attribution is claimed.

### 3. Environmental pathway
- Signal: climate conditions associated with pathogen growth/survival.
- Dataset: NOAA weather (temperature, precipitation, anomalies).
- Status: THIN. Currently a single NY station; replacement with NOAA nClimDiv state-level
  monthly climate is pending. Weather features are flagged "safe but sparse".

### 4. Supply-chain pathway
- Signal: product movement, lot isolation, and replacement allocation.
- Dataset: seeded Synthetic_Operational_Network (isolated under `data/synthetic/`, every
  record labeled SIMULATED) plus the firewalled FSIS Recall feed as an independent
  regulatory-evidence channel.
- Status: synthetic network drives the decision optimizer; recalls are a pending
  independent channel (HTTP 403 at ingest).

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
