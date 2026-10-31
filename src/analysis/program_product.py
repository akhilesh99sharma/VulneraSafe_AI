"""S01 — Multi-pathogen product & program stratification (descriptive).

Reads the RAW per-sample FSIS sampling data (the per-fiscal-year ZIPs under
``data/raw/{raw_poultry,rte,raw_beef}_sampling_data/``) and computes OBSERVED
positivity stratified by:

* FSIS sampling program (``project_code`` / ``project_name``),
* sample source (``sample_source_name``),
* product/control category (``product_type`` for Salmonella, ``production_alternative``
  for Listeria; STEC has neither — recorded as unavailable).

For every (pathogen, dimension, category) group it reports the valid-test
denominator, positive count, observed positivity and a Wilson 95% confidence
interval. These are purely OBSERVED historical surveillance figures — no model,
no forecast, no contamination claim. Non-diagnostic / canceled / not-analyzed
rows are excluded; "Confirmed Negative of a Previous Presumptive" counts as a
negative, never a positive.

The heavy raw scan runs offline via :func:`compute_program_product` and is
cached to ``data/interim/s01_program_product.json``; the exporter reads that
cache and shapes the public artifact. Nothing here is fabricated: an absent
dimension for a pathogen yields an explicit ``availability_status`` with a
reason.
"""

from __future__ import annotations

import json
import math
import re
import zipfile
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_ROOT = REPO_ROOT / "data" / "raw"
INTERIM_DIR = REPO_ROOT / "data" / "interim"
CACHE_PATH = INTERIM_DIR / "s01_program_product.json"

MODULE_ID = "S01"
METHOD_VERSION = "s01.v1"

_FY_RE = re.compile(r"fy(\d{4})", re.IGNORECASE)

#: pathogen -> (raw program dir, primary analysis column, product/control column)
_PATHOGEN_CONFIG: dict[str, dict[str, Any]] = {
    "Salmonella": {
        "dir": RAW_ROOT / "raw_poultry_sampling_data",
        "analysis_col": "salmonella_sp_analysis",
        "product_col": "product_type",
        "commodity": "raw_poultry",
    },
    "Listeria": {
        "dir": RAW_ROOT / "rte_sampling_data",
        "analysis_col": "lm_listeria_analysis",
        "product_col": "production_alternative",
        "commodity": "rte",
    },
    "STEC": {
        "dir": RAW_ROOT / "raw_beef_sampling_data",
        "analysis_col": "stec_analysis",
        "product_col": None,  # no product/control category column in raw beef
        "commodity": "raw_beef",
    },
}

#: Diagnostic-result classification. Anything not matched here is NON-diagnostic
#: and excluded from the denominator (lab problems, cancellations, blanks).
_POSITIVE_VALUES = {"positive"}
_NEGATIVE_VALUES = {
    "negative",
    "confirmed negative of a previous presumptive",  # a negative confirmation
}


def _classify_result(value: Any) -> Optional[bool]:
    """Return True (positive), False (negative) or None (non-diagnostic)."""
    if value is None:
        return None
    s = str(value).strip().lower()
    if s == "":
        return None
    if s in _POSITIVE_VALUES:
        return True
    if s in _NEGATIVE_VALUES:
        return False
    # Anything else (lab-problem codes, "25-5 Lab problem...", etc.) is
    # non-diagnostic and excluded — never counted as negative.
    return None


def wilson_ci(positives: int, n: int, z: float = 1.959963984540054) -> tuple[Optional[float], Optional[float]]:
    """Wilson score 95% interval for a binomial proportion. Returns (low, high)
    or (None, None) when n == 0."""
    if n <= 0:
        return (None, None)
    p = positives / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = (z / denom) * math.sqrt(p * (1.0 - p) / n + z * z / (4 * n * n))
    return (max(0.0, center - margin), min(1.0, center + margin))


