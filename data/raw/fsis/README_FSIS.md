# FSIS manual data drop

The FSIS web host (`fsis.usda.gov`) returns **HTTP 403** to the build
environment used for this project, so the FSIS laboratory-sampling and recall
files **cannot be downloaded automatically**. `src/pipeline/ingest.py` falls
back to a **local file importer**: drop the official FSIS files into this
directory and the pipeline will auto-detect, classify, and load them. Nothing
is fabricated — if a file is missing, the pipeline records an honest provenance
gap and continues with the other One Health sources (Req 2.3, 3.7).

## Where to get the files

Official landing page (open in a normal browser):

> https://www.fsis.usda.gov/science-data/data-sets-visualizations/laboratory-sampling-data

Download each of the following datasets (CSV, or ZIP containing CSVs) and save
the file **into this `data/raw/fsis/` directory** with any filename — the
importer classifies by inspecting the columns, not the name:

| Drop into `data/raw/fsis/` | FSIS dataset | Feeds module |
|----------------------------|--------------|--------------|
| Raw poultry sampling CSV/ZIP | **Raw Poultry Sampling Data** (Salmonella + Campylobacter results) | Salmonella in raw poultry (primary predictive) |
| RTE sampling CSV/ZIP | **Ready-to-Eat Meat and Poultry Sampling Data** (Listeria *Lm* + Salmonella results, RTEPROD project codes) | Listeria (RTE) |
| Raw beef STEC CSV/ZIP | **Raw Beef (N60 / trim) STEC Sampling Data** (STEC / O157 results) | STEC in raw beef |
| Recalls JSON/CSV | **FSIS Recall / Public Health Alert** export, saved as `recalls*.json` or `recalls*.csv` | Regulatory-evidence track |

## Notes

- Accepted extensions: `*.csv` and `*.zip` (ZIPs are expanded in memory; any
  `*.csv` inside is read). Recalls may also be dropped as `recalls*.json`.
- The importer records, per file, a `ProvenanceEntry` with a SHA-256 checksum,
  the official source URL above, the access date, the detected dataset class,
  and a note that the file was **manually provided** because the host is
  firewalled in this environment.
- Files placed here are git-ignored except this README and `.gitkeep`.
