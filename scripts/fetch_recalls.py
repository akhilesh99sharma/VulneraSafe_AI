"""One-time offline fetch of real food-recall records from the openFDA food
enforcement API (FDA jurisdiction), filtered to the VulneraSafe pathogens, and
cached to data/raw/recalls/ for reproducible offline builds.

IMPORTANT (honesty): openFDA /food/enforcement covers FDA-regulated foods. The
USDA FSIS meat/poultry/egg recall feed (fsis.usda.gov/fsis/api/recall) is behind
a WAF that returns 403 to non-browser clients in this environment, so true FSIS
meat/poultry recalls cannot be retrieved here. These FDA recalls are for the SAME
pathogens and are labeled as FDA-jurisdiction, with that caveat recorded.
"""
from __future__ import annotations
import json, urllib.request, urllib.parse
from pathlib import Path
from datetime import date

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "data" / "raw" / "recalls"
OUT = OUT_DIR / "openfda_food_enforcement.json"

BASE = "https://api.fda.gov/food/enforcement.json"
# Our pathogens; openFDA reason_for_recall is free text so we OR the terms.
SEARCH = 'reason_for_recall:(listeria+salmonella+coli)+AND+status:"Ongoing"'
LIMIT = 50

def fetch() -> dict:
    q = "?search=" + SEARCH + "&limit=" + str(LIMIT) + "&sort=report_date:desc"
    url = BASE + q
    req = urllib.request.Request(url, headers={"User-Agent": "VulneraSafe-AI/1.0 (offline cache build)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))

def main() -> None:
    data = fetch()
    results = data.get("results", [])
    meta = data.get("meta", {})
    payload = {
        "source": "openFDA food enforcement API",
        "source_url": BASE,
        "jurisdiction": "FDA (US Food and Drug Administration)",
        "jurisdiction_caveat": (
            "openFDA food enforcement covers FDA-regulated foods. USDA FSIS "
            "meat/poultry/egg recalls use a separate feed that is WAF-blocked "
            "(HTTP 403) for non-browser clients in this environment and could "
            "not be retrieved. These recalls are for the same pathogens but are "
            "FDA-jurisdiction, not FSIS."
        ),
        "pathogen_filter": "listeria OR salmonella OR coli; status Ongoing",
        "fetched_at": date.today().isoformat(),
        "openfda_last_updated": meta.get("last_updated"),
        "total_matching": meta.get("results", {}).get("total"),
        "count_cached": len(results),
        "results": results,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("WROTE", OUT, "count", len(results), "of total", payload["total_matching"])

if __name__ == "__main__":
    main()