def _iter_raw_records(program_dir: Path):
    """Yield (fiscal_year, record_dict) for every sample row in a program dir.

    Reuses the FSIS tidy-data layout: each ZIP wraps a JSON whose rows live
    under ``data.primary_table_data``.
    """
    if not program_dir.exists():
        return
    for zip_path in sorted(program_dir.glob("*.zip")):
        m = _FY_RE.search(zip_path.name)
        fy = int(m.group(1)) if m else None
        try:
            with zipfile.ZipFile(zip_path) as z:
                members = [n for n in z.namelist() if n.lower().endswith(".json")]
                for name in members:
                    raw = z.read(name)
                    try:
                        payload = json.loads(raw.decode("utf-8"))
                    except UnicodeDecodeError:
                        payload = json.loads(raw.decode("latin-1"))
                    rows = _primary_records(payload)
                    for r in rows:
                        if isinstance(r, dict):
                            yield fy, r
        except (zipfile.BadZipFile, OSError, ValueError):
            continue


def _primary_records(payload: Any) -> list[dict]:
    """Extract ``data.primary_table_data`` records, tolerant of a few shapes."""
    element = payload
    if isinstance(payload, list):
        if not payload:
            return []
        first = payload[0]
        if isinstance(first, dict) and "data" not in first and "primary_table_data" not in first:
            return [r for r in payload if isinstance(r, dict)]
        element = first
    if not isinstance(element, dict):
        return []
    data = element.get("data", element)
    if isinstance(data, dict):
        primary = data.get("primary_table_data")
        if isinstance(primary, list):
            return [r for r in primary if isinstance(r, dict)]
    return []


def _norm_category(value: Any) -> str:
    """Normalize a category label so casing/whitespace/enumerator variants of the
    same real category merge (e.g. "Alt 3"/"ALT 3"; "a. Breast"/"Breast"). Literal
    "NULL"/blank become the explicit unspecified bucket. This is label cleanup
    only — counts are never invented."""
    if value is None:
        return "(unspecified)"
    s = str(value).strip()
    if s == "" or s.upper() == "NULL":
        return "(unspecified)"
    # strip a leading single-letter/number enumerator like "a. ", "b. ", "1. "
    s = re.sub(r"^[a-zA-Z0-9]{1,2}[.)]\s+", "", s).strip()
    # collapse internal whitespace and upppercase for case-insensitive merge
    s = re.sub(r"\s+", " ", s).upper()
    return s if s else "(unspecified)"


def _tally(records, analysis_col, dim_col):
    """Return {category: {"n": int, "pos": int}} over valid diagnostic rows."""
    out: dict[str, dict[str, int]] = {}
    valid = 0
    for _fy, rec in records:
        verdict = _classify_result(rec.get(analysis_col))
        if verdict is None:
            continue
        valid += 1
        cat = _norm_category(rec.get(dim_col)) if dim_col else "(all)"
        g = out.setdefault(cat, {"n": 0, "pos": 0})
        g["n"] += 1
        if verdict:
            g["pos"] += 1
    return out, valid


