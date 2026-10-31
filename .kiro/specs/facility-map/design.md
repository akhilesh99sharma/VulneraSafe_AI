# Design Document

## Overview

The Facility Map is a new first-class web tab plus a schema-validated artifact that
geographically plots FSIS-sampled establishments carrying an elevated surveillance
signal, as an OBSERVED sourcing-scrutiny reference layer for the retailer's Food
Safety Operations Director. It introduces **no new modeling and no model training**:
it is a deterministic join and offline geocode over data that already exists in the
project.

The feature reuses two existing module caches as its only signal inputs:

- **S03** (`src/analysis/establishment_surveillance.py`, `load_cache()`) — per-pathogen
  establishment records keyed by establishment id, each with `establishment_id`,
  `establishment_name`, `state`, `sample_n`, `positive_n`, `value`, `eb_posterior`,
  `ci_low`, `ci_high`, `support_status`, and (at the pathogen level)
  `availability_status` / `unavailable_reason`.
- **Action Queue** (`src/decision/action_queue.py`, `load_cache()`) — the ACTIONQ
  artifact; the Facility Map consumes only its entries with `target_type == "establishment"`.

A signal-bearing establishment is placed by joining it to the FSIS Meat, Poultry &
Egg Product Inspection (MPI) Directory by a normalized establishment number to obtain
a real published address that was geocoded **once, offline**, and committed as a cache
file. Establishments that cannot be matched or geocoded are never approximated; they
are listed as unplaced with a stated reason, and geocode coverage is a reported
measured percentage.

The design follows the project's established module + data-contract conventions
exactly, mirroring the S03 cache pattern, the `action_queue` decision-layer module,
the `build_action_queue`/`build_establishment_surveillance` exporter builders, the
`FacilityMapItem` TypedDict + TypeScript parity convention, the `SurveillanceActions`
web panel, and the `build_us_geojson.py` offline-once committed-output script.

### Honest scope and the open MPI matching risk (Req 13)

We do **not** yet know the MPI Directory match rate for the establishment numbers S03
carries. The design treats this as an explicit, reported risk rather than an
assumption:

- "MPI Directory not yet obtained" and "establishment number not found" are explicit
  **unplaced reasons**, not errors to hide.
- Geocode coverage is always a **measured** placed/total percentage, never assumed to
  be 100%.
- The geocoding mechanism (a committed local gazetteer file, or a one-time
  manual/offline geocode whose output is committed) is a swappable implementation
  detail behind a small interface, but the **committed-cache contract is fixed**: the
  runtime build reads the committed cache only and makes no network call. A missing
  required key fails the build loudly (Req 3.4) — it never silently re-geocodes.

### What this surface is NOT

The Facility Map is distinct from two existing surfaces and must say so prominently:

- It is **not** the base platform's SIMULATED optimizer Recommended Action Panel.
- It is **not** the state-level PREDICTED `risk_map` choropleth.

Its framing note reads: *"FSIS-sampled establishments with elevated surveillance
signal, by location — OBSERVED surveillance, sourcing-scrutiny reference layer, NOT
your suppliers; distinct from the SIMULATED optimizer and the state-level PREDICTED
risk map."*

## Architecture

### Data flow

```mermaid
flowchart LR
  subgraph Offline["Offline, once — committed to the repo"]
    MPI[FSIS MPI Directory\n(external source)]
    GEO[scripts/build_facility_geocode.py\nnormalize + geocode ONCE]
    GC[(data/external/facility_geocode.json\nkeyed by Normalized_Establishment_Number)]
    MPI --> GEO --> GC
  end

  subgraph Runtime["Runtime build — no network"]
    S03[(data/interim/\ns03_establishment_surveillance.json)]
    AQ[(data/interim/action_queue.json)]
    FM[src/decision/facility_map.py\ncompute_facility_map]
    FMC[(data/interim/facility_map.json)]
    EXP[src/artifacts/exporter.py\nbuild_facility_map]
    ART[(web/public/data/facility_map.json\n+ manifest entry)]
    S03 --> FM
    AQ --> FM
    GC --> FM
    FM --> FMC --> EXP --> ART
  end

  subgraph Web["React web app"]
    HOOK[useArtifact<FacilityMapItem[]>\n('facility_map')]
    UI[FacilityMap.tsx tab]
    ART --> HOOK --> UI
  end
```

