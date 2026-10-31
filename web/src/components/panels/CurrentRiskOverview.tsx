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

export function CurrentRiskOverview() {
  const { pathogen, region, setRegion } = useSelection();
  const mapState = useArtifact<RiskMapFeature[]>("risk_map");
  const tsState = useArtifact<RiskTimeseriesPoint[]>("risk_timeseries");

  // The status tag reflects the nature of the map values; read verbatim off the
  // artifact record (never invented). Absent until the first feature loads.
  const first = mapState.data?.[0];
  const headerStatus = first ? statusOf(first) : null;

  return (
    <PanelShell
      title="Current Risk Overview"
      subtitle="Geographic surveillance risk + historical trend"
      info="Each state is shaded by its PREDICTED probability of elevated pathogen surveillance positivity next period (teal = higher). This is a prioritization signal, not a contamination finding. Click a state to see its risk over time with a 95% uncertainty band."
      className="lg:col-span-2"
      accessory={headerStatus ? <StatusTag status={headerStatus} /> : null}
    >
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

          return (
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <div>
                <MapLabel
                  pathogen={pathogen ?? sample.pathogen}
                  geography={geography}
                  period={sample.period}
                  status={labelStatus}
                  uncertainty={formatUncertainty(sample.uncertainty)}
                  dataFreshness={sample.data_freshness}
                />
                <MapView
                  features={visible}
                  selectedRegion={region}
                  onSelectRegion={setRegion}
                />
              </div>

              <div>
                <TimeSeriesSection
                  state={tsState}
                  region={region}
                  pathogen={pathogen}
                />
              </div>
            </div>
          );
        }}
      />
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
}: {
  state: ReturnType<typeof useArtifact<RiskTimeseriesPoint[]>>;
  region: string | null;
  pathogen: string | null;
}) {
  return (
    <ArtifactBody
      state={state}
      artifactName="risk_timeseries"
      isEmpty={(p) => p.length === 0}
      emptyTitle="No time-series data available"
      emptyDetail="The risk_timeseries artifact is present but contains no points."
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
              Showing {resolution} reporting periods for {effectivePathogen}.
            </p>
            <TimeSeries
              points={series}
              ariaLabel={`Risk time-series for region ${region}, ${effectivePathogen}`}
            />
          </div>
        );
      }}
    />
  );
}

export default CurrentRiskOverview;
