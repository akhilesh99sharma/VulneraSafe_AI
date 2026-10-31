"""Per-source One Health data ingestion with provenance and checksums.

This module implements Phase 1, Task 2.1 of the VulneraSafe AI pipeline. Each
One Health source is fetched by an isolated per-source function that:

* downloads / loads raw bytes into ``data/raw/<source>/`` (raw files are kept
  strictly under ``data/raw/`` and never mixed with synthetic data),
* computes a SHA-256 checksum over the bytes (Req 4.1),
* builds a :class:`~src.artifacts.schemas.ProvenanceEntry` describing the
  source, URL, ISO-8601 access date, license, coverage, checksum, counts, a
  missingness placeholder, known biases and notes (Req 4.1, 4.3), and
* **halts only its own stream** on failure or zero records — other sources
  keep going — recording the exact error and manual-download instructions
  (Req 2.3, 3.7).

Nothing is fabricated. When a source is unavailable the loaded data is ``None``
and that is recorded honestly as a provenance gap (Req 4.6).

Design reference: design.md sections "One Health Data Architecture" and
"Per-source ingestion interfaces".

Verified data-access facts baked into the defaults:

* **NOAA** uses the NCEI Access Data Service (token-free JSON) by default; an
  optional CDO v2 path uses ``NOAA_TOKEN`` from the environment when present.
* **USDA Food Access Research Atlas** files are fetched from real
  ``ers.usda.gov`` URLs with a browser User-Agent.
* **US Census ACS** requires ``CENSUS_API_KEY``; absent, ACS is skipped with a
  recorded gap (status ``skipped_no_key``), never a failure of the whole run.
* **FSIS** (``fsis.usda.gov``) is firewalled (HTTP 403) in this environment, so
  the FSIS functions import files the user manually drops into
  ``data/raw/fsis/``; an optional auto-download is attempted first and falls
  back to the local importer on any error.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import io
import json
import os
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional

import pandas as pd
import requests

from src.artifacts.schemas import ProvenanceEntry
from src.pipeline.env import load_dotenv

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

#: Browser-like User-Agent — several public hosts reject the default
#: ``python-requests`` agent, so every outbound request uses this.
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

#: Default network timeout (connect, read) in seconds.
DEFAULT_TIMEOUT = (10, 60)

#: Repository root inferred from this file's location (src/pipeline/ingest.py).
REPO_ROOT = Path(__file__).resolve().parents[2]

#: Raw-data root. Raw files live strictly under here, isolated from synthetic.
RAW_ROOT = REPO_ROOT / "data" / "raw"

#: Interim directory for provenance + report outputs and expanded ZIP members.
INTERIM_ROOT = REPO_ROOT / "data" / "interim"

#: FSIS manual-drop directory.
FSIS_DIR = RAW_ROOT / "fsis"

#: Program -> raw directory mapping for the user-dropped FSIS program archives.
#: Each directory holds one ZIP per fiscal year; each ZIP wraps an FSIS
#: "tidy data" JSON whose sample records live under ``data.primary_table_data``.
#: The directory is the *authoritative* program label (Req: use the known
#: program, not column-sniffing alone), while classify_fsis_dataframe still
#: runs so any mismatch can be flagged in provenance notes.
FSIS_PROGRAM_DIRS: dict[str, Path] = {
    "raw_poultry_salmonella": RAW_ROOT / "raw_poultry_sampling_data",
    "rte_listeria": RAW_ROOT / "rte_sampling_data",
    "raw_beef_stec": RAW_ROOT / "raw_beef_sampling_data",
}

#: Regex extracting the fiscal year from a filename, e.g. ``..._fy2019.zip``.
_FY_RE = re.compile(r"fy(\d{4})", re.IGNORECASE)

#: NCEI Access Data Service base (token-free JSON).
NCEI_ACCESS_BASE = "https://www.ncei.noaa.gov/access/services/data/v1"

#: Optional NOAA CDO v2 base (token required via NOAA_TOKEN).
NOAA_CDO_BASE = "https://www.ncei.noaa.gov/cdo-web/api/v2"

#: NOAA nClimDiv statewide bulk-data directory (token-free HTTP index). The
#: statewide (``*st``) files carry one line per (state, element, year) with 12
#: monthly columns; they are the PRIMARY weather source (national state-level
#: coverage) that replaces the single-station demo path.
NCEI_CLIMDIV_BASE = "https://www.ncei.noaa.gov/pub/data/cirs/climdiv/"

#: nClimDiv statewide element -> filename stem. The version/date suffix of the
#: real files rotates (e.g. ``-v1.0.0-YYYYMMDD``); we resolve the exact filename
#: at run time from the directory index so we never hard-code a stale date.
NCLIMDIV_ELEMENTS: dict[str, str] = {
    "tavg": "climdiv-tmpcst-",   # statewide average temperature (°F)
    "tmax": "climdiv-tmaxst-",   # statewide average maximum temperature (°F)
    "tmin": "climdiv-tminst-",   # statewide average minimum temperature (°F)
    "pcpn": "climdiv-pcpnst-",   # statewide total precipitation (inches)
}

#: Official NCEI nClimDiv statewide state codes (first 3 chars of each data
#: line) -> USPS 2-letter code. The 48 contiguous states are numbered 001-048
#: alphabetically by state name; code 050 is Alaska. Hawaii has NO nClimDiv
#: statewide series (a documented coverage gap, NOT fabricated). Regional /
#: national roll-up codes (101-110, 111+) are intentionally excluded here so
#: only real states are emitted.
NCLIMDIV_STATE_CODE: dict[str, str] = {
    "001": "AL", "002": "AZ", "003": "AR", "004": "CA", "005": "CO",
    "006": "CT", "007": "DE", "008": "FL", "009": "GA", "010": "ID",
    "011": "IL", "012": "IN", "013": "IA", "014": "KS", "015": "KY",
    "016": "LA", "017": "ME", "018": "MD", "019": "MA", "020": "MI",
    "021": "MN", "022": "MS", "023": "MO", "024": "MT", "025": "NE",
    "026": "NV", "027": "NH", "028": "NJ", "029": "NM", "030": "NY",
    "031": "NC", "032": "ND", "033": "OH", "034": "OK", "035": "OR",
    "036": "PA", "037": "RI", "038": "SC", "039": "SD", "040": "TN",
    "041": "TX", "042": "UT", "043": "VT", "044": "VA", "045": "WA",
    "046": "WV", "047": "WI", "048": "WY", "050": "AK",
}

#: CDC NORS (National Outbreak Reporting System) Socrata dataset id, verified
#: live via the data.cdc.gov catalog. State-level, year + month, with etiology
#: and illness/hospitalization/death counts. 1971-2023 coverage.
CDC_NORS_DATASET_ID = "5xkq-dg7x"
CDC_NORS_SODA_BASE = "https://data.cdc.gov/resource"
CDC_NORS_LANDING = "https://data.cdc.gov/Foodborne-Waterborne-and-Related-Diseases/NORS/5xkq-dg7x"

#: US Census ACS 5-year base.
CENSUS_ACS_BASE = "https://api.census.gov/data"

#: Real USDA Food Access Research Atlas file URLs (ers.usda.gov).
FOOD_ACCESS_ATLAS_URLS: dict[str, str] = {
    "lram_2019_xlsx": (
        "https://www.ers.usda.gov/media/5626/"
        "2019-large-retailer-access-map-lram-formerly-known-as-the-"
        "food-access-research-atlas-fara-data.xlsx"
    ),
    "fara_2015_zip": (
        "https://www.ers.usda.gov/media/5623/"
        "2015-food-access-research-atlas-fara-data-and-documentation.zip"
    ),
}

#: Official FSIS landing pages (for provenance + manual instructions).
FSIS_SAMPLING_URL = (
    "https://www.fsis.usda.gov/science-data/data-sets-visualizations/"
    "laboratory-sampling-data"
)
FSIS_RECALL_API_URL = "https://www.fsis.usda.gov/fsis/api/recall/v/1"

#: Status values a per-source result may carry.
Status = Literal["ok", "skipped_no_key", "failed"]

#: FSIS dataset classes recognised by :func:`classify_fsis_dataframe`.
FsisClass = Literal[
    "raw_poultry_salmonella",
    "rte_listeria",
    "raw_beef_stec",
    "recalls",
    "unknown",
]


# --------------------------------------------------------------------------- #
# Result container
# --------------------------------------------------------------------------- #

@dataclass
class IngestResult:
    """Outcome of one per-source ingestion.

    Attributes
    ----------
    source:
        Source identifier (e.g. ``"noaa"``, ``"fsis_local"``).
    status:
        ``"ok"`` | ``"skipped_no_key"`` | ``"failed"``.
    data:
        Loaded payload (a DataFrame, a list/dict of DataFrames, or ``None``).
        ``None`` means no empirical data was obtained — recorded honestly.
    provenance:
        One or more :class:`ProvenanceEntry` dicts describing what was fetched.
    error:
        Human-readable error/skip reason when ``status`` is not ``"ok"``.
    manual_instructions:
        How a human can obtain the data when auto-access failed/was skipped.
    """

    source: str
    status: Status
    data: Any = None
    provenance: list[ProvenanceEntry] = field(default_factory=list)
    error: Optional[str] = None
    manual_instructions: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"


# --------------------------------------------------------------------------- #
# Low-level helpers
# --------------------------------------------------------------------------- #

def _today_iso() -> str:
    """Return today's date as an ISO-8601 ``YYYY-MM-DD`` string (Req 4.1)."""
    return _dt.date.today().isoformat()


