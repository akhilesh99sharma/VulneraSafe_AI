import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { RiskMapFeature } from "../../../types/artifacts";
import { formatRisk } from "../../../types/viewModels";
import { colorForRisk, NO_DATA_COLOR, RISK_BANDS } from "./riskBands";

// Re-export so existing importers can pull the shared bucketing from either
// module; riskBands.ts is the single source of truth.
export { colorForRisk, riskBandLabel } from "./riskBands";

/**
 * Geographic risk choropleth (Req 12.1, task 6.3).
 *
 * MapLibre US-states choropleth filled by model risk, from a STATIC same-origin
 * GeoJSON (`web/public/geo/us-states.json`, keyed by `postal`). Two-letter state
 * labels are drawn as HTML overlays positioned at each polygon's centroid (so no
 * glyph/font server is needed), and a hover tooltip shows the state + risk.
 * Degrades to an accessible colored grid if WebGL/GeoJSON is unavailable.
 */

export interface MapViewProps {
  features: RiskMapFeature[];
  selectedRegion: string | null;
  onSelectRegion: (region: string) => void;
}

const MAP_HEIGHT = 480;

function geojsonUrl(): string {
  const base = import.meta.env.BASE_URL ?? "/";
  return `${base}geo/us-states.json`;
}
function buildFillExpression(byPostal: Map<string, number>): any {
  const stops: (string | number)[] = [];
  for (const [p, r] of byPostal) stops.push(p, colorForRisk(r));
  return ["match", ["get", "postal"], ...(stops.length ? stops : ["__none__", NO_DATA_COLOR]), NO_DATA_COLOR];
}

/**
 * Area-weighted centroid of a single polygon outer ring (the standard
 * polygon-centroid formula), clamped to the ring's bounding box. Returns the
 * centroid and the signed area magnitude so a MultiPolygon can pick its largest
 * sub-polygon. A degenerate (zero-area) ring falls back to its bbox center so a
 * label still lands inside the ring rather than at an undefined point.
 */
function ringCentroid(ring: number[][]): { c: [number, number]; area: number } | null {
  if (!ring || ring.length < 3) return null;
  let a = 0, cx = 0, cy = 0;
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (let i = 0; i < ring.length; i++) {
    const [x0, y0] = ring[i];
    const [x1, y1] = ring[(i + 1) % ring.length];
    const cross = x0 * y1 - x1 * y0;
    a += cross;
    cx += (x0 + x1) * cross;
    cy += (y0 + y1) * cross;
    if (x0 < minX) minX = x0;
    if (y0 < minY) minY = y0;
    if (x0 > maxX) maxX = x0;
    if (y0 > maxY) maxY = y0;
  }
  a *= 0.5;
  let c: [number, number];
  if (Math.abs(a) < 1e-12) {
    // Degenerate ring: use the bounding-box center.
    c = [(minX + maxX) / 2, (minY + maxY) / 2];
  } else {
    c = [cx / (6 * a), cy / (6 * a)];
    // Clamp into the ring's bounding box so a near-degenerate case still lands
    // inside the polygon rather than drifting outside.
    c = [
      Math.min(maxX, Math.max(minX, c[0])),
      Math.min(maxY, Math.max(minY, c[1])),
    ];
  }
  return { c, area: Math.abs(a) };
}

/**
 * Label anchor for a GeoJSON geometry (lng,lat):
 *   - Polygon:      area-weighted centroid of its OUTER ring.
 *   - MultiPolygon: area-weighted centroid of the LARGEST sub-polygon's outer
 *     ring, so states with islands/panhandles (FL, HI, AK, LA, MI) keep their
 *     label on the mainland instead of at the vertex-average of every polygon.
 */
function centroidOf(geom: any): [number, number] | null {
  if (!geom) return null;
  if (geom.type === "Polygon") {
    const r = ringCentroid(geom.coordinates?.[0]);
    return r ? r.c : null;
  }
  if (geom.type === "MultiPolygon") {
    let best: { c: [number, number]; area: number } | null = null;
    for (const poly of geom.coordinates ?? []) {
      const r = ringCentroid(poly?.[0]);
      if (r && (!best || r.area > best.area)) best = r;
    }
    return best ? best.c : null;
  }
  return null;
}

interface LabelPoint { postal: string; lng: number; lat: number; }

