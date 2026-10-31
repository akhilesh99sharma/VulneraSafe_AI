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
    python -m src.artifacts.exporter                    (writes web/public/data/*.json + manifest.json)

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
- data/raw, data/interim, and data/processed are git-ignored; only the final
  web/public/data artifacts are committed, so the deployed site needs no raw data.
- All figures are OBSERVED surveillance or documented context — never fabricated.
  See each module's spec under .kiro/specs/ for its honesty constraints.