def sha256_bytes(data: bytes) -> str:
    """Return the hex SHA-256 checksum of ``data`` (Req 4.1)."""
    return hashlib.sha256(data).hexdigest()


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def new_provenance(
    source: str,
    url: str,
    *,
    checksum: str = "",
    license: str = "unknown",
    geographic_coverage: str = "unknown",
    temporal_coverage: str = "unknown",
    total_samples: Optional[int] = None,
    positive_count: Optional[int] = None,
    missingness: Optional[dict[str, float]] = None,
    known_biases: Optional[list[str]] = None,
    notes: str = "",
) -> ProvenanceEntry:
    """Build a :class:`ProvenanceEntry` with today's access date (Req 4.1, 4.3).

    Unknown counts stay ``None`` (never fabricated, Req 4.6); ``missingness`` is
    a placeholder ``{}`` until the audit stage (Task 2.4) computes per-column
    fractions.
    """

    return ProvenanceEntry(
        source=source,
        url=url,
        access_date=_today_iso(),
        license=license,
        geographic_coverage=geographic_coverage,
        temporal_coverage=temporal_coverage,
        checksum=checksum,
        total_samples=total_samples,
        positive_count=positive_count,
        missingness=missingness if missingness is not None else {},
        known_biases=known_biases if known_biases is not None else [],
        notes=notes,
    )


def fetch_url(
    url: str,
    dest: Optional[Path] = None,
    headers: Optional[dict[str, str]] = None,
    *,
    params: Optional[dict[str, Any]] = None,
    timeout: Any = DEFAULT_TIMEOUT,
) -> tuple[Optional[bytes], str, Optional[str]]:
    """Download ``url`` to ``dest`` and compute a SHA-256 checksum.

    Uses a browser User-Agent by default and never raises past this boundary:
    timeouts and HTTP errors are returned as a structured failure so a single
    source cannot abort the whole run (Req 2.3, 3.7).

    Parameters
    ----------
    url:
        The URL to download.
    dest:
        Optional path under ``data/raw/`` to persist the bytes to. Parent
        directories are created. ``None`` keeps the bytes in memory only.
    headers:
        Extra request headers merged over the default browser UA.
    params:
        Optional query-string parameters.
    timeout:
        ``requests`` timeout (connect, read).

    Returns
    -------
    tuple
        ``(data_bytes, checksum, error)``. On success ``error`` is ``None``;
        on failure ``data_bytes`` is ``None``, ``checksum`` is ``""`` and
        ``error`` holds the reason.
    """

    merged_headers = {"User-Agent": BROWSER_UA}
    if headers:
        merged_headers.update(headers)

    try:
        resp = requests.get(
            url, headers=merged_headers, params=params, timeout=timeout
        )
        resp.raise_for_status()
    except requests.exceptions.RequestException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        reason = f"HTTP {status}: {exc}" if status else str(exc)
        return None, "", f"request failed for {url}: {reason}"

    data = resp.content
    checksum = sha256_bytes(data)

    if dest is not None:
        try:
            _ensure_dir(dest.parent)
            dest.write_bytes(data)
        except OSError as exc:
            return data, checksum, f"downloaded but could not write {dest}: {exc}"

    return data, checksum, None


# --------------------------------------------------------------------------- #
# FSIS dataset classification
# --------------------------------------------------------------------------- #

def _norm_cols(df: pd.DataFrame) -> set[str]:
    """Return a set of lower-cased, stripped column names for matching."""
    return {str(c).strip().lower() for c in df.columns}


def classify_fsis_dataframe(df: pd.DataFrame, filename: str = "") -> FsisClass:
    """Classify an FSIS table into one of the known dataset families.

    Classification inspects real FSIS column names (robust to case/space) with
    a filename hint as a tie-breaker:

    * ``recalls`` — recall-specific columns (recall number / RTE classifier,
      product/establishment with a recall classification).
    * ``rte_listeria`` — RTE data carries **both** Listeria monocytogenes and
      Salmonella result columns plus the ``RTEPROD`` project codes
      (``RTEPROD_RAND`` / ``RTEPROD_RISK``).
    * ``raw_poultry_salmonella`` — a Salmonella result column together with a
      Campylobacter column (raw poultry is tested for both).
    * ``raw_beef_stec`` — STEC / O157 / N60 result columns.
    * ``unknown`` — kept, but flagged, when nothing matches (Req 3.7).

    Returns
    -------
    FsisClass
    """

    cols = _norm_cols(df)
    fname = filename.lower()

    def has(*needles: str) -> bool:
        return any(any(n in c for c in cols) for n in needles)

    # --- Recalls -----------------------------------------------------------
    recall_signals = has("recall_number", "recall number", "recallnumber",
                          "recall_case", "field_recall", "field_title")
    if recall_signals or ("recall" in fname and has("classification", "product")):
        return "recalls"

    salmonella = has("salmonella")
    listeria = has("listeria", "l. monocytogenes", "lmono", "_lm", "lm_result",
                   "lm result")
    campylobacter = has("campylobacter", "campy")
    stec = has("stec", "o157", "non-o157", "n60", "shiga")
    rteprod = has("rteprod")

    # --- RTE Listeria: both Lm and Salmonella results, or RTEPROD codes -----
    if rteprod or (listeria and salmonella):
        return "rte_listeria"
    if listeria and ("rte" in fname or "ready" in fname):
        return "rte_listeria"

    # --- Raw beef STEC -----------------------------------------------------
    if stec:
        return "raw_beef_stec"

    # --- Raw poultry Salmonella: Salmonella + Campylobacter ----------------
    if salmonella and campylobacter:
        return "raw_poultry_salmonella"
    if salmonella and ("poultry" in fname or "young_chicken" in fname
                       or "chicken" in fname or "turkey" in fname):
        return "raw_poultry_salmonella"

    # --- Filename-only last resort ----------------------------------------
    if "poultry" in fname and salmonella:
        return "raw_poultry_salmonella"
    if listeria:
        return "rte_listeria"

    return "unknown"


# --------------------------------------------------------------------------- #
# FSIS local-file importer (Req 2.3, 3.7)
# --------------------------------------------------------------------------- #

def _read_csv_bytes(raw: bytes, label: str) -> Optional[pd.DataFrame]:
    """Parse CSV bytes into a DataFrame, trying a couple of encodings."""
    for enc in ("utf-8", "latin-1"):
        try:
            return pd.read_csv(io.BytesIO(raw), encoding=enc, low_memory=False)
        except Exception:  # noqa: BLE001 - try next encoding
            continue
    return None


def _fsis_json_primary_records(payload: Any) -> Optional[list[dict[str, Any]]]:
    """Extract the FSIS tidy-data ``primary_table_data`` records from a payload.

    The official FSIS "tidy data" JSON is a one-element list whose element has
    ``metadata`` / ``data`` / ``appendix`` keys; the sample rows live under
    ``data.primary_table_data``. This helper is tolerant of a few shapes:

    * ``[{"data": {"primary_table_data": [...]}}]`` — the real FSIS layout,
    * ``{"data": {"primary_table_data": [...]}}`` — same, un-wrapped,
    * ``{"primary_table_data": [...]}`` — data dict passed directly,
    * a bare list of record dicts.

    Returns the list of record dicts, or ``None`` when no primary table is
    found (the caller records that honestly rather than fabricating rows).
    """

    element: Any = payload
    if isinstance(element, list):
        if not element:
            return None
        # A list of plain record dicts (no tidy wrapper) is itself the table.
        first = element[0]
        if isinstance(first, dict) and "data" not in first and (
            "primary_table_data" not in first
        ):
            return [r for r in element if isinstance(r, dict)]
        element = first

    if not isinstance(element, dict):
        return None

    data = element.get("data", element)
    if isinstance(data, dict):
        primary = data.get("primary_table_data")
        if isinstance(primary, list):
            return [r for r in primary if isinstance(r, dict)]
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    return None


