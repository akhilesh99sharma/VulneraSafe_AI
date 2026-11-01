import { useState } from "react";
import { useArtifact, useManifest } from "../../data/hooks";
import { useSelection } from "../../state/selection";
import type {
  AttentionQueueItem,
  ObservedPositivityFeature,
  ProvenanceEntry,
  RiskMapFeature,
} from "../../types/artifacts";
import {
  filterAttentionByPathogen,
  filterMapByPathogen,
  formatRisk,
  formatUncertainty,
  NOT_AVAILABLE,
} from "../../types/viewModels";
import {
  PageHeader,
  ControlBar,
  ControlGroup,
  PathogenPills,
  StatCard,
  StatCardRow,
  SectionCard,
  TwoColumn,
} from "../ui";
import EmptyState from "../EmptyState";
import StatusLegend from "../legend/StatusLegend";
import CurrentRiskOverview, { type MapViewMode } from "./CurrentRiskOverview";
import AttentionQueue from "./AttentionQueue";
import { colorForRisk, riskBandLabel } from "./charts/riskBands";

/**
 * Risk Dashboard (UI redesign, step 2).
 *
 * Recomposes the existing mandatory panels into a professional dashboard
 * layout built entirely from the step-1 UI primitives:
 *   1. navy-gradient {@link PageHeader} with a data-freshness status chip
 *   2. a single {@link ControlBar} of pathogen pills (driving the shared
 *      {@link useSelection} selection) + a small lens select
 *   3. a row of four KPI {@link StatCard}s
 *   4. {@link TwoColumn}: Current Risk Overview hero + a "Top states by risk"
 *      ranked table
 *   5. {@link TwoColumn}: the Attention Queue + a "Model evidence & data
 *      sources" rail (with the status legend)
 *
 * CRITICAL HONESTY CONSTRAINT: every KPI is derived from real loaded artifact
 * data (the `risk_map` + `attention_queue` artifacts, filtered to the selected
 * pathogen) or shown as N/A. No value is fabricated. In particular the
 * reference layout's "predicted national change" card is intentionally NOT
 * shown — a single national 4-week delta is not defensibly derivable — and is
 * replaced by the honestly-derivable "Highest-risk state".
 */

/** The three fallback pathogen pill options when the manifest is unavailable. */
const FALLBACK_PATHOGENS = ["Salmonella", "Listeria", "STEC"] as const;

/** Threshold at/above which a state counts as "elevated risk" (KPI 2). */
const ELEVATED_THRESHOLD = 0.5;

/** Bucket a mean 0..1 risk into an honest label + card tone. */
function riskBucket(mean: number | null): {
  label: string;
  tone: "default" | "alert" | "info" | "teal";
} {
  if (mean === null || Number.isNaN(mean)) {
    return { label: NOT_AVAILABLE, tone: "default" };
  }
  if (mean >= 0.66) return { label: "High", tone: "alert" };
  if (mean >= 0.33) return { label: "Moderate", tone: "info" };
  if (mean > 0) return { label: "Low", tone: "teal" };
  return { label: NOT_AVAILABLE, tone: "default" };
}

/** One honest, flat export row mirroring exactly what the dashboard shows. */
interface ExportRow {
  region: string;
  pathogen: string;
  period: string;
  view: "predicted" | "observed";
  value: number;
  value_label: "predicted_elevated_risk_probability" | "observed_positivity";
  uncertainty: string; // "" / "N/A" in observed mode (no model band)
  sample_n: string; // "" / "N/A" in predicted mode (no measured count)
  status: "PREDICTED" | "OBSERVED";
}

/** Ordered export columns (also the CSV header row). */
const EXPORT_COLUMNS: Array<keyof ExportRow> = [
  "region",
  "pathogen",
  "period",
  "view",
  "value",
  "value_label",
  "uncertainty",
  "sample_n",
  "status",
];

/**
 * Build export rows from exactly the states currently shown for the active
 * pathogen + view. Carries the honest per-row status/label; never fabricates
 * uncertainty (observed) or sample_n (predicted) — those cells are left blank
 * for the mode that lacks them.
 */
