"""Facility Map — reproducible decision layer: deterministic join + offline geocode.

Geographically plots FSIS-sampled establishments carrying an elevated surveillance
signal as an OBSERVED sourcing-scrutiny reference layer for the retailer Food Safety
Operations Director. Introduces NO new modeling and NO model training: it is a
deterministic join of the S03 establishment-surveillance scan and the ACTIONQ
action_queue against a committed, geocoded-once MPI Directory cache.

Decision support only: every surfaced establishment is OBSERVED, carries
human_review=True, and is framed as a sampling location with a surveillance signal —
never a contamination or illness claim, never the retailer's supplier, never
"recall"/"contaminated"/"unsafe"/a regulatory directive. Establishments that cannot be
matched or geocoded are listed as unplaced with a stated reason, never approximated;
geocode coverage is a reported measured percentage, never assumed to be 100%.

This module currently provides the module constants and the establishment-number
normalization used identically on both join sides. Selection, join, coverage, and the
orchestrator are added by later tasks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Protocol, TypedDict

REPO_ROOT = Path(__file__).resolve().parents[2]
INTERIM_DIR = REPO_ROOT / "data" / "interim"
EXTERNAL_DIR = REPO_ROOT / "data" / "external"
CACHE_PATH = INTERIM_DIR / "facility_map.json"
GEOCODE_CACHE_PATH = EXTERNAL_DIR / "facility_geocode.json"
#: Supplemental, SEPARATE historical-candidate overlay for S03 establishments that are
#: ABSENT from the FSIS MPI Directory. This is NOT the official MPI geocode cache and is
#: NEVER written by this module; it is read-only. See load_supplemental_mapping.
SUPPLEMENTAL_MAPPING_PATH = EXTERNAL_DIR / "facility_supplemental_mapping.json"

MODULE_ID = "FACILITYMAP"
METHOD_VERSION = "fm.v1"

#: Mirrors src/decision/action_queue.TOP_N_S03 (the locked top-N establishment
#: selection). Re-declared here with this comment; kept equal to action_queue's — a
#: unit test asserts the two constants cannot silently diverge.
TOP_N_S03 = 12

#: Mirrors src/decision/action_queue.FORBIDDEN_TERMS (enforced again by the exporter).
FORBIDDEN_TERMS = ("recall", "contaminated", "unsafe", "seize", "shut down",
                   "destroy", "government order", "mandate")

_PATHOGENS = ("Salmonella", "Listeria", "STEC")
_COMMODITY = {"Salmonella": "raw_poultry", "Listeria": "rte", "STEC": "raw_beef"}


def normalize_establishment_number(raw: str) -> str:
    """Deterministic normalization applied identically to both join sides (Req 2.1).

    1. Trim surrounding whitespace.
    2. Remove leading zeros (but keep at least one digit; "00" -> "0").
    3. Uppercase.

    Pure, order-independent, and idempotent. None or whitespace-only input yields "".
    """
    if raw is None:
        return ""
    s = str(raw).strip()
    if not s:
        return ""
    # Strip leading zeros while keeping at least one character: "00" -> "0",
    # "007" -> "7", "0A5" -> "A5". lstrip never removes the final char because we
    # restore a single "0" when the whole string was zeros.
    stripped = s.lstrip("0")
    if stripped == "":
        stripped = "0"
    return stripped.upper()


# ---------------------------------------------------------------------------
# Swappable geocoder interface (OFFLINE-ONLY, BUILD-TIME-ONLY)
# ---------------------------------------------------------------------------


class Geocoder(Protocol):
    """Offline geocoder contract. Resolves an MPI-published address to a location.

    OFFLINE-ONLY and BUILD-TIME-ONLY: a ``Geocoder`` is used exclusively by the
    one-time offline build script (``scripts/build_facility_geocode.py``, a later
    task), which resolves each MPI-published address to a location exactly once and
    commits the result to the Geocode_Cache. It is NEVER called by the runtime
    exporter/compute path — that path reads only the committed Geocode_Cache and
    makes no network geocode request (Req 3.1, 3.3).

    The interface is swappable so the actual geocoding mechanism is an implementation
    detail (committed local gazetteer, replayed one-time offline/manual result, etc.)
    while the committed-cache contract stays fixed.
    """

    def geocode(self, address: str) -> Optional[tuple[float, float]]:
        """Return (lat, lon) or None when the address cannot be resolved offline.

        Never makes a network call; an implementation may use a committed local
        gazetteer or replay a one-time offline/manual result.
        """
        ...


class GazetteerGeocoder:
    """Concrete default :class:`Geocoder` backed by a committed local gazetteer.

    The gazetteer is an in-memory mapping (loaded from a committed file by the build
    script, or passed in directly for tests) from an address string — or a
    normalized key — to a ``(lat, lon)`` pair. Lookup is a pure, deterministic
    dictionary hit: :meth:`geocode` returns the mapped location or ``None`` on a miss.

    This makes NO network calls. The gazetteer file it reads from is committed to the
    repository, so the lookup is reproducible and the geocode is computed offline.
    Like every :class:`Geocoder`, it is BUILD-TIME-ONLY — invoked by the one-time
    offline build script, never by the runtime exporter.
    """

    def __init__(self, gazetteer: dict[str, tuple[float, float]]) -> None:
        """Construct with an in-memory gazetteer mapping address/key -> (lat, lon)."""
        self._gazetteer = dict(gazetteer)

    def geocode(self, address: str) -> Optional[tuple[float, float]]:
        """Return the committed gazetteer hit for ``address`` or ``None`` on a miss.

        Pure and deterministic; performs no network request.
        """
        if address is None:
            return None
        return self._gazetteer.get(address)

# ---------------------------------------------------------------------------
# Selection helpers (pure; operate on already-loaded caches)
# ---------------------------------------------------------------------------
#
# These helpers accept caches that have already been loaded (by the caller, via
# the S03 / action_queue ``load_cache`` functions) so they stay pure and trivially
# unit-testable with small in-memory fixtures: they perform NO I/O and write NOTHING.
#
# Identity note (action_queue):
#   The ACTIONQ action_queue establishment entries produced by
#   ``src.decision.action_queue.derive_s03_actions`` do NOT carry a stable
#   ``establishment_id``. Each entry carries ``target_type == "establishment"``,
#   ``pathogen``, ``evidence_summary``, ``human_review``, ``status`` and a display
#   ``target`` string of the form ``"<name> (<state>)"`` where
#   ``name = establishment_name or f"Establishment {establishment_id}"``. We never
#   fabricate an ``establishment_id`` from that string. Instead, to recover the real
#   establishment identity, we reconstruct the SAME display string from each S03
#   record (via :func:`_s03_action_target_label`) and match the action's ``target``
#   back to the S03 record, keying the union on the S03 record's true
#   ``establishment_id``. An action-queue establishment target that matches no S03
#   record for its pathogen carries only the identity the action itself holds (its
#   ``target`` label), and is keyed on that label — no ``establishment_id`` is invented.


class SelectedEstablishment(TypedDict):
    """One signal-bearing establishment selected for the Facility Map (pre-join).

    Preserves the S03 identity/signal fields needed for later placement and the
    rendered rows. ``source_selection`` records whether the establishment was
    selected from the elevated S03 signal only, the action_queue only, or both.
    ``establishment_id`` is the join identity: the real S03 ``establishment_id`` when
    the establishment is known to S03; for an action-queue-only target that matched no
    S03 record, it falls back to the action's display ``target`` label (no id is
    fabricated). ``normalized_establishment_number`` is the MPI join key; it is empty
    for an action-queue-only target with no recoverable establishment number.
    """

    pathogen: str
    establishment_id: str
    normalized_establishment_number: str
    establishment_name: Optional[str]
    state: str
    eb_posterior: Optional[float]
    ci_low: Optional[float]
    ci_high: Optional[float]
    sample_n: int
    positive_n: int
    support_status: str
    source_selection: str            # "s03" | "action_queue" | "both"
    evidence_summary: str
    human_review: bool               # always True
    status: str                      # "OBSERVED"


def _s03_action_target_label(record: dict) -> str:
    """Reconstruct the action_queue display ``target`` for an S03 establishment.

    Mirrors ``src.decision.action_queue.derive_s03_actions`` exactly:
    ``name = establishment_name or f"Establishment {establishment_id}"`` and
    ``target = f"{name} ({state})"``. Used ONLY to match an action-queue establishment
    target back to its S03 record so the union can key on the real establishment_id —
    never to fabricate an identity.
    """
    name = record.get("establishment_name") or f"Establishment {record.get('establishment_id')}"
    state = record.get("state", "UNK")
    return f"{name} ({state})"


def select_s03_elevated(s03_cache: Optional[dict]) -> dict[str, list[dict]]:
    """Per pathogen, the top ``TOP_N_S03`` elevated-signal S03 establishments.

    For each pathogen whose ``availability_status == "available"``, take the
    establishments with ``support_status == "ok"`` AND a non-null ``eb_posterior``,
    order them by ``eb_posterior`` descending (stable deterministic tie-break by
    normalized establishment number ascending), and keep the top ``TOP_N_S03``
    (Req 1.1). ``low_support`` establishments are NEVER included here and are never on
    the elevated-selection basis (Req 1.4); they are also never labeled safe or clean.

    Returns a ``{pathogen: [s03_record, ...]}`` mapping that keeps all available
    pathogens first-class (a pathogen with zero elevated establishments maps to an
    empty list). Pure: reads only the passed cache, writes nothing. When
    ``s03_cache`` is ``None`` or carries no pathogens, returns an empty mapping.
    """
    out: dict[str, list[dict]] = {}
    if not s03_cache or not s03_cache.get("pathogens"):
        return out
    for pathogen, pdata in s03_cache["pathogens"].items():
        if pdata.get("availability_status") != "available":
            continue
        ests = [
            e for e in pdata.get("establishments", {}).values()
            if e.get("support_status") == "ok" and e.get("eb_posterior") is not None
        ]
        # Deterministic order: eb_posterior desc, then normalized establishment
        # number asc as a stable tie-break so repeated builds are identical.
        ests.sort(
            key=lambda e: (
                -(e.get("eb_posterior") or 0.0),
                normalize_establishment_number(e.get("establishment_id", "")),
            )
        )
        out[pathogen] = ests[:TOP_N_S03]
    return out


def select_action_queue_establishments(aq_cache: Optional[dict]) -> dict[str, list[dict]]:
    """Per pathogen, the action_queue entries that target an establishment.

    Selects the ACTIONQ ``actions`` with ``target_type == "establishment"`` (Req 1.2),
    grouping them by ``pathogen``. Each selected entry carries forward
    ``human_review=True`` and ``status="OBSERVED"`` and the entry's own
    ``evidence_summary`` (Req 10.4). We do not trust the cache's stamped values blindly
    for the two provenance flags — they are set explicitly to their fixed decision-layer
    values so an action-queue target can never be surfaced as anything other than a
    human-reviewed, OBSERVED suggestion.

    Returns a ``{pathogen: [entry, ...]}`` mapping. Pure: reads only the passed cache,
    writes nothing. When ``aq_cache`` is ``None`` or carries no actions, returns an
    empty mapping.
    """
    out: dict[str, list[dict]] = {}
    if not aq_cache or not aq_cache.get("actions"):
        return out
    for action in aq_cache["actions"]:
        if action.get("target_type") != "establishment":
            continue
        pathogen = action.get("pathogen")
        if pathogen is None:
            continue
        entry = {
            "pathogen": pathogen,
            "target": action.get("target"),
            "source_module": action.get("source_module"),
            "evidence_summary": action.get("evidence_summary", ""),
            "human_review": True,
            "status": "OBSERVED",
        }
        out.setdefault(pathogen, []).append(entry)
    return out


def select_signal_bearing(
    s03_cache: Optional[dict],
    aq_cache: Optional[dict],
) -> dict[str, list[SelectedEstablishment]]:
    """Per-pathogen union of elevated-S03 and action-queue establishment selections.

    Combines :func:`select_s03_elevated` and
    :func:`select_action_queue_establishments`, de-duplicated by
    ``(pathogen, establishment_id)`` (Req 1.5). Each resulting record records its
    ``source_selection`` in ``{"s03", "action_queue", "both"}``:

    * ``"s03"``       — selected only from the elevated S03 signal.
    * ``"action_queue"`` — selected only as an action-queue establishment target.
    * ``"both"``      — both (the action target matched an elevated S03 record).

    Establishments that are neither elevated-S03 nor an action-queue establishment
    target are excluded (Req 1.3); a ``low_support`` establishment is therefore never
    here on the elevated basis (Req 1.4). All three pathogens stay first-class: every
    pathogen that appears in either selection is a key (an available pathogen with no
    signal-bearing establishment maps to an empty list). Each record preserves the S03
    fields (name, state, eb_posterior, ci_low, ci_high, sample_n, positive_n) when the
    establishment is known to S03, for the later placed/unplaced rows.

    Action-queue establishment targets are matched back to the S03 records by the
    reconstructed display label (see :func:`_s03_action_target_label`); the match keys
    the union on the S03 record's real ``establishment_id``. An action-queue-only target
    that matches no S03 record carries only the identity the action holds (its display
    ``target`` label) and is keyed on that label — no ``establishment_id`` is fabricated.

    Pure: reads only the two passed caches, writes nothing. Output lists are emitted in
    a deterministic order (eb_posterior desc then establishment_id asc, action-queue-only
    targets last ordered by their label) so repeated builds are identical.
    """
    s03_by_pathogen = select_s03_elevated(s03_cache)
    aq_by_pathogen = select_action_queue_establishments(aq_cache)

    # Build a per-pathogen lookup of EVERY S03 record (not just elevated) so an
    # action-queue target can be matched back to its real establishment identity
    # even when that establishment is not in the elevated top-N.
    s03_records_by_pathogen: dict[str, dict[str, dict]] = {}
    s03_label_index: dict[str, dict[str, dict]] = {}
    if s03_cache and s03_cache.get("pathogens"):
        for pathogen, pdata in s03_cache["pathogens"].items():
            if pdata.get("availability_status") != "available":
                continue
            by_id: dict[str, dict] = {}
            by_label: dict[str, dict] = {}
            for record in pdata.get("establishments", {}).values():
                eid = str(record.get("establishment_id"))
                by_id[eid] = record
                by_label[_s03_action_target_label(record)] = record
            s03_records_by_pathogen[pathogen] = by_id
            s03_label_index[pathogen] = by_label

    pathogens = sorted(set(s03_by_pathogen) | set(aq_by_pathogen))
    out: dict[str, list[SelectedEstablishment]] = {}

    for pathogen in pathogens:
        # key -> SelectedEstablishment, keyed by the join identity for de-dup.
        selected: dict[str, SelectedEstablishment] = {}

        # 1) Elevated S03 selections.
        for record in s03_by_pathogen.get(pathogen, []):
            eid = str(record.get("establishment_id"))
            selected[eid] = _selected_from_s03(pathogen, record, "s03")

        # 2) Action-queue establishment targets.
        label_index = s03_label_index.get(pathogen, {})
        for entry in aq_by_pathogen.get(pathogen, []):
            target = entry.get("target")
            matched = label_index.get(target) if target is not None else None
            if matched is not None:
                eid = str(matched.get("establishment_id"))
                if eid in selected:
                    # Already elevated-S03 selected -> both sources.
                    selected[eid]["source_selection"] = "both"
                    # Prefer the action's evidence_summary when present (it is the
                    # human-review-facing summary the action queue surfaced).
                    if entry.get("evidence_summary"):
                        selected[eid]["evidence_summary"] = entry["evidence_summary"]
                else:
                    # Known to S03 but not in the elevated top-N: selected purely as an
                    # action-queue target, with its real S03 identity/signal fields.
                    rec = _selected_from_s03(pathogen, matched, "action_queue")
                    if entry.get("evidence_summary"):
                        rec["evidence_summary"] = entry["evidence_summary"]
                    selected[eid] = rec
            else:
                # No S03 record matched: key on the action's display label; do NOT
                # fabricate an establishment_id or normalized number.
                key = f"__aq__:{target}"
                if key not in selected:
                    selected[key] = SelectedEstablishment(
                        pathogen=pathogen,
                        establishment_id=str(target) if target is not None else "",
                        normalized_establishment_number="",
                        establishment_name=None,
                        state="UNK",
                        eb_posterior=None,
                        ci_low=None,
                        ci_high=None,
                        sample_n=0,
                        positive_n=0,
                        support_status="unknown",
                        source_selection="action_queue",
                        evidence_summary=entry.get("evidence_summary", ""),
                        human_review=True,
                        status="OBSERVED",
                    )

        # Deterministic order: eb_posterior desc (nulls last), then
        # establishment_id asc, so repeated builds are byte-identical.
        ordered = sorted(
            selected.values(),
            key=lambda r: (
                r["eb_posterior"] is None,
                -(r["eb_posterior"] or 0.0),
                r["establishment_id"],
            ),
        )
        out[pathogen] = ordered

    return out


def _selected_from_s03(
    pathogen: str,
    record: dict,
    source_selection: str,
) -> SelectedEstablishment:
    """Build a :class:`SelectedEstablishment` from an S03 establishment record.

    Preserves the S03 identity/signal fields and stamps the fixed decision-layer
    provenance (``human_review=True``, ``status="OBSERVED"``). Pure helper used by
    :func:`select_signal_bearing`.
    """
    eid = str(record.get("establishment_id"))
    return SelectedEstablishment(
        pathogen=pathogen,
        establishment_id=eid,
        normalized_establishment_number=normalize_establishment_number(eid),
        establishment_name=record.get("establishment_name"),
        state=record.get("state", "UNK"),
        eb_posterior=record.get("eb_posterior"),
        ci_low=record.get("ci_low"),
        ci_high=record.get("ci_high"),
        sample_n=int(record.get("sample_n", 0) or 0),
        positive_n=int(record.get("positive_n", 0) or 0),
        support_status=record.get("support_status", "unknown"),
        source_selection=source_selection,
        evidence_summary=record.get("evidence_summary", ""),
        human_review=True,
        status="OBSERVED",
    )

# ---------------------------------------------------------------------------
# Join, coverage, and orchestrator (BUILD-TIME, OFFLINE-ONLY)
# ---------------------------------------------------------------------------
#
# These functions complete the runtime decision-layer build. They NEVER call a
# Geocoder and NEVER make a network request: placement reads only the committed
# Geocode_Cache that the one-time offline build script wrote. Establishments that
# cannot be matched/geocoded are recorded as unplaced with a stated reason — never
# approximated — and geocode coverage is a reported measured percentage, never
# assumed to be 100% (Req 2.7, 3.3, 4.1-4.6, 13.2, 13.3).

import json as _json
from typing import Any

# Decision-layer loaders for the two upstream caches. Imported at module scope (per the
# design) so they can be monkeypatched in tests. Aliased to avoid shadowing this module's
# own load_cache. These NEVER geocode; they read already-written interim caches.
from src.analysis.establishment_surveillance import load_cache as load_s03_cache
from src.decision.action_queue import load_cache as load_aq_cache


#: The documented unplaced reasons (Req 2.3-2.5, 2.7). A placed row always clears
#: ``unplaced_reason``; an unplaced row always carries exactly one of these.
UNPLACED_DIRECTORY_NOT_OBTAINED = "MPI Directory not yet obtained"
UNPLACED_NOT_FOUND = "establishment number not found in MPI Directory"
UNPLACED_NO_ADDRESS = "no published address in MPI Directory"
UNPLACED_AMBIGUOUS = "ambiguous match in MPI Directory"


def load_geocode_cache(path: Path = GEOCODE_CACHE_PATH) -> dict:
    """Read the committed Geocode_Cache; NEVER geocodes and makes NO network call (Req 3.3).

    Returns the committed cache dict with the designed shape::

        {"source": str, "normalization": str, "obtained": bool,
         "conflicts": [<normalized key>, ...],
         "entries": {"<normalized_establishment_number>":
                        {"lat": float, "lon": float, "address": str, "source": str}}}

    When the committed cache file does not exist, returns an honest empty fallback with
    ``obtained=False`` and empty ``entries`` so EVERY selected establishment becomes
    unplaced with the stated reason "MPI Directory not yet obtained" (Req 2.7) rather
    than fabricating a location. Malformed JSON is tolerated the same way S03's
    ``load_cache`` tolerates it — an ``(OSError, ValueError)`` falls back to the same
    honest empty structure rather than raising at build time.

    Normalizes the returned shape defensively: missing ``obtained`` defaults to False,
    missing ``conflicts`` to an empty list, and missing ``entries`` to an empty dict, so
    downstream placement can rely on the keys always being present.
    """
    fallback = {
        "source": "FSIS MPI Directory",
        "normalization": "trim; strip leading zeros; uppercase",
        "obtained": False,
        "conflicts": [],
        "entries": {},
    }
    if not path.exists():
        return fallback
    try:
        raw = _json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback
    if not isinstance(raw, dict):
        return fallback
    return {
        "source": raw.get("source", "FSIS MPI Directory"),
        "normalization": raw.get("normalization", "trim; strip leading zeros; uppercase"),
        "obtained": bool(raw.get("obtained", False)),
        "conflicts": list(raw.get("conflicts", []) or []),
        "entries": dict(raw.get("entries", {}) or {}),
    }


def load_supplemental_mapping(path: Path = SUPPLEMENTAL_MAPPING_PATH) -> dict:
    """Read the committed supplemental historical-candidate overlay; NEVER geocodes.

    This overlay is a SEPARATE, read-only file (``data/external/facility_supplemental_mapping.json``)
    of historical-candidate facility locations for S03 establishments that are ABSENT
    from the FSIS MPI Directory. It is NOT the official MPI geocode cache
    (:data:`GEOCODE_CACHE_PATH`) and never overwrites it. Each entry is keyed on the S03
    numeric ``establishment_id`` string; the numeric id is NEVER asserted to equal the
    historical USDA inspection number — the link is an external-research heuristic
    (name + state + address) that is NOT verified against any FSIS establishment id.

    Makes NO network call. Returns the committed dict with at least an ``entries`` key.
    When the file is absent or malformed, returns an honest empty fallback
    (``{"entries": {}}``) with the same ``(OSError, ValueError)`` tolerance as
    :func:`load_geocode_cache`, so a missing overlay simply means no supplemental
    candidates rather than a build failure.
    """
    fallback = {"entries": {}}
    if not path.exists():
        return fallback
    try:
        raw = _json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback
    if not isinstance(raw, dict):
        return fallback
    entries = raw.get("entries", {})
    if not isinstance(entries, dict):
        entries = {}
    out = dict(raw)
    out["entries"] = entries
    return out


def _usable_coord(value: Any) -> Optional[float]:
    """Coerce a cache ``lat``/``lon`` to a float, or ``None`` when unusable.

    A usable coordinate is a real finite number. ``None``, a non-numeric string, or a
    non-finite float (NaN/inf) is NOT usable and makes the row unplaced for "no
    published address in MPI Directory" rather than a fabricated/garbage pin.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):  # NaN or inf
        return None
    return f