def _read_fsis_json_bytes(raw: bytes, label: str) -> Optional[pd.DataFrame]:
    """Parse FSIS tidy-data JSON bytes into a primary-table DataFrame.

    Tries utf-8 then latin-1 decoding, then extracts
    ``data.primary_table_data`` via :func:`_fsis_json_primary_records`. Returns
    ``None`` when the bytes are not parseable JSON or carry no primary table.
    """

    for enc in ("utf-8", "latin-1"):
        try:
            text = raw.decode(enc)
        except UnicodeDecodeError:
            continue
        try:
            payload = json.loads(text)
        except ValueError:
            return None
        records = _fsis_json_primary_records(payload)
        if records is None:
            return None
        return pd.DataFrame.from_records(records)
    return None


def _read_member_bytes(raw: bytes, member_name: str) -> Optional[pd.DataFrame]:
    """Parse one inner member (CSV or FSIS tidy-data JSON) into a DataFrame."""
    lower = member_name.lower()
    if lower.endswith(".json"):
        return _read_fsis_json_bytes(raw, member_name)
    return _read_csv_bytes(raw, member_name)


def _iter_local_tables(path: Path):
    """Yield ``(member_name, raw_bytes, dataframe|None)`` for a data file.

    Supports standalone ``.csv`` / ``.json`` files and ``.zip`` archives whose
    inner members are CSV or FSIS tidy-data JSON. The real user-provided FSIS
    program archives each wrap a single large tidy-data ``*.json`` member.
    """
    suffix = path.suffix.lower()
    if suffix == ".csv":
        raw = path.read_bytes()
        yield path.name, raw, _read_csv_bytes(raw, path.name)
    elif suffix == ".json":
        raw = path.read_bytes()
        yield path.name, raw, _read_fsis_json_bytes(raw, path.name)
    elif suffix == ".zip":
        raw = path.read_bytes()
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                members = [
                    m for m in zf.namelist()
                    if m.lower().endswith((".csv", ".json"))
                ]
                if not members:
                    yield path.name, raw, None
                for member in members:
                    inner = zf.read(member)
                    yield (
                        f"{path.name}!{member}",
                        inner,
                        _read_member_bytes(inner, member),
                    )
        except zipfile.BadZipFile:
            yield path.name, raw, None


def _fiscal_year_from_name(name: str) -> Optional[int]:
    """Extract a fiscal year (e.g. ``2019``) from a filename via ``fy(\\d{4})``."""
    m = _FY_RE.search(name)
    return int(m.group(1)) if m else None


def reopen_fsis_member(zip_path: Path, member_name: str) -> Optional[pd.DataFrame]:
    """Lazily re-open one scanned FSIS member as a DataFrame (audit stage).

    ``member_name`` is either the archive's own name (standalone file) or the
    ``inner`` member recorded in the scan summary. The frame is read fresh from
    disk so the scan stage can hold only lightweight summaries, not every large
    frame at once. Returns ``None`` if the archive/member cannot be read.
    """

    zip_path = Path(zip_path)
    if not zip_path.exists():
        return None
    try:
        for name, _raw, df in _iter_local_tables(zip_path):
            # ``name`` is either ``path.name`` or ``path.name!member``.
            tail = name.split("!", 1)[-1]
            if member_name in (name, tail) or member_name == zip_path.name:
                return df
    except Exception:  # noqa: BLE001 - re-open must never crash the audit
        return None
    return None


