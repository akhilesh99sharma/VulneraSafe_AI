import { useArtifact } from "../../data/hooks";
import { useSelection } from "../../state/selection";
import type { RiskMapFeature, RiskTimeseriesPoint } from "../../types/artifacts";
import {
  filterMapByPathogen,
  formatUncertainty,
  orNotAvailable,
  timeseriesForRegion,
} from "../../types/viewModels";
import { statusOf } from "../../types/status";
import EmptyState from "../EmptyState";
import MapLabel from "../MapLabel";
import StatusTag from "../StatusTag";
import PanelShell, { ArtifactBody } from "./PanelShell";
import MapView from "./charts/MapView";
import TimeSeries from "./charts/TimeSeries";

/**
 * Current Risk Overview (Req 12.1–12.3).
 *
 * Presents an interactive geography view (`MapView`) beside an interactive
 * time-series (`TimeSeries`), both driven by dated surveillance / validated
 * predictions from the `risk_map` and `risk_timeseries` artifacts. Selecting a
 * region updates the time-series (Req 12.2). When there is no dated data for
 * the selected region/range, an empty-state names the gap rather than drawing
 * a misleading empty chart (Req 12.3). The panel is labeled with the active
 * pathogen and period.
 */

/**
 * Which halves of the overview to render:
 *   - "full"  → map + time-series side by side (default, unchanged behavior)
 *   - "map"   → only the geographic map, full width
 *   - "trend" → only the time-series ("National Risk Trend"), full width
 *
 * The split modes let the dashboard promote the map to a full hero and move the
 * trend into its own full-width row, while every mode reuses the SAME inner map
 * and trend render logic below (no duplicated/divergent honesty logic).
 */
export type CurrentRiskView = "full" | "map" | "trend";

/** Which quantity the map is displaying (drives labels + captions). */
export type MapViewMode = "predicted" | "observed";

export interface CurrentRiskOverviewProps {
  view?: CurrentRiskView;
  /**
   * Optional injected map features. When provided, the map body renders these
   * instead of reading the `risk_map` artifact itself — this lets the dashboard
   * drive a Predicted/Observed toggle through one honest code path. When
   * omitted the component reads `risk_map` exactly as before (standalone use).
   */
  features?: RiskMapFeature[];
  /**
   * Which quantity the injected features represent. Defaults to "predicted".
   * Only meaningful together with `features`; it selects the honest captions.
   */
  viewMode?: MapViewMode;
  /**
   * Optional per-region measured sample size (keyed by plain region code), only
   * consulted by the map's hover tooltip in observed mode. Passed straight
   * through to {@link MapView}; never fabricated.
   */
  sampleByRegion?: Map<string, number | null>;
}

/** Human captions per view mode so predicted and observed are never conflated. */
const VIEW_COPY: Record<
  MapViewMode,
  { quantity: string; subtitle: string; title: string; definition: string }
> = {
  predicted: {
    quantity: "predicted next-period elevated-risk probability",
    subtitle: "Geographic surveillance risk",
    title: "Current Risk Overview",
    definition:
      "Risk % = the model's estimated probability that this state's FSIS food-sample positivity will be elevated above its own recent baseline next period. A prioritization signal — not a case count or a contamination finding.",
  },
  observed: {
    quantity: "observed positivity (latest measured period)",
    subtitle: "Geographic observed positivity",
    title: "Current Positivity Overview",
    definition:
      "Positivity % = the measured share of FSIS food samples that tested positive for this pathogen in the latest reporting period (positive samples ÷ samples tested). An observed surveillance rate — not a forecast.",
  },
};