def place_establishment(selected: SelectedEstablishment, geocode_cache: dict) -> dict:
    """Join one :class:`SelectedEstablishment` to the committed Geocode_Cache (Req 2.2).

    Performs the exact-equality join on ``normalized_establishment_number`` against
    ``geocode_cache["entries"]`` — no establishment-name, no fuzzy matching (Req 2.2).
    Returns a row dict carrying through every SelectedEstablishment field plus the
    placement outcome. A placed row carries real ``lat``/``lon``/``address`` from the
    matched cache entry and a cleared ``unplaced_reason``; an unplaced row carries
    ``lat``/``lon``/``address = None`` and a non-empty ``unplaced_reason`` drawn from the
    documented set (Req 2.3-2.7):

    * cache ``obtained`` is False               -> "MPI Directory not yet obtained" (Req 2.7)
    * normalized number is ""                    -> "establishment number not found in MPI Directory" (Req 2.4)
    * key absent from ``entries``                -> "establishment number not found in MPI Directory" (Req 2.4)
    * key listed in ``conflicts``                -> "ambiguous match in MPI Directory" (Req 2.3)
    * entry lacks usable lat/lon OR has no address -> "no published address in MPI Directory" (Req 2.5)
    * otherwise                                   -> placed, carrying lat/lon/address (Req 2.6)

    Pure: reads only the passed selection and cache, writes nothing, NEVER geocodes.
    """
    norm = selected.get("normalized_establishment_number", "") or ""
    entries = geocode_cache.get("entries", {}) or {}
    conflicts = set(geocode_cache.get("conflicts", []) or [])
    obtained = bool(geocode_cache.get("obtained", False))

    def _row(placement_status: str,
             lat: Optional[float], lon: Optional[float],
             address: Optional[str], unplaced_reason: Optional[str]) -> dict:
        return {
            "pathogen": selected["pathogen"],
            "establishment_id": selected["establishment_id"],
            "normalized_establishment_number": norm,
            "establishment_name": selected.get("establishment_name"),
            "state": selected.get("state", "UNK"),
            "eb_posterior": selected.get("eb_posterior"),
            "ci_low": selected.get("ci_low"),
            "ci_high": selected.get("ci_high"),
            "sample_n": int(selected.get("sample_n", 0) or 0),
            "positive_n": int(selected.get("positive_n", 0) or 0),
            "support_status": selected.get("support_status", "unknown"),
            "source_selection": selected.get("source_selection", "s03"),
            "placement_status": placement_status,
            "lat": lat,
            "lon": lon,
            "address": address,
            "unplaced_reason": unplaced_reason,
            "evidence_summary": selected.get("evidence_summary", ""),
            "human_review": True,
            "status": "OBSERVED",
        }

    # (a) Directory not yet obtained -> everything unplaced honestly (Req 2.7).
    if not obtained:
        return _row("unplaced", None, None, None, UNPLACED_DIRECTORY_NOT_OBTAINED)

    # (b) No recoverable establishment number (action-queue-only target) -> not found.
    if norm == "":
        return _row("unplaced", None, None, None, UNPLACED_NOT_FOUND)

    # (c) Ambiguous: the normalized key collided across >1 MPI rows (Req 2.3).
    if norm in conflicts:
        return _row("unplaced", None, None, None, UNPLACED_AMBIGUOUS)

    # (d) Absent from the committed cache entries (Req 2.4).
    entry = entries.get(norm)
    if entry is None:
        return _row("unplaced", None, None, None, UNPLACED_NOT_FOUND)

    # (e) Matched, but no usable location / published address (Req 2.5).
    lat = _usable_coord(entry.get("lat"))
    lon = _usable_coord(entry.get("lon"))
    address = entry.get("address")
    if lat is None or lon is None or not address:
        return _row("unplaced", None, None, None, UNPLACED_NO_ADDRESS)

    # (f) Placed: carry the real cached location + published address (Req 2.6).
    return _row("placed", lat, lon, str(address), None)