export function MapView({ features, selectedRegion, onSelectRegion }: MapViewProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [glReady, setGlReady] = useState(false);
  const [useGrid, setUseGrid] = useState(false);
  const [labels, setLabels] = useState<LabelPoint[]>([]);
  const [screen, setScreen] = useState<Record<string, { x: number; y: number }>>({});
  const [hover, setHover] = useState<{ postal: string; x: number; y: number } | null>(null);
  const onSelectRef = useRef(onSelectRegion);
  onSelectRef.current = onSelectRegion;

  const byPostal = useMemo(() => {
    const m = new Map<string, number>();
    for (const f of features) m.set(f.region, f.risk);
    return m;
  }, [features]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    let cancelled = false;
    let map: maplibregl.Map;
    try {
      map = new maplibregl.Map({
        container: containerRef.current,
        style: { version: 8, sources: {}, layers: [{ id: "bg", type: "background", paint: { "background-color": "#eef2f6" } }] },
        center: [-96, 38], zoom: 3.1, attributionControl: false, dragRotate: false,
      });
    } catch { setUseGrid(true); return; }
    mapRef.current = map;
    const fail = () => { if (!cancelled) setUseGrid(true); };

    const projectLabels = (pts: LabelPoint[]) => {
      const next: Record<string, { x: number; y: number }> = {};
      const cw = map.getContainer().clientWidth;
      const ch = map.getContainer().clientHeight;
      for (const p of pts) {
        const pt = map.project([p.lng, p.lat]);
        // Only keep labels whose centroid is inside the visible map area, with
        // a small margin, so panned-away states do not leave floating labels.
        if (pt.x < -4 || pt.y < -4 || pt.x > cw + 4 || pt.y > ch + 4) continue;
        next[p.postal] = { x: pt.x, y: pt.y };
      }
      setScreen(next);
    };

    map.on("load", async () => {
      try {
        map.resize();
        const resp = await fetch(geojsonUrl());
        if (!resp.ok) throw new Error(`geojson HTTP ${resp.status}`);
        const gj = await resp.json();
        if (cancelled) return;
        map.addSource("states", { type: "geojson", data: gj });
        map.addLayer({ id: "states-fill", type: "fill", source: "states",
          paint: { "fill-color": buildFillExpression(byPostal), "fill-opacity": 0.92 } });
        map.addLayer({ id: "states-outline", type: "line", source: "states",
          paint: { "line-color": "#ffffff", "line-width": 0.8 } });
        map.addLayer({ id: "states-selected", type: "line", source: "states",
          paint: { "line-color": "#0f2742", "line-width": 2.5 },
          filter: ["==", ["get", "postal"], selectedRegion ?? "__none__"] });

        // Build centroid label points once.
        const pts: LabelPoint[] = [];
        for (const f of gj.features ?? []) {
          const postal = f?.properties?.postal;
          const c = centroidOf(f?.geometry);
          if (postal && c) pts.push({ postal, lng: c[0], lat: c[1] });
        }
        if (!cancelled) { setLabels(pts); projectLabels(pts); }

        map.on("click", "states-fill", (e) => {
          const p = e.features?.[0]?.properties as { postal?: string } | undefined;
          if (p?.postal) onSelectRef.current(p.postal);
        });
        map.on("mousemove", "states-fill", (e) => {
          const p = e.features?.[0]?.properties as { postal?: string } | undefined;
          map.getCanvas().style.cursor = "pointer";
          if (p?.postal) setHover({ postal: p.postal, x: e.point.x, y: e.point.y });
        });
        map.on("mouseleave", "states-fill", () => { map.getCanvas().style.cursor = ""; setHover(null); });
        // Reposition labels during pan/zoom WITHOUT a setState-per-frame storm:
        // coalesce into a single requestAnimationFrame between gesture events.
        let raf = 0;
        const schedule = () => {
          if (raf) return;
          raf = requestAnimationFrame(() => { raf = 0; projectLabels(pts); });
        };
        map.on("move", schedule);
        map.on("zoom", schedule);
        map.on("moveend", () => projectLabels(pts));
        map.on("resize", () => projectLabels(pts));

        setTimeout(() => { if (!cancelled) { map.resize(); projectLabels(pts); setGlReady(true); } }, 60);
      } catch { fail(); }
    });
    map.on("error", () => { /* non-fatal style/tile noise */ });

    return () => { cancelled = true; map.remove(); mapRef.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.getLayer || !map.getLayer("states-fill")) return;
    map.setPaintProperty("states-fill", "fill-color", buildFillExpression(byPostal));
  }, [byPostal]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.getLayer || !map.getLayer("states-selected")) return;
    map.setFilter("states-selected", ["==", ["get", "postal"], selectedRegion ?? "__none__"]);
  }, [selectedRegion]);

  if (useGrid) {
    return <FallbackGrid features={features} selectedRegion={selectedRegion} onSelectRegion={onSelectRegion} />;
  }

  const hoverRisk = hover ? byPostal.get(hover.postal) : undefined;

  return (
    <div className="flex flex-col gap-2">
      <div className="relative" style={{ height: MAP_HEIGHT }}>
        <div
          ref={containerRef}
          data-testid="map-view"
          role="group"
          aria-label="Risk by US state (choropleth)"
          style={{ position: "absolute", inset: 0, borderRadius: 8, overflow: "hidden" }}
          className="border border-navy/10"
        />
        {/* HTML overlay: 2-letter state labels at projected centroids. */}
        {glReady
          ? labels.map((l) => {
              const s = screen[l.postal];
              if (!s) return null;
              const risk = byPostal.get(l.postal);
              const dark = (risk ?? 0) >= 0.5;
              return (
                <span
                  key={l.postal}
                  aria-hidden
                  style={{ position: "absolute", left: s.x, top: s.y, transform: "translate(-50%,-50%)" }}
                  className={`pointer-events-none select-none text-[9px] font-bold leading-none ${dark ? "text-white" : "text-navy/80"}`}
                >
                  {l.postal}
                </span>
              );
            })
          : null}
        {/* Hover tooltip */}
        {glReady && hover ? (
          <div
            style={{ position: "absolute", left: hover.x + 10, top: hover.y + 10 }}
            className="pointer-events-none rounded bg-navy px-2 py-1 text-[11px] font-semibold text-white shadow-lg"
          >
            {hover.postal}: {risk(hoverRisk)}
          </div>
        ) : null}
        {!glReady ? (
          <div className="absolute inset-0 overflow-auto rounded border border-navy/10 bg-white p-2">
            <FallbackGrid features={features} selectedRegion={selectedRegion} onSelectRegion={onSelectRegion} compact />
          </div>
        ) : null}
      </div>
      <MapLegend />
    </div>
  );
}

