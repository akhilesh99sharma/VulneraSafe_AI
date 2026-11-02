import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useArtifact } from "../../data/hooks";
import type { FacilityMapItem } from "../../types/artifacts";
import StatusTag from "../StatusTag";
import EmptyState from "../EmptyState";
import PanelShell, { ArtifactBody } from "./PanelShell";

/**
 * Facility Map (facility-map spec, Req 5/6/9/10/11).
 *
 * A first-class decision-support tab that geographically plots FSIS-sampled
 * establishments carrying an elevated OBSERVED surveillance signal, at their
 * SAMPLING location. It is a sourcing-scrutiny reference layer only — NOT the
 * retailer's suppliers, NOT a contamination or illness claim, and distinct from
 * the base platform's SIMULATED optimizer and the state-level PREDICTED risk map.
 *
 * Two location provenances are shown with visually DISTINCT markers:
 *   - mpi_verified       -> SOLID teal/navy filled circle ("FSIS MPI Directory Matched")
 *   - historical_candidate -> HOLLOW dashed orange outline ("Historical Candidate — Identity Unconfirmed")
 *
 * The maplibre-gl map degrades to an accessible selectable grid under jsdom
 * (maplibre-gl is mocked to throw in setupTests.ts) via the same
 * try/catch -> setUseGrid fallback pattern as charts/MapView.tsx.
 */

const PATHOGENS = ["Salmonella", "Listeria", "STEC"] as const;

type SourceFilter = "" | "s03" | "action_queue";

const SOURCES: Array<{ id: SourceFilter; label: string }> = [
  { id: "", label: "All sources" },
  { id: "s03", label: "Supplier surveillance (S03)" },
  { id: "action_queue", label: "Action queue (ACTIONQ)" },
];

const LOCATION_META: Record<
  string,
  { label: string; short: string; badge: string }
> = {
  mpi_verified: {
    label: "Verified (FSIS MPI)",
    short: "Verified",
    badge: "bg-teal/15 text-teal-700 border border-teal/30",
  },
  historical_candidate: {
    label: "Historical candidate",
    short: "Historical candidate",
    badge: "border border-dashed border-orange-500/60 bg-orange-500/10 text-orange-700",
  },
  unresolved: {
    label: "Unresolved",
    short: "Unresolved",
    badge: "bg-slate-100 text-slate-600 border border-slate-300",
  },
};

const MAP_HEIGHT = 560;

interface StateLabel { postal: string; lng: number; lat: number; }

function ringCentroidFM(ring: number[][]): { c: [number, number]; area: number } | null {
  if (!ring || ring.length < 3) return null;
  let a = 0, cx = 0, cy = 0;
  for (let i = 0; i < ring.length; i++) {
    const [x0, y0] = ring[i];
    const [x1, y1] = ring[(i + 1) % ring.length];
    const cross = x0 * y1 - x1 * y0;
    a += cross; cx += (x0 + x1) * cross; cy += (y0 + y1) * cross;
  }
  a *= 0.5;
  if (Math.abs(a) < 1e-12) return null;
  return { c: [cx / (6 * a), cy / (6 * a)], area: Math.abs(a) };
}

function centroidOfFM(geom: any): [number, number] | null {
  if (!geom) return null;
  if (geom.type === "Polygon") { const r = ringCentroidFM(geom.coordinates?.[0]); return r ? r.c : null; }
  if (geom.type === "MultiPolygon") {
    let best: { c: [number, number]; area: number } | null = null;
    for (const poly of geom.coordinates ?? []) { const r = ringCentroidFM(poly?.[0]); if (r && (!best || r.area > best.area)) best = r; }
    return best ? best.c : null;
  }
  return null;
}

/** Same-origin US-states GeoJSON (keyed by postal), reused from the risk-map
 * choropleth so the facility pins sit on a recognizable US base map rather than
 * a blank grey canvas. */
function statesGeojsonUrl(): string {
  const base = import.meta.env.BASE_URL ?? "/";
  return `${base}geo/us-states.json`;
}
const VERIFIED_FILL = "#0f8578"; // solid teal
const CANDIDATE_OUTLINE = "#ea7a1d"; // orange outline

/** A plotted facility: a row that carries a real numeric lat AND lon. */
interface Pin {
  row: FacilityMapItem;
  lat: number;
  lon: number;
}

function hasRealCoords(r: FacilityMapItem): r is FacilityMapItem & { lat: number; lon: number } {
  return typeof r.lat === "number" && Number.isFinite(r.lat) && typeof r.lon === "number" && Number.isFinite(r.lon);
}

function pct(v: number | null | undefined): string {
  return v === null || v === undefined ? "N/A" : `${(v * 100).toFixed(1)}%`;
}

function identityName(r: FacilityMapItem): string {
  return r.establishment_name ?? "(name not published)";
}

function identityNumber(r: FacilityMapItem): string {
  return r.establishment_number ?? r.establishment_id;
}