The flow has three stages, matching the project's existing layering:

1. **Offline geocode build (once, committed).** `scripts/build_facility_geocode.py`
   obtains the MPI Directory, normalizes establishment numbers, resolves each address
   to a location exactly once, and writes a committed cache
   `data/external/facility_geocode.json` keyed on `Normalized_Establishment_Number`.
   This mirrors `scripts/build_us_geojson.py`, which downloads a public source once and
   commits a static output under `web/public/geo` so the app never calls a live origin.
2. **Runtime decision-layer build (no network).** `src/decision/facility_map.py`
   (`compute_facility_map()`) reads the S03 cache, the action_queue cache, and the
   committed geocode cache; selects signal-bearing establishments; joins to the geocode
   cache; splits placed vs unplaced; computes coverage; stamps every row
   `human_review=True` and `status="OBSERVED"`; and writes
   `data/interim/facility_map.json` with `json.dumps(cache, indent=2, sort_keys=True)`.
   `load_cache()` reads it back (same try/except pattern as S03).
3. **Exporter + web.** `src/artifacts/exporter.build_facility_map()` reads that cache,
   validates every row against `FacilityMapItem`, enforces the forbidden-terms guard,
   stamps a deterministic `generated_at`, and writes `web/public/data/facility_map.json`
   with a manifest entry (checksum + count). `FacilityMap.tsx` loads it through
   `useArtifact` and renders the map, ranked list, and unplaced panel.

### Layering and reuse

- `src/decision/facility_map.py` lives in the decision layer beside
  `src/decision/action_queue.py`, which it already resembles structurally (constants at
  top, `compute_*`/`load_cache` pair, interim JSON cache).
- The geocode cache is an external committed input under `data/external/` — the only new
  committed data file. No raw data is reprocessed.
- The exporter builder and the web panel reuse the exact patterns of the existing S03
  and action_queue artifacts so the two definitions cannot drift and the UI degrades
  gracefully.

## Components and Interfaces

### Python: `src/decision/facility_map.py`

Module constants (mirroring S03):

```python
REPO_ROOT = Path(__file__).resolve().parents[2]
INTERIM_DIR = REPO_ROOT / "data" / "interim"
EXTERNAL_DIR = REPO_ROOT / "data" / "external"
CACHE_PATH = INTERIM_DIR / "facility_map.json"
GEOCODE_CACHE_PATH = EXTERNAL_DIR / "facility_geocode.json"

MODULE_ID = "FACILITYMAP"
METHOD_VERSION = "fm.v1"

#: Mirrors src/decision/action_queue.TOP_N_S03 (the locked top-N establishment
#: selection). Re-declared here with this comment; kept equal to action_queue's.
TOP_N_S03 = 12

#: Mirrors src/decision/action_queue.FORBIDDEN_TERMS (enforced again by the exporter).
FORBIDDEN_TERMS = ("recall", "contaminated", "unsafe", "seize", "shut down",
                   "destroy", "government order", "mandate")

_PATHOGENS = ("Salmonella", "Listeria", "STEC")
_COMMODITY = {"Salmonella": "raw_poultry", "Listeria": "rte", "STEC": "raw_beef"}
```

> Note on `TOP_N_S03`: the design keeps a local re-declaration equal to
> `action_queue.TOP_N_S03` with an explicit comment (rather than an import) to avoid
> coupling the decision modules' import graph; a unit test asserts the two constants are
> equal so they cannot silently diverge.

#### Establishment-number normalization

```python
def normalize_establishment_number(raw: str) -> str:
    """Deterministic normalization applied identically to both join sides (Req 2.1).

    1. Trim surrounding whitespace.
    2. Remove leading zeros (but keep at least one digit; "00" -> "0").
    3. Uppercase.
    Documented, pure, and order-independent.
    """
```

This exact function is used on both the S03 `establishment_id` side and the MPI
Directory side at geocode-build time, so the key spaces are identical (Req 2.1, 2.2).

#### Geocoder interface (swappable, offline-only)

