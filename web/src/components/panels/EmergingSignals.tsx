import { useMemo, useState } from "react";
import { useArtifact } from "../../data/hooks";
import type { EmergingRiskStratum } from "../../types/artifacts";
import { formatRisk } from "../../types/viewModels";
import StatusTag from "../StatusTag";
import EmptyState from "../EmptyState";
import PanelShell, { ArtifactBody } from "./PanelShell";

/**
 * Emerging Signals (S04). For each pathogen it shows OBSERVED state-by-quarter
 * positivity with a leakage-safe trailing baseline, and distinguishes:
 *   - PERSISTENT: states that have sat above their own trailing band for a large
 *     fraction of their history (chronic elevation);
 *   - EMERGING: a state-quarter flagged as a statistically unusual increase vs.
 *     its prior-only expected band (retrospective, OBSERVED — never a forecast).
 * Geography is SAMPLING LOCATION only. Every number comes from the
 * `emerging_risk` artifact; no fabricated values. A forecast is shown only if it
 * beat a naive baseline — in the current data none did, so this is a
 * retrospective view with stated uncertainty.
 */

const PATHOGENS = ["Salmonella", "Listeria", "STEC"] as const;
type Pathogen = (typeof PATHOGENS)[number];

type View = "persistent" | "emerging";

/** One state's ordered period rows, plus its persistence score. */
interface StateSeries {
  region: string;
  persistent_score: number | null;
  rows: EmergingRiskStratum[]; // ordered by period_start
}

function groupByState(rows: EmergingRiskStratum[]): StateSeries[] {
  const byState = new Map<string, EmergingRiskStratum[]>();
  for (const r of rows) {
    if (r.availability_status !== "available") continue;
    const arr = byState.get(r.region) ?? [];
    arr.push(r);
    byState.set(r.region, arr);
  }
  const out: StateSeries[] = [];
  for (const [region, arr] of byState) {
    arr.sort((a, b) => a.period_start.localeCompare(b.period_start));
    out.push({
      region,
      persistent_score: arr[0]?.persistent_score ?? null,
      rows: arr,
    });
  }
  return out;
}

export function EmergingSignals() {
  const state = useArtifact<EmergingRiskStratum[]>("emerging_risk");
  const [pathogen, setPathogen] = useState<Pathogen>("Salmonella");
  const [view, setView] = useState<View>("persistent");

  return (
    <div className="mx-auto max-w-7xl px-6 py-6">
      <section className="mb-6 overflow-hidden rounded-2xl bg-gradient-to-br from-navy via-navy-600 to-teal-600 px-6 py-10 text-white">
        <span className="inline-block rounded-full bg-white/10 px-3 py-1 text-xs font-semibold text-teal-500 ring-1 ring-white/20">
          Persistent vs. emerging · Retrospective surveillance signals
        </span>
        <h1 className="mt-4 text-3xl font-extrabold tracking-tight sm:text-4xl">Emerging Signals</h1>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-white/80">
          Tell apart long-standing elevation (persistent) from a statistically unusual new
          increase (emerging), per US state and quarter. These are OBSERVED historical
          surveillance signals with stated uncertainty — never a forecast, and never a claim
          that a product is contaminated.
        </p>
      </section>

      {/* Pathogen selector */}
      <div className="mb-4">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-navy/60">Select a pathogen</p>
        <div className="flex flex-wrap gap-2">
          {PATHOGENS.map((p) => {
            const on = p === pathogen;
            return (
              <button
                key={p}
                type="button"
                aria-pressed={on}
                onClick={() => setPathogen(p)}
                className={`rounded-lg border px-4 py-2 text-sm font-semibold transition ${
                  on ? "border-teal bg-teal text-white" : "border-navy/15 bg-white text-navy/70 hover:border-navy/30"
                }`}
              >
                {p === "STEC" ? "STEC (E. coli)" : p}
              </button>
            );
          })}
        </div>
      </div>

      {/* How to read this */}
      <div className="mb-5 rounded-lg border border-navy/10 bg-surface-muted px-4 py-3 text-[11px] leading-relaxed text-navy/70">
        <span className="font-semibold text-navy">How to read this:</span>{" "}
        <span className="font-semibold">Persistent</span> means a state's positivity sat above its own
        trailing expected band for a large share of its history — a chronic, long-standing level.{" "}
        <span className="font-semibold">Emerging</span> means a single quarter rose above the band computed
        only from that state's earlier quarters — a retrospective flag of an unusual increase, decided using
        only information available in or before that quarter.{" "}
        <span className="italic">Geography is the sampling (establishment) location, not where a product was
        sold or where anyone became ill.</span> State-quarters with fewer than 30 tests are shown as
        low-support and are never treated as "normal".
        <span className="mt-1 block text-navy/60">
          <span className="font-semibold text-navy">Not the Dashboard:</span> the Dashboard shows forward-looking,
          model-driven operational risk and recommended actions. This page is backward-looking only — a
          model-free read of the historical surveillance record, telling long-standing problems apart from new
          spikes.
        </span>
      </div>


      <PanelShell
        title={`${pathogen} — ${view === "persistent" ? "persistent elevation" : "emerging signals"}`}
        subtitle="OBSERVED FSIS surveillance · state × quarter · 95% likely range"
        info="Positivity per state and quarter with a leakage-safe trailing baseline. Persistent = chronic elevation over the window; emerging = a retrospective unusual-increase flag using only prior data. Never a forecast."
        accessory={
          <div className="flex items-center gap-1 text-[10px]">
            <span className="text-navy/40">View:</span>
            <button
              type="button"
              onClick={() => setView("persistent")}
              aria-pressed={view === "persistent"}
              className={`rounded px-2 py-0.5 font-semibold transition ${
                view === "persistent" ? "bg-navy text-white" : "border border-navy/20 text-navy/60"
              }`}
            >
              Persistent
            </button>
            <button
              type="button"
              onClick={() => setView("emerging")}
              aria-pressed={view === "emerging"}
              className={`rounded px-2 py-0.5 font-semibold transition ${
                view === "emerging" ? "bg-navy text-white" : "border border-navy/20 text-navy/60"
              }`}
            >
              Emerging
            </button>
          </div>
        }
      >
        <ArtifactBody
          state={state}
          artifactName="emerging_risk"
          isEmpty={(rows) => rows.length === 0}
          emptyTitle="No emerging-risk data available"
          emptyDetail="The emerging_risk artifact is present but empty. Run: python -m src.analysis.emerging_risk && python -m src.artifacts.exporter"
          render={(rows) => <SignalsBody rows={rows} pathogen={pathogen} view={view} />}
        />
      </PanelShell>
    </div>
  );
}

