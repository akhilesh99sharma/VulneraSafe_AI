"""Build data/external/facility_geocode.json: the committed MPI geocode cache.

OFFLINE, ONCE, COMMITTED, NO NETWORK, NO GEOCODING. Maintainer-run build script that
produces the committed Geocode_Cache the Facility Map decision layer reads at build
time. Mirrors ``scripts/build_us_geojson.py``: read a local source exactly once, write a
static committed output, and let the app read only that output so the runtime build
never calls a live origin and no network geocode happens at artifact-build time
(Req 3.1, 3.2, 3.3).

Coordinates come from REAL FSIS-published latitude/longitude
----------------------------------------------------------------
The FSIS Meat, Poultry & Egg Product Inspection (MPI) Directory CSVs already carry a
published ``latitude``/``longitude`` for each establishment. This script uses those
published coordinates DIRECTLY — it NEVER geocodes, NEVER calls a network service, and
NEVER fabricates a coordinate. A row whose latitude/longitude is missing, blank, or
non-numeric contributes NO coordinate; the establishment is honestly unplaced downstream
for "no published address in MPI Directory".

Join identity (verified)
-------------------------
The S03 establishment-surveillance ``establishment_id`` is the NUMERIC establishment id
(e.g. "10", "465", "126740", "6165844") — the SAME numeric space as the MPI files'
``establishment_id`` column. S03 does NOT carry the inspection "establishment number"
(the G####/M####/P#### string). Therefore the committed cache is KEYED on
``normalize_establishment_number(establishment_id)`` (the numeric id), which is exactly
what the decision layer joins on. The inspection ``establishment_number`` string is
carried THROUGH into each cache entry for display, but is never the join key.

What it does
------------
1. Read BOTH MPI directories under ``data/raw/fsis/`` (see ``MPI_ACTIVE_CANDIDATES`` /
   ``MPI_INACTIVE_CANDIDATES``), or explicit paths passed on the command line. Each row
   yields: ``establishment_id`` (numeric join id), ``establishment_number`` (inspection
   string, for display), ``establishment_name``, a full assembled address
   ("street, city, state zip"), ``county``, ``fips_code``, and ``latitude``/``longitude``.
2. If NEITHER directory is present, DO NOT fail and DO NOT fabricate: write an honest
   fallback cache with ``obtained=false`` and empty ``entries`` so every selected
   establishment becomes an Unplaced_Establishment with the stated reason "MPI Directory
   not yet obtained" (Req 2.7). This fallback is explicitly shippable.
3. If at least one directory is present: for each row, normalize the NUMERIC
   ``establishment_id`` with ``src.decision.facility_map.normalize_establishment_number``
   (the IDENTICAL normalization used on the join side), and write
   ``entries[normalized_id] = {lat, lon, address, source, establishment_number, county,
   fips_code}`` using the row's published latitude/longitude directly.

Precedence and the duplicate-key rule (Req 3.2)
-----------------------------------------------
* ACTIVE wins over INACTIVE. Rows are processed ACTIVE directory first, then INACTIVE.
  When the same normalized id appears in both, the ACTIVE entry is kept and the INACTIVE
  row is ignored silently (an active establishment superseding its inactive history is
  not an ambiguity).
* Within the SAME directory, if the same normalized id appears more than once:
  - IDENTICAL coordinates (same rounded lat/lon) collapse to a single entry
    (first-wins) with NO conflict recorded.
  - DIFFERENT coordinates are a genuine ambiguity: the key is recorded once in the
    top-level ``conflicts`` list and the first-seen entry is kept. The decision layer
    treats a key present in ``conflicts`` as an "ambiguous match in MPI Directory"
    unplaced reason, keeping the ambiguity honest rather than silently picking a winner.

Output cache shape (matches design + ``facility_map.load_geocode_cache``)
-------------------------------------------------------------------------
::

    {
      "source": "FSIS MPI Directory",
      "normalization": "trim; strip leading zeros; uppercase",
      "obtained": <bool>,
      "generated_from": ["<active filename>", "<inactive filename>"],
      "conflicts": ["<normalized id ambiguous within a directory>", ...],
      "entries": {
        "<Normalized_Establishment_Number (numeric id)>": {
          "lat": <float>, "lon": <float>,
          "address": "<assembled street, city, state zip>",
          "source": "fsis_mpi_active" | "fsis_mpi_inactive",
          "establishment_number": "<inspection G####/M#### string>",
          "county": "<county name or null>",
          "fips_code": "<fips or null>"
        }
      }
    }

``load_geocode_cache`` reads ``source``/``normalization``/``obtained``/``conflicts``/
``entries`` and tolerates the extra top-level ``generated_from`` key and the extra
per-entry keys (``establishment_number``/``county``/``fips_code``): it copies each entry
object wholesale via ``dict(raw["entries"])``, so the extra fields survive load.
``place_establishment`` needs only ``lat``/``lon``/``address`` and therefore keeps
working unchanged; the extra fields are carried for a later exporter row-enrichment task.

Written deterministically with ``json.dumps(..., indent=2, sort_keys=True)``, BOM-free
UTF-8, creating ``data/external`` if needed.

Reproducibility
---------------
The script is maintainer-run and its output committed to the repo; it is NEVER invoked
at build time by the exporter. Run it from the repository root::

    python scripts/build_facility_geocode.py [ACTIVE_MPI_PATH] [INACTIVE_MPI_PATH]

Both arguments are optional; with no paths and no local drop present, it writes the
honest ``obtained=false`` fallback.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]

# Make the ``src`` package importable when this script is run directly as
# ``python scripts/build_facility_geocode.py`` from the repo root (mirrors conftest.py,
# which does the same for the test suite). Must precede the ``from src...`` import.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Reuse the decision layer's normalization and committed-cache location so the build
# side and the join side can never diverge (Req 2.1, 3.1). Do NOT re-implement them.
from src.decision.facility_map import (  # noqa: E402  (after sys.path bootstrap)
    GEOCODE_CACHE_PATH,
    normalize_establishment_number,
)

RAW_FSIS_DIR = REPO_ROOT / "data" / "raw" / "fsis"

#: Documented local input locations for the ACTIVE FSIS MPI Directory, checked in order.
#: The real directory is a manual drop (the FSIS host is firewalled in this environment,
#: see data/raw/fsis/README_FSIS.md), so the maintainer saves it under data/raw/fsis/
#: with one of these names, or passes an explicit path as the first CLI argument.
MPI_ACTIVE_CANDIDATES = (
    RAW_FSIS_DIR / "MPI_Directory_by_Establishment_Number.csv",
    RAW_FSIS_DIR / "mpi_directory.csv",
    RAW_FSIS_DIR / "fsis_mpi_directory.csv",
)

#: Documented local input locations for the INACTIVE FSIS MPI Directory, checked in order.
MPI_INACTIVE_CANDIDATES = (
    RAW_FSIS_DIR / "MPI_Inactive_Directory_by_Establishment_Number.csv",
    RAW_FSIS_DIR / "mpi_inactive_directory.csv",
    RAW_FSIS_DIR / "fsis_mpi_inactive_directory.csv",
)

CACHE_SOURCE = "FSIS MPI Directory"
CACHE_NORMALIZATION = "trim; strip leading zeros; uppercase"

SOURCE_ACTIVE = "fsis_mpi_active"
SOURCE_INACTIVE = "fsis_mpi_inactive"

#: Round published coordinates to this many decimals when assembling entries so repeated
#: builds are byte-identical and duplicate-coordinate detection is stable. 6 decimals is
#: ~0.1 m precision — well beyond what a facility-location reference layer needs.
_COORD_ROUND = 6


def _norm_header(key: str) -> str:
    """Normalize a CSV header cell: strip, lowercase, spaces -> underscores."""
    return str(key).strip().lower().replace(" ", "_")


def _get(row: dict, *names: str) -> Optional[str]:
    """Return the first non-empty value in ``row`` whose header matches one of ``names``.

    Headers are matched case-insensitively with spaces normalized to underscores, so a
    directory exported with ``"Establishment ID"`` reads the same as ``establishment_id``.
    Returns ``None`` when no name matches or the matched value is blank.
    """
    lowered = {_norm_header(k): v for k, v in row.items()}
    for name in names:
        if name in lowered:
            val = lowered[name]
            if val is not None and str(val).strip() != "":
                return str(val).strip()
    return None


def _assemble_address(row: dict) -> Optional[str]:
    """Assemble a human-readable "street, city, state zip" address from an MPI row.

    Uses only the published location fields needed to identify the sampling location
    (Req 5.6 limits display to geocode-relevant address parts; no phone/email/contact).
    Returns ``None`` when no usable address component is present so the establishment is
    honestly unplaced for "no published address in MPI Directory" rather than carrying an
    empty string.
    """
    street = _get(row, "street", "address", "street_address")
    city = _get(row, "city")
    state = _get(row, "state", "state_code", "st")
    zip_code = _get(row, "zip", "zip_code", "zipcode", "postal_code")

    city_state_zip_parts: list[str] = []
    if city:
        city_state_zip_parts.append(city)
    tail = " ".join(p for p in (state, zip_code) if p)
    if tail:
        city_state_zip_parts.append(tail)

    segments: list[str] = []
    if street:
        segments.append(street)
    segments.extend(city_state_zip_parts)

    assembled = ", ".join(s.strip() for s in segments if s and s.strip())
    return assembled or None


def _usable_coord(value: Optional[str]) -> Optional[float]:
    """Coerce a published lat/lon string to a finite float, or ``None`` when unusable.

    A usable coordinate is a real finite number. ``None``, a blank/non-numeric string,
    or a non-finite float (NaN/inf) is NOT usable and contributes no coordinate — the
    establishment is unplaced downstream, never pinned at a fabricated location.
    """
    if value is None:
        return None
    s = str(value).strip()
    if s == "":
        return None
    try:
        f = float(s)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):  # NaN or inf
        return None
    return f


def read_mpi_rows(path: Path) -> list[dict]:
    """Read one FSIS MPI Directory CSV into normalized row dicts, in file order.

    Each returned row carries the fields the committed cache needs, with raw values
    pre-extracted by header alias:

      * ``establishment_id``     — the NUMERIC join id (raw, un-normalized)
      * ``establishment_number`` — the inspection G####/M#### string (for display)
      * ``establishment_name``   — FSIS-published name (or ``None``)
      * ``address``              — assembled "street, city, state zip" (or ``None``)
      * ``county`` / ``fips_code`` — carried for later row enrichment (or ``None``)
      * ``lat`` / ``lon``        — published coordinates as floats (or ``None``)

    Rows are returned in the source file's original order so the within-directory
    duplicate-key first-wins resolution is deterministic. Read as UTF-8 with BOM
    tolerance (``utf-8-sig``).
    """
    rows: list[dict] = []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        for raw in csv.DictReader(fh):
            rows.append({
                "establishment_id": _get(raw, "establishment_id", "est_id", "estid"),
                "establishment_number": _get(
                    raw, "establishment_number", "establishment_no", "est_number",
                    "est_no",
                ),
                "establishment_name": _get(raw, "establishment_name", "name"),
                "address": _assemble_address(raw),
                "county": _get(raw, "county"),
                "fips_code": _get(raw, "fips_code", "fips"),
                "lat": _usable_coord(_get(raw, "latitude", "lat")),
                "lon": _usable_coord(_get(raw, "longitude", "lon", "lng")),
            })
    return rows


def _add_rows(
    rows: list[dict],
    source_label: str,
    entries: dict[str, dict],
    conflict_set: set[str],
) -> None:
    """Fold one directory's rows into ``entries`` applying the precedence + dup rules.

    Called ACTIVE-first then INACTIVE. A key already owned by an EARLIER directory
    (active) is never overwritten by a later one (inactive): ACTIVE wins (the inactive
    row is skipped silently, not a conflict). Within the SAME directory call, a repeated
    key with identical rounded coordinates collapses first-wins with no conflict; a
    repeated key with different coordinates records the key in ``conflict_set`` once and
    keeps the first entry. A row with no usable establishment id, no usable coordinate,
    or no assembled address contributes no entry (honest, never fabricated).
    """
    claimed_this_dir: set[str] = set()
    for row in rows:
        key = normalize_establishment_number(row.get("establishment_id") or "")
        if not key:
            continue
        lat, lon = row.get("lat"), row.get("lon")
        address = row.get("address")
        if lat is None or lon is None or not address:
            # No published coordinate/address -> no entry (unplaced downstream), honest.
            continue
        lat_r, lon_r = round(float(lat), _COORD_ROUND), round(float(lon), _COORD_ROUND)

        if key in entries:
            # Already owned. If owned by an EARLIER directory (active beating inactive),
            # precedence applies: skip silently. If owned within THIS directory, compare
            # coordinates to decide identical-collapse vs genuine ambiguity.
            if key in claimed_this_dir:
                existing = entries[key]
                if (existing.get("lat") != lat_r) or (existing.get("lon") != lon_r):
                    conflict_set.add(key)
                # identical coordinates -> collapse first-wins, no conflict.
            # else: owned by the active directory -> active wins, skip inactive row.
            continue

        claimed_this_dir.add(key)
        entries[key] = {
            "lat": lat_r,
            "lon": lon_r,
            "address": str(address),
            "source": source_label,
            "establishment_number": row.get("establishment_number"),
            "county": row.get("county"),
            "fips_code": row.get("fips_code"),
        }


def build_entries(
    active_rows: list[dict],
    inactive_rows: list[dict],
) -> tuple[dict[str, dict], list[str]]:
    """Build the committed ``entries`` + ``conflicts`` from active + inactive MPI rows.

    ACTIVE rows are folded first (so active wins on any id present in both), then
    INACTIVE rows. Returns ``(entries, conflicts)`` where ``conflicts`` is the sorted,
    de-duplicated list of normalized ids that were ambiguous WITHIN a single directory
    (same id, different coordinates). Active-vs-inactive overlap is NOT a conflict — it
    is resolved by precedence (Req 3.2).
    """
    entries: dict[str, dict] = {}
    conflict_set: set[str] = set()
    _add_rows(active_rows, SOURCE_ACTIVE, entries, conflict_set)
    _add_rows(inactive_rows, SOURCE_INACTIVE, entries, conflict_set)
    return entries, sorted(conflict_set)


def build_cache(
    active_path: Optional[Path],
    inactive_path: Optional[Path],
) -> dict:
    """Assemble the full committed Geocode_Cache dict (does not write it).

    When NEITHER directory path exists, returns the honest ``obtained=false`` fallback
    (empty ``entries``/``conflicts``). Otherwise reads whichever directories are present
    (active and/or inactive), uses their published coordinates directly (no geocoding),
    and returns a populated ``obtained=true`` cache. Never raises on an absent directory.
    """
    have_active = active_path is not None and active_path.exists()
    have_inactive = inactive_path is not None and inactive_path.exists()

    if not have_active and not have_inactive:
        return {
            "source": CACHE_SOURCE,
            "normalization": CACHE_NORMALIZATION,
            "obtained": False,
            "generated_from": [],
            "conflicts": [],
            "entries": {},
        }

    active_rows = read_mpi_rows(active_path) if have_active else []
    inactive_rows = read_mpi_rows(inactive_path) if have_inactive else []
    entries, conflicts = build_entries(active_rows, inactive_rows)

    generated_from: list[str] = []
    if have_active:
        generated_from.append(active_path.name)
    if have_inactive:
        generated_from.append(inactive_path.name)

    return {
        "source": CACHE_SOURCE,
        "normalization": CACHE_NORMALIZATION,
        "obtained": True,
        "generated_from": generated_from,
        "conflicts": conflicts,
        "entries": entries,
    }


def write_cache(cache: dict, out_path: Path = GEOCODE_CACHE_PATH) -> None:
    """Write ``cache`` to ``out_path`` deterministically and BOM-free (Req 3.1, 3.5).

    Creates the parent directory if needed and serializes with
    ``json.dumps(..., indent=2, sort_keys=True)`` so repeated builds from identical
    inputs are byte-identical. Written as UTF-8 WITHOUT a byte-order mark.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(cache, indent=2, sort_keys=True)
    out_path.write_text(text, encoding="utf-8")