```python
class Geocoder(Protocol):
    """Offline geocoder contract. Resolves an MPI-published address to a location
    exactly once at BUILD time (scripts/build_facility_geocode.py). The RUNTIME
    build never calls a Geocoder — it reads only the committed Geocode_Cache."""

    def geocode(self, address: str) -> Optional[tuple[float, float]]:
        """Return (lat, lon) or None when the address cannot be resolved offline.
        Never makes a network call at runtime; an implementation may use a committed
        local gazetteer or replay a one-time offline/manual result."""
```

Concrete default: `GazetteerGeocoder` — resolves against a committed local gazetteer
file. The build script is the only caller; the runtime reads the cache the build wrote.

#### Selection, join, coverage helpers

```python
def select_s03_elevated(s03_cache: Optional[dict]) -> dict[str, list[dict]]:
    """Per pathogen, the top TOP_N_S03 establishments among support_status=="ok"
    with a non-null eb_posterior, ordered by eb_posterior desc (Req 1.1).
    low_support establishments are NEVER included here (Req 1.4)."""

def select_action_queue_establishments(aq_cache: Optional[dict]) -> dict[str, list[dict]]:
    """Per pathogen, the action_queue entries with target_type == "establishment"
    (Req 1.2). Carries forward human_review (True) and status (OBSERVED) (Req 10.4)."""

def select_signal_bearing(s03_cache, aq_cache) -> dict[str, list[SelectedEstablishment]]:
    """Union per pathogen of select_s03_elevated and select_action_queue_establishments,
    de-duplicated by (pathogen, establishment_id). Each record records its
    source_selection in {"s03", "action_queue", "both"} (Req 1.5). Establishments that
    are neither are excluded (Req 1.3)."""

def load_geocode_cache() -> dict[str, dict]:
    """Read the committed Geocode_Cache (Req 3.3). Never geocodes. Each value is
    {"lat": float, "lon": float, "address": str, "source": str}."""

def place_establishment(sel: SelectedEstablishment, geocode_cache: dict) -> PlacedOrUnplaced:
    """Exact-equality join on Normalized_Establishment_Number (Req 2.2). Returns a
    placed row with lat/lon/address when the key resolves to exactly one entry;
    otherwise an unplaced row with a stated reason:
      - "MPI Directory not yet obtained" (Req 2.7, when the cache is empty/absent)
      - "establishment number not found in MPI Directory" (Req 2.4)
      - "no published address in MPI Directory" (Req 2.5)
      - "ambiguous match in MPI Directory" (Req 2.3)
      - "establishment number not in committed geocode cache" (Req 3.4 is the EXPORTER
        fail-loud path; at decision-layer this is recorded as unplaced only when the
        policy is 'skip-missing'; see Error Handling for the fail-loud contract)."""

def compute_coverage(selected: list, placed: list) -> CoverageBlock:
    """total = len(selected); placed_count = len(placed);
    unplaced_count = total - placed_count. coverage_pct =
    round(100 * placed_count / total, 1) in [0.0, 100.0] when total > 0;
    None with a "no establishments selected" state when total == 0 (Req 4.1, 4.2).
    Invariant: placed_count + unplaced_count == total (Req 4.6)."""
```

#### Orchestrator

```python
def compute_facility_map(*, round_to: int = 6) -> dict[str, Any]:
    """Select -> join -> split -> coverage -> stamp -> write cache.

    - selected = select_signal_bearing(S03.load_cache(), action_queue.load_cache())
    - for each selected establishment, place_establishment against the geocode cache
    - compute per-pathogen coverage
    - every row: human_review=True, status="OBSERVED" (Req 8.6, 10.3)
    - rows sorted by Normalized_Establishment_Number (Req 3.7)
    - write CACHE_PATH with json.dumps(cache, indent=2, sort_keys=True)
    Returns the cache dict."""

def load_cache() -> Optional[dict[str, Any]]:
    """Read CACHE_PATH back; same try/except (OSError, ValueError) -> None as S03."""
```

The written cache has the shape:

```json
{
  "module_id": "FACILITYMAP",
  "method_version": "fm.v1",
  "top_n_s03": 12,
  "normalization": "trim; strip leading zeros; uppercase",
  "geocode_source": "committed data/external/facility_geocode.json",
  "forbidden_terms": ["recall", "..."],
  "pathogens": {
    "Salmonella": {
      "pathogen": "Salmonella",
      "commodity": "raw_poultry",
      "availability_status": "available",
      "unavailable_reason": null,
      "coverage": {"total_selected": 12, "placed": 9, "unplaced": 3,
                   "coverage_pct": 75.0, "coverage_state": "computed"},
      "rows": [ /* FacilityMapItem-shaped dicts */ ]
    }
  }
}
```

### Python: `scripts/build_facility_geocode.py` (offline, once)

Mirrors `scripts/build_us_geojson.py`: obtains the MPI Directory, normalizes every
establishment number with `normalize_establishment_number`, geocodes each published
address once via a `Geocoder`, and writes the committed cache. Handles the duplicate-key
rule (Req 3.2): when two or more MPI rows normalize to the same key, write a single
entry and record a `conflict` indication naming the duplicated key. The script is run
manually by a maintainer and its output is committed; it is never invoked at build time.

### Python: `src/artifacts/exporter.py` additions

```python
def build_facility_map() -> list[dict]:
    """Decision layer -> OBSERVED facility-map rows.

    from src.decision.facility_map import load_cache
    stamp = resolve_generated_at()
    cache = load_cache()
    - if cache missing: return [] (an empty map is an honest result)
    - build one FacilityMapItem per row across all pathogens
    - stamp artifact_version, module_id="FACILITYMAP", method_version, generated_at=stamp
    - FORBIDDEN_TERMS guard (Req 10.2): before returning, scan every string-valued field
      of every row case-insensitively; raise SchemaValidationError naming the offending
      field if any forbidden term is found, BEFORE any write.
    - rows sorted by (pathogen, normalized_establishment_number) for deterministic order.
    """
```

Integration points, each mirroring the action_queue/S03 wiring:

- Add `FacilityMapItem` and the coverage helper type to the
  `from src.artifacts.schemas import (...)` block.
- In `build_all_artifacts()`: build + `validate_payload(rows, FacilityMapItem,
  label="facility_map[item]")`, then add `"facility_map": facility_map` to the returned
  mapping. The generic machinery in `_build_artifact_objects` / `export_all` then writes
  `web/public/data/facility_map.json` and records its manifest entry (sha256 over
  substantive bytes + record count) exactly like every other artifact (Req 8.3, 8.4).

### Web: `web/src/components/panels/FacilityMap.tsx`

Props/state:

```ts
// no props — the panel is a tab root, like SurveillanceActions.
const state = useArtifact<FacilityMapItem[]>("facility_map"); // {data, loading, error}
const [pathogen, setPathogen] = useState<string>("");  // "" = all; else Salmonella|Listeria|STEC
const [source, setSource]   = useState<string>("");    // "" = all; else "s03"|"action_queue"
```

Rendering contract (Req 9):

- **Loading** (`state.loading`): render a loading indication only; do NOT render the
  ranked list, map view, or unplaced panel (Req 9.3). Reuse `PanelShell` / `ArtifactBody`
  as `SurveillanceActions` does.
- **Error** (`state.error`): render an `EmptyState` naming the failed artifact
  (`facility_map`); failure does not block other tabs (Req 9.4) — guaranteed by the
  per-artifact `useArtifact` hook.
- **Filters** (Req 9.5): pathogen filter = distinct pathogens present + an "All" option;
  source filter = `s03` / `action_queue` / all. Changing either restricts the ranked
  list, the map view, and the unplaced count to rows matching **both** filters.
- **Map view** (Req 9.6): reuse the `MapView` fallback-grid pattern. Because
  `maplibre-gl` is mocked to throw under jsdom (`web/src/setupTests.ts`), the component
  renders the accessible grid fallback deterministically in tests, exposing one
  selectable element per **placed** establishment (`data-testid="facility-pin"`).
- **Ranked list** (Req 9.7): placed+unplaced elevated establishments ordered by
  descending `eb_posterior` (nulls last), each showing FSIS identity (number, published
  name or number-only when name is null per Req 5.2, state), the Surveillance_Signal
  labeled as such with its `[ci_low, ci_high]` pair in the same view (Req 6.1, 6.3), the
  evidence summary, a low-support indicator when `sample_n < 30` (Req 6.5), and a visible
  **Human-Review chip** (Req 9.10, 10.3).