def ingest_fsis_local(
    fsis_dir: Path = FSIS_DIR,
    *,
    program_dirs: Optional[dict[str, Path]] = None,
    hold_frames: bool = False,
) -> IngestResult:
    """Scan the user's FSIS program archives (and the manual drop dir), classify
    and load them, flagging any program↔sniffed-class mismatch (Req 2.3, 3.7).

    Real layout — three sibling program directories under ``data/raw/``, each
    holding one ZIP per fiscal year (FY2014–FY2026), each ZIP wrapping an FSIS
    tidy-data ``*.json`` member whose sample rows live under
    ``data.primary_table_data``:

    * ``raw_poultry_sampling_data``  → program ``raw_poultry_salmonella``
    * ``rte_sampling_data``          → program ``rte_listeria``
    * ``raw_beef_sampling_data``     → program ``raw_beef_stec``

    The **directory** implies the authoritative program/class; ``classify_
    fsis_dataframe`` still runs on each table and a ``MISMATCH`` flag is recorded
    in provenance notes when the sniffed class disagrees (the directory wins).
    Each loaded record is tagged with ``program`` and ``fiscal_year`` so the
    audit stage can group by them, and can re-open any frame lazily via
    :func:`reopen_fsis_member` using the ``(zip_path, inner)`` recorded in the
    scan summary.

    The flat manual-drop directory ``data/raw/fsis/`` is still scanned as a
    fallback (CSV/JSON/ZIP, class sniffed from columns), and an empty/absent set
    of inputs returns gracefully with a recorded gap (Req 2.3, 3.7, 4.6).

    Parameters
    ----------
    fsis_dir:
        The flat manual-drop directory. When it is the default
        :data:`FSIS_DIR`, the three program directories are also scanned.
    program_dirs:
        Override for the program→directory mapping. Defaults to
        :data:`FSIS_PROGRAM_DIRS` when ``fsis_dir`` is the default, else ``{}``
        (so passing a custom ``fsis_dir`` scans only that directory — this keeps
        test isolation intact).
    hold_frames:
        When ``False`` (default) program-directory frames are summarised and
        released to bound memory (13 FY × 3 programs of large JSON). When
        ``True`` the loaded frames are retained in ``data`` for in-process use.

    Returns an :class:`IngestResult` whose ``data`` is a dict with:

    * ``by_class`` — class → list of ``{"name", "class", "program",
      "fiscal_year", "dataframe"|None}`` records (``dataframe`` is ``None`` for
      program-dir members unless ``hold_frames`` is set),
    * ``scan`` — list of per-(program, fy) summaries suitable for serialisation
      (inner member name, row/column counts, declared vs sniffed class, flag,
      zip path + checksum),
    * ``programs`` — per-program roll-up (fiscal years loaded, total rows,
      mismatch count).
    """

    # Decide which program directories to scan. Only auto-scan the three real
    # program dirs when the caller is using the default manual-drop dir, so a
    # test that points ``fsis_dir`` at a temp folder stays fully isolated.
    if program_dirs is None:
        program_dirs = dict(FSIS_PROGRAM_DIRS) if fsis_dir == FSIS_DIR else {}

    manual = (
        "FSIS host is firewalled (HTTP 403) in this environment. Download the "
        f"sampling/recall files from {FSIS_SAMPLING_URL}. Program archives go "
        "into data/raw/{raw_poultry_sampling_data,rte_sampling_data,"
        "raw_beef_sampling_data}/ (one ZIP per fiscal year); ad-hoc files may "
        f"be dropped into {fsis_dir} (*.csv, *.json, *.zip). See "
        "data/raw/fsis/README_FSIS.md."
    )

    by_class: dict[str, list[dict[str, Any]]] = {}
    provenance: list[ProvenanceEntry] = []
    scan: list[dict[str, Any]] = []
    programs: dict[str, dict[str, Any]] = {}
    loaded_any = False

    def _record_member(
        *,
        program: str,
        declared_class: str,
        fiscal_year: Optional[int],
        zip_path: Path,
        member_name: str,
        df: Optional[pd.DataFrame],
    ) -> None:
        nonlocal loaded_any
        inner = member_name.split("!", 1)[-1]
        if df is None:
            scan.append(
                {
                    "program": program,
                    "declared_class": declared_class,
                    "fiscal_year": fiscal_year,
                    "zip_path": str(zip_path),
                    "inner": inner,
                    "member": member_name,
                    "rows": None,
                    "columns": None,
                    "column_names": None,
                    "sniffed_class": None,
                    "mismatch": None,
                    "readable": False,
                }
            )
            return

        sniffed = classify_fsis_dataframe(df, member_name)
        mismatch = (
            sniffed != declared_class and sniffed != "unknown"
            if declared_class in FSIS_PROGRAM_DIRS
            else False
        )
        loaded_any = True
        by_class.setdefault(declared_class, []).append(
            {
                "name": member_name,
                "class": declared_class,
                "program": program,
                "fiscal_year": fiscal_year,
                "dataframe": df if hold_frames else None,
                "zip_path": str(zip_path),
                "inner": inner,
            }
        )
        scan.append(
            {
                "program": program,
                "declared_class": declared_class,
                "fiscal_year": fiscal_year,
                "zip_path": str(zip_path),
                "inner": inner,
                "member": member_name,
                "rows": int(len(df)),
                "columns": int(df.shape[1]),
                "column_names": [str(c) for c in df.columns],
                "sniffed_class": sniffed,
                "mismatch": bool(mismatch),
                "readable": True,
            }
        )
        prog = programs.setdefault(
            program,
            {"fiscal_years": set(), "total_rows": 0, "mismatches": 0, "files": 0},
        )
        if fiscal_year is not None:
            prog["fiscal_years"].add(fiscal_year)
        prog["total_rows"] += int(len(df))
        prog["files"] += 1
        if mismatch:
            prog["mismatches"] += 1

    # --- 1) Scan the three real program directories (authoritative class) ---
    for program, pdir in program_dirs.items():
        if not pdir.exists():
            provenance.append(
                new_provenance(
                    source=f"fsis_local:{program}",
                    url=FSIS_SAMPLING_URL,
                    license="US Government public domain (USDA FSIS)",
                    geographic_coverage="United States (FSIS-regulated establishments)",
                    temporal_coverage="unknown (directory absent)",
                    notes=(
                        f"GAP: FSIS program directory {pdir} absent; no "
                        f"{program} data loaded. Nothing fabricated. " + manual
                    ),
                )
            )
            continue

        archives = sorted(
            p for p in pdir.iterdir()
            if p.is_file() and p.suffix.lower() in (".zip", ".csv", ".json")
        )
        if not archives:
            provenance.append(
                new_provenance(
                    source=f"fsis_local:{program}",
                    url=FSIS_SAMPLING_URL,
                    license="US Government public domain (USDA FSIS)",
                    geographic_coverage="United States (FSIS-regulated establishments)",
                    temporal_coverage="unknown (no archives)",
                    notes=(
                        f"GAP: no archives in {pdir} for program {program}. "
                        "Nothing fabricated. " + manual
                    ),
                )
            )
            continue

        for archive in archives:
            fy = _fiscal_year_from_name(archive.name)
            raw_all = archive.read_bytes()
            checksum = sha256_bytes(raw_all)
            del raw_all  # release the zip bytes promptly (large files)

            member_rows: list[str] = []
            file_mismatch = False
            for member_name, _member_bytes, df in _iter_local_tables(archive):
                _record_member(
                    program=program,
                    declared_class=program,
                    fiscal_year=fy,
                    zip_path=archive,
                    member_name=member_name,
                    df=df,
                )
                last = scan[-1]
                if last["readable"]:
                    member_rows.append(
                        f"{last['inner']} rows={last['rows']} "
                        f"sniffed={last['sniffed_class']}"
                        + ("  MISMATCH" if last["mismatch"] else "")
                    )
                    file_mismatch = file_mismatch or bool(last["mismatch"])
                else:
                    member_rows.append(f"{last['inner']} UNREADABLE")
                # Drop the frame reference so it can be GC'd between members.
                df = None  # noqa: F841

            total_rows = sum(
                s["rows"] or 0 for s in scan
                if s["zip_path"] == str(archive)
            )
            provenance.append(
                new_provenance(
                    source=f"fsis_local:{program}:{archive.name}",
                    url=FSIS_SAMPLING_URL,
                    checksum=checksum,
                    license="US Government public domain (USDA FSIS)",
                    geographic_coverage="United States (FSIS-regulated establishments)",
                    temporal_coverage=(f"FY{fy}" if fy else "unknown fiscal year"),
                    total_samples=total_rows or None,
                    notes=(
                        f"FSIS program '{program}' archive (authoritative class "
                        f"from directory), FY={fy}. Members: "
                        f"{'; '.join(member_rows) or 'unreadable'}."
                        + (
                            " FLAG: sniffed class disagrees with the directory-"
                            "declared program for at least one member; the "
                            "directory program is authoritative (recorded for "
                            "audit)."
                            if file_mismatch else ""
                        )
                        + " Loaded locally because " + manual
                    ),
                )
            )

    # --- 2) Fallback: flat manual-drop directory (class sniffed) -----------
    if not fsis_dir.exists():
        _ensure_dir(fsis_dir)

    flat_files = sorted(
        p for p in fsis_dir.iterdir()
        if p.is_file() and p.suffix.lower() in (".csv", ".zip", ".json")
        and not p.name.lower().startswith("recalls")
    ) if fsis_dir.exists() else []

    for path in flat_files:
        raw_all = path.read_bytes()
        checksum = sha256_bytes(raw_all)
        fy = _fiscal_year_from_name(path.name)
        file_classes: list[str] = []
        file_rows = 0

        for member_name, _member_bytes, df in _iter_local_tables(path):
            if df is None:
                file_classes.append("unknown")
                continue
            cls = classify_fsis_dataframe(df, member_name)
            file_classes.append(cls)
            by_class.setdefault(cls, []).append(
                {
                    "name": member_name,
                    "class": cls,
                    "program": "manual_drop",
                    "fiscal_year": fy,
                    "dataframe": df,  # manual drops are small; keep the frame
                    "zip_path": str(path),
                    "inner": member_name.split("!", 1)[-1],
                }
            )
            file_rows += len(df)
            if cls != "unknown":
                loaded_any = True

        classes_note = ", ".join(sorted(set(file_classes))) or "unreadable"
        provenance.append(
            new_provenance(
                source=f"fsis_local:{path.name}",
                url=FSIS_SAMPLING_URL,
                checksum=checksum,
                license="US Government public domain (USDA FSIS)",
                geographic_coverage="United States (FSIS-regulated establishments)",
                temporal_coverage=(f"FY{fy}" if fy else "per-file (see audit)"),
                total_samples=file_rows or None,
                notes=(
                    f"Manually provided FSIS file; detected class(es): "
                    f"{classes_note}. Loaded locally because {manual}"
                ),
            )
        )

    # --- 3) Nothing found anywhere → honest gap ----------------------------
    if not loaded_any and not scan:
        prov = new_provenance(
            source="fsis_local",
            url=FSIS_SAMPLING_URL,
            license="US Government public domain (USDA FSIS)",
            geographic_coverage="United States (FSIS-regulated establishments)",
            temporal_coverage="unknown (no file provided)",
            notes=(
                "GAP: no FSIS program archives or manual-drop files present. "
                "No data loaded; nothing fabricated. " + manual
            ),
        )
        return IngestResult(
            source="fsis_local",
            status="failed",
            data=None,
            provenance=provenance + [prov] if provenance else [prov],
            error="no FSIS files found (program dirs + data/raw/fsis/ empty)",
            manual_instructions=manual,
        )

    # Finalise per-program roll-ups into JSON-serialisable shapes.
    programs_summary = {
        name: {
            "fiscal_years": sorted(info["fiscal_years"]),
            "fiscal_years_loaded": len(info["fiscal_years"]),
            "total_rows": info["total_rows"],
            "files": info["files"],
            "mismatches": info["mismatches"],
        }
        for name, info in programs.items()
    }

    data_payload = {
        "by_class": by_class,
        "scan": scan,
        "programs": programs_summary,
    }
    status: Status = "ok" if loaded_any else "failed"
    return IngestResult(
        source="fsis_local",
        status=status,
        data=data_payload if loaded_any else None,
        provenance=provenance,
        error=None if loaded_any else "FSIS files present but none classifiable",
        manual_instructions=None if loaded_any else manual,
    )