/** eb_posterior descending, nulls last; stable tiebreak on normalized number. */
function byPosteriorDesc(a: FacilityMapItem, b: FacilityMapItem): number {
  const av = a.eb_posterior;
  const bv = b.eb_posterior;
  if (av === null && bv === null) {
    return a.normalized_establishment_number.localeCompare(b.normalized_establishment_number);
  }
  if (av === null) return 1;
  if (bv === null) return -1;
  if (bv !== av) return bv - av;
  return a.normalized_establishment_number.localeCompare(b.normalized_establishment_number);
}

export function FacilityMap() {
  const state = useArtifact<FacilityMapItem[]>("facility_map");
  const [pathogen, setPathogen] = useState<string>("");
  const [source, setSource] = useState<SourceFilter>("");
  // Independent show/hide toggles per location_status.
  const [showStatus, setShowStatus] = useState<Record<string, boolean>>({
    mpi_verified: true,
    historical_candidate: true,
    unresolved: true,
  });
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const toggleStatus = (key: string) =>
    setShowStatus((s) => ({ ...s, [key]: !s[key] }));

  return (
    <div className="mx-auto max-w-7xl px-6 py-6">
      <section className="mb-6 overflow-hidden rounded-2xl bg-gradient-to-br from-navy via-navy-600 to-teal-600 px-6 py-10 text-white">
        <span className="inline-block rounded-full bg-white/10 px-3 py-1 text-xs font-semibold text-teal-500 ring-1 ring-white/20">
          Sourcing-scrutiny reference layer · OBSERVED surveillance · Human-in-the-loop
        </span>
        <h1 className="mt-4 text-3xl font-extrabold tracking-tight sm:text-4xl">Facility Map</h1>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-white/80">
          FSIS-sampled establishments with an elevated OBSERVED surveillance signal, shown at their
          sampling location — a sourcing-scrutiny reference layer, NOT the retailer&apos;s suppliers,
          NOT a contamination or illness claim. Distinct from the SIMULATED optimizer and the
          state-level PREDICTED risk map.
        </p>
      </section>

      {/* filters */}
      <div className="mb-4 flex flex-wrap items-end gap-4">
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-navy/60">Pathogen</p>
          <div className="flex flex-wrap gap-2">
            <FilterPill on={pathogen === ""} onClick={() => setPathogen("")}>
              All
            </FilterPill>
            {PATHOGENS.map((p) => (
              <FilterPill key={p} on={p === pathogen} onClick={() => setPathogen(p)}>
                {p}
              </FilterPill>
            ))}
          </div>
        </div>

        <label className="text-[11px] font-semibold text-navy/60">
          Source{" "}
          <select
            value={source}
            onChange={(e) => setSource(e.target.value as SourceFilter)}
            className="rounded border border-navy/20 bg-white px-2 py-1 text-xs text-navy focus:outline-none focus:ring-2 focus:ring-teal"
          >
            {SOURCES.map((s) => (
              <option key={s.id || "all"} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
        </label>

        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-navy/60">Show location types</p>
          <div className="flex flex-wrap gap-2">
            {(["mpi_verified", "historical_candidate", "unresolved"] as const).map((k) => {
              const on = showStatus[k];
              const meta = LOCATION_META[k];
              return (
                <button
                  key={k}
                  type="button"
                  aria-pressed={on}
                  data-testid={`status-toggle-${k}`}
                  onClick={() => toggleStatus(k)}
                  className={`rounded-lg border px-3 py-1.5 text-xs font-semibold transition ${
                    on
                      ? "border-navy/30 bg-navy text-white"
                      : "border-navy/15 bg-white text-navy/40 line-through hover:border-navy/30"
                  }`}
                >
                  {meta.label}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* framing / how to read */}
      <div className="mb-5 rounded-lg border border-navy/10 bg-surface-muted px-4 py-3 text-[11px] leading-relaxed text-navy/70">
        <span className="font-semibold text-navy">How to read this:</span> each facility is an
        FSIS-sampled establishment with an elevated <span className="font-semibold">OBSERVED</span>{" "}
        surveillance signal, plotted at its <span className="font-semibold">sampling location</span>.
        This is a <span className="font-semibold">sourcing-scrutiny reference layer</span>, not the
        retailer&apos;s suppliers. Every establishment carries a visible human-review gate.{" "}
        <span className="italic">
          This surface is derived from real surveillance and is separate from the base platform&apos;s
          SIMULATED allocation optimizer and from the state-level PREDICTED risk-map choropleth. No
          element here is a determination that a product is contaminated or safe.
        </span>
      </div>

      <PanelShell
        title="Signal-bearing FSIS establishments by sampling location"
        subtitle="OBSERVED · verified vs historical candidate · human-review-gated"
        info="Signal-bearing establishments selected from the S03 surveillance cache and the ACTIONQ action queue, joined to the FSIS MPI Directory for a verified sampling location. Historical candidates are shown for context only and are NOT confirmed against the FSIS establishment id. Coverage is a measured percentage, never assumed."
      >
        <ArtifactBody
          state={state}
          artifactName="facility_map"
          isEmpty={(rows) => rows.length === 0}
          emptyTitle="No facilities to map"
          emptyDetail="The facility_map artifact is present but contains no establishments. An empty map is an honest result."
          render={(rows) => (
            <FacilityMapBody
              rows={rows}
              pathogen={pathogen}
              source={source}
              showStatus={showStatus}
              selectedId={selectedId}
              onSelect={setSelectedId}
            />
          )}
        />
      </PanelShell>
    </div>
  );
}

function FilterPill({
  on,
  onClick,
  children,
}: {
  on: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onClick}
      className={`rounded-lg border px-3 py-1.5 text-xs font-semibold transition ${
        on ? "border-teal bg-teal text-white" : "border-navy/15 bg-white text-navy/70 hover:border-navy/30"
      }`}
    >
      {children}
    </button>
  );
}

function FacilityMapBody({
  rows,
  pathogen,
  source,
  showStatus,
  selectedId,
  onSelect,
}: {
  rows: FacilityMapItem[];
  pathogen: string;
  source: SourceFilter;
  showStatus: Record<string, boolean>;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}) {
  // A row matches the source filter when its source_selection is exactly the
  // chosen source OR "both".
  const filtered = useMemo(
    () =>
      rows
        .filter((r) => (pathogen ? r.pathogen === pathogen : true))
        .filter((r) =>
          source ? r.source_selection === source || r.source_selection === "both" : true,
        )
        .filter((r) => showStatus[r.location_status] !== false),
    [rows, pathogen, source, showStatus],
  );

  const ranked = useMemo(() => [...filtered].sort(byPosteriorDesc), [filtered]);

  const pins: Pin[] = useMemo(
    () =>
      filtered
        .filter(hasRealCoords)
        .map((r) => ({ row: r, lat: r.lat, lon: r.lon })),
    [filtered],
  );

  const unplaced = useMemo(
    () => filtered.filter((r) => r.placement_status === "unplaced"),
    [filtered],
  );

  // Per-pathogen coverage blocks visible under the current pathogen filter. The
  // coverage block is read verbatim from the rows — never recomputed.
  const coverageByPathogen = useMemo(() => {
    const seen = new Map<string, FacilityMapItem["coverage"]>();
    for (const r of filtered) {
      if (!seen.has(r.pathogen)) seen.set(r.pathogen, r.coverage);
    }
    return [...seen.entries()].map(([p, cov]) => ({ pathogen: p, cov }));
  }, [filtered]);

  const selected = useMemo(
    () => filtered.find((r) => r.establishment_id === selectedId) ?? null,
    [filtered, selectedId],
  );

  if (filtered.length === 0) {
    return (
      <EmptyState
        title="No facilities for this filter"
        detail="Try a different pathogen, source, or re-enable a location type."
      />
    );
  }

  return (
    <div className="flex flex-col gap-5">
      {/* Full-width map on top */}
      <div className="flex flex-col gap-2">
        <FacilityMapView pins={pins} selectedId={selectedId} onSelect={onSelect} />
        <MarkerLegend />
        <CoverageNote blocks={coverageByPathogen} />
      </div>

      {/* Selected-establishment detail (if any), then the ranked list below the map */}
      {selected ? (
        <DetailPanel row={selected} onClose={() => onSelect(null)} />
      ) : null}
      <RankedList rows={ranked} selectedId={selectedId} onSelect={onSelect} />

      <UnresolvedSection rows={unplaced} onSelect={onSelect} />

      <Methodology />

      <p className="mt-1 text-[10px] italic text-navy/50">
        Locations are FSIS-published sampling locations for establishments with an elevated OBSERVED
        surveillance signal; they are not supplier relationships, product destinations, or illness
        locations. Historical candidates are shown for context and are not confirmed against the FSIS
        establishment id. Every establishment requires human review and is retailer decision support
        — never a determination that a product is contaminated or safe, and never a regulatory
        directive.
      </p>
    </div>
  );
}

/* --------------------------------------------------------------------------- */
/* Coverage strip                                                              */
/* --------------------------------------------------------------------------- */

function CoverageNote({ blocks }: { blocks: Array<{ pathogen: string; cov: FacilityMapItem["coverage"] }> }) {
  const totalSelected = blocks.reduce((n, b) => n + b.cov.total_selected, 0);
  const placed = blocks.reduce((n, b) => n + b.cov.placed, 0);
  const historical = blocks.reduce((n, b) => n + b.cov.historical_candidate, 0);
  const unresolved = blocks.reduce((n, b) => n + b.cov.unresolved, 0);
  const plotted = placed + historical;
  return (
    <p data-testid="coverage-note" className="text-[11px] leading-relaxed text-navy/60">
      <span className="font-semibold text-navy">{plotted} of {totalSelected}</span> establishments plotted:{" "}
      <span className="font-semibold text-teal-700">{placed} FSIS-verified</span>{" "}
      (matched to the FSIS MPI Directory by establishment id)
      {historical > 0 ? (<> + <span className="font-semibold text-orange-700">{historical} historical candidate{historical === 1 ? "" : "s"}</span> (external research, identity unconfirmed against FSIS)</>) : null}
      {unresolved > 0 ? <>; <span className="font-semibold text-navy/70">{unresolved} unresolved</span></> : null}.
      {" "}<span className="italic text-navy/45">Only FSIS-verified establishments count toward verified coverage; historical candidates never do.</span>
    </p>
  );
}

/* --------------------------------------------------------------------------- */
/* Map                                                                         */
/* --------------------------------------------------------------------------- */

function MarkerLegend() {
  return (
    <div className="flex flex-wrap items-center gap-4 text-[11px] text-navy/70">
      <span className="inline-flex items-center gap-1.5">
        <span
          aria-hidden
          className="inline-block h-3 w-3 rounded-full"
          style={{ backgroundColor: VERIFIED_FILL }}
        />
        Verified — FSIS MPI Directory matched
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span
          aria-hidden
          className="inline-block h-3 w-3 rounded-full border-2 border-dashed bg-white"
          style={{ borderColor: CANDIDATE_OUTLINE }}
        />
        Historical candidate — identity unconfirmed
      </span>
    </div>
  );
}

/**
 * maplibre-gl US map with a clustered GeoJSON source and two distinct marker
 * styles. Degrades to an accessible selectable grid (FallbackGrid) under jsdom
 * via the same try/catch -> setUseGrid pattern as charts/MapView.tsx.
 */
function FacilityMapView({
  pins,
  selectedId,
  onSelect,
}: {
  pins: Pin[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [useGrid, setUseGrid] = useState(false);
  const [glReady, setGlReady] = useState(false);
  const [hover, setHover] = useState<{ id: string; x: number; y: number } | null>(null);
  const [stateLabels, setStateLabels] = useState<StateLabel[]>([]);
  const [labelScreen, setLabelScreen] = useState<Record<string, { x: number; y: number }>>({});
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  const pinsRef = useRef(pins);
  pinsRef.current = pins;

  const geojson = useMemo(
    () => ({
      type: "FeatureCollection" as const,
      features: pins.map((p) => ({
        type: "Feature" as const,
        geometry: { type: "Point" as const, coordinates: [p.lon, p.lat] },
        properties: {
          id: p.row.establishment_id,
          name: identityName(p.row),
          state: p.row.state,
          location_status: p.row.location_status,
          verified: p.row.location_status === "mpi_verified" ? 1 : 0,
        },
      })),
    }),
    [pins],
  );

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    let cancelled = false;
    let map: maplibregl.Map;
    try {
      map = new maplibregl.Map({
        container: containerRef.current,
        style: {
          version: 8,
          sources: {},
          layers: [{ id: "bg", type: "background", paint: { "background-color": "#eef2f6" } }],
        },
        center: [-96, 38],
        zoom: 3.3,
        attributionControl: false,
        dragRotate: false,
      });
    } catch {
      setUseGrid(true);
      return;
    }
    mapRef.current = map;
    try {
      map.addControl(new maplibregl.NavigationControl({ showCompass: false, showZoom: true }), "top-left");
    } catch { /* controls are an enhancement, not required */ }
    const fail = () => {
      if (!cancelled) setUseGrid(true);
    };

    map.on("load", async () => {
      try {
        map.resize();
        // Base map: US state polygons (same-origin GeoJSON). Drawn first so the
        // facility pins render on top of a recognizable map, not a blank canvas.
        try {
          const resp = await fetch(statesGeojsonUrl());
          if (resp.ok) {
            const gj = await resp.json();
            if (!cancelled) {
              map.addSource("us-states", { type: "geojson", data: gj });
              map.addLayer({ id: "states-fill", type: "fill", source: "us-states",
                paint: { "fill-color": "#dbe4ec", "fill-opacity": 0.9 } });
              map.addLayer({ id: "states-outline", type: "line", source: "us-states",
                paint: { "line-color": "#ffffff", "line-width": 0.8 } });
              const pts: StateLabel[] = [];
              for (const f of gj.features ?? []) {
                const postal = f?.properties?.postal;
                const c = centroidOfFM(f?.geometry);
                if (postal && c) pts.push({ postal, lng: c[0], lat: c[1] });
              }
              setStateLabels(pts);
              const project = () => {
                const next: Record<string, { x: number; y: number }> = {};
                const cw = map.getContainer().clientWidth;
                const ch = map.getContainer().clientHeight;
                for (const pt of pts) {
                  const sp = map.project([pt.lng, pt.lat]);
                  if (sp.x < -4 || sp.y < -4 || sp.x > cw + 4 || sp.y > ch + 4) continue;
                  next[pt.postal] = { x: sp.x, y: sp.y };
                }
                setLabelScreen(next);
              };
              project();
              let raf = 0;
              const schedule = () => { if (raf) return; raf = requestAnimationFrame(() => { raf = 0; project(); }); };
              map.on("move", schedule);
              map.on("zoom", schedule);
              map.on("moveend", project);
              map.on("resize", project);
            }
          }
        } catch {
          /* basemap is an enhancement; pins still render without it */
        }
        if (cancelled) return;
        map.addSource("facilities", {
          type: "geojson",
          data: geojson,
          cluster: true,
          clusterRadius: 50,
          clusterMaxZoom: 10,
        });

        // Clusters
        map.addLayer({
          id: "clusters",
          type: "circle",
          source: "facilities",
          filter: ["has", "point_count"],
          paint: {
            "circle-color": "#0f2742",
            "circle-opacity": 0.85,
            "circle-radius": ["step", ["get", "point_count"], 16, 5, 22, 15, 28],
          },
        });
        map.addLayer({
          id: "cluster-count",
          type: "symbol",
          source: "facilities",
          filter: ["has", "point_count"],
          layout: { "text-field": ["get", "point_count_abbreviated"], "text-size": 12 },
          paint: { "text-color": "#ffffff" },
        });

        // VERIFIED leaves: SOLID teal filled circle with a dark ring.
        map.addLayer({
          id: "verified-pins",
          type: "circle",
          source: "facilities",
          filter: ["all", ["!", ["has", "point_count"]], ["==", ["get", "verified"], 1]],
          paint: {
            "circle-color": VERIFIED_FILL,
            "circle-radius": 7,
            "circle-stroke-color": "#0f2742",
            "circle-stroke-width": 1.5,
          },
        });

        // HISTORICAL CANDIDATE leaves: HOLLOW white fill with a thick dashed-feel
        // orange outline (distinct from the solid verified marker).
        map.addLayer({
          id: "candidate-pins",
          type: "circle",
          source: "facilities",
          filter: ["all", ["!", ["has", "point_count"]], ["==", ["get", "verified"], 0]],
          paint: {
            "circle-color": "#ffffff",
            "circle-opacity": 0.9,
            "circle-radius": 7,
            "circle-stroke-color": CANDIDATE_OUTLINE,
            "circle-stroke-width": 2.5,
          },
        });

        const leafClick = (e: maplibregl.MapLayerMouseEvent) => {
          const id = e.features?.[0]?.properties?.id as string | undefined;
          if (id) onSelectRef.current(id);
        };
        map.on("click", "verified-pins", leafClick);
        map.on("click", "candidate-pins", leafClick);

        // Click a cluster -> zoom into its leaves.
        map.on("click", "clusters", (e) => {
          const feat = e.features?.[0];
          const coords = (feat?.geometry as { coordinates?: [number, number] })?.coordinates;
          if (coords) map.easeTo({ center: coords, zoom: Math.min((map.getZoom() ?? 3) + 2, 10) });
        });

        const enter = (e: maplibregl.MapLayerMouseEvent) => {
          const id = e.features?.[0]?.properties?.id as string | undefined;
          map.getCanvas().style.cursor = "pointer";
          if (id) setHover({ id, x: e.point.x, y: e.point.y });
        };
        const leave = () => {
          map.getCanvas().style.cursor = "";
          setHover(null);
        };
        map.on("mousemove", "verified-pins", enter);
        map.on("mousemove", "candidate-pins", enter);
        map.on("mouseleave", "verified-pins", leave);
        map.on("mouseleave", "candidate-pins", leave);

        setTimeout(() => {
          if (!cancelled) {
            map.resize();
            setGlReady(true);
          }
        }, 60);
      } catch {
        fail();
      }
    });
    map.on("error", () => {
      /* non-fatal style/tile noise */
    });

    return () => {
      cancelled = true;
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Keep the GeoJSON source in sync when the filtered pin set changes.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.getSource) return;
    const src = map.getSource("facilities") as maplibregl.GeoJSONSource | undefined;
    if (src && typeof src.setData === "function") src.setData(geojson);
  }, [geojson]);

  if (useGrid) {
    return <FallbackGrid pins={pins} selectedId={selectedId} onSelect={onSelect} />;
  }

  const hoverPin = hover ? pins.find((p) => p.row.establishment_id === hover.id) : undefined;

  return (
    <div className="relative" style={{ height: MAP_HEIGHT }}>
      <div
        ref={containerRef}
        data-testid="facility-map-view"
        role="group"
        aria-label="Signal-bearing FSIS establishments by sampling location"
        style={{ position: "absolute", inset: 0, borderRadius: 8, overflow: "hidden" }}
        className="border border-navy/10"
      />
      {glReady ? (
        <button
          type="button"
          data-testid="facility-map-reset"
          aria-label="Reset map view"
          onClick={() => { const m = mapRef.current; if (m) m.flyTo({ center: [-96, 38], zoom: 3.3, duration: 500 }); }}
          className="absolute left-2 top-24 z-20 rounded border border-navy/15 bg-white px-2 py-1 text-[11px] font-semibold text-navy shadow hover:border-teal hover:text-teal focus:outline-none focus:ring-2 focus:ring-teal"
        >
          Reset
        </button>
      ) : null}
      {glReady
        ? stateLabels.map((l) => {
            const sp = labelScreen[l.postal];
            if (!sp) return null;
            return (
              <span
                key={l.postal}
                aria-hidden
                style={{ position: "absolute", left: sp.x, top: sp.y, transform: "translate(-50%,-50%)" }}
                className="pointer-events-none select-none text-[11px] font-bold leading-none text-slate-500"
              >
                {l.postal}
              </span>
            );
          })
        : null}
      {glReady && hover && hoverPin ? (
        <div
          style={{ position: "absolute", left: hover.x + 10, top: hover.y + 10 }}
          className="pointer-events-none max-w-[240px] rounded bg-navy px-2.5 py-1.5 text-xs font-semibold text-white shadow-lg"
        >
          {identityName(hoverPin.row)} · {hoverPin.row.state}
          <span
            className={`ml-1 rounded px-1.5 py-0.5 text-[10px] font-bold ${
              hoverPin.row.location_status === "mpi_verified"
                ? "bg-teal-500 text-white"
                : "bg-orange-500 text-white"
            }`}
          >
            {LOCATION_META[hoverPin.row.location_status]?.short ?? hoverPin.row.location_status}
          </span>
        </div>
      ) : null}
      {!glReady ? (
        <div className="absolute inset-0 overflow-auto rounded border border-navy/10 bg-white p-2">
          <FallbackGrid pins={pins} selectedId={selectedId} onSelect={onSelect} compact />
        </div>
      ) : null}
    </div>
  );
}

/**
 * Accessible fallback rendered deterministically under jsdom. Each plotted
 * facility is a selectable button exposing the test hooks Task 6.3 relies on:
 *   data-testid="facility-pin", data-establishment-id, data-location-status.
 * Verified vs historical-candidate markers stay visually distinct here too:
 * verified = solid teal dot; candidate = hollow dashed orange ring.
 */
function FallbackGrid({
  pins,
  selectedId,
  onSelect,
  compact = false,
}: {
  pins: Pin[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  compact?: boolean;
}) {
  if (pins.length === 0) {
    return (
      <div
        data-testid="facility-map-view"
        role="group"
        aria-label="Signal-bearing FSIS establishments by sampling location"
        className="flex h-full items-center justify-center p-4 text-center text-[11px] text-navy/50"
      >
        No establishments have a verified sampling location for this filter. See the ranked list and
        the unresolved section below.
      </div>
    );
  }
  const ordered = [...pins].sort((a, b) => byPosteriorDesc(a.row, b.row));
  return (
    <div
      data-testid="facility-map-view"
      role="group"
      aria-label="Signal-bearing FSIS establishments by sampling location"
      className={`grid gap-2 ${compact ? "grid-cols-2 sm:grid-cols-3" : "grid-cols-1 sm:grid-cols-2"}`}
    >
      {ordered.map(({ row }) => {
        const verified = row.location_status === "mpi_verified";
        const sel = row.establishment_id === selectedId;
        return (
          <button
            key={row.establishment_id}
            type="button"
            data-testid="facility-pin"
            data-establishment-id={row.establishment_id}
            data-location-status={row.location_status}
            aria-pressed={sel}
            onClick={() => onSelect(row.establishment_id)}
            className={`flex items-start gap-2 rounded-lg border px-2.5 py-2 text-left transition focus:outline-none focus:ring-2 focus:ring-teal ${
              sel ? "border-navy bg-navy/5" : "border-navy/15 bg-white hover:border-navy/30"
            }`}
          >
            <span
              aria-hidden
              className={`mt-0.5 inline-block h-3 w-3 shrink-0 rounded-full ${
                verified ? "" : "border-2 border-dashed bg-white"
              }`}
              style={
                verified
                  ? { backgroundColor: VERIFIED_FILL }
                  : { borderColor: CANDIDATE_OUTLINE }
              }
            />
            <span className="min-w-0">
              <span className="block truncate text-[11px] font-semibold text-navy">
                {identityName(row)}
              </span>
              <span className="block text-[10px] text-navy/60">
                {row.state} · {verified ? "Verified" : "Historical candidate"} ·{" "}
                {pct(row.eb_posterior)}
              </span>
            </span>
          </button>
        );
      })}
    </div>
  );
}

/* --------------------------------------------------------------------------- */
/* Ranked list                                                                 */
/* --------------------------------------------------------------------------- */

function RankedList({
  rows,
  selectedId,
  onSelect,
}: {
  rows: FacilityMapItem[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  if (rows.length === 0) {
    return <EmptyState title="No facilities for this filter" detail="Try a different pathogen or source." />;
  }
  const COLLAPSED = 5;
  const shown = expanded ? rows : rows.slice(0, COLLAPSED);
  return (
    <div className="flex flex-col gap-3">
      <p className="text-[11px] text-navy/50">
        Showing {shown.length} of {rows.length} establishment(s), highest surveillance signal first.
      </p>
      <ul className="flex flex-col gap-2">
        {shown.map((r) => {
          const meta = LOCATION_META[r.location_status] ?? LOCATION_META.unresolved;
          const lowSupport = r.sample_n < 30;
          const sel = r.establishment_id === selectedId;
          return (
            <li key={r.establishment_id}>
              <button
                type="button"
                data-testid="ranked-facility"
                data-establishment-id={r.establishment_id}
                aria-pressed={sel}
                onClick={() => onSelect(r.establishment_id)}
                className={`w-full rounded-lg border p-4 text-left transition focus:outline-none focus:ring-2 focus:ring-teal ${
                  sel ? "border-navy bg-navy/5" : "border-navy/10 bg-white hover:border-navy/30"
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="mb-1 flex flex-wrap items-center gap-2">
                      <span className="rounded-full border border-navy/15 px-2 py-0.5 text-[10px] font-semibold text-navy/60">
                        {identityNumber(r)} · {r.pathogen}
                      </span>
                      <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${meta.badge}`}>
                        {meta.short}
                      </span>
                      <span className="rounded-full bg-navy/10 px-2 py-0.5 text-[10px] font-semibold text-navy/60">
                        {r.source_selection === "both" ? "S03 + ACTIONQ" : r.source_selection}
                      </span>
                    </div>
                    <p className="text-sm font-semibold text-navy">{identityName(r)}</p>
                    <p className="mt-0.5 text-[11px] text-navy/60">
                      {r.state}
                      {r.county ? ` · ${r.county}` : ""}
                    </p>
                    <p className="mt-1 text-[11px] text-navy/70">
                      <span className="font-semibold text-navy/70">Surveillance signal: </span>
                      {pct(r.eb_posterior)}{" "}
                      <span className="text-navy/50">
                        [{pct(r.ci_low)}, {pct(r.ci_high)}]
                      </span>
                    </p>
                    <p className="mt-0.5 text-[10px] text-navy/50">
                      {r.positive_n}/{r.sample_n} positive
                      {lowSupport ? (
                        <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 font-semibold text-slate-600">
                          low support (n&lt;30)
                        </span>
                      ) : null}
                    </p>
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-1">
                    <StatusTag status={r.status} />
                    <span className="rounded-full bg-orange-500/15 px-2 py-0.5 text-[10px] font-bold text-orange-700">
                      ⚠ Human review
                    </span>
                  </div>
                </div>
              </button>
            </li>
          );
        })}
      </ul>
      {rows.length > COLLAPSED ? (
        <button
          type="button"
          data-testid="ranked-facility-toggle"
          onClick={() => setExpanded((v) => !v)}
          className="mx-auto rounded-lg border border-navy/20 px-4 py-1.5 text-xs font-semibold text-navy/70 transition hover:bg-surface-muted focus:outline-none focus:ring-2 focus:ring-teal"
        >
          {expanded ? "Show top 5 only" : `Show all ${rows.length} establishments`}
        </button>
      ) : null}
    </div>
  );
}

/* --------------------------------------------------------------------------- */
/* Detail panel                                                                */
/* --------------------------------------------------------------------------- */

function DetailPanel({ row, onClose }: { row: FacilityMapItem; onClose: () => void }) {
  const verified = row.location_status === "mpi_verified";
  const candidate = row.location_status === "historical_candidate";
  const meta = LOCATION_META[row.location_status] ?? LOCATION_META.unresolved;
  return (
    <div data-testid="facility-detail" className="rounded-xl border border-navy/15 bg-white p-4">
      <div className="mb-2 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${meta.badge}`}>
              {meta.label}
            </span>
            <StatusTag status={row.status} />
            <span className="rounded-full bg-orange-500/15 px-2 py-0.5 text-[10px] font-bold text-orange-700">
              ⚠ Human review
            </span>
          </div>
          <h3 className="text-base font-bold text-navy">{identityName(row)}</h3>
          <p className="text-[11px] text-navy/60">
            FSIS est. {identityNumber(row)} · {row.pathogen} · {row.state}
            {row.county ? ` · ${row.county}` : ""}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded border border-navy/15 px-2 py-1 text-[11px] font-semibold text-navy/60 hover:border-navy/30"
        >
          Close
        </button>
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-[11px]">
        <Field label="Surveillance signal" value={`${pct(row.eb_posterior)} [${pct(row.ci_low)}, ${pct(row.ci_high)}]`} />
        <Field label="Samples" value={`${row.positive_n}/${row.sample_n} positive`} />
        <Field label="Source" value={row.source_selection === "both" ? "S03 + ACTIONQ" : row.source_selection} />
        <Field label="Support" value={row.support_status} />
        <Field label="Match method" value={row.match_method ?? "N/A"} />
        <Field label="Match confidence" value={row.match_confidence ?? "N/A"} />
        {verified ? (
          <>
            <Field label="Coordinate source" value={row.coordinate_source ?? "N/A"} />
            <Field label="Sampling location" value={row.address ?? "N/A"} />
          </>
        ) : null}
      </dl>

      {candidate ? (
        <div className="mt-3 rounded-lg border border-dashed border-orange-500/50 bg-orange-500/5 p-3">
          <p className="text-[11px] font-semibold text-orange-700">Historical candidate details</p>
          <dl className="mt-1 grid grid-cols-1 gap-y-1 text-[11px]">
            <Field label="Historical address" value={row.historical_address ?? "N/A"} />
            <Field label="Historical inspection number" value={row.historical_inspection_number ?? "N/A"} />
          </dl>
          {row.evidence_urls.length > 0 ? (
            <div className="mt-1">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-navy/50">Evidence</p>
              <ul className="mt-0.5 flex flex-col gap-0.5">
                {row.evidence_urls.map((url) => (
                  <li key={url}>
                    <a
                      href={url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="break-all text-[11px] font-medium text-teal-700 underline hover:text-teal-600"
                    >
                      {url}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}

      <p className="mt-3 text-[11px] leading-relaxed text-navy/60">
        <span className="font-semibold text-navy/70">Evidence: </span>
        {row.evidence_summary}
      </p>

      {row.unplaced_reason ? (
        <p className="mt-2 text-[11px] text-navy/60">
          <span className="font-semibold text-navy/70">Not plotted: </span>
          {row.unplaced_reason}
        </p>
      ) : null}

      <p
        className={`mt-3 rounded-lg px-3 py-2 text-[11px] leading-relaxed ${
          verified ? "bg-teal/5 text-navy/70" : "bg-orange-500/5 text-orange-800"
        }`}
      >
        {verified ? (
          <>
            Matched to the FSIS MPI Directory by establishment id; coordinates are the FSIS-published
            sampling location.
          </>
        ) : (
          <>
            Historical candidate — identity NOT confirmed against the FSIS establishment id. The
            historical inspection number and address come from external records and are not proven to
            correspond to this numeric surveillance establishment id.
          </>
        )}
      </p>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-[10px] font-semibold uppercase tracking-wide text-navy/40">{label}</dt>
      <dd className="truncate text-navy/80" title={value}>
        {value}
      </dd>
    </div>
  );
}

/* --------------------------------------------------------------------------- */
/* Unresolved section                                                          */
/* --------------------------------------------------------------------------- */

function UnresolvedSection({
  rows,
  onSelect,
}: {
  rows: FacilityMapItem[];
  onSelect: (id: string) => void;
}) {
  if (rows.length === 0) return null;
  return (
    <div data-testid="unresolved-section" className="rounded-xl border border-navy/10 bg-surface-muted p-4">
      <h3 className="text-sm font-bold text-navy">Not plotted ({rows.length})</h3>
      <p className="mt-0.5 text-[11px] text-navy/60">
        These signal-bearing establishments could not be plotted at a verified FSIS sampling location.
        Each is listed with its stated reason — never approximated onto the map.
      </p>
      <ul className="mt-3 flex flex-col gap-2">
        {rows.map((r) => {
          const candidate = r.location_status === "historical_candidate";
          return (
            <li
              key={r.establishment_id}
              className="rounded-lg border border-navy/10 bg-white p-3"
            >
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  data-testid="unresolved-facility"
                  data-establishment-id={r.establishment_id}
                  data-location-status={r.location_status}
                  onClick={() => onSelect(r.establishment_id)}
                  className="text-sm font-semibold text-navy underline-offset-2 hover:underline"
                >
                  {identityName(r)}
                </button>
                <span className="rounded-full border border-navy/15 px-2 py-0.5 text-[10px] font-semibold text-navy/60">
                  {identityNumber(r)} · {r.pathogen} · {r.state}
                </span>
                <span
                  className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                    (LOCATION_META[r.location_status] ?? LOCATION_META.unresolved).badge
                  }`}
                >
                  {(LOCATION_META[r.location_status] ?? LOCATION_META.unresolved).short}
                </span>
              </div>
              <p className="mt-1 text-[11px] text-navy/70">
                <span className="font-semibold text-navy/70">Reason: </span>
                {r.unplaced_reason ?? "not stated"}
              </p>
              {candidate ? (
                <div className="mt-1.5 rounded-md border border-dashed border-orange-500/40 bg-orange-500/5 px-2.5 py-2">
                  {r.historical_address ? (
                    <p className="text-[11px] text-navy/70">
                      <span className="font-semibold text-navy/70">Candidate address: </span>
                      {r.historical_address}
                    </p>
                  ) : null}
                  {r.evidence_urls.length > 0 ? (
                    <ul className="mt-1 flex flex-col gap-0.5">
                      {r.evidence_urls.map((url) => (
                        <li key={url}>
                          <a
                            href={url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="break-all text-[11px] font-medium text-teal-700 underline hover:text-teal-600"
                          >
                            {url}
                          </a>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  <p className="mt-1 text-[10px] italic text-orange-700">
                    Identity unconfirmed — not proven to correspond to this numeric surveillance
                    establishment id.
                  </p>
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/* --------------------------------------------------------------------------- */
/* Methodology                                                                 */
/* --------------------------------------------------------------------------- */

function Methodology() {
  return (
    <details className="rounded-xl border border-navy/10 bg-white p-4 text-[11px] leading-relaxed text-navy/70">
      <summary className="cursor-pointer text-sm font-bold text-navy">Methodology &amp; limitations</summary>
      <div className="mt-2 flex flex-col gap-2">
        <p>
          Establishments are selected from the OBSERVED S03 surveillance cache (top establishments by
          empirical-Bayes posterior among adequately-supported records) and the ACTIONQ action queue
          (establishment targets). Each is joined to the FSIS Meat, Poultry &amp; Egg Product
          Inspection (MPI) Directory by a normalized establishment id to obtain a verified,
          FSIS-published sampling location.
        </p>
        <p>
          Verified coverage is a <span className="font-semibold">measured</span> placed/selected
          percentage — never assumed to be complete. Establishments that cannot be matched are listed
          as unresolved or as historical candidates with a stated reason; their coordinates are never
          approximated or fabricated.
        </p>
        <p>
          Historical candidates are context only. Their inspection numbers and addresses come from
          external records and are <span className="font-semibold">not</span> proven to correspond to
          the numeric surveillance establishment id, so they are excluded from verified coverage.
        </p>
        <p className="italic text-navy/50">
          This layer is retailer decision support for sourcing scrutiny. It is distinct from the
          SIMULATED allocation optimizer and from the state-level PREDICTED risk map, and it is never
          a contamination or illness finding.
        </p>
      </div>
    </details>
  );
}

export default FacilityMap;