- **Empty filtered list** (Req 9.8): render an `EmptyState` in place of the list.
- **Unplaced panel** (Req 9.9, 4.3, 4.4): show coverage % + placed/total counts + each
  unplaced establishment with its stated reason. Coverage is read from the carried
  coverage block, not recomputed.
- **Framing note** (Req 5.3, 11.1, 11.2): the prominent note quoted in the Overview; the
  content is labeled OBSERVED and no element is labeled PREDICTED or SIMULATED.

Theme (Req 11.3, 11.4): navy/teal/slate/gray only, except an alert-family (orange)
accent on the elevated-signal/human-review emphasis — matching `SurveillanceActions`.
Because it uses orange, **`panels/FacilityMap.tsx` must be added to the
`ALERT_CONTEXT_FILES` allowlist in `web/src/components/__tests__/themeDiscipline.test.tsx`**.

### Web: `web/src/App.tsx` wiring

- Extend the `Tab` union: add `"facilitymap"`.
- Import `FacilityMap`.
- Add `{ id: "facilitymap", label: "Facility Map" }` to the header `tabs` array (after
  `actions`).
- Add the render branch `) : tab === "facilitymap" ? ( <FacilityMap /> )`.

## Data Models

### `FacilityMapItem` (Python, `src/artifacts/schemas.py`)

Added immediately **before** the `STATUS_TAGS` anchor (the
`#: All status-bearing literal values...` comment and the `STATUS_TAGS` frozenset),
after the `ActionQueueItem` class, following the `ActionQueueItem` `Optional[...]` style.

```python
class FacilityMapCoverage(TypedDict):
    """Per-pathogen geocode-coverage summary carried in each row so the web
    component does not recompute it (Req 4.1-4.3). ``coverage_pct`` is None with
    ``coverage_state="not_applicable"`` when ``total_selected`` is 0 (Req 4.2);
    otherwise ``coverage_state="computed"`` and ``coverage_pct`` is in [0.0, 100.0]."""

    pathogen: str
    total_selected: int
    placed: int
    unplaced: int
    coverage_pct: Optional[float]
    coverage_state: str            # "computed" | "not_applicable"


class FacilityMapItem(TypedDict):
    """One OBSERVED signal-bearing FSIS-sampled establishment plotted (or listed as
    unplaced) on the Facility Map. Decision-support reference layer only: identity is
    FSIS-published (number, optional published name, state) with NO contact detail;
    the location is the establishment's SAMPLING location, never a product destination
    or illness location, and no supplier/retailer relationship is implied. The value is
    a Surveillance_Signal (eb_posterior), never a contamination or illness claim.
    ``human_review`` is always True and ``status`` is always OBSERVED (never
    PREDICTED/SIMULATED). A placed row carries a real lat/lon/address from the committed
    Geocode_Cache; an unplaced row carries lat/lon/address=None and a non-empty
    ``unplaced_reason``. ``coverage`` repeats the per-pathogen coverage block so the UI
    reads it without recomputing."""

    artifact_version: str
    module_id: str                 # "FACILITYMAP"
    method_version: str            # "fm.v1"
    pathogen: str
    normalized_establishment_number: str
    establishment_id: str
    establishment_name: Optional[str]
    state: str
    eb_posterior: Optional[float]
    ci_low: Optional[float]
    ci_high: Optional[float]
    sample_n: int
    positive_n: int
    support_status: str            # "ok" | "low_support"
    source_selection: str          # "s03" | "action_queue" | "both"
    placement_status: str          # "placed" | "unplaced"
    lat: Optional[float]
    lon: Optional[float]
    address: Optional[str]
    unplaced_reason: Optional[str]
    evidence_summary: str
    coverage: FacilityMapCoverage
    human_review: bool             # always True
    status: StatusTag              # OBSERVED
    generated_at: str
```

> `support_status` is carried so the UI can show the low-support indicator (Req 6.5)
> without re-deriving it; `sample_n`/`positive_n` are the raw counts behind the signal.
> `normalized_establishment_number` is the join key and the documented sort key (Req 3.7).