function SignalsBody({
  rows,
  pathogen,
  view,
}: {
  rows: EmergingRiskStratum[];
  pathogen: Pathogen;
  view: View;
}) {
  const forPathogen = useMemo(() => rows.filter((r) => r.pathogen === pathogen), [rows, pathogen]);

  const unavailable = forPathogen.find((r) => r.availability_status === "unavailable");
  const series = useMemo(() => groupByState(forPathogen), [forPathogen]);

  // All periods present (for the scrubber), ascending.
  const allPeriods = useMemo(() => {
    const s = new Set<string>();
    for (const r of forPathogen) if (r.availability_status === "available") s.add(r.period);
    return Array.from(s).sort();
  }, [forPathogen]);

  const [periodIdx, setPeriodIdx] = useState(allPeriods.length - 1);
  const safeIdx = Math.min(Math.max(0, periodIdx), Math.max(0, allPeriods.length - 1));
  const period = allPeriods[safeIdx];

  // Prospective status (same for all rows of a pathogen).
  const prospectiveStatus = forPathogen[0]?.prospective_status ?? "not_attempted";
  const prospectiveEval = forPathogen.find((r) => r.prospective_eval)?.prospective_eval ?? null;

  const [selectedState, setSelectedState] = useState<string | null>(null);

  if (unavailable) {
    return (
      <EmptyState
        title={`${pathogen} — not available`}
        detail={unavailable.unavailable_reason ?? "Series unavailable for this pathogen."}
      />
    );
  }
  if (series.length === 0 || allPeriods.length === 0) {
    return <EmptyState title="No data for this pathogen" detail={`No state-quarter series recorded for ${pathogen}.`} />;
  }

  const years = forPathogen[0]?.fiscal_years ?? [];
  const yearLabel = years.length ? `${years[0]}–${years[years.length - 1]}` : "—";

  // Persistent view: rank states by persistent_score (nulls = insufficient history, shown separately).
  const scored = series.filter((s) => s.persistent_score !== null);
  const unscored = series.filter((s) => s.persistent_score === null);
  const rankedPersistent = [...scored].sort((a, b) => (b.persistent_score ?? 0) - (a.persistent_score ?? 0));

  // Emerging view: states with a retrospective anomaly in the scrubbed period
  // (only information available in or before that period is used for the flag).
  const emergingRows = forPathogen
    .filter((r) => r.period === period && r.retro_anomaly === true)
    .sort((a, b) => (b.value ?? 0) - (a.value ?? 0));

  const activeState =
    selectedState ??
    (view === "emerging" ? emergingRows[0]?.region : undefined) ??
    rankedPersistent[0]?.region ??
    series[0].region;

  const activeSeries = series.find((s) => s.region === activeState) ?? null;

  return (
    <div className="flex flex-col gap-5">
      {/* Prospective-forecast honesty banner */}
      {prospectiveStatus !== "validated" ? (
        <div className="rounded-lg border border-navy/10 bg-surface-muted px-4 py-3 text-[11px] leading-relaxed text-navy/70">
          <span className="font-semibold text-navy">No forward-looking forecast is shown.</span>{" "}
          A one-quarter-ahead anomaly forecast was tested and did not beat a naive persistence
          baseline{prospectiveEval
            ? ` (precision ${formatRisk(prospectiveEval.precision)}, recall ${formatRisk(prospectiveEval.recall)})`
            : ""}
          , so no PREDICTED alerts are presented. This panel is retrospective only — an honest
          description of the past with stated uncertainty.
        </div>
      ) : null}

      {view === "persistent" ? (
        <PersistentList ranked={rankedPersistent} unscored={unscored} onSelect={(s) => setSelectedState(s)} activeState={activeState} />
      ) : (
        <EmergingList rows={emergingRows} period={period} onSelect={(s) => setSelectedState(s)} activeState={activeState} />
      )}


      {/* Time scrubber */}
      <div className="rounded-lg border border-navy/10 bg-white p-4">
        <div className="mb-2 flex items-center justify-between gap-2">
          <h3 className="text-sm font-bold text-navy">Time scrubber</h3>
          <span className="text-[11px] font-semibold text-navy">
            {period}{" "}
            <span className="font-normal text-navy/40">
              ({safeIdx + 1} of {allPeriods.length})
            </span>
          </span>
        </div>
        <input
          type="range"
          min={0}
          max={allPeriods.length - 1}
          value={safeIdx}
          onChange={(e) => setPeriodIdx(Number(e.target.value))}
          aria-label="Select quarter"
          className="w-full accent-teal"
        />
        <p className="mt-1 text-[10px] italic text-navy/50">
          The emerging view reflects only information available in or before the selected quarter —
          anomaly flags never peek at the future.
        </p>
      </div>

      {/* Trend for the active state */}
      {activeSeries ? (
        <TrendCard series={activeSeries} selectedPeriod={period} yearLabel={yearLabel} />
      ) : null}

      <p className="text-[10px] italic text-navy/50">
        OBSERVED USDA FSIS establishment sampling, state × quarter, fiscal years {yearLabel}. Positivity =
        positive ÷ valid diagnostic tests; non-diagnostic excluded. Baseline and anomaly flags use only
        prior-quarter data (leakage-safe). FSIS establishment geography is a sampling site, never a consumer
        or infection location. Retrospective surveillance signal, not a forecast or contamination claim.
        Full-screen multi-map views are added with the Multi-Map Explorer page.
      </p>
    </div>
  );
}