function risk(v: number | undefined): string {
  return v === undefined ? "no data" : formatRisk(v);
}

/**
 * Plain-language explanation of the neutral-grey "No data" band, surfaced in a
 * small (i) tooltip beside the legend instead of verbose inline legend text.
 */
const NO_DATA_INFO =
  "Grey = No data: not enough FSIS sampling to produce a defensible estimate for this state and pathogen in this view. Coverage varies by pathogen and by Predicted vs Observed view.";

/**
 * Accessible info marker (copied from the PanelShell/SectionCard idiom): shows
 * `text` on hover and keyboard focus. Kept local so the map does not invent a
 * new tooltip mechanism.
 */
function MapInfoDot({ text }: { text: string }) {
  return (
    <span className="group relative inline-flex">
      <button
        type="button"
        data-testid="map-info"
        aria-label="What does grey mean on this map?"
        className="flex h-4 w-4 items-center justify-center rounded-full border border-navy/30 text-[10px] font-bold text-navy/60 hover:bg-navy/5 focus:outline-none focus:ring-2 focus:ring-teal"
      >
        i
      </button>
      <span
        role="tooltip"
        className="pointer-events-none absolute left-0 bottom-6 z-30 w-64 rounded-lg border border-navy/10 bg-navy px-3 py-2 text-[11px] leading-relaxed text-white opacity-0 shadow-lg transition group-hover:opacity-100 group-focus-within:opacity-100"
      >
        {text}
      </span>
    </span>
  );
}

/**
 * Discrete, named risk-band legend (teal ramp + neutral grey for no-data). Each
 * row is a small color swatch + the band name, sharing the single-source
 * {@link RISK_BANDS} so the legend and the choropleth bucket identically. The
 * "No data" band keeps only its grey swatch; its explanation lives in the
 * adjacent (i) tooltip rather than as verbose inline text.
 */
function MapLegend() {
  return (
    <div
      data-testid="map-legend"
      className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11px] text-navy/70"
      aria-label="Risk band legend"
    >
      {RISK_BANDS.map((band) => (
        <span key={band.label} className="inline-flex items-center gap-1.5">
          <span
            aria-hidden
            className="inline-block h-3 w-3 rounded-sm border border-navy/10"
            style={{ backgroundColor: band.color }}
          />
          <span>{band.label}</span>
        </span>
      ))}
      <MapInfoDot text={NO_DATA_INFO} />
    </div>
  );
}

function FallbackGrid({
  features, selectedRegion, onSelectRegion, compact = false,
}: MapViewProps & { compact?: boolean }) {
  const ordered = [...features].sort((a, b) => b.risk - a.risk);
  const cell = (r: number, sel: boolean): CSSProperties => ({
    backgroundColor: colorForRisk(r),
    outline: sel ? "2px solid #0f2742" : "1px solid rgba(15,39,66,0.12)",
  });
  return (
    <div data-testid="map-view" role="group" aria-label="Risk by region"
      className={`grid gap-2 ${compact ? "grid-cols-3 sm:grid-cols-4" : "grid-cols-2 sm:grid-cols-3"}`}>
      {ordered.map((f) => (
        <button key={`${f.pathogen}:${f.region}`} type="button" data-testid="map-region" data-region={f.region}
          aria-pressed={f.region === selectedRegion} onClick={() => onSelectRegion(f.region)}
          style={cell(f.risk, f.region === selectedRegion)}
          className="flex flex-col items-start rounded px-2 py-1.5 text-left transition focus:outline-none focus:ring-2 focus:ring-teal">
          <span className="text-[11px] font-semibold text-navy">{f.region}</span>
          <span className="text-[10px] text-navy/80">risk {formatRisk(f.risk)}</span>
        </button>
      ))}
    </div>
  );
}

export default MapView;