### TypeScript mirror (`web/src/types/artifacts.ts`)

Appended after the existing `ActionQueueItem` interface, with **identical snake_case
field names** so the parity test passes (Req 8.5, 12.4):

```ts
// facility_map -> Facility Map view (deterministic join + offline geocode over S03 + action_queue)
export interface FacilityMapCoverage {
  pathogen: string;
  total_selected: number;
  placed: number;
  unplaced: number;
  coverage_pct: number | null;
  coverage_state: string;
}

export interface FacilityMapItem {
  artifact_version: string;
  module_id: string;
  method_version: string;
  pathogen: string;
  normalized_establishment_number: string;
  establishment_id: string;
  establishment_name: string | null;
  state: string;
  eb_posterior: number | null;
  ci_low: number | null;
  ci_high: number | null;
  sample_n: number;
  positive_n: number;
  support_status: string;
  source_selection: string;
  placement_status: string;
  lat: number | null;
  lon: number | null;
  address: string | null;
  unplaced_reason: string | null;
  evidence_summary: string;
  coverage: FacilityMapCoverage;
  human_review: boolean;
  status: StatusTag;
  generated_at: string;
}
```

### Geocode cache shape (`data/external/facility_geocode.json`, committed)

```json
{
  "source": "FSIS MPI Directory",
  "normalization": "trim; strip leading zeros; uppercase",
  "obtained": true,
  "conflicts": ["<normalized key written once despite >1 MPI rows>"],
  "entries": {
    "<Normalized_Establishment_Number>": {
      "lat": 39.1, "lon": -75.5,
      "address": "<MPI-published address used to geocode>",
      "source": "gazetteer|offline-manual"
    }
  }
}
```

When `obtained` is `false` (directory not yet acquired), `entries` is empty and every
selected establishment becomes unplaced with reason "MPI Directory not yet obtained"
(Req 2.7).

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid
executions of a system — essentially, a formal statement about what the system should
do. Properties serve as the bridge between human-readable specifications and
machine-verifiable correctness guarantees.*

The Facility Map is pure deterministic selection/join/accounting over in-memory caches,
so property-based testing applies well to its selection and coverage logic. These
properties are written against `compute_facility_map` over hand-built S03 /
action_queue / geocode-cache fixtures.

### Property 1: Only signal-bearing establishments appear

*For any* S03 cache and action_queue cache, every establishment in the Facility Map
output for a pathogen is either among that pathogen's top `TOP_N_S03` `support_status=="ok"`
establishments ordered by `eb_posterior` desc, or appears in the action_queue with
`target_type=="establishment"`; no other establishment appears.

**Validates: Requirements 1.1, 1.2, 1.3**

### Property 2: Low-support is never elevated-selected and never called safe

*For any* S03 cache, an establishment with `support_status=="low_support"` is never
selected on the basis of the elevated S03 signal, and no output row for any
establishment carries a "safe" or "clean" label.

**Validates: Requirements 1.4, 6.4**

### Property 3: Placed + unplaced equals total selected, per pathogen

*For any* selection, for each pathogen the per-pathogen `coverage.placed` plus
`coverage.unplaced` equals `coverage.total_selected`, and that total equals the number
of distinct selected establishments for that pathogen.

**Validates: Requirements 4.6**

### Property 4: Every placed row has a real cached location, never fabricated

*For any* output, every row with `placement_status=="placed"` has non-null `lat`, `lon`,
and `address` equal to the committed Geocode_Cache entry for its
`normalized_establishment_number`; no placed row carries a placeholder or fabricated
coordinate (every placed coordinate is traceable to a cache entry).

**Validates: Requirements 2.6, 3.1, 3.3**

### Property 5: Every unplaced row has a non-empty stated reason

*For any* output, every row with `placement_status=="unplaced"` has null `lat`/`lon`/
`address` and a non-empty `unplaced_reason` drawn from the documented reason set.

**Validates: Requirements 2.3, 2.4, 2.5, 2.7, 4.4**

### Property 6: Coverage is the measured percentage, never assumed 100%