export function CurrentRiskOverview({
  view = "full",
  features: injectedFeatures,
  viewMode = "predicted",
  sampleByRegion,
}: CurrentRiskOverviewProps) {
  const { pathogen, region, setRegion } = useSelection();
  const artifactMapState = useArtifact<RiskMapFeature[]>("risk_map");
  // The trend follows the Predicted/Observed toggle: in observed mode it reads
  // the OBSERVED positivity time-series (measured rate per state across ALL
  // periods, with a real Wilson band), otherwise the PREDICTED risk_timeseries.
  // Both share the RiskTimeseriesPoint shape so TimeSeriesSection is unchanged.
  const tsName = viewMode === "observed" ? "observed_timeseries" : "risk_timeseries";
  const tsState = useArtifact<RiskTimeseriesPoint[]>(tsName);

  // When the dashboard injects a feature list (Predicted/Observed toggle), wrap
  // it in a synthetic "loaded" artifact state so the SAME ArtifactBody render
  // path handles both. Otherwise fall back to reading the risk_map artifact.
  const mapState = injectedFeatures
    ? { data: injectedFeatures, loading: false, error: null }
    : artifactMapState;

  // The status tag reflects the nature of the map values; read verbatim off the
  // artifact record (never invented). Absent until the first feature loads.
  const first = mapState.data?.[0];
  const headerStatus = first ? statusOf(first) : null;

  // The map body (label + MapView). `layout` controls whether the inner grid
  // shows the trend beside the map ("full") or the map spans full width.
  const mapBody = (layout: "full" | "map") => (
    <ArtifactBody
      state={mapState}
      artifactName="risk_map"
      isEmpty={(f) => f.length === 0}
      emptyTitle="No risk-map data available"
      emptyDetail="The risk_map artifact is present but contains no regions."
      render={(features) => {
        const visible = filterMapByPathogen(features, pathogen);
        const activePathogen = orNotAvailable(pathogen ?? visible[0]?.pathogen);

        if (visible.length === 0) {
          return (
            <EmptyState
              title="No risk-map data for the selected pathogen"
              detail={`No regions carry ${activePathogen} risk for this view.`}
            />
          );
        }

        // Six mandatory map-label fields (Req 14.1), each read from the
        // artifact; any absent one becomes an explicit N/A (Req 14.2, 14.6).
        const sample = visible[0];
        // Geography: a selected region if one is chosen, else the set of
        // regions this map covers.
        const geography = region
          ? region
          : `${visible.length} region${visible.length === 1 ? "" : "s"}`;
        // Status read verbatim off the record — never invented (Req 14.3).
        const labelStatus = statusOf(sample);

        const mapPanel = (
          <div>
            <MapLabel
              pathogen={pathogen ?? sample.pathogen}
              geography={geography}
              period={sample.period}
              status={labelStatus}
              uncertainty={formatUncertainty(sample.uncertainty)}
              dataFreshness={sample.data_freshness}
            />
            <p
              data-testid="map-quantity-caption"
              className="mb-1 text-[11px] leading-relaxed text-navy/50"
            >
              Each state is shaded by its {VIEW_COPY[viewMode].quantity}.
            </p>
            <p
              data-testid="quantity-definition"
              className="mb-2 text-[11px] italic leading-relaxed text-navy/60"
            >
              {VIEW_COPY[viewMode].definition}
            </p>
            <MapView
              features={visible}
              selectedRegion={region}
              onSelectRegion={setRegion}
              viewMode={viewMode}
              sampleByRegion={sampleByRegion}
            />
          </div>
        );

        // "map" layout: the map fills the whole panel body.
        if (layout === "map") return mapPanel;

        // "full" layout: map beside the trend (historical behavior).
        return (
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {mapPanel}
            <div>
              <TimeSeriesSection
                state={tsState}
                region={region}
                pathogen={pathogen}
                viewMode={viewMode}
              />
            </div>
          </div>
        );
      }}
    />
  );

  if (view === "trend") {
    // Only the time-series, in its own panel. Region selection (shared
    // selection) still drives it; all empty-state gap messages are intact. The
    // title/subtitle/info follow the active view so the Observed trend never
    // reads as a PREDICTED forecast.
    const observed = viewMode === "observed";
    return (
      <PanelShell
        title={observed ? "National Positivity Trend" : "National Risk Trend"}
        subtitle={
          observed
            ? "Historical observed positivity for the selected region"
            : "Historical trend for the selected region"
        }
        info={
          observed
            ? "Observed positivity over time for the selected region: measured FSIS routine positivity across every reporting period that has real samples, with a 95% Wilson interval from the real counts. This is a measured surveillance rate, not a forecast and not a contamination finding."
            : "Risk over time for the region selected on the map, as a PREDICTED probability of elevated pathogen surveillance positivity with a 95% uncertainty band. This is a prioritization signal, not a contamination finding."
        }
      >
        <TimeSeriesSection
          state={tsState}
          region={region}
          pathogen={pathogen}
          viewMode={viewMode}
        />
      </PanelShell>
    );
  }

  const info =
    viewMode === "observed"
      ? "Each state is shaded by its OBSERVED positivity in the latest reporting period (teal = higher) — a measured surveillance rate, not a forecast and not a contamination finding. Click a state to see its risk over time with a 95% uncertainty band."
      : "Each state is shaded by its PREDICTED probability of elevated pathogen surveillance positivity next period (teal = higher). This is a prioritization signal, not a contamination finding. Click a state to see its risk over time with a 95% uncertainty band.";

  return (
    <PanelShell
      title={VIEW_COPY[viewMode].title}
      subtitle={
        view === "map"
          ? VIEW_COPY[viewMode].subtitle
          : `${VIEW_COPY[viewMode].subtitle} + historical trend`
      }
      info={info}
      className={view === "full" ? "lg:col-span-2" : undefined}
      accessory={headerStatus ? <StatusTag status={headerStatus} /> : null}
    >
      {mapBody(view === "map" ? "map" : "full")}
    </PanelShell>
  );
}