function buildExportRows(
  features: RiskMapFeature[],
  view: MapViewMode,
  sampleByKey: Map<string, number | null>,
): ExportRow[] {
  const observed = view === "observed";
  return features.map((f) => {
    const sample = observed ? sampleByKey.get(`${f.pathogen}:${f.region}`) : undefined;
    return {
      region: f.region,
      pathogen: f.pathogen,
      period: f.period,
      view,
      value: f.risk,
      value_label: observed ? "observed_positivity" : "predicted_elevated_risk_probability",
      uncertainty:
        observed || f.uncertainty === null || f.uncertainty === undefined || Number.isNaN(f.uncertainty)
          ? ""
          : String(f.uncertainty),
      sample_n: observed ? (sample === null || sample === undefined ? "" : String(sample)) : "",
      status: observed ? "OBSERVED" : "PREDICTED",
    };
  });
}

/** Escape one CSV field per RFC 4180 (quote when it contains , " or newline). */
function csvField(value: string | number): string {
  const s = String(value);
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function rowsToCsv(rows: ExportRow[]): string {
  const header = EXPORT_COLUMNS.join(",");
  const body = rows.map((r) => EXPORT_COLUMNS.map((c) => csvField(r[c])).join(","));
  return [header, ...body].join("\r\n");
}

/**
 * Trigger a client-side download via a Blob + temporary <a download>. Guards
 * against environments lacking URL.createObjectURL (older jsdom) so an export
 * click never throws in tests.
 */
function downloadFile(filename: string, mime: string, text: string): void {
  if (typeof URL === "undefined" || typeof URL.createObjectURL !== "function") return;
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  if (typeof URL.revokeObjectURL === "function") URL.revokeObjectURL(url);
}

export function RiskDashboard() {
  const { pathogen, region, setPathogen, setRegion } = useSelection();

  // Map "View" toggle: PREDICTED (default) shows the risk_map's predicted
  // next-period probability; OBSERVED shows the latest-period measured
  // positivity derived from risk_timeseries. These are DIFFERENT quantities,
  // clearly labeled — never the same number relabeled.
  const [mapViewMode, setMapViewMode] = useState<MapViewMode>("predicted");

  const manifest = useManifest();
  const mapState = useArtifact<RiskMapFeature[]>("risk_map");
  const observedState = useArtifact<ObservedPositivityFeature[]>("observed_positivity");
  const queueState = useArtifact<AttentionQueueItem[]>("attention_queue");
  const provenanceState = useArtifact<ProvenanceEntry[]>("provenance");

  // Pathogen pill options come from the manifest when available, else a
  // conservative fallback so the control is never empty.
  const pathogenOptions = manifest.data
    ? Object.keys(manifest.data.pathogens)
    : [...FALLBACK_PATHOGENS];
  // PathogenPills is a controlled single-value selector; map the shared
  // nullable selection onto the first option when nothing is chosen yet.
  const activePathogen = pathogen ?? pathogenOptions[0] ?? "";

  // --- KPI inputs: only READ from successfully-loaded artifacts ------------
  // While an artifact is still loading or errored, its features are treated as
  // absent so the affected card shows N/A rather than blocking the dashboard.
  //
  // The "View" toggle selects the ACTIVE quantity used by the map, the KPIs and
  // the top-states table so they stay consistent and honestly labeled:
  //   - predicted -> the raw risk_map features (the PREDICTED model probability).
  //   - observed  -> the NEW `observed_positivity` artifact: REAL MEASURED
  //                  routine positivity for each (pathogen, state)'s latest
  //                  measured period, mapped into the RiskMapFeature shape the
  //                  map/KPIs/top-states consume. These are two GENUINELY
  //                  different, honestly-labeled quantities — not one number
  //                  relabeled. `uncertainty` is null in observed mode (measured
  //                  positivity has no model uncertainty band) and surfaces as
  //                  N/A rather than a fabricated band.
  // Missing data in either view yields [] -> the cards/table show N/A honestly,
  // and states with no measured period simply do not appear ("No data").
  const predictedFeatures: RiskMapFeature[] =
    mapState.data && !mapState.error ? mapState.data : [];
  const observedFeatures: RiskMapFeature[] =
    observedState.data && !observedState.error
      ? observedState.data
          // Only genuinely measured rows map to a shaded region; a null rate is
          // omitted so the map renders it as a neutral "No data" region.
          .filter((o) => o.positivity !== null)
          .map((o) => ({
            region: o.region,
            pathogen: o.pathogen,
            period: o.period,
            risk: o.positivity as number,
            // Observed positivity carries no model uncertainty band — keep it
            // absent so the UI shows N/A (honest), never an invented interval.
            uncertainty: null as unknown as number,
            status: "OBSERVED" as const,
            data_freshness: o.period,
          }))
      : [];
  const mapFeatures: RiskMapFeature[] =
    mapViewMode === "observed" ? observedFeatures : predictedFeatures;

  // Observed-mode sample counts, keyed by `${pathogen}:${region}`, read straight
  // from the observed_positivity artifact. RiskMapFeature carries no sample_n,
  // so the top-states "Samples (n)" column (observed mode only) looks the real
  // measured count up here rather than fabricating one or widening the schema.
  const observedSampleByKey = new Map<string, number | null>();
  if (observedState.data && !observedState.error) {
    for (const o of observedState.data) {
      observedSampleByKey.set(`${o.pathogen}:${o.region}`, o.sample_n);
    }
  }

  const queueItems: AttentionQueueItem[] =
    queueState.data && !queueState.error ? queueState.data : [];

  const pathogenMap = filterMapByPathogen(mapFeatures, pathogen ?? activePathogen);

  // Region-keyed measured sample sizes for the ACTIVE pathogen, consumed by the
  // map's hover tooltip in observed mode. Derived from the same observed_positivity
  // lookup above so no count is fabricated; keyed by plain region code to match
  // the MapView `sampleByRegion` contract.
  const activePathogenName = pathogen ?? activePathogen;
  const sampleByRegion = new Map<string, number | null>();
  for (const [key, n] of observedSampleByKey) {
    const [p, r] = key.split(":");
    if (p === activePathogenName) sampleByRegion.set(r, n);
  }
  const pathogenQueue = filterAttentionByPathogen(
    queueItems,
    pathogen ?? activePathogen,
  );

  const n = pathogenMap.length;

  // KPI 1 — Current national risk: bucket of the MEAN risk across the selected
  // pathogen's map features. N/A when there are no features.
  const meanRisk =
    n > 0 ? pathogenMap.reduce((sum, f) => sum + f.risk, 0) / n : null;
  const bucket = riskBucket(meanRisk);

  // KPI 2 — States at elevated risk: count of features with risk >= 0.5.
  const elevatedCount =
    n > 0 ? pathogenMap.filter((f) => f.risk >= ELEVATED_THRESHOLD).length : null;

  // KPI 3 — Highest-risk state: the region with the max risk for the pathogen.
  // (Honest replacement for the reference "predicted change" card.)
  const highest =
    n > 0
      ? pathogenMap.reduce((best, f) => (f.risk > best.risk ? f : best), pathogenMap[0])
      : null;

  // KPI 4 — Attention items: count of queue items for the selected pathogen.
  // The artifact being missing/empty honestly yields 0 (no items), not a guess.
  const attentionCount =
    queueState.loading || queueState.error ? NOT_AVAILABLE : pathogenQueue.length;

  // Data-freshness chip: newest date in the manifest's data_freshness map.
  const freshness = manifest.data?.data_freshness ?? {};
  const freshnessDates = Object.values(freshness).filter(Boolean);
  const latestFreshness =
    freshnessDates.length > 0
      ? freshnessDates.slice().sort().slice(-1)[0]
      : null;

  // Top states by risk (right rail of row 4): top 10 features desc by risk.
  const topStates = [...pathogenMap].sort((a, b) => b.risk - a.risk).slice(0, 10);

  // Short word + longer phrase for the active quantity, used in honest captions
  // so predicted probability and observed positivity are never conflated.
  const quantityWord = mapViewMode === "observed" ? "observed" : "predicted";
  const quantityPhrase =
    mapViewMode === "observed"
      ? "observed positivity (latest measured period)"
      : "predicted next-period elevated-risk probability";

  // Export the states ACTUALLY shown (pathogenMap) for the active view, so the
  // file matches the screen exactly and carries the honest per-row label/status.
  const exportFileBase = `risk-dashboard_${activePathogenName}_${mapViewMode}`;
  const handleExport = (format: "csv" | "json") => {
    const rows = buildExportRows(pathogenMap, mapViewMode, observedSampleByKey);
    if (format === "csv") {
      downloadFile(`${exportFileBase}.csv`, "text/csv;charset=utf-8", rowsToCsv(rows));
    } else {
      downloadFile(`${exportFileBase}.json`, "application/json", JSON.stringify(rows, null, 2));
    }
  };

  return (
    <div data-testid="risk-dashboard" className="mx-auto flex max-w-7xl flex-col gap-4 px-6 py-6">
      <PageHeader
        title="Risk Dashboard"
        subtitle="Predicted surveillance risk and prioritized signals across states, derived only from observed surveillance and validated model output."
        breadcrumb={["Home", "Risk Dashboard"]}
        status={{
          label: latestFreshness ? "Data current" : "Freshness unavailable",
          detail: latestFreshness ? `as of ${latestFreshness}` : undefined,
          ok: Boolean(latestFreshness),
        }}
      />

      <ControlBar>
        <ControlGroup label="Pathogen">
          <PathogenPills
            value={activePathogen}
            onChange={(p) => setPathogen(p)}
            options={pathogenOptions}
          />
        </ControlGroup>
        <ControlGroup label="View">
          <MapViewToggle value={mapViewMode} onChange={setMapViewMode} />
        </ControlGroup>
        <ControlGroup label="Export">
          <ExportButtons
            disabled={pathogenMap.length === 0}
            onExport={handleExport}
          />
        </ControlGroup>
      </ControlBar>

      <StatCardRow>
        <StatCard
          label={mapViewMode === "observed" ? "Current national positivity" : "Current national risk"}
          value={bucket.label}
          sub={
            n > 0
              ? `${quantityWord} mean across ${n} state${n === 1 ? "" : "s"}`
              : `no ${quantityWord} states for this pathogen`
          }
          tone={bucket.tone}
        />
        <StatCard
          label={mapViewMode === "observed" ? "States at elevated positivity" : "States at elevated risk"}
          value={elevatedCount === null ? NOT_AVAILABLE : elevatedCount}
          sub={
            elevatedCount === null
              ? "no map features loaded"
              : `of ${n} state${n === 1 ? "" : "s"} (${quantityWord} \u2265 ${ELEVATED_THRESHOLD})`
          }
          tone={elevatedCount && elevatedCount > 0 ? "info" : "default"}
        />
        <StatCard
          label={mapViewMode === "observed" ? "Highest-positivity state" : "Highest-risk state"}
          value={highest ? highest.region : NOT_AVAILABLE}
          sub={highest ? formatRisk(highest.risk) : "no map features loaded"}
          tone="teal"
        />
        <StatCard
          label="Attention items"
          value={attentionCount}
          sub="ranked signals"
          tone="default"
        />
      </StatCardRow>

      <p data-testid="kpi-caption" className="text-[11px] leading-relaxed text-navy/50">
        These figures are derived from the {quantityPhrase} for the selected
        view ({mapViewMode === "observed" ? "OBSERVED" : "PREDICTED"}) and the
        prioritized attention queue. A single national &ldquo;predicted
        change&rdquo; delta is intentionally not shown because it is not a
        defensible single national figure; the highest-{quantityWord} state is
        shown instead because it is honestly derivable from the map.
      </p>

      <TwoColumn
        left={
          <CurrentRiskOverview
            className="h-full"
            view="map"
            features={mapFeatures}
            viewMode={mapViewMode}
            sampleByRegion={sampleByRegion}
          />
        }
        right={
          <div className="flex h-full flex-col gap-4">
          <SectionCard
            className="flex-1"
            title={mapViewMode === "observed" ? "Top states by positivity" : "Top states by risk"}
            subtitle={`Ranked for ${activePathogen} \u00b7 ${quantityPhrase}`}
            info={
              mapViewMode === "observed"
                ? "Positivity % = the measured share of FSIS food samples that tested positive for this pathogen in the latest reporting period (positive samples ÷ samples tested). An observed surveillance rate — not a forecast. These are the highest-positivity states for the selected pathogen; the pill shows the measured positivity, bucketed into a named band. Select a state to drive the map and the trend below."
                : "Risk % = the model's estimated probability that a state's FSIS food-sample positivity will be elevated above its own recent baseline next period. A prioritization signal — not a case count or a contamination finding. These are the highest-risk states for the selected pathogen, read directly from the risk map; the pill shows that PREDICTED probability, bucketed into a named band. Select a state to drive the map and the trend below."
            }
          >
            <div data-testid="top-states">
              {topStates.length === 0 ? (
                <EmptyState
                  title="No states to rank"
                  detail={`No risk-map features for ${activePathogen}.`}
                />
              ) : (
                <>
                <p
                  data-testid="top-states-definition"
                  className="mb-2 text-[11px] italic leading-relaxed text-navy/60"
                >
                  {mapViewMode === "observed"
                    ? "Positivity % = measured share of FSIS food samples that tested positive this period (positive \u00f7 tested). An observed rate, not a forecast."
                    : "Risk % = the model's estimated probability this state's positivity will be elevated above its own recent baseline next period. A prioritization signal, not a contamination finding."}
                </p>
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="text-[10px] uppercase tracking-wide text-navy/50">
                      <th className="py-2 pr-2 font-semibold">#</th>
                      <th className="py-2 pr-2 font-semibold">State</th>
                      <th className="py-2 pr-2 font-semibold">
                        {mapViewMode === "observed" ? "Positivity" : "Risk"}
                      </th>
                      <th className="py-2 font-semibold">
                        {mapViewMode === "observed" ? "Samples (n)" : "Uncertainty"}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {topStates.map((f, i) => {
                      const selected = f.region === region;
                      return (
                      <tr
                        key={`${f.region}:${f.period}`}
                        data-testid="top-state-row-tr"
                        data-selected={selected ? "true" : undefined}
                        aria-selected={selected}
                        className={`border-t border-navy/5 ${
                          selected ? "bg-teal/5 border-l-2 border-l-teal" : ""
                        }`}
                      >
                        <td className="py-2 pr-2 text-navy/60">{i + 1}</td>
                        <td className="py-2 pr-2">
                          <button
                            type="button"
                            data-testid="top-state-row"
                            data-region={f.region}
                            onClick={() => setRegion(f.region)}
                            className="font-semibold text-navy hover:text-teal-600 focus:outline-none focus:ring-2 focus:ring-teal"
                          >
                            {f.region}
                          </button>
                        </td>
                        <td className="py-2 pr-2">
                          <RiskPill risk={f.risk} />
                        </td>
                        <td className="py-2 text-navy/70" data-testid="top-state-third-col">
                          {mapViewMode === "observed"
                            ? ((): string => {
                                const nSamples = observedSampleByKey.get(
                                  `${f.pathogen}:${f.region}`,
                                );
                                return nSamples === null || nSamples === undefined
                                  ? NOT_AVAILABLE
                                  : nSamples.toLocaleString();
                              })()
                            : formatUncertainty(f.uncertainty)}
                        </td>
                      </tr>
                      );
                    })}
                  </tbody>
                </table>
                </>
              )}
            </div>
          </SectionCard>
          <SectionCard
            title="Legend"
            subtitle="How to read the tags and alert color"
          >
            <StatusLegend variant="bare" />
          </SectionCard>
          </div>
        }
      />

      <CurrentRiskOverview view="trend" />

      <TwoColumn
        left={<AttentionQueue ignoreLens />}
        right={
          <SectionCard
            className="h-full"
            title="Model evidence & data sources"
            subtitle="Where the numbers come from"
            info="The underlying data sources and their freshness, plus the key to the three provenance tags used across the dashboard."
          >
            <div data-testid="evidence-rail" className="flex flex-col gap-3">
              <EvidenceSources
                provenance={provenanceState.data && !provenanceState.error ? provenanceState.data : null}
                freshness={freshness}
              />
            </div>
          </SectionCard>
        }
      />
    </div>
  );
}

/**
 * The map "View" toggle: two pill buttons switching the map + KPIs + top-states
 * between the PREDICTED (default) and OBSERVED quantities. Teal-when-active /
 * navy-outline-when-inactive, matching the pathogen-pill idiom (theme
 * discipline: teal/navy only, Req 14.4). Controlled; no internal state.
 */
function MapViewToggle({
  value,
  onChange,
}: {
  value: MapViewMode;
  onChange: (v: MapViewMode) => void;
}) {
  const options: Array<{ mode: MapViewMode; label: string; testid: string }> = [
    { mode: "predicted", label: "Predicted", testid: "view-predicted" },
    { mode: "observed", label: "Observed", testid: "view-observed" },
  ];
  return (
    <div data-testid="map-view-toggle" className="flex gap-2">
      {options.map((o) => {
        const on = o.mode === value;
        return (
          <button
            key={o.mode}
            type="button"
            data-testid={o.testid}
            aria-pressed={on}
            onClick={() => onChange(o.mode)}
            className={`rounded-lg border px-4 py-2 text-sm font-semibold transition ${
              on
                ? "border-teal bg-teal text-white"
                : "border-navy/15 bg-white text-navy/70 hover:border-navy/30"
            }`}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

/**
 * The two download buttons. Each exports exactly the states currently shown for
 * the active pathogen + Predicted/Observed view, with honest per-row status and
 * labels. Real <button>s with aria-labels; teal/navy only (theme discipline).
 * Disabled (and visibly so) when there is nothing on screen to export.
 */
function ExportButtons({
  disabled,
  onExport,
}: {
  disabled: boolean;
  onExport: (format: "csv" | "json") => void;
}) {
  const base =
    "rounded-lg border px-3 py-2 text-sm font-semibold transition focus:outline-none focus:ring-2 focus:ring-teal";
  const enabled = "border-navy/15 bg-white text-navy/70 hover:border-navy/30";
  const off = "cursor-not-allowed border-navy/10 bg-navy/5 text-navy/30";
  return (
    <div data-testid="export-controls" className="flex gap-2">
      <button
        type="button"
        data-testid="export-csv"
        aria-label="Download the current view as CSV"
        disabled={disabled}
        onClick={() => onExport("csv")}
        className={`${base} ${disabled ? off : enabled}`}
      >
        Download CSV
      </button>
      <button
        type="button"
        data-testid="export-json"
        aria-label="Download the current view as JSON"
        disabled={disabled}
        onClick={() => onExport("json")}
        className={`${base} ${disabled ? off : enabled}`}
      >
        Download JSON
      </button>
    </div>
  );
}

/**
 * Color-coded risk pill for the top-states table. The background is the shared
 * teal-ramp color for the risk (single source of truth: {@link colorForRisk}),
 * the label is the honest percentage ({@link formatRisk}), and the accessible
 * name carries the named band so screen readers hear e.g. "Very high risk,
 * 80.0%". Text contrast mirrors the map's label rule (white at/above 0.5 risk,
 * navy below). Teal/navy only — no alert colors (theme discipline, Req 14.4).
 */
function RiskPill({ risk }: { risk: number }) {
  const dark = risk >= 0.5;
  return (
    <span
      className={`inline-flex items-center justify-center rounded-full px-2 py-0.5 text-[11px] font-semibold ${
        dark ? "text-white" : "text-navy"
      }`}
      style={{ backgroundColor: colorForRisk(risk) }}
      title={`${riskBandLabel(risk)} risk`}
      aria-label={`${riskBandLabel(risk)} risk, ${formatRisk(risk)}`}
    >
      {formatRisk(risk)}
    </span>
  );
}

/**
 * The compact source list for the evidence rail. Prefers the `provenance`
 * artifact (source name + access date); falls back to the manifest
 * `data_freshness` map; shows an honest note when neither is available.
 */
function EvidenceSources({
  provenance,
  freshness,
}: {
  provenance: ProvenanceEntry[] | null;
  freshness: Record<string, string>;
}) {
  if (provenance && provenance.length > 0) {
    return (
      <ul className="flex flex-col gap-2 text-xs">
        {provenance.map((p) => (
          <li key={p.source} className="flex items-start justify-between gap-2 border-b border-navy/5 pb-1.5">
            <span className="min-w-0">
              <span className="block truncate text-[13px] font-semibold text-navy">{p.source}</span>
              {p.license ? <span className="block text-[11px] text-navy/50">{p.license}</span> : null}
            </span>
            <span className="shrink-0 text-[11px] text-navy/60">{p.access_date || NOT_AVAILABLE}</span>
          </li>
        ))}
      </ul>
    );
  }

  const entries = Object.entries(freshness).filter(([, v]) => v);
  if (entries.length > 0) {
    return (
      <ul className="flex flex-col gap-2 text-xs">
        {entries.map(([source, date]) => (
          <li key={source} className="flex items-center justify-between gap-2 border-b border-navy/5 pb-1.5">
            <span className="truncate text-[13px] font-semibold text-navy">{source}</span>
            <span className="shrink-0 text-[11px] text-navy/60">{date}</span>
          </li>
        ))}
      </ul>
    );
  }

  return (
    <EmptyState
      title="Sources unavailable"
      detail="Neither the provenance artifact nor the manifest data-freshness map could be loaded."
    />
  );
}

export default RiskDashboard;