*For any* selection with `total_selected > 0`, `coverage.coverage_pct` equals
`round(100 * placed / total_selected, 1)` and lies in `[0.0, 100.0]`; when
`total_selected == 0`, `coverage_pct` is null and `coverage_state == "not_applicable"`.
A selection where nothing can be placed yields `coverage_pct == 0.0` with every row
unplaced (never an empty "successful" map).

**Validates: Requirements 4.1, 4.2, 4.5, 13.3**

### Property 7: Every row is human-reviewed and OBSERVED

*For any* output, every row has `human_review == True` and `status == "OBSERVED"`; no row
has `status` in `{"PREDICTED", "SIMULATED"}`.

**Validates: Requirements 7.3, 8.6, 10.3, 10.4, 11.2**

### Property 8: No forbidden language in any field

*For any* output, no string-valued field of any row contains any term from the
Forbidden_Terms set, matched case-insensitively; if one would, the exporter raises
before writing any output.

**Validates: Requirements 10.1, 10.2**

### Property 9: Deterministic, sorted output

*For any* fixed inputs, two builds produce byte-identical substantive output (excluding
`generated_at`), and rows are emitted sorted by `normalized_establishment_number`.

**Validates: Requirements 3.5, 3.6, 3.7**

### Property 10: Schema ↔ TypeScript field-name parity

*For any* field, the set of serialized snake_case field names of `FacilityMapItem` (and
`FacilityMapCoverage`) equals the set of field names of the mirrored TypeScript
interface in `web/src/types/artifacts.ts`; a field present in one but absent from the
other fails.

**Validates: Requirements 8.5, 12.4**

### Reflection on redundant properties

The initial draft also contained a separate "source_selection is recorded as one of
s03/action_queue/both" property and a separate "placed count is non-negative" property.
The first is subsumed by Property 1 together with the schema `Literal`-style constraint
on `source_selection` enforced at validation, and the second is implied by Property 3
(`placed + unplaced == total`, all counts derived from list lengths). They are removed
to keep each property uniquely valuable.

## Error Handling

- **Missing committed geocode key (Req 3.4).** The committed cache is the single source
  of truth at runtime. The exporter's fail-loud contract: if a selected establishment's
  `normalized_establishment_number` is required for placement but absent from the
  committed cache under a "strict" policy, `build_facility_map` raises a clear error
  naming the missing key and performs **no network geocode** and writes nothing. The
  decision layer distinguishes the two honest modes it is asked to support: (a) when the
  MPI Directory is "not yet obtained" (`obtained=false`), establishments are recorded as
  unplaced with a stated reason (Req 2.7); (b) when the directory is obtained but a
  specific required key is missing, this is the strict fail-loud path (Req 3.4). The
  design never silently re-geocodes in either case.
- **S03 cache unavailable or a pathogen `unavailable`.** When `S03.load_cache()` returns
  `None`, no S03-sourced establishments are selected (action_queue-sourced ones may still
  appear). When a pathogen's `availability_status == "unavailable"`, the pathogen is kept
  as a selectable filter value and surfaced with its `unavailable_reason` text, with zero
  plotted establishments (Req 7.5). A pathogen that is "available" but has zero
  signal-bearing establishments is shown with an explicit empty-result indication and no
  fabricated establishment (Req 7.4).
- **action_queue cache unavailable.** `action_queue.load_cache()` returning `None` simply
  yields no action_queue-sourced selections; an otherwise-empty map is an honest result.
- **Schema validation failure (Req 8.1, 8.2).** The exporter validates every row against
  `FacilityMapItem` before writing any byte; a failure raises a `SchemaValidationError`
  identifying each failing row/field and leaves the existing
  `web/public/data/facility_map.json` unchanged (the generic writer only writes after all
  payloads validate in `build_all_artifacts`).
- **Forbidden-term violation (Req 10.2).** The forbidden-terms guard runs before writing;
  a violation raises and nothing is written.
- **Artifact load failure in the UI (Req 9.4).** `useArtifact` surfaces `error`; the
  panel renders an `EmptyState` naming `facility_map`. Because each artifact is fetched
  independently and cached per-name, a Facility Map load failure does not prevent other
  tabs/panels from rendering their own successfully-loaded data.

## Testing Strategy