def compute_program_product(*, round_to: int = 6) -> dict[str, Any]:
    """Run the full raw-FSIS stratification for all three pathogens.

    Returns a cache-shaped dict (also written to :data:`CACHE_PATH`). This is the
    slow path (reads every raw ZIP); the exporter uses the cache.
    """
    pathogens_out: dict[str, Any] = {}
    for pathogen, cfg in _PATHOGEN_CONFIG.items():
        program_dir: Path = cfg["dir"]
        analysis_col: str = cfg["analysis_col"]
        product_col: Optional[str] = cfg["product_col"]

        # Materialize once (records are modest in size) so we can tally several
        # dimensions without re-reading the ZIPs.
        records: list[tuple[Optional[int], dict]] = list(_iter_raw_records(program_dir))
        total_rows = len(records)
        fiscal_years = sorted({fy for fy, _ in records if fy is not None})

        dims: dict[str, Any] = {}

        # program dimension (project_name preferred, fallback project_code)
        prog_col = "project_name"
        has_prog_name = any(r.get("project_name") for _, r in records)
        if not has_prog_name:
            prog_col = "project_code"
        dims["program"] = _dim_block(records, analysis_col, prog_col, dim_label="program")

        # sample source dimension
        dims["sample_source"] = _dim_block(
            records, analysis_col, "sample_source_name", dim_label="sample_source"
        )

        # product/control dimension (pathogen-specific; may be unavailable)
        if product_col:
            dims["product"] = _dim_block(
                records, analysis_col, product_col, dim_label="product"
            )
        else:
            dims["product"] = {
                "dimension": "product",
                "source_column": None,
                "availability_status": "unavailable",
                "unavailable_reason": (
                    "Raw beef (STEC) sampling records carry no product_type or "
                    "production_alternative column; a product/control breakdown is "
                    "not derivable from the source."
                ),
                "categories": [],
            }

        # overall positivity (single (all) group) for the headline metric card
        overall, overall_valid = _tally(records, analysis_col, None)
        all_group = overall.get("(all)", {"n": 0, "pos": 0})
        lo, hi = wilson_ci(all_group["pos"], all_group["n"])
        pathogens_out[pathogen] = {
            "pathogen": pathogen,
            "commodity": cfg["commodity"],
            "total_rows": total_rows,
            "valid_tests": overall_valid,
            "fiscal_years": fiscal_years,
            "overall": {
                "sample_n": all_group["n"],
                "positive_n": all_group["pos"],
                "value": round(all_group["pos"] / all_group["n"], round_to) if all_group["n"] else None,
                "ci_low": round(lo, round_to) if lo is not None else None,
                "ci_high": round(hi, round_to) if hi is not None else None,
            },
            "dimensions": dims,
            "analysis_column": analysis_col,
        }

    cache = {
        "module_id": MODULE_ID,
        "method_version": METHOD_VERSION,
        "ci_method": "wilson_95",
        "result_mapping": {
            "positive": sorted(_POSITIVE_VALUES),
            "negative": sorted(_NEGATIVE_VALUES),
            "excluded": "all other values (lab problems, cancellations, blanks) are non-diagnostic",
        },
        "pathogens": pathogens_out,
    }
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")
    return cache


def _dim_block(records, analysis_col, dim_col, *, dim_label, round_to: int = 6, min_n: int = 1):
    """Build one dimension block: categories sorted by descending n."""
    tally, _valid = _tally(records, analysis_col, dim_col)
    cats = []
    missing = 0
    for cat, g in tally.items():
        if cat == "(unspecified)":
            missing += g["n"]
        if g["n"] < min_n:
            continue
        lo, hi = wilson_ci(g["pos"], g["n"])
        cats.append(
            {
                "category": cat,
                "sample_n": g["n"],
                "positive_n": g["pos"],
                "value": round(g["pos"] / g["n"], round_to) if g["n"] else None,
                "ci_low": round(lo, round_to) if lo is not None else None,
                "ci_high": round(hi, round_to) if hi is not None else None,
            }
        )
    cats.sort(key=lambda c: (-c["sample_n"], c["category"]))
    total_n = sum(c["sample_n"] for c in cats)
    return {
        "dimension": dim_label,
        "source_column": dim_col,
        "availability_status": "available" if cats else "unavailable",
        "unavailable_reason": None if cats else f"No diagnostic rows carried {dim_col}.",
        "unspecified_n": missing,
        "unspecified_share": round(missing / total_n, round_to) if total_n else None,
        "categories": cats,
    }


def load_cache() -> Optional[dict[str, Any]]:
    """Return the cached S01 result if present, else None."""
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
    return None


if __name__ == "__main__":
    result = compute_program_product()
    for p, d in result["pathogens"].items():
        print(
            f"{p}: rows={d['total_rows']} valid={d['valid_tests']} "
            f"years={d['fiscal_years'][:1]}..{d['fiscal_years'][-1:]} "
            f"overall_pos={d['overall']['value']}"
        )