def compute_coverage(rows_for_pathogen: list[dict]) -> dict:
    """Measured geocode-coverage block for one pathogen (Req 4.1, 4.2, 4.6).

    Given the pathogen's placed+unplaced rows, returns a ``FacilityMapCoverage``-shaped
    dict::

        {"pathogen": str, "total_selected": int, "placed": int, "unplaced": int,
         "coverage_pct": Optional[float], "coverage_state": str}

    * ``coverage_pct = round(100 * placed / total_selected, 1)`` in ``[0.0, 100.0]`` and
      ``coverage_state = "computed"`` when ``total_selected > 0`` (Req 4.1).
    * ``coverage_pct = None`` and ``coverage_state = "not_applicable"`` when
      ``total_selected == 0`` — the explicit "no establishments selected" state, no
      division performed (Req 4.2).

    Invariant: ``placed + unplaced == total_selected`` (Req 4.6). A selection where
    nothing places yields ``coverage_pct == 0.0`` with every row unplaced, never an
    empty "successful" map (Req 4.5). ``pathogen`` is taken from the rows when present.

    VERIFIED-BASELINE HONESTY (Req 4): ``coverage_pct`` counts ONLY MPI-verified
    placements (``placement_status == "placed"``) over ``total_selected`` and is NEVER
    inflated by the supplemental historical-candidate overlay. ``unplaced`` is defined as
    ``total_selected - placed`` so the ``placed + unplaced == total_selected`` invariant
    holds and ``unplaced`` INCLUDES both historical candidates and truly unresolved rows.
    The two additional informational sub-counts partition that ``unplaced`` total:

    * ``historical_candidate`` = count of ``placement_status == "historical_candidate"``
      rows (supplemental overlay candidates, with or without coordinates).
    * ``unresolved`` = count of rows that are neither verified-placed nor a historical
      candidate.

    So ``historical_candidate + unresolved == unplaced``; they surface how many of the
    unplaced establishments are historical candidates vs truly unresolved WITHOUT
    touching the verified headline percentage.
    """
    total = len(rows_for_pathogen)
    placed = sum(1 for r in rows_for_pathogen if r.get("placement_status") == "placed")
    unplaced = total - placed
    historical_candidate = sum(
        1 for r in rows_for_pathogen if r.get("placement_status") == "historical_candidate"
    )
    unresolved = unplaced - historical_candidate
    pathogen = rows_for_pathogen[0]["pathogen"] if rows_for_pathogen else ""
    if total == 0:
        return {
            "pathogen": pathogen,
            "total_selected": 0,
            "placed": 0,
            "unplaced": 0,
            "historical_candidate": 0,
            "unresolved": 0,
            "coverage_pct": None,
            "coverage_state": "not_applicable",
        }
    # VERIFIED coverage: placed-only, never inflated by historical candidates.
    pct = round(100.0 * placed / total, 1)
    # Clamp defensively into [0.0, 100.0] (placed <= total makes this a no-op).
    pct = max(0.0, min(100.0, pct))
    return {
        "pathogen": pathogen,
        "total_selected": total,
        "placed": placed,
        "unplaced": unplaced,
        "historical_candidate": historical_candidate,
        "unresolved": unresolved,
        "coverage_pct": pct,
        "coverage_state": "computed",
    }