The feature is tested with a dual approach mirroring `tests/test_action_queue.py` and
`SurveillanceActions.test.tsx`.

### Property-based testing applicability

The selection, join, and coverage logic is pure and input-sensitive, so it is a good fit
for property-based tests (behavior varies meaningfully with the fixtures). The web
rendering and the offline geocode script are **not** PBT targets: the component is
example/snapshot-style UI assertion, and the geocode build is a one-shot offline script.

### Python property/unit library

Use **Hypothesis** (already a project dependency — see `.hypothesis/` and
`tests/test_feasibility.py`) for the property tests. Each property test runs a minimum of
100 iterations and is tagged with a comment referencing its design property:
`# Feature: facility-map, Property N: <property text>`.

### `tests/test_facility_map.py`

Small hand-built S03 + action_queue + geocode-cache fixtures (same spirit as
`test_action_queue.py`'s `_s03_cache()` / `_s06_cache()` helpers), covering:

- **Property 1-2 (selection):** only top-`TOP_N_S03` `ok` establishments + action_queue
  establishment targets appear; a `low_support` establishment with a high `eb_posterior`
  is excluded from elevated selection and never labeled safe. Also assert the local
  `TOP_N_S03` equals `action_queue.TOP_N_S03`.
- **Property 3 (invariant):** a Hypothesis property over randomly generated fixtures
  asserting `placed + unplaced == total_selected` per pathogen.
- **Property 4-5 (placement honesty, Req 12.2):** every placed row's `lat`/`lon`/`address`
  equals the committed geocode cache entry for its normalized key and no placed row has a
  placeholder coordinate; every unplaced row has null coordinates and a non-empty reason.
- **Property 6 (coverage):** `coverage_pct` equals the measured percentage; `0` placed of
  `>0` selected yields `0.0`; `0` selected yields the not-applicable state.
- **Property 7 (status/human_review):** every row `human_review is True`,
  `status == "OBSERVED"`.
- **Property 8 (forbidden terms):** a fixture injecting a forbidden term into a string
  field causes `build_facility_map` to raise, and nothing is written.
- **Property 9 (determinism):** two `compute_facility_map` runs over identical inputs
  produce identical substantive bytes (excluding `generated_at`), and rows are sorted by
  `normalized_establishment_number`.
- **Parity-adjacent check:** assert the `FacilityMapItem` annotated key set is exactly the
  documented set (mirrors `tests/test_schemas.py`'s key-set checks), so a schema drift is
  caught on the Python side; the full cross-language parity is the vitest parity test.

### `web/src/components/panels/__tests__/FacilityMap.test.tsx` (Req 12.3)

Uses the `installArtifactFetch` / `renderWithSelection` helpers
(`web/src/test/renderHelpers.tsx`) and benefits from the maplibre mock, asserting:

- the tab renders and loads via `useArtifact("facility_map")`;
- the **pathogen filter** and **source filter** are present and functional (changing the
  source filter drops non-matching rows);
- the **ranked list** renders establishments by descending `eb_posterior` with FSIS
  identity, the Surveillance_Signal with its `[ci_low, ci_high]` pair, the evidence
  summary, and a visible **Human-Review chip** on every surfaced establishment;
- the **unplaced-establishments panel** shows the coverage %, placed/total counts, and
  each unplaced establishment with its stated reason;
- the framing note distinguishing OBSERVED geography from the SIMULATED optimizer and the
  PREDICTED risk map is present;
- a missing artifact degrades to an `EmptyState` naming `facility_map`.

### Parity test (Req 12.4)

A parity assertion compares the serialized snake_case field names of `FacilityMapItem`
(and `FacilityMapCoverage`) against the field names of the mirrored TypeScript interface
in `web/src/types/artifacts.ts`, so a field present in one but absent from the other
fails — consistent with the project's existing schema↔TS parity convention referenced in
`src/artifacts/schemas.py`.

### Theme-discipline test update (Req 11.4)

`panels/FacilityMap.tsx` is added to `ALERT_CONTEXT_FILES` in
`web/src/components/__tests__/themeDiscipline.test.tsx`, because it applies an orange
alert-family accent only to elevated-signal / human-review emphasis; all other elements
use navy/teal/slate/gray.