function PersistentList({
  ranked,
  unscored,
  onSelect,
  activeState,
}: {
  ranked: StateSeries[];
  unscored: StateSeries[];
  onSelect: (region: string) => void;
  activeState: string;
}) {
  const max = Math.max(...ranked.map((s) => s.persistent_score ?? 0), 0.0001);
  const top = ranked.slice(0, 15);
  return (
    <div className="rounded-lg border border-navy/10 bg-white p-4">
      <div className="mb-1 flex items-center justify-between gap-2">
        <h3 className="text-sm font-bold text-navy">Most persistently elevated states</h3>
        <span className="text-[10px] text-navy/40">{ranked.length} states scored</span>
      </div>
      <p className="mb-3 text-[11px] text-navy/50">
        Share of a state's gradeable quarters that sat above its own trailing expected band. Select a
        state to see its trend below.
      </p>
      <ul className="flex flex-col gap-2">
        {top.map((s) => {
          const on = s.region === activeState;
          return (
            <li key={s.region}>
              <button
                type="button"
                onClick={() => onSelect(s.region)}
                aria-pressed={on}
                className={`grid w-full grid-cols-[3rem,1fr,3rem] items-center gap-x-3 rounded-md px-2 py-1 text-left transition ${
                  on ? "bg-teal/10 ring-1 ring-teal/40" : "hover:bg-surface-muted"
                }`}
              >
                <span className="text-xs font-bold text-navy">{s.region}</span>
                <span className="h-2 w-full overflow-hidden rounded-full bg-navy/10" aria-hidden>
                  <span
                    className="block h-full rounded-full bg-teal"
                    style={{ width: `${Math.min(100, ((s.persistent_score ?? 0) / max) * 100)}%` }}
                  />
                </span>
                <span className="text-right text-xs font-semibold text-navy">
                  {formatRisk(s.persistent_score)}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      {unscored.length > 0 ? (
        <p className="mt-3 border-t border-navy/5 pt-2 text-[10px] italic text-navy/40">
          {unscored.length} state(s) had too few gradeable quarters to score and are not ranked
          (insufficient history), rather than shown as zero.
        </p>
      ) : null}
    </div>
  );
}

function EmergingList({
  rows,
  period,
  onSelect,
  activeState,
}: {
  rows: EmergingRiskStratum[];
  period: string;
  onSelect: (region: string) => void;
  activeState: string;
}) {
  if (rows.length === 0) {
    return (
      <div className="rounded-lg border border-navy/10 bg-white p-4">
        <h3 className="text-sm font-bold text-navy">Emerging signals in {period}</h3>
        <p className="mt-1 text-xs italic text-navy/60">
          No state showed a statistically unusual increase in {period} (using only data available by then).
        </p>
      </div>
    );
  }
  return (
    <div className="rounded-lg border border-navy/10 bg-white p-4">
      <div className="mb-1 flex items-center justify-between gap-2">
        <h3 className="text-sm font-bold text-navy">Emerging signals in {period}</h3>
        <span className="text-[10px] text-navy/40">{rows.length} flagged</span>
      </div>
      <p className="mb-3 text-[11px] text-navy/50">
        States whose positivity rose above their prior-only expected band this quarter. Retrospective and
        OBSERVED — not a prediction. Select a state to see its trend below.
      </p>
      <ul className="flex flex-col gap-2">
        {rows.map((r) => {
          const on = r.region === activeState;
          return (
            <li key={r.region}>
              <button
                type="button"
                onClick={() => onSelect(r.region)}
                aria-pressed={on}
                className={`grid w-full grid-cols-[3rem,1fr,auto] items-center gap-x-3 rounded-md px-2 py-1 text-left transition ${
                  on ? "bg-teal/10 ring-1 ring-teal/40" : "hover:bg-surface-muted"
                }`}
              >
                <span className="text-xs font-bold text-navy">{r.region}</span>
                <span className="text-[11px] text-navy/60">
                  {formatRisk(r.value)} observed{" "}
                  <span className="text-navy/40">
                    (expected ≤ {formatRisk(r.retro_threshold)}; {r.positive_n}/{r.sample_n} positive)
                  </span>
                </span>
                <span className="rounded-full bg-orange-500/15 px-2 py-0.5 text-[10px] font-bold text-orange-700">
                  emerging
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}


/** Minimal dependency-free SVG trend of positivity with the baseline band. */
function TrendCard({
  series,
  selectedPeriod,
  yearLabel,
}: {
  series: StateSeries;
  selectedPeriod: string;
  yearLabel: string;
}) {
  const rows = series.rows;
  const W = 640;
  const H = 120;
  const pad = 6;
  const maxY = Math.max(
    ...rows.map((r) => Math.max(r.value ?? 0, r.baseline_high ?? 0)),
    0.01,
  );
  const x = (i: number) => (rows.length <= 1 ? pad : pad + (i * (W - 2 * pad)) / (rows.length - 1));
  const y = (v: number) => H - pad - (v / maxY) * (H - 2 * pad);

  const valuePath = rows
    .map((r, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(r.value ?? 0).toFixed(1)}`)
    .join(" ");

  return (
    <div className="rounded-lg border border-navy/10 bg-white p-4">
      <div className="mb-1 flex items-center justify-between gap-2">
        <h3 className="text-sm font-bold text-navy">
          {series.region} — quarterly positivity trend
        </h3>
        <div className="flex items-center gap-2">
          <StatusTag status="OBSERVED" />
          <span className="text-[10px] text-navy/40">FY {yearLabel}</span>
        </div>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={`${series.region} positivity trend`}>
        {/* anomaly + selected-period markers */}
        {rows.map((r, i) => {
          const isSel = r.period === selectedPeriod;
          const isAnom = r.retro_anomaly === true;
          const low = r.support_status === "low_support";
          return (
            <g key={r.period}>
              {isSel ? (
                <line x1={x(i)} y1={pad} x2={x(i)} y2={H - pad} stroke="#0d9488" strokeWidth={1} strokeDasharray="3 3" />
              ) : null}
              <circle
                cx={x(i)}
                cy={y(r.value ?? 0)}
                r={isAnom ? 3.5 : 2}
                fill={isAnom ? "#ea580c" : low ? "#cbd5e1" : "#0f172a"}
              />
            </g>
          );
        })}
        <path d={valuePath} fill="none" stroke="#0f172a" strokeWidth={1.25} />
      </svg>
      <div className="mt-1 flex items-center justify-between text-[10px] text-navy/50">
        <span>{rows[0]?.period}</span>
        <span className="flex items-center gap-3">
          <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full bg-orange-500" /> emerging</span>
          <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full bg-slate-300" /> low support</span>
        </span>
        <span>{rows[rows.length - 1]?.period}</span>
      </div>
    </div>
  );
}

export default EmergingSignals;