def ingest_fsis_recalls(fsis_dir: Path = FSIS_DIR) -> IngestResult:
    """Fetch FSIS recalls from the API; fall back to a local recalls file.

    Attempts the FSIS Recall API with a browser UA (Req 2.1 regulatory track).
    On any failure (403 firewall here) it looks for a locally-dropped
    ``recalls*.json`` / ``recalls*.csv`` in ``data/raw/fsis/``. If neither is
    available it records an honest gap and returns ``failed`` without crashing
    (Req 3.7, 4.6).
    """

    manual = (
        "FSIS Recall API is firewalled (HTTP 403) here. Export recalls from "
        f"{FSIS_RECALL_API_URL} (or the recalls page under {FSIS_SAMPLING_URL}) "
        f"and save as recalls*.json or recalls*.csv in {fsis_dir}."
    )

    # 1) Try the live API.
    dest = RAW_ROOT / "fsis" / "recalls_api.json"
    data_bytes, checksum, err = fetch_url(FSIS_RECALL_API_URL, dest=dest)
    if err is None and data_bytes:
        try:
            payload = json.loads(data_bytes.decode("utf-8"))
            records = payload if isinstance(payload, list) else payload.get("data", payload)
            df = pd.json_normalize(records) if records else pd.DataFrame()
            if not df.empty:
                prov = new_provenance(
                    source="fsis_recalls",
                    url=FSIS_RECALL_API_URL,
                    checksum=checksum,
                    license="US Government public domain (USDA FSIS)",
                    geographic_coverage="United States",
                    temporal_coverage="live recall feed",
                    total_samples=len(df),
                    notes="FSIS Recall API (regulatory-evidence track).",
                )
                return IngestResult("fsis_recalls", "ok", df, [prov])
        except (ValueError, UnicodeDecodeError) as exc:
            err = f"recall API returned unparseable payload: {exc}"

    # 2) Fall back to a locally-dropped recalls file.
    if fsis_dir.exists():
        candidates = sorted(
            p for p in fsis_dir.iterdir()
            if p.is_file() and p.name.lower().startswith("recalls")
            and p.suffix.lower() in (".json", ".csv")
        )
        for path in candidates:
            raw = path.read_bytes()
            checksum = sha256_bytes(raw)
            try:
                if path.suffix.lower() == ".json":
                    payload = json.loads(raw.decode("utf-8", errors="replace"))
                    records = payload if isinstance(payload, list) else payload.get("data", payload)
                    df = pd.json_normalize(records)
                else:
                    df = _read_csv_bytes(raw, path.name)
            except Exception:  # noqa: BLE001
                df = None
            if df is not None and not df.empty:
                prov = new_provenance(
                    source=f"fsis_recalls:{path.name}",
                    url=FSIS_RECALL_API_URL,
                    checksum=checksum,
                    license="US Government public domain (USDA FSIS)",
                    geographic_coverage="United States",
                    temporal_coverage="per-file",
                    total_samples=len(df),
                    notes=(
                        "Manually provided FSIS recalls file (API firewalled). "
                        + manual
                    ),
                )
                return IngestResult("fsis_recalls", "ok", df, [prov])

    # 3) Honest gap.
    prov = new_provenance(
        source="fsis_recalls",
        url=FSIS_RECALL_API_URL,
        license="US Government public domain (USDA FSIS)",
        geographic_coverage="United States",
        temporal_coverage="unknown (unavailable)",
        notes="GAP: FSIS recalls unavailable (API firewalled, no local file). " + manual,
    )
    return IngestResult(
        source="fsis_recalls",
        status="failed",
        data=None,
        provenance=[prov],
        error=err or "FSIS recalls unavailable (API firewalled, no local file)",
        manual_instructions=manual,
    )


# --------------------------------------------------------------------------- #
# NOAA (NCEI Access Data Service — token-free by default)
# --------------------------------------------------------------------------- #

def ingest_noaa(
    stations: list[str],
    start: str,
    end: str,
    *,
    data_types: Optional[list[str]] = None,
    use_cdo: bool = False,
) -> IngestResult:
    """Fetch NOAA daily weather via the token-free NCEI Access Data Service.

    By default this hits ``NCEI_ACCESS_BASE`` (dataset ``daily-summaries``),
    which returns JSON **without a token**. When ``use_cdo`` is true (or
    ``NOAA_TOKEN`` is set and ``use_cdo`` is requested) it uses the optional
    CDO v2 API with the token from the ``NOAA_TOKEN`` env var.

    Parameters
    ----------
    stations:
        GHCND station ids (e.g. ``["USW00094728"]`` for NYC Central Park).
    start, end:
        ISO ``YYYY-MM-DD`` date bounds (inclusive).
    data_types:
        NCEI dataTypes; defaults to ``["TMAX", "TMIN", "PRCP"]``.
    use_cdo:
        Use the optional token-based CDO v2 path instead of the Access service.

    Returns an :class:`IngestResult` with a DataFrame on success. Never raises
    past this boundary (Req 2.3, 3.7).
    """

    data_types = data_types or ["TMAX", "TMIN", "PRCP"]
    station_param = ",".join(stations)
    dtype_param = ",".join(data_types)

    if use_cdo:
        return _ingest_noaa_cdo(stations, start, end, data_types)

    params = {
        "dataset": "daily-summaries",
        "stations": station_param,
        "startDate": start,
        "endDate": end,
        "dataTypes": dtype_param,
        "format": "json",
        "units": "metric",
    }
    dest = RAW_ROOT / "noaa" / f"ncei_{start}_{end}.json"
    data_bytes, checksum, err = fetch_url(NCEI_ACCESS_BASE, dest=dest, params=params)

    manual = (
        "NOAA NCEI Access Data Service is token-free; if this failed it is a "
        f"transient network issue. Retry {NCEI_ACCESS_BASE} with "
        "dataset=daily-summaries. Station ids are GHCND ids."
    )

    if err is not None or not data_bytes:
        prov = new_provenance(
            source="noaa",
            url=NCEI_ACCESS_BASE,
            license="US Government public domain (NOAA NCEI)",
            geographic_coverage=f"stations: {station_param}",
            temporal_coverage=f"{start}..{end}",
            notes="GAP: NOAA fetch failed. " + manual,
        )
        return IngestResult("noaa", "failed", None, [prov], err or "empty NOAA response", manual)

    try:
        records = json.loads(data_bytes.decode("utf-8"))
        df = pd.DataFrame(records)
    except (ValueError, UnicodeDecodeError) as exc:
        prov = new_provenance(
            source="noaa", url=NCEI_ACCESS_BASE, checksum=checksum,
            notes=f"GAP: NOAA payload unparseable: {exc}. " + manual,
        )
        return IngestResult("noaa", "failed", None, [prov], str(exc), manual)

    if df.empty:
        prov = new_provenance(
            source="noaa", url=NCEI_ACCESS_BASE, checksum=checksum,
            geographic_coverage=f"stations: {station_param}",
            temporal_coverage=f"{start}..{end}",
            notes="GAP: NOAA returned zero records for the requested window. " + manual,
        )
        return IngestResult("noaa", "failed", None, [prov], "zero records", manual)

    prov = new_provenance(
        source="noaa",
        url=NCEI_ACCESS_BASE,
        checksum=checksum,
        license="US Government public domain (NOAA NCEI)",
        geographic_coverage=f"GHCND stations: {station_param}",
        temporal_coverage=f"{start}..{end}",
        total_samples=len(df),
        known_biases=[
            "station network is spatially uneven; rural coverage is sparser",
        ],
        notes=(
            "NOAA NCEI Access Data Service (token-free), dataset "
            f"daily-summaries, dataTypes {dtype_param}."
        ),
    )
    return IngestResult("noaa", "ok", df, [prov])


def _ingest_noaa_cdo(
    stations: list[str], start: str, end: str, data_types: list[str]
) -> IngestResult:
    """Optional NOAA CDO v2 path using ``NOAA_TOKEN`` (Req 2.1 token note)."""
    token = os.environ.get("NOAA_TOKEN", "").strip()
    manual = (
        "NOAA CDO v2 requires a free token. Request one at "
        "https://www.ncei.noaa.gov/cdo-web/token and set NOAA_TOKEN in your "
        ".env. The default token-free NCEI Access service needs no token."
    )
    if not token:
        prov = new_provenance(
            source="noaa_cdo", url=NOAA_CDO_BASE,
            notes="SKIPPED: NOAA_TOKEN not set for optional CDO v2 path. " + manual,
        )
        return IngestResult("noaa_cdo", "skipped_no_key", None, [prov],
                            "NOAA_TOKEN not set", manual)

    params = {
        "datasetid": "GHCND",
        "stationid": [f"GHCND:{s}" for s in stations],
        "startdate": start,
        "enddate": end,
        "datatypeid": data_types,
        "limit": 1000,
        "units": "metric",
    }
    data_bytes, checksum, err = fetch_url(
        f"{NOAA_CDO_BASE}/data", headers={"token": token}, params=params
    )
    if err is not None or not data_bytes:
        prov = new_provenance(
            source="noaa_cdo", url=NOAA_CDO_BASE, notes="GAP: CDO v2 fetch failed. " + manual,
        )
        return IngestResult("noaa_cdo", "failed", None, [prov], err or "empty", manual)
    try:
        payload = json.loads(data_bytes.decode("utf-8"))
        df = pd.DataFrame(payload.get("results", []))
    except (ValueError, UnicodeDecodeError) as exc:
        prov = new_provenance(source="noaa_cdo", url=NOAA_CDO_BASE, checksum=checksum,
                              notes=f"GAP: CDO payload unparseable: {exc}.")
        return IngestResult("noaa_cdo", "failed", None, [prov], str(exc), manual)
    prov = new_provenance(
        source="noaa_cdo", url=NOAA_CDO_BASE, checksum=checksum,
        license="US Government public domain (NOAA NCEI)",
        geographic_coverage=f"GHCND stations: {','.join(stations)}",
        temporal_coverage=f"{start}..{end}", total_samples=len(df),
        notes="NOAA CDO v2 (token path).",
    )
    status: Status = "ok" if not df.empty else "failed"
    return IngestResult("noaa_cdo", status, df if not df.empty else None, [prov])


