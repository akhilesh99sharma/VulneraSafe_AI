"""One-pass data inventory extractor for Task 2.10.

Reads parquet schemas/shapes/heads (no full stats loops) and computes
missing%/n_unique/numeric-stats from ONE representative FY file per FSIS
program plus the ACS/Atlas/processed tables. Emits scripts/inventory_data.json.

Run ONCE:
    python scripts\\inventory.py > scripts\\inventory.out.txt 2>&1
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
OUT = ROOT / "scripts" / "inventory_data.json"

result: dict = {"parquet": {}, "fsis_fy": {}, "acs": {}, "atlas": {}, "errors": []}


def jsan(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, pd.Timestamp):
        return str(o)
    return str(o)


def col_stats(s: pd.Series, low_card: int = 12) -> dict:
    n = len(s)
    miss = s.isna().sum()
    out = {
        "dtype": str(s.dtype),
        "missing_pct": round(100.0 * miss / n, 2) if n else None,
        "n_unique": int(s.nunique(dropna=True)),
    }
    # numeric?
    num = pd.to_numeric(s, errors="coerce")
    non_null_num = num.notna().sum()
    is_num = non_null_num > 0 and (non_null_num >= 0.5 * (n - miss) if (n - miss) else False)
    if is_num and str(s.dtype) != "object" or (is_num and out["n_unique"] > low_card):
        v = num.dropna()
        if len(v):
            out["numeric"] = {
                "min": float(v.min()), "max": float(v.max()),
                "mean": round(float(v.mean()), 4), "median": float(v.median()),
                "p25": float(v.quantile(0.25)), "p75": float(v.quantile(0.75)),
            }
    if out["n_unique"] <= low_card:
        vc = s.dropna().astype(str).value_counts().head(low_card)
        out["top_values"] = {str(k): int(vv) for k, vv in vc.items()}
    return out


# --- 1. Parquet shapes + schema + head (ONE read each) --------------------- #
for name in [
    "features_salmonella", "features_listeria", "features_stec",
    "model_salmonella", "model_listeria", "model_stec",
    "harmonized_salmonella", "harmonized_listeria", "harmonized_stec",
]:
    p = PROC / f"{name}.parquet"
    try:
        df = pd.read_parquet(p)
        info = {
            "rows": int(df.shape[0]),
            "cols": int(df.shape[1]),
            "columns": list(df.columns),
        }
        # period range if present
        if "period" in df.columns:
            per = df["period"].dropna().astype(str)
            info["period_min"] = per.min() if len(per) else None
            info["period_max"] = per.max() if len(per) else None
        if "quarter" in df.columns:
            q = df["quarter"].dropna().astype(str)
            info["quarter_min"] = q.min() if len(q) else None
            info["quarter_max"] = q.max() if len(q) else None
        # label counts for model tables
        for lc in ("y_elevated", "y_elevated_v2", "labelable", "labelable_v2"):
            if lc in df.columns:
                s = df[lc]
                info[f"{lc}_value_counts"] = {
                    str(k): int(v) for k, v in s.value_counts(dropna=True).items()
                }
        result["parquet"][name] = info
    except Exception as e:  # noqa: BLE001
        result["errors"].append(f"{name}: {e}")


# --- 2. ONE representative FY per FSIS program ----------------------------- #
# Use FY2023 (mature, full columns) for each program.
fsis_rep = {
    "raw_poultry_salmonella": RAW / "raw_poultry_sampling_data" / "raw_poultry_sampling_data_fy2023.zip",
    "rte_listeria": RAW / "rte_sampling_data" / "rte_sampling_data_fy2023.zip",
    "raw_beef_stec": RAW / "raw_beef_sampling_data" / "raw_beef_sampling_data_fy2023.zip",
}
for prog, zp in fsis_rep.items():
    try:
        import hashlib
        with zipfile.ZipFile(zp) as zf:
            inner = [n for n in zf.namelist() if n.endswith(".json")][0]
            with zf.open(inner) as fh:
                data = json.load(fh)
        df = pd.DataFrame(data)
        # coerce any non-scalar cells to string so stats never hit unhashable dicts
        for c in df.columns:
            if df[c].map(lambda v: isinstance(v, (dict, list))).any():
                df[c] = df[c].map(lambda v: json.dumps(v) if isinstance(v, (dict, list)) else v)
        stats = {"rep_file": zp.name, "inner": inner, "rows": int(len(df)),
                 "cols": int(df.shape[1]), "columns": {}}
        for c in df.columns:
            stats["columns"][c] = col_stats(df[c])
        # 5 representative rows with establishment ids masked
        head = df.head(5).copy()
        for mcol in ("establishment_id", "establishment_number", "establishment_name"):
            if mcol in head.columns:
                head[mcol] = head[mcol].astype(str).map(
                    lambda x: "EST_" + hashlib.sha1(x.encode()).hexdigest()[:8]
                )
        stats["sample_rows"] = json.loads(head.to_json(orient="records"))
        result["fsis_fy"][prog] = stats
    except Exception as e:  # noqa: BLE001
        import traceback
        result["errors"].append(f"{prog}: {e} :: {traceback.format_exc()[-300:]}")
    # checkpoint write after each program so partial progress survives
    OUT.write_text(json.dumps(result, indent=2, default=jsan), encoding="utf-8")


# --- 3. ACS + Atlas raw ---------------------------------------------------- #
try:
    acs_p = RAW / "census" / "acs5_2022.json"
    acs = json.load(open(acs_p))
    # ACS api returns list-of-lists with header row
    if isinstance(acs, list) and acs and isinstance(acs[0], list):
        hdr = acs[0]
        adf = pd.DataFrame(acs[1:], columns=hdr)
    else:
        adf = pd.DataFrame(acs)
    result["acs"] = {
        "file": "acs5_2022.json", "rows": int(len(adf)), "cols": int(adf.shape[1]),
        "columns": list(adf.columns),
        "sample_rows": json.loads(adf.head(5).to_json(orient="records")),
    }
except Exception as e:  # noqa: BLE001
    result["errors"].append(f"acs: {e}")

try:
    atlas_p = RAW / "food_access" / "lram_2019_xlsx.xlsx"
    # read only a slice of columns/rows to avoid heavy load
    xl = pd.ExcelFile(atlas_p)
    # pick the biggest data sheet (not the Read Me / lookup)
    data_sheet = None
    for s in xl.sheet_names:
        if "read me" in s.lower() or "lookup" in s.lower():
            continue
        data_sheet = s
        break
    data_sheet = data_sheet or xl.sheet_names[-1]
    adf = xl.parse(data_sheet, nrows=5)  # header + 5 rows only (fast)
    result["atlas"] = {
        "file": "lram_2019_xlsx.xlsx", "sheet": data_sheet,
        "all_sheets": xl.sheet_names,
        "cols": int(adf.shape[1]),
        "columns": list(map(str, adf.columns))[:80],
        "sample_rows": json.loads(adf.astype(str).head(5).to_json(orient="records")),
    }
except Exception as e:  # noqa: BLE001
    result["errors"].append(f"atlas: {e}")


OUT.write_text(json.dumps(result, indent=2, default=jsan), encoding="utf-8")
print("WROTE", OUT)
print("errors:", result["errors"])
for k, v in result["parquet"].items():
    print(k, v.get("rows"), "x", v.get("cols"))
print("ACS rows", result["acs"].get("rows"), "Atlas rows_est", result["atlas"].get("rows_est"))