def _round_opt(value: Any, round_to: int) -> Any:
    """Round a float to ``round_to`` places; pass ``None``/non-floats through."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, float):
        return round(value, round_to)
    return value


def _pathogen_meta(s03_cache: Optional[dict]) -> dict[str, dict]:
    """Per-pathogen availability metadata from the S03 cache, all pathogens first-class.

    Returns ``{pathogen: {"commodity", "availability_status", "unavailable_reason"}}``
    for every pathogen in ``_PATHOGENS``. A pathogen present in the S03 cache carries its
    S03 ``availability_status``/``unavailable_reason`` (so an "unavailable" pathogen is
    retained with its reason — Req 7.5); a pathogen absent from the cache defaults to
    "unavailable" with a stated reason so it is never silently dropped.
    """
    meta: dict[str, dict] = {}
    s03_pathogens = (s03_cache or {}).get("pathogens", {}) or {}
    for pathogen in _PATHOGENS:
        pdata = s03_pathogens.get(pathogen)
        if pdata is None:
            meta[pathogen] = {
                "commodity": _COMMODITY.get(pathogen, "unknown"),
                "availability_status": "unavailable",
                "unavailable_reason": "S03 establishment-surveillance cache unavailable.",
            }
        else:
            meta[pathogen] = {
                "commodity": pdata.get("commodity", _COMMODITY.get(pathogen, "unknown")),
                "availability_status": pdata.get("availability_status", "unavailable"),
                "unavailable_reason": pdata.get("unavailable_reason"),
            }
    return meta


#: Default coordinate-source label stamped on an MPI-verified placed row.
_MPI_COORDINATE_SOURCE = "FSIS MPI Directory (published)"


def _stamp_overlay_fields(row: dict, supplemental_entries: dict, round_to: int) -> None:
    """Stamp the location_status / match provenance / historical overlay fields on a row.

    Mutates ``row`` in place. Three honest cases, keyed on the row's placement and the
    supplemental historical-candidate overlay (CRITICAL HONESTY rules below):

    1. PLACED (MPI-verified; ``placement_status == "placed"``): the establishment matched
       the committed FSIS MPI Directory geocode cache, so it is a verified placement:
       ``location_status="mpi_verified"``, ``match_method="fsis_mpi_establishment_id"``,
       ``match_confidence="verified"``, ``verified_against_fsis_id=True``,
       ``coordinate_source="FSIS MPI Directory (published)"``; the historical_* fields and
       evidence_urls are empty/None (they belong to the supplemental overlay only).

    2. UNPLACED and NOT in the supplemental overlay: honestly unresolved —
       ``location_status="unresolved"``, all match/historical fields None/empty,
       ``verified_against_fsis_id=False``.

    3. UNPLACED and IN the supplemental overlay: merge the supplemental entry's own
       attributes (historical_inspection_number, historical_address, evidence_urls,
       match_method, match_confidence). ``verified_against_fsis_id`` is ALWAYS False —
       the identity is NOT confirmed against an FSIS establishment id.
         * ``do_not_map == True`` OR the entry's ``location_status == "unresolved"``:
           the row stays unplaced and unresolved — lat/lon/address stay None,
           coordinate_source None, the existing ``unplaced_reason`` is preserved, and
           ``location_status="unresolved"``.
         * else (entry ``location_status == "historical_candidate"``):
           ``location_status="historical_candidate"``. When the entry carries non-null
           NUMERIC lat AND lon, promote the row to a THIRD placement value
           ``placement_status="historical_candidate"`` with those (rounded) coordinates,
           ``address=historical_address`` and ``coordinate_source`` from the entry. When
           lat/lon are null, the candidate is metadata-only: ``placement_status`` stays
           "unplaced" with no coordinates/address, carrying only its historical_* fields.

    NEVER sets ``verified_against_fsis_id`` True for a supplemental row; NEVER fabricates
    lat/lon (only coordinates actually present in the supplemental file are used); the
    historical_inspection_number is the overlay's own attribute, NEVER asserted equal to
    the numeric establishment_id.
    """
    # Optional display fields carried for the schema; None unless an enriched cache
    # populated them in place_establishment (it does not today).
    row.setdefault("establishment_number", None)
    row.setdefault("county", None)
    row.setdefault("fips_code", None)

    placed = row.get("placement_status") == "placed"

    if placed:
        row["location_status"] = "mpi_verified"
        row["match_method"] = "fsis_mpi_establishment_id"
        row["match_confidence"] = "verified"
        row["verified_against_fsis_id"] = True
        row["historical_inspection_number"] = None
        row["historical_address"] = None
        row["coordinate_source"] = _MPI_COORDINATE_SOURCE
        row["evidence_urls"] = []
        return

    # Unplaced: look up the supplemental overlay by establishment_id.
    eid = str(row.get("establishment_id", ""))
    entry = supplemental_entries.get(eid)

    if entry is None:
        # Honestly unresolved — no supplemental candidate.
        row["location_status"] = "unresolved"
        row["match_method"] = None
        row["match_confidence"] = None
        row["verified_against_fsis_id"] = False
        row["historical_inspection_number"] = None
        row["historical_address"] = None
        row["coordinate_source"] = None
        row["evidence_urls"] = []
        return

    # Supplemental overlay present. Merge its own attributes. Identity is NEVER confirmed
    # against an FSIS establishment id, so verified_against_fsis_id is ALWAYS False.
    row["match_method"] = entry.get("match_method") or "historical_name_state_address"
    row["match_confidence"] = entry.get("match_confidence")
    row["verified_against_fsis_id"] = False
    row["historical_inspection_number"] = entry.get("historical_inspection_number")
    row["historical_address"] = entry.get("historical_address")
    evidence_urls = entry.get("evidence_urls", [])
    row["evidence_urls"] = list(evidence_urls) if isinstance(evidence_urls, list) else []

    do_not_map = bool(entry.get("do_not_map", False))
    entry_status = entry.get("location_status")

    if do_not_map or entry_status == "unresolved":
        # Keep the row unresolved/unplaced; preserve the existing unplaced_reason.
        row["location_status"] = "unresolved"
        row["coordinate_source"] = None
        # lat/lon/address stay None from place_establishment; do not touch them.
        return

    # Historical candidate.
    row["location_status"] = "historical_candidate"
    lat = _usable_coord(entry.get("lat"))
    lon = _usable_coord(entry.get("lon"))
    if lat is not None and lon is not None:
        # Real coordinates present -> promote to a historical_candidate placement.
        row["placement_status"] = "historical_candidate"
        row["lat"] = _round_opt(lat, round_to)
        row["lon"] = _round_opt(lon, round_to)
        row["address"] = entry.get("historical_address")
        row["coordinate_source"] = entry.get("coordinate_source")
    else:
        # Metadata-only candidate: no pin yet. placement_status stays "unplaced".
        row["coordinate_source"] = None
        # lat/lon/address stay None from place_establishment.


def compute_facility_map(*, round_to: int = 6) -> dict[str, Any]:
    """Orchestrate the runtime decision-layer build end to end (NO network, OFFLINE).

    Pipeline (Req 2.2-2.7, 3.3, 3.7, 4.1-4.6, 7.3-7.5, 8.6, 10.3):

    1. Load the S03 cache (``establishment_surveillance.load_cache``), the action_queue
       cache (``action_queue.load_cache``), and the committed Geocode_Cache
       (:func:`load_geocode_cache`). The geocode cache is read ONLY — never geocoded.
    2. :func:`select_signal_bearing` -> per-pathogen signal-bearing selections.
    3. :func:`place_establishment` on each -> placed/unplaced rows carrying the real
       cached lat/lon/address or a stated unplaced reason.
    4. Stamp every row ``human_review=True`` and ``status="OBSERVED"`` (already set by
       :func:`place_establishment`; re-asserted here) (Req 8.6, 10.3) and round floats.
    5. Per-pathogen :func:`compute_coverage` (Req 4.1-4.6).
    6. Sort rows deterministically by ``(pathogen, normalized_establishment_number)`` so
       repeated builds are byte-identical (Req 3.7).
    7. Keep all three pathogens first-class: an *available* pathogen with zero
       signal-bearing establishments yields an empty ``rows`` list and a coverage block
       with ``total_selected=0`` (Req 7.4); an *unavailable* pathogen is retained with its
       ``unavailable_reason`` (Req 7.5).
    8. Assemble the cache with method metadata and write ``CACHE_PATH`` with
       ``json.dumps(cache, indent=2, sort_keys=True)``, creating ``INTERIM_DIR`` if
       needed.

    Returns the assembled cache dict. This path NEVER fails loud on a missing committed
    geocode key — a missing key is an honest unplaced "not found" row here; the strict
    fail-loud contract (Req 3.4) lives in the EXPORTER (a later task).
    """
    s03_cache = load_s03_cache()
    aq_cache = load_aq_cache()
    geocode_cache = load_geocode_cache()
    supplemental = load_supplemental_mapping()
    supplemental_entries = supplemental.get("entries", {}) or {}

    selected_by_pathogen = select_signal_bearing(s03_cache, aq_cache)
    meta = _pathogen_meta(s03_cache)

    # Every pathogen that is first-class: the fixed trio plus any the selection surfaced.
    all_pathogens = sorted(set(_PATHOGENS) | set(selected_by_pathogen))

    pathogens_out: dict[str, Any] = {}
    for pathogen in all_pathogens:
        pmeta = meta.get(pathogen, {
            "commodity": _COMMODITY.get(pathogen, "unknown"),
            "availability_status": "unavailable",
            "unavailable_reason": "S03 establishment-surveillance cache unavailable.",
        })

        rows: list[dict] = []
        for selected in selected_by_pathogen.get(pathogen, []):
            row = place_establishment(selected, geocode_cache)
            # Stamp the overlay/provenance fields based on placement, merging the
            # supplemental historical-candidate overlay for honestly-unplaced rows
            # whose establishment_id appears in the supplemental mapping (Req 3.4,
            # 8.1-8.4). NEVER fabricates coordinates or asserts FSIS-id verification.
            _stamp_overlay_fields(row, supplemental_entries, round_to)
            # Round the signal floats + the geocoded coordinates (Req: deterministic).
            for k in ("eb_posterior", "ci_low", "ci_high", "lat", "lon"):
                row[k] = _round_opt(row.get(k), round_to)
            # Re-assert the fixed decision-layer provenance (Req 8.6, 10.3).
            row["human_review"] = True
            row["status"] = "OBSERVED"
            rows.append(row)

        # Deterministic within-pathogen order by normalized establishment number,
        # with establishment_id as a stable tie-break (Req 3.7).
        rows.sort(key=lambda r: (r["normalized_establishment_number"], r["establishment_id"]))

        coverage = compute_coverage(rows)

        pathogens_out[pathogen] = {
            "pathogen": pathogen,
            "commodity": pmeta.get("commodity", _COMMODITY.get(pathogen, "unknown")),
            "availability_status": pmeta.get("availability_status", "unavailable"),
            "unavailable_reason": pmeta.get("unavailable_reason"),
            "coverage": coverage,
            "rows": rows,
        }

    cache: dict[str, Any] = {
        "module_id": MODULE_ID,
        "method_version": METHOD_VERSION,
        "top_n_s03": TOP_N_S03,
        "normalization": "trim; strip leading zeros; uppercase",
        "geocode_source": "committed data/external/facility_geocode.json",
        "geocode_obtained": bool(geocode_cache.get("obtained", False)),
        "forbidden_terms": list(FORBIDDEN_TERMS),
        "pathogens": pathogens_out,
    }

    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(
        _json.dumps(cache, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return cache


def load_cache() -> Optional[dict[str, Any]]:
    """Read ``CACHE_PATH`` back; same ``(OSError, ValueError) -> None`` as S03's load_cache."""
    if CACHE_PATH.exists():
        try:
            return _json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
    return None