# --------------------------------------------------------------------------- #
# NOAA nClimDiv statewide monthly climate (PRIMARY weather source, Req 2.1)
# --------------------------------------------------------------------------- #

def _resolve_climdiv_filename(index_html: str, stem: str) -> Optional[str]:
    """Pick the current filename for a climdiv element stem from the index HTML.

    The statewide files are named ``<stem>v<ver>-<YYYYMMDD>`` and the date
    suffix rotates monthly, so we never hard-code it: the directory listing is
    scanned and the lexicographically-largest matching name (newest date) is
    returned, or ``None`` when no file matches (recorded honestly)."""
    names = re.findall(r'href="([^"?/]+)"', index_html)
    matches = sorted(n for n in names if n.startswith(stem))
    return matches[-1] if matches else None


def _parse_climdiv_statewide(text: str, element: str) -> pd.DataFrame:
    """Parse one nClimDiv statewide fixed-width file into a tidy monthly frame.

    Each line is ``SSSEEYYYY`` (3-char state code, 2-char element, 4-char year)
    followed by 12 whitespace-separated monthly values. ``-99.90`` /
    ``-9999`` sentinels are treated as missing (NaN), never fabricated. Only
    real state codes in :data:`NCLIMDIV_STATE_CODE` are kept (regional/national
    roll-up codes are dropped). Returns columns ``state``, ``year``, ``month``,
    and ``<element>`` (e.g. ``tavg``)."""
    records: list[dict[str, Any]] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if len(line) < 11:
            continue
        code = line[:3]
        usps = NCLIMDIV_STATE_CODE.get(code)
        if usps is None:
            continue  # regional/national roll-up — not a real state
        year_str = line[6:10]
        if not year_str.isdigit():
            continue
        year = int(year_str)
        values = line[10:].split()
        for month_idx, token in enumerate(values[:12], start=1):
            try:
                val = float(token)
            except ValueError:
                continue
            # nClimDiv missing sentinels
            if val <= -99.0 or val == -9999.0:
                val = float("nan")
            records.append({
                "state": usps,
                "year": year,
                "month": month_idx,
                element: val,
            })
    return pd.DataFrame.from_records(records)


def ingest_nclimdiv(
    *,
    start_year: int = 2014,
    end_year: int = 2026,
    elements: Optional[list[str]] = None,
) -> IngestResult:
    """Fetch NOAA nClimDiv STATEWIDE monthly climate — the PRIMARY weather source.

    Downloads the statewide average-temperature + precipitation (and, when
    available, max/min temperature) bulk files from :data:`NCEI_CLIMDIV_BASE`,
    parses them into a tidy ``(state, year, month, tavg, tmax, tmin, pcpn)``
    table over ``[start_year, end_year]``, and records provenance + a SHA-256
    checksum per element file (Req 2.1, 4.1).

    nClimDiv statewide series give NATIONAL state-level monthly coverage (the 48
    contiguous states + Alaska), which replaces the single-NYC-station demo path
    as the weather source. Hawaii has no nClimDiv statewide series — a documented
    coverage gap, never fabricated. Values are in the file's native units
    (temperature °F, precipitation inches); harmonize converts/derives anomalies.

    Never raises past this boundary: a network/parse failure records a gap and
    returns ``failed`` so the overall run is unaffected (Req 2.3, 3.7)."""

    elements = elements or ["tavg", "pcpn", "tmax", "tmin"]
    manual = (
        "NOAA nClimDiv statewide monthly files are token-free bulk downloads at "
        f"{NCEI_CLIMDIV_BASE} (files climdiv-tmpcst-* avg temp, climdiv-pcpnst-* "
        "precip, climdiv-tmaxst-/tminst-* max/min temp). If this failed it is a "
        "transient network issue — retry. Each line is SSSEEYYYY + 12 monthly "
        "columns; state codes 001-048 are the contiguous states (alphabetical), "
        "050 is Alaska; Hawaii has no statewide nClimDiv series."
    )

    # Resolve the current filenames from the directory index.
    index_bytes, _idx_ck, idx_err = fetch_url(NCEI_CLIMDIV_BASE)
    if idx_err is not None or not index_bytes:
        prov = new_provenance(
            source="noaa_nclimdiv", url=NCEI_CLIMDIV_BASE,
            license="US Government public domain (NOAA NCEI)",
            geographic_coverage="United States (statewide)",
            temporal_coverage=f"{start_year}..{end_year}",
            notes="GAP: could not list nClimDiv directory. " + manual,
        )
        return IngestResult("noaa_nclimdiv", "failed", None, [prov],
                            idx_err or "empty index", manual)
    index_html = index_bytes.decode("utf-8", errors="replace")

    frames: list[pd.DataFrame] = []
    provenance: list[ProvenanceEntry] = []
    elements_loaded: list[str] = []
    for element in elements:
        stem = NCLIMDIV_ELEMENTS.get(element)
        if stem is None:
            continue
        fname = _resolve_climdiv_filename(index_html, stem)
        if fname is None:
            provenance.append(new_provenance(
                source=f"noaa_nclimdiv:{element}", url=NCEI_CLIMDIV_BASE,
                license="US Government public domain (NOAA NCEI)",
                geographic_coverage="United States (statewide)",
                temporal_coverage=f"{start_year}..{end_year}",
                notes=f"GAP: no statewide file matching '{stem}'. " + manual,
            ))
            continue
        url = NCEI_CLIMDIV_BASE + fname
        dest = RAW_ROOT / "noaa_nclimdiv" / fname
        data_bytes, checksum, err = fetch_url(url, dest=dest)
        if err is not None or not data_bytes:
            provenance.append(new_provenance(
                source=f"noaa_nclimdiv:{element}", url=url,
                notes=f"GAP: fetch failed for {fname}: {err}. " + manual,
            ))
            continue
        text = data_bytes.decode("utf-8", errors="replace")
        tidy = _parse_climdiv_statewide(text, element)
        tidy = tidy[(tidy["year"] >= start_year) & (tidy["year"] <= end_year)]
        if tidy.empty:
            provenance.append(new_provenance(
                source=f"noaa_nclimdiv:{element}", url=url, checksum=checksum,
                notes=f"GAP: {fname} parsed to zero rows in range. " + manual,
            ))
            continue
        frames.append(tidy)
        elements_loaded.append(element)
        n_states = int(tidy["state"].nunique())
        provenance.append(new_provenance(
            source=f"noaa_nclimdiv:{element}", url=url, checksum=checksum,
            license="US Government public domain (NOAA NCEI)",
            geographic_coverage=f"United States statewide ({n_states} states)",
            temporal_coverage=f"{int(tidy['year'].min())}..{int(tidy['year'].max())}",
            total_samples=int(len(tidy)),
            known_biases=[
                "statewide averages smooth over within-state spatial variation",
                "Hawaii has no nClimDiv statewide series (coverage gap)",
            ],
            notes=(
                f"NOAA nClimDiv statewide {element} ({fname}); fixed-width "
                "SSSEEYYYY + 12 monthly columns; -99.90/-9999 sentinels -> NaN."
            ),
        ))

    if not frames:
        prov = new_provenance(
            source="noaa_nclimdiv", url=NCEI_CLIMDIV_BASE,
            notes="GAP: no nClimDiv elements loaded. " + manual,
        )
        return IngestResult("noaa_nclimdiv", "failed", None, [prov] + provenance,
                            "no elements loaded", manual)

    # Outer-merge the per-element tidy frames on (state, year, month).
    merged = frames[0]
    for extra in frames[1:]:
        merged = merged.merge(extra, on=["state", "year", "month"], how="outer")
    merged = merged.sort_values(["state", "year", "month"]).reset_index(drop=True)

    return IngestResult("noaa_nclimdiv", "ok", merged, provenance)


# --------------------------------------------------------------------------- #
# CDC NORS human-health outbreak stream (One Health human pathway, Req 2.1/2.2)
# --------------------------------------------------------------------------- #

#: Etiology substrings (case-insensitive) that map a NORS outbreak to one of the
#: three FSIS pathogens. STEC is matched broadly (Shiga-toxin / O157 / E. coli).
CDC_NORS_PATHOGEN_PATTERNS: dict[str, tuple[str, ...]] = {
    "Salmonella": ("salmonella",),
    "Listeria": ("listeria",),
    "STEC": ("shiga", "stec", "o157", "escherichia coli", "e. coli"),
}


