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

/** Rough centroid of a GeoJSON Polygon/MultiPolygon outer rings (lng,lat). */
function centroidOf(geom: any): [number, number] | null {
  let x = 0, y = 0, n = 0;
  const addRing = (ring: number[][]) => { for (const [lng, lat] of ring) { x += lng; y += lat; n++; } };
  if (!geom) return null;
  if (geom.type === "Polygon") geom.coordinates.forEach((r: number[][]) => addRing(r));
  else if (geom.type === "MultiPolygon") geom.coordinates.forEach((poly: number[][][]) => poly.forEach((r) => addRing(r)));
  return n ? [x / n, y / n] : null;
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
 * Discrete, named risk-band legend (teal ramp + neutral grey for no-data). Each
 * row is a small color swatch + the band name, sharing the single-source
 * {@link RISK_BANDS} so the legend and the choropleth bucket identically.
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
