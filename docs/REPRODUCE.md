# Reproducing the VulneraSafe AI analysis

Raw source data (about 230 MB of public-domain US government datasets) is NOT
committed, to keep the repository lightweight. All raw data is freely
re-fetchable. The committed web/public/data/*.json artifacts are what the
deployed site renders; the steps below regenerate them from scratch.

## 1. Environment

Create a virtual environment and install dependencies:

    python -m venv .venv
    .venv\Scripts\activate        (Windows)   or   . .venv/bin/activate  (macOS/Linux)
    pip install -r requirements.txt

Copy .env.example to .env and add a free Census API key
(https://api.census.gov/data/key_signup.html). NOAA is token-free by default.

## 2. Fetch raw data into data/raw/

FSIS laboratory sampling (Salmonella / Listeria / STEC per-fiscal-year ZIPs):
download from USDA FSIS Laboratory Sampling Data
(https://www.fsis.usda.gov/science-data/data-sets-visualizations) into
data/raw/raw_poultry_sampling_data/, data/raw/rte_sampling_data/, and
data/raw/raw_beef_sampling_data/.

CDC NORS foodborne outbreaks (about 7 MB):

    curl -L -o data/raw/cdc_nors_outbreaks.csv "https://data.cdc.gov/api/views/5xkq-dg7x/rows.csv?accessType=DOWNLOAD"

ACS and USDA Food Access Atlas: fetched by the ingest pipeline using the Census
key (ACS) and the public Atlas file (see src/pipeline/ingest.py).

## 3. Run the analysis and regenerate artifacts

    python -m src.analysis.program_product              (S01 product/program stratification)
    python -m src.analysis.emerging_risk                (S04 persistent vs emerging)
    python -m src.analysis.establishment_surveillance   (S03 establishment EB surveillance)
    python -m src.analysis.human_comparison             (S05 FSIS vs CDC NORS; needs the NORS CSV)
    python -m src.analysis.community_impact             (S06 vulnerability-aware ranking)
    python -m src.decision.action_queue                 (Surveillance Actions decision layer -> action_queue.json)
    python scripts/build_county_vulnerability.py        (S07 offline county ACS + USDA Atlas -> committed data/processed/county_vulnerability.json; needs CENSUS_API_KEY)
    python -m src.analysis.county_community_impact      (S07 county vulnerability x state-level hazard -> s07_county_community_impact.json)
    python -m src.artifacts.exporter                    (writes web/public/data/*.json + manifest.json)

The exporter now writes 28 files, including action_queue.json, facility_map.json,
and county_community_impact.json alongside the original artifacts and manifest.json.

Facility Map geocode cache: the committed data/external/facility_geocode.json is built
once by `python scripts/build_facility_geocode.py` from the FSIS MPI Directory CSVs
dropped into data/raw/fsis/ (the FSIS host is firewalled in this environment, so the
MPI Directory is a manual drop like the other FSIS data). The runtime exporter reads
ONLY the committed geocode cache and makes no network geocode call; build_facility_map,
build_action_queue, and build_county_community_impact all run as part of the exporter.

Because data/processed/county_vulnerability.json is committed, a reviewer WITHOUT a
Census key still gets the real county vulnerability table: the S07 compute step reads
the committed table rather than re-pulling ACS/Atlas.

## 4. Verify

    python -m pytest
    cd web
    npm ci
    npm run test
    npm run build

## 5. Run the site locally

    cd web
    npm run dev

Then open http://localhost:5173/VulneraSafe_AI/

## Notes

- The analysis modules reuse each other: S05 and S06 read the FSIS state series
  built by S04, and S03 reuses the establishment panel from src/models/establishment.py.
  Run them in the order above (or just run the exporter, which triggers the
  builders that read each module's cache).
- data/raw, data/interim, and most of data/processed are git-ignored; the
  committed web/public/data artifacts are what the deployed site renders, so it
  needs no raw data. Two small DERIVED inputs are committed for reproducibility via
  explicit .gitignore exceptions: data/external/facility_geocode.json (FSIS MPI
  Directory coordinates) and data/processed/county_vulnerability.json (county ACS +
  USDA Atlas), so the Facility Map and County Communities tabs reproduce without a
  Census key or the 85 MB Atlas download.
- All figures are OBSERVED surveillance or documented context — never fabricated.
  See each module's spec under .kiro/specs/ for its honesty constraints.