def _resolve_path(arg: Optional[str], candidates: tuple[Path, ...]) -> Optional[Path]:
    """Resolve an input path from a CLI arg or the documented candidates.

    An explicit CLI argument wins (even if it does not exist — the caller sees the
    not-found handling). Otherwise the first existing candidate is used, or ``None``.
    """
    if arg:
        return Path(arg)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def main(argv: Optional[list[str]] = None) -> int:
    """Entry point: resolve inputs, build the cache, write it, and report what happened.

    ``argv[0]`` (optional) is the ACTIVE MPI Directory path; ``argv[1]`` (optional) is
    the INACTIVE MPI Directory path. Returns 0 always (an absent directory is an honest,
    shippable outcome, not a failure).
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    active_arg = argv[0] if len(argv) >= 1 else None
    inactive_arg = argv[1] if len(argv) >= 2 else None

    active_path = _resolve_path(active_arg, MPI_ACTIVE_CANDIDATES)
    inactive_path = _resolve_path(inactive_arg, MPI_INACTIVE_CANDIDATES)

    have_active = active_path is not None and active_path.exists()
    have_inactive = inactive_path is not None and inactive_path.exists()

    if not have_active and not have_inactive:
        looked = " | ".join(
            str(c) for c in (*MPI_ACTIVE_CANDIDATES, *MPI_INACTIVE_CANDIDATES)
        )
        print(
            "MPI Directory NOT FOUND. Looked for: "
            f"{looked}. Writing honest fallback cache with obtained=false and empty "
            "entries; every selected establishment will be unplaced with reason "
            '"MPI Directory not yet obtained" (Req 2.7). This is a shippable result.'
        )
        cache = build_cache(None, None)
        write_cache(cache)
        print(f"WROTE {GEOCODE_CACHE_PATH} obtained=false entries=0 conflicts=0")
        return 0

    cache = build_cache(active_path if have_active else None,
                        inactive_path if have_inactive else None)
    write_cache(cache)

    active_count = sum(1 for e in cache["entries"].values()
                       if e.get("source") == SOURCE_ACTIVE)
    inactive_count = sum(1 for e in cache["entries"].values()
                         if e.get("source") == SOURCE_INACTIVE)
    print(
        f"WROTE {GEOCODE_CACHE_PATH} obtained=true "
        f"entries={len(cache['entries'])} "
        f"(active={active_count} inactive={inactive_count}) "
        f"conflicts={len(cache['conflicts'])}"
    )
    print(f"generated_from={cache['generated_from']}")
    if cache["conflicts"]:
        print(
            "CONFLICTS (same normalized id, different coords within one directory, "
            f"first-wins): count={len(cache['conflicts'])} sample={cache['conflicts'][:20]}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
