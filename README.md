# VulneraSafe AI — Predict the Hazard. Protect the Vulnerable.

A multi-pathogen, vulnerability-aware, One Health food-safety early-warning and
operational decision-support platform for the 2026 NAFSI Hub SENS-D Data Challenge.

**Primary decision-maker:** Food Safety Operations Director of a regional grocery retail chain.
**Pathogens:** Salmonella (raw poultry, primary), Listeria (RTE meat/poultry), STEC (raw beef).

The platform pairs a reproducible Python analysis layer (One Health data integration,
predictive modeling, and safety-constrained operational optimization) with a static
React/TypeScript/Vite web application that reads precomputed, validated JSON artifacts.
All reported numbers come from real data sources; model-generated outputs were reviewed,
and synthetic operational data is isolated and clearly labeled `SIMULATED`.

---

## Repository layout

| Path | Contents |
|---|---|
| `src/` | Python analysis layer — `pipeline/` (ingest, harmonize, align), `models/` (baseline + integrated risk models), `decision/` (safety-constrained optimizer, scenarios), `artifacts/` (exporter + schemas), `responsible.py` (interpretation guardrails). |
| `requirements.txt` | Pinned Python dependencies. |
| `web/` | React 18 + TypeScript + Vite + Tailwind decision-support app. Reads artifacts from `web/public/data/*.json`. |
| `docs/` | Data dictionary, provenance, team science, and reports (`docs/reports/`). |
| `.kiro/specs/vulnerasafe-ai/` | Kiro spec: `requirements.md`, `design.md`, `tasks.md`. |
| `.github/workflows/deploy.yml` | GitHub Pages deploy workflow (build-and-deploy). |
| `data/` | Interim and processed analytic tables, model artifacts, and reports. |

---

## Build and deploy instructions

The project has two layers. The Python layer regenerates the analytic artifacts; the
web layer renders them. You can run either independently once the artifacts exist under
`web/public/data/`.

### Layer 1 — Python analysis (pipeline, models, exporter, tests)

1. **Create and activate a virtual environment** (Python 3.11+ recommended):

   ```bash
   python -m venv .venv
   # Windows (PowerShell)
   .venv\Scripts\Activate.ps1
   # macOS / Linux
   source .venv/bin/activate
   ```

2. **Install pinned dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

3. **Regenerate the web artifacts** (reads the pipeline/model outputs under `data/`
   and writes the validated JSON the app consumes to `web/public/data/*.json`):

   ```bash
   python -m src.artifacts.exporter
   ```

4. **Run the test suite** (unit + property-based tests):

   ```bash
   python -m pytest
   ```

Artifacts are reproducible: the pipeline and models run from fixed random seeds, so
rerunning the exporter on the same inputs produces the same artifacts.

### Layer 2 — Web application (React / TypeScript / Vite)

All web commands run from the `web/` directory.

1. **Install dependencies** (Node 18+ or 20 recommended; from a clean lockfile):

   ```bash
   cd web
   npm ci
   ```

2. **Start the dev server:**

   ```bash
   npm run dev
   ```

   Open **`http://localhost:5173/VulneraSafe_AI/`**. The `/VulneraSafe_AI/` base path is
   required — Vite is configured with `base: "/VulneraSafe_AI/"` so artifact fetches resolve
   under that path. The app will not load correctly at the bare root `/`.

3. **Production build** (runs `tsc -b` then `vite build`, output to `web/dist/`):

   ```bash
   npm run build
   ```

> Local note: if `node`/`npm` are not on your PATH (for example a Windows install under
> `C:\Program Files\nodejs`), add that directory to PATH or call the binaries by full path.
> Standard instructions above assume `node` and `npm` are available.

### Deploy to GitHub Pages

A deploy workflow is committed at `.github/workflows/deploy.yml`. It builds the web app and
publishes `web/dist/` to GitHub Pages.

The site goes live **only after** you:

1. Push the repository to GitHub.
2. In the repository, open **Settings → Pages** and set the **Source** to **"GitHub Actions"**.
3. Let the `deploy` workflow run to completion.

**Deployment has not been verified live.** Do not treat the hosted site as available until the
steps above have been completed and the workflow has succeeded.

---

## Reproducibility requirements

To reproduce the analysis and rebuild the application from scratch:

- **Python:** 3.11 or newer.
- **Python dependencies:** `pip install -r requirements.txt` (versions pinned:
  scikit-learn, xgboost, lightgbm, shap, pandas, numpy, pyarrow, ortools, pytest,
  hypothesis, requests, openpyxl, pypdf).
- **Node.js:** 18+ or 20; install web dependencies with `npm ci` in `web/`.
- **Regenerate artifacts:** `python -m src.artifacts.exporter` → writes `web/public/data/*.json`.
- **Rebuild the app:** `npm run build` in `web/` (or `npm run dev` for local preview at
  `http://localhost:5173/VulneraSafe_AI/`).
- **Verify:** `python -m pytest` for the analysis layer.
- **Fixed-seed guarantee:** pipeline and model steps use fixed random seeds, so artifacts
  regenerate deterministically from the same inputs.

---

## AI-assistance disclosure

This project was built with AI-assisted development using **AWS Kiro** (an agentic
spec-driven workflow with steering files and hooks). AI assistance contributed to:

- scaffolding and drafting code across the Python analysis layer and the web application,
- drafting documentation and report prose, and
- generating and refining the Kiro spec (requirements, design, tasks).

All input data is **real**, drawn from documented public sources (see `docs/provenance.md`).
All model-generated outputs, metrics, and report claims were **reviewed** by the team, and
synthetic operational data is isolated and labeled `SIMULATED` rather than presented as
observed. The analysis reasoning and decisions reflect the team's own judgment; AI assistance
accelerated implementation and drafting, it did not substitute for data or for review. This
disclosure is intentionally neither over- nor under-stated.

---

## Submission package — six-component checklist

Status of the six required submission components (Req 18.1, 18.6). Present components are on
disk; pending items are user-completed steps and are flagged honestly rather than claimed
complete.

| # | Component | Path(s) | Status |
|---|---|---|---|
| 1 | Reproducible analysis scripts/pipeline | `src/`, `requirements.txt` | **Present** |
| 2 | Kiro artifacts / spec | `.kiro/specs/vulnerasafe-ai/` (`requirements.md`, `design.md`, `tasks.md`) | **Present** |
| 3 | Decision-support application | `web/` (deployed Pages site pending — see deploy steps) | **Present (not yet deployed live)** |
| 4 | Data dictionary + provenance | `docs/data_dictionary.md`, `docs/provenance.md` | **Present** |
| 5 | Final report (answers the 10 questions) | `docs/reports/final_report.md` | **Present (Markdown); PDF export pending** |
| 6 | README + reproducibility list + AI disclosure | `README.md` (this file) | **Present** |

### Items pending completion (not yet done — flagged, not hidden)

- **Team science (`docs/team_science.md`) contains placeholders.** Real team member names,
  disciplines, contributions, and the attributed decision owner must be filled in before
  submission. The dataset/ablation substance is real, but the individual identities are
  placeholders.
- **PDF of the final report is not generated.** `docs/reports/final_report.md` answers all ten
  questions and includes all required sections; exporting it to PDF is a user step.
- **Live GitHub Pages deployment is not verified.** The workflow exists; the site goes live only
  after the user pushes and sets the Pages source to "GitHub Actions".

---

## Further documentation

See `.kiro/specs/vulnerasafe-ai/` for the full requirements, design, and tasks, and `docs/`
for the data dictionary, provenance records, model validation, ablation, feasibility, and the
final report.