def ingest_cdc_nors(
    *,
    start_year: int = 2014,
    end_year: int = 2023,
    page_limit: int = 50000,
) -> IngestResult:
    """Fetch CDC NORS foodborne-outbreak rows (human-health One Health pathway).

    Pulls the verified NORS Socrata dataset (:data:`CDC_NORS_DATASET_ID`) over
    ``[start_year, end_year]`` via SODA JSON with a browser UA, keeping only
    foodborne-transmission outbreaks (``primary_mode`` = Food). Each row is
    state + year + month + etiology + illness/hospitalization/death counts, so
    it can be aggregated to ``(state, period)`` counts downstream. Provenance +
    checksum are recorded (Req 2.1, 4.1).

    HONESTY: NORS carries outbreak dates, NOT report dates, and has long
    reporting delays. The predictive availability lag is applied later in
    harmonize; here we only fetch and record the raw outbreak table. On any
    failure a gap is recorded and ``failed`` is returned (Req 2.3, 3.7)."""

    manual = (
        "CDC NORS is a public Socrata dataset. Download JSON/CSV from "
        f"{CDC_NORS_LANDING} or query {CDC_NORS_SODA_BASE}/{CDC_NORS_DATASET_ID}.json "
        "with $where=year between <a> and <b>. No token required."
    )
    url = f"{CDC_NORS_SODA_BASE}/{CDC_NORS_DATASET_ID}.json"
    params = {
        "$where": (
            f"year >= {start_year} AND year <= {end_year} "
            "AND primary_mode = 'Food'"
        ),
        "$limit": page_limit,
        "$order": "year,month,state",
    }
    dest = RAW_ROOT / "cdc_nors" / f"nors_food_{start_year}_{end_year}.json"
    data_bytes, checksum, err = fetch_url(url, dest=dest, params=params)
    if err is not None or not data_bytes:
        prov = new_provenance(
            source="cdc_nors", url=url,
            license="US Government public domain (CDC NORS)",
            geographic_coverage="United States (state)",
            temporal_coverage=f"{start_year}..{end_year}",
            notes="GAP: CDC NORS fetch failed. " + manual,
        )
        return IngestResult("cdc_nors", "failed", None, [prov], err, manual)

    try:
        records = json.loads(data_bytes.decode("utf-8"))
        df = pd.DataFrame(records)
    except (ValueError, UnicodeDecodeError) as exc:
        prov = new_provenance(
            source="cdc_nors", url=url, checksum=checksum,
            notes=f"GAP: CDC NORS payload unparseable: {exc}. " + manual,
        )
        return IngestResult("cdc_nors", "failed", None, [prov], str(exc), manual)

    if df.empty:
        prov = new_provenance(
            source="cdc_nors", url=url, checksum=checksum,
            geographic_coverage="United States (state)",
            temporal_coverage=f"{start_year}..{end_year}",
            notes="GAP: CDC NORS returned zero foodborne rows in range. " + manual,
        )
        return IngestResult("cdc_nors", "failed", None, [prov], "zero records", manual)

    prov = new_provenance(
        source="cdc_nors", url=url, checksum=checksum,
        license="US Government public domain (CDC NORS)",
        geographic_coverage="United States (state-level)",
        temporal_coverage=f"{start_year}..{end_year} (outbreak dates)",
        total_samples=int(len(df)),
        known_biases=[
            "NORS outbreak dates are NOT report dates; long reporting delays",
            "outbreak counts depend on state surveillance/reporting capacity",
            "dataset is HISTORICAL evidence; predictive use needs a large lag",
        ],
        notes=(
            f"CDC NORS foodborne outbreaks (dataset {CDC_NORS_DATASET_ID}), "
            "primary_mode=Food. Columns include year, month, state, etiology, "
            "illnesses, hospitalizations, deaths. Used mainly as historical One "
            "Health human-health evidence; predictive join applies a large "
            "availability lag (see harmonize)."
        ),
    )
    return IngestResult("cdc_nors", "ok", df, [prov])


# --------------------------------------------------------------------------- #
# US Census ACS (keyed; skip-with-gap when no key)
# --------------------------------------------------------------------------- #

def ingest_census_acs(
    year: int,
    variables: list[str],
    geo: str = "state:*",
) -> IngestResult:
    """Fetch US Census ACS 5-year data; skip with a gap if no API key.

    Reads ``CENSUS_API_KEY`` from the environment. Without it the ACS endpoint
    returns a "Missing Key" HTML page, so this returns ``skipped_no_key`` with
    a recorded gap and manual instructions — it does **not** fail the whole run
    (Req 2.3, 3.7, 4.6).

    Parameters
    ----------
    year:
        ACS 5-year vintage (e.g. ``2022``).
    variables:
        ACS variable codes (e.g. ``["B01001_001E"]`` total population).
    geo:
        Census geography predicate (e.g. ``"state:*"``).
    """

    manual = (
        "US Census ACS requires a free API key. Sign up at "
        "https://api.census.gov/data/key_signup.html and set CENSUS_API_KEY "
        "in your .env, then re-run."
    )
    key = os.environ.get("CENSUS_API_KEY", "").strip()
    url = f"{CENSUS_ACS_BASE}/{year}/acs/acs5"

    if not key:
        prov = new_provenance(
            source="census_acs", url=url,
            license="US Government public domain (US Census Bureau)",
            geographic_coverage=geo, temporal_coverage=f"ACS5 {year}",
            notes="SKIPPED: CENSUS_API_KEY not set. " + manual,
        )
        return IngestResult("census_acs", "skipped_no_key", None, [prov],
                            "CENSUS_API_KEY not set", manual)

    get_param = ",".join(["NAME", *variables])
    params = {"get": get_param, "for": geo, "key": key}
    dest = RAW_ROOT / "census" / f"acs5_{year}.json"
    data_bytes, checksum, err = fetch_url(url, dest=dest, params=params)

    if err is not None or not data_bytes:
        prov = new_provenance(
            source="census_acs", url=url, geographic_coverage=geo,
            temporal_coverage=f"ACS5 {year}", notes="GAP: ACS fetch failed. " + manual,
        )
        return IngestResult("census_acs", "failed", None, [prov], err or "empty", manual)

    try:
        rows = json.loads(data_bytes.decode("utf-8"))
        # ACS returns a header row followed by data rows.
        df = pd.DataFrame(rows[1:], columns=rows[0]) if rows else pd.DataFrame()
    except (ValueError, UnicodeDecodeError, IndexError) as exc:
        prov = new_provenance(
            source="census_acs", url=url, checksum=checksum,
            notes=f"GAP: ACS payload unparseable (likely Missing-Key HTML): {exc}. " + manual,
        )
        return IngestResult("census_acs", "failed", None, [prov], str(exc), manual)

    if df.empty:
        prov = new_provenance(
            source="census_acs", url=url, checksum=checksum, geographic_coverage=geo,
            temporal_coverage=f"ACS5 {year}", notes="GAP: ACS returned zero rows.",
        )
        return IngestResult("census_acs", "failed", None, [prov], "zero rows", manual)

    prov = new_provenance(
        source="census_acs", url=url, checksum=checksum,
        license="US Government public domain (US Census Bureau)",
        geographic_coverage=geo, temporal_coverage=f"ACS5 {year}",
        total_samples=len(df),
        known_biases=["survey estimates carry margins of error; small areas noisier"],
        notes=f"ACS 5-year {year}; variables {','.join(variables)}.",
    )
    return IngestResult("census_acs", "ok", df, [prov])


# --------------------------------------------------------------------------- #
# USDA Food Access Research Atlas (bulk file download)
# --------------------------------------------------------------------------- #