/**
 * Derive a stable default pathogen for a region's time-series so a single line
 * never mixes time resolutions when no pathogen is explicitly selected. Picks
 * the pathogen of the chronologically-first point for the region (points are
 * sorted by ISO period), falling back to the alphabetically-first pathogen
 * present for that region. Returns null when the region has no points at all.
 */
function defaultPathogenForRegion(
  points: RiskTimeseriesPoint[],
  region: string,
): string | null {
  const regional = points.filter((p) => p.region === region);
  if (regional.length === 0) return null;
  const sorted = [...regional].sort((a, b) => a.period.localeCompare(b.period));
  const firstPeriod = sorted[0].period;
  // Among the earliest period's points, prefer the alphabetically-first
  // pathogen so the default is deterministic regardless of input order.
  const earliest = sorted.filter((p) => p.period === firstPeriod);
  return earliest
    .map((p) => p.pathogen)
    .sort((a, b) => a.localeCompare(b))[0];
}

/**
 * The time-series half. Kept separate so its own loading/error/empty states
 * resolve independently of the map (graceful degradation within the panel).
 */
function TimeSeriesSection({
  state,
  region,
  pathogen,
  viewMode = "predicted",
}: {
  state: ReturnType<typeof useArtifact<RiskTimeseriesPoint[]>>;
  region: string | null;
  pathogen: string | null;
  viewMode?: MapViewMode;
}) {
  // Honest labels per view: observed = measured positivity with a real Wilson
  // band; predicted = elevated-risk probability with the display band.
  const observed = viewMode === "observed";
  const valueLabel = observed ? "Observed positivity" : "Predicted risk";
  const bandLabel = observed ? "95% Wilson interval" : "95% uncertainty";
  const yLabel = observed ? "Observed positivity" : "Elevated-risk probability";
  const artifactName = observed ? "observed_timeseries" : "risk_timeseries";
  return (
    <ArtifactBody
      state={state}
      artifactName={artifactName}
      isEmpty={(p) => p.length === 0}
      emptyTitle="No time-series data available"
      emptyDetail={`The ${artifactName} artifact is present but contains no points.`}
      render={(points) => {
        if (!region) {
          return (
            <EmptyState
              title="Select a region"
              detail="Choose a region on the map to see its risk over time."
            />
          );
        }
        // A single line must never mix time resolutions (monthly Salmonella vs
        // quarterly Listeria/STEC for the same region). So the series is always
        // scoped to exactly ONE pathogen. Use the explicit selection when set,
        // otherwise derive a stable default from the region's own data: the
        // pathogen of the chronologically-first point, falling back to the
        // alphabetically-first pathogen present for that region.
        const effectivePathogen = pathogen ?? defaultPathogenForRegion(points, region);

        if (!effectivePathogen) {
          // No points at all for this region -> name the gap (Req 12.3).
          return (
            <EmptyState
              title="No dated data for this selection"
              detail={`No surveillance or validated predictions for region "${region}" in the available range.`}
            />
          );
        }

        const series = timeseriesForRegion(points, region, effectivePathogen);
        if (series.length === 0) {
          // Req 12.3: name the specific gap for the selected region/pathogen.
          return (
            <EmptyState
              title="No dated data for this selection"
              detail={`No surveillance or validated predictions for region "${region}" and pathogen "${effectivePathogen}" in the available range.`}
            />
          );
        }
        // Read verbatim off the first point — series is non-empty here, and the
        // status is never invented (Req 14.3).
        const status = statusOf(series[0]);
        // Resolution is read from the period string: a "Q" marks a quarter,
        // otherwise the period is a month (e.g. "2024-05").
        const resolution = series[0].period.includes("Q") ? "quarterly" : "monthly";
        return (
          <div>
            <div className="mb-2 flex items-center justify-between">
              <p className="text-xs text-navy/70">
                Risk over time · region{" "}
                <span className="font-semibold">{region}</span> ·{" "}
                <span className="font-semibold">{effectivePathogen}</span>
              </p>
              <StatusTag status={status} />
            </div>
            <p className="mb-2 text-[11px] text-navy/50">
              Showing {resolution} {observed ? "measured positivity" : "reporting"} periods for {effectivePathogen}.
            </p>
            <TimeSeries
              points={series}
              ariaLabel={`${observed ? "Observed positivity" : "Risk"} time-series for region ${region}, ${effectivePathogen}`}
              valueLabel={valueLabel}
              bandLabel={bandLabel}
              yLabel={yLabel}
            />
          </div>
        );
      }}
    />
  );
}

export default CurrentRiskOverview;