def ingest_food_access_atlas(which: str = "lram_2019_xlsx") -> IngestResult:
    """Download a real USDA Food Access Research Atlas file (xlsx or zip).

    Fetches from ``ers.usda.gov`` with a browser UA. ``which`` selects an entry
    of :data:`FOOD_ACCESS_ATLAS_URLS`. On any network/parse failure it records
    an honest gap and returns ``failed`` without crashing (Req 3.7, 4.6).
    """

    url = FOOD_ACCESS_ATLAS_URLS.get(which)
    manual = (
        "USDA Food Access Research Atlas has no API. Download the file from "
        f"{url or 'https://www.ers.usda.gov/data-products/food-access-research-atlas'} "
        "in a browser and place it under data/raw/food_access/."
    )
    if url is None:
        prov = new_provenance(
            source="food_access_atlas",
            url="https://www.ers.usda.gov/data-products/food-access-research-atlas",
            notes=f"GAP: unknown Atlas key '{which}'. " + manual,
        )
        return IngestResult("food_access_atlas", "failed", None, [prov],
                            f"unknown key {which}", manual)

    ext = ".xlsx" if url.endswith(".xlsx") else ".zip"
    dest = RAW_ROOT / "food_access" / f"{which}{ext}"
    data_bytes, checksum, err = fetch_url(url, dest=dest)

    if err is not None or not data_bytes:
        prov = new_provenance(
            source="food_access_atlas", url=url,
            license="US Government public domain (USDA ERS)",
            geographic_coverage="United States (census tracts)",
            temporal_coverage="2015/2019 Atlas vintage",
            notes="GAP: Atlas download failed. " + manual,
        )
        return IngestResult("food_access_atlas", "failed", None, [prov], err or "empty", manual)

    df: Optional[pd.DataFrame] = None
    parse_note = ""
    try:
        if ext == ".xlsx":
            try:
                sheets = pd.read_excel(io.BytesIO(data_bytes), sheet_name=None)
                # Prefer the data sheet with the most rows.
                if sheets:
                    df = max(sheets.values(), key=len)
            except ImportError:
                parse_note = (
                    " openpyxl not installed; bytes saved to data/raw/ for later "
                    "parsing (pip install openpyxl)."
                )
        else:  # zip
            with zipfile.ZipFile(io.BytesIO(data_bytes)) as zf:
                members = [m for m in zf.namelist()
                           if m.lower().endswith((".csv", ".xlsx"))]
                for member in members:
                    inner = zf.read(member)
                    if member.lower().endswith(".csv"):
                        df = _read_csv_bytes(inner, member)
                    else:
                        try:
                            sheets = pd.read_excel(io.BytesIO(inner), sheet_name=None)
                            if sheets:
                                df = max(sheets.values(), key=len)
                        except ImportError:
                            parse_note = " openpyxl not installed for xlsx member."
                    if df is not None and not df.empty:
                        break
    except Exception as exc:  # noqa: BLE001 - bytes are saved; record and continue
        parse_note = f" parse error: {exc}"

    total = int(len(df)) if df is not None else None
    status: Status = "ok" if (df is not None and not df.empty) else "failed"
    prov = new_provenance(
        source="food_access_atlas",
        url=url,
        checksum=checksum,
        license="US Government public domain (USDA ERS)",
        geographic_coverage="United States (census tracts)",
        temporal_coverage="2015/2019 Atlas vintage",
        total_samples=total,
        known_biases=[
            "tract-level access thresholds are policy choices, not ground truth",
        ],
        notes=(
            f"USDA Food Access Research Atlas file '{which}' downloaded "
            f"({len(data_bytes)} bytes).{parse_note}"
        ),
    )
    return IngestResult(
        source="food_access_atlas",
        status=status,
        data=df if (df is not None and not df.empty) else None,
        provenance=[prov],
        error=None if status == "ok" else ("saved raw but could not parse table" + parse_note),
        manual_instructions=None if status == "ok" else manual,
    )


# --------------------------------------------------------------------------- #
# Top-level orchestration
# --------------------------------------------------------------------------- #

def _default_config() -> dict[str, Any]:
    """Default ingestion config (overridable via ``run_ingestion(config)``)."""
    return {
        # PRIMARY weather source: nClimDiv statewide monthly (national coverage).
        "nclimdiv": {
            "start_year": 2014,
            "end_year": 2026,
            "elements": ["tavg", "pcpn", "tmax", "tmin"],
        },
        # CDC NORS human-health outbreak stream (One Health human pathway).
        "cdc_nors": {
            "start_year": 2014,
            "end_year": 2023,
        },
        "noaa": {
            # DEMOTED single-station demo path (kept for provenance only).
            # NYC Central Park GHCND station; tiny default window.
            "stations": ["USW00094728"],
            "start": "2023-01-01",
            "end": "2023-01-07",
            "data_types": ["TMAX", "TMIN", "PRCP"],
            "use_cdo": False,
        },
        "census_acs": {
            "year": 2022,
            "variables": ["B01001_001E"],  # total population
            "geo": "state:*",
        },
        "food_access_atlas": {"which": "lram_2019_xlsx"},
        "fsis_dir": str(FSIS_DIR),
    }


def run_ingestion(config: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Run every One Health source, collect provenance, and write reports.

    Each source is run behind its own boundary so one failure never aborts the
    others (Req 2.3, 3.7). Provenance records from all sources are written to
    ``data/interim/provenance_ingest.json`` and a short missingness/failure
    summary to ``data/interim/ingest_report.json`` (Req 2.7, 4.3).

    Returns a dict with the per-source :class:`IngestResult` objects and the
    paths of the two written reports.
    """

    # Load the project .env (dependency-free) so keyed sources such as
    # ACS (CENSUS_API_KEY) and the optional NOAA CDO path (NOAA_TOKEN) pick up
    # their secrets. Real environment variables always win over the file, and
    # the loader never logs or returns the secret values (Req 4).
    load_dotenv(REPO_ROOT / ".env")

    cfg = config or _default_config()
    fsis_dir = Path(cfg.get("fsis_dir", FSIS_DIR))
    _ensure_dir(INTERIM_ROOT)

    results: dict[str, IngestResult] = {}

    # Each call is independently guarded; the functions already swallow network
    # errors, but we wrap once more so an unexpected bug in one source cannot
    # take down the run (Req 2.3).
    def _guard(name: str, fn, *args, **kwargs) -> None:
        try:
            results[name] = fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            prov = new_provenance(
                source=name, url="",
                notes=f"GAP: unexpected ingestion error: {exc!r}",
            )
            results[name] = IngestResult(
                name, "failed", None, [prov], f"unexpected error: {exc!r}", None
            )

    # PRIMARY weather source: nClimDiv statewide monthly (national coverage).
    nclimdiv_cfg = cfg.get("nclimdiv", {})
    _guard(
        "noaa_nclimdiv", ingest_nclimdiv,
        start_year=nclimdiv_cfg.get("start_year", 2014),
        end_year=nclimdiv_cfg.get("end_year", 2026),
        elements=nclimdiv_cfg.get("elements"),
    )

    # CDC NORS human-health outbreak stream (One Health human pathway).
    nors_cfg = cfg.get("cdc_nors", {})
    _guard(
        "cdc_nors", ingest_cdc_nors,
        start_year=nors_cfg.get("start_year", 2014),
        end_year=nors_cfg.get("end_year", 2023),
    )

    # DEMOTED single-station NOAA demo path (retained for provenance). Only run
    # when explicitly enabled so the slow/narrow demo fetch does not run by
    # default now that nClimDiv is the primary weather source.
    if cfg.get("noaa") is not None:
        noaa_cfg = cfg.get("noaa", {})
        _guard(
            "noaa", ingest_noaa,
            noaa_cfg.get("stations", ["USW00094728"]),
            noaa_cfg.get("start", "2023-01-01"),
            noaa_cfg.get("end", "2023-01-07"),
            data_types=noaa_cfg.get("data_types"),
            use_cdo=noaa_cfg.get("use_cdo", False),
        )

    acs_cfg = cfg.get("census_acs", {})
    _guard(
        "census_acs", ingest_census_acs,
        acs_cfg.get("year", 2022),
        acs_cfg.get("variables", ["B01001_001E"]),
        acs_cfg.get("geo", "state:*"),
    )

    atlas_cfg = cfg.get("food_access_atlas", {})
    _guard("food_access_atlas", ingest_food_access_atlas,
           atlas_cfg.get("which", "lram_2019_xlsx"))

    _guard("fsis_local", ingest_fsis_local, fsis_dir)
    _guard("fsis_recalls", ingest_fsis_recalls, fsis_dir)

    # Collect provenance (Req 4.3) and write to interim.
    all_provenance: list[ProvenanceEntry] = []
    for res in results.values():
        all_provenance.extend(res.provenance)

    provenance_path = INTERIM_ROOT / "provenance_ingest.json"
    provenance_path.write_text(
        json.dumps(all_provenance, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Missingness / failure report (Req 2.3, 2.7).
    report = {
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "sources": {
            name: {
                "status": res.status,
                "has_data": res.data is not None,
                "error": res.error,
                "manual_instructions": res.manual_instructions,
                "provenance_count": len(res.provenance),
            }
            for name, res in results.items()
        },
        "summary": {
            "ok": sorted(n for n, r in results.items() if r.status == "ok"),
            "skipped_no_key": sorted(
                n for n, r in results.items() if r.status == "skipped_no_key"
            ),
            "failed": sorted(n for n, r in results.items() if r.status == "failed"),
        },
    }
    report_path = INTERIM_ROOT / "ingest_report.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return {
        "results": results,
        "provenance_path": provenance_path,
        "report_path": report_path,
        "report": report,
    }


if __name__ == "__main__":  # pragma: no cover - manual run entry point
    outcome = run_ingestion()
    print(json.dumps(outcome["report"], indent=2))
