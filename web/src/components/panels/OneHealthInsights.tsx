import { useMemo, useState } from "react";
import { useArtifact } from "../../data/hooks";
import type { HumanOutbreakComparison } from "../../types/artifacts";
import { formatRisk } from "../../types/viewModels";
import EmptyState from "../EmptyState";
import PanelShell, { ArtifactBody } from "./PanelShell";

/**
 * One Health Insights (S05). Shows FSIS food-surveillance positivity and CDC
 * NORS human foodborne-outbreak reports side by side, per pathogen x state x
 * year, STRICTLY as corroboration. NORS is modeled available ~365 days after the
 * event and is never used to predict FSIS. No same-strain link, no food-to-illness
 * causation, no sub-state/county human estimate. All numbers come from the
 * `one_health_human_comparison` artifact.
 */

const PATHOGENS = ["Salmonella", "Listeria", "STEC"] as const;
type Pathogen = (typeof PATHOGENS)[number];

export function OneHealthInsights() {
  const state = useArtifact<HumanOutbreakComparison[]>("one_health_human_comparison");
  const [pathogen, setPathogen] = useState<Pathogen>("Salmonella");
  const [region, setRegion] = useState<string>("");

  return (
    <div className="mx-auto max-w-7xl px-6 py-6">
      <section className="mb-6 overflow-hidden rounded-2xl bg-gradient-to-br from-navy via-navy-600 to-teal-600 px-6 py-10 text-white">
        <span className="inline-block rounded-full bg-white/10 px-3 py-1 text-xs font-semibold text-teal-500 ring-1 ring-white/20">
          One Health · Food surveillance meets human outbreaks
        </span>
        <h1 className="mt-4 text-3xl font-extrabold tracking-tight sm:text-4xl">One Health Insights</h1>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-white/80">
          FSIS food-surveillance positivity (food/animal domain) shown alongside CDC NORS human
          foodborne-outbreak reports (human domain), per state and year. These two systems
          corroborate one another as One Health context — they are never evidence that one caused
          the other.
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
                onClick={() => { setPathogen(p); setRegion(""); }}
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

      {/* No-causal-link explanation — prominent */}
      <div className="mb-5 rounded-lg border border-teal/30 bg-teal/5 px-4 py-3 text-[11px] leading-relaxed text-navy/80">
        <span className="font-semibold text-teal-700">Corroboration, not causation.</span>{" "}
        The FSIS line (food testing) and the CDC line (human outbreaks) are two independent
        surveillance systems. Seeing them move together — or apart — is context, not proof that
        contaminated food caused an outbreak or vice versa. CDC outbreak data is reported with a
        long delay (modeled here as ~365 days), so it is never used to predict the food-testing
        signal. Geography is state-level only; no county or individual human estimate is produced.
      </div>

      <PanelShell
        title={`${pathogen} — FSIS food surveillance vs. CDC human outbreaks`}
        subtitle="One Health corroboration · state × year · CDC lagged ~365 days"
        info="Two independent surveillance systems shown side by side as corroboration. Never a same-strain link, a causal claim, or a human case forecast. FSIS positivity is OBSERVED food surveillance; CDC counts are OBSERVED human outbreaks."
      >
        <ArtifactBody
          state={state}
          artifactName="one_health_human_comparison"
          isEmpty={(rows) => rows.length === 0}
          emptyTitle="No One Health comparison data available"
          emptyDetail="The one_health_human_comparison artifact is present but empty. Run: python -m src.analysis.human_comparison && python -m src.artifacts.exporter"
          render={(rows) => (
            <InsightsBody rows={rows} pathogen={pathogen} region={region} setRegion={setRegion} />
          )}
        />
      </PanelShell>
    </div>
  );
}

interface YearPoint {
  year: number;
  fsis_positivity: number | null;
  fsis_sample_n: number;
  nors_outbreaks: number | null;
  nors_illnesses: number | null;
  coverage: string;
}

function InsightsBody({
  rows,
  pathogen,
  region,
  setRegion,
}: {
  rows: HumanOutbreakComparison[];
  pathogen: Pathogen;
  region: string;
  setRegion: (r: string) => void;
}) {
  const forPathogen = useMemo(() => rows.filter((r) => r.pathogen === pathogen), [rows, pathogen]);
  const unavailable = forPathogen.find((r) => r.availability_status === "unavailable");
  const available = useMemo(
    () => forPathogen.filter((r) => r.availability_status === "available"),
    [forPathogen],
  );

  const regions = useMemo(
    () => Array.from(new Set(available.map((r) => r.region))).sort(),
    [available],
  );

  // Aggregate to a national (all-states) or single-state annual series.
  const scope = region ? available.filter((r) => r.region === region) : available;

  const series: YearPoint[] = useMemo(() => {
    const byYear = new Map<number, YearPoint>();
    for (const r of scope) {
      if (!/^\d+$/.test(r.period)) continue;
      const y = Number(r.period);
      const pt = byYear.get(y) ?? {
        year: y, fsis_positivity: null, fsis_sample_n: 0,
        nors_outbreaks: null, nors_illnesses: null, coverage: r.coverage_status,
      };
      // FSIS: weight positivity by sample_n to form a scope-level rate
      if (r.fsis_sample_n && r.fsis_positive_n != null) {
        const priorPos = (pt.fsis_positivity ?? 0) * pt.fsis_sample_n;
        pt.fsis_sample_n += r.fsis_sample_n;
        pt.fsis_positivity = pt.fsis_sample_n ? (priorPos + r.fsis_positive_n) / pt.fsis_sample_n : null;
      }
      // NORS: sum where present (null stays null until at least one real value)
      if (r.nors_outbreak_count != null) pt.nors_outbreaks = (pt.nors_outbreaks ?? 0) + r.nors_outbreak_count;
      if (r.nors_illness_count != null) pt.nors_illnesses = (pt.nors_illnesses ?? 0) + r.nors_illness_count;
      // a year is "covered" if ANY contributing cell had real NORS data (ok);
      // otherwise it stays coverage_limited / not-available.
      if (r.coverage_status === "ok") pt.coverage = "ok";
      byYear.set(y, pt);

    }
    return Array.from(byYear.values()).sort((a, b) => a.year - b.year);
  }, [scope]);

  const leadLag = available.find((r) => r.lead_lag)?.lead_lag ?? null;
  const coverageLimited = available.some((r) => r.coverage_status === "coverage_limited");

  if (unavailable) {
    return <EmptyState title={`${pathogen} — not available`} detail={unavailable.unavailable_reason ?? "Comparison unavailable."} />;
  }
  if (available.length === 0 || series.length === 0) {
    return <EmptyState title="No comparison data for this pathogen" detail={`No overlapping FSIS/CDC cells for ${pathogen}.`} />;
  }

  return (
    <div className="flex flex-col gap-5">
      {/* scope control + source badges */}
      <div className="flex flex-wrap items-center gap-3">
        <label className="text-[11px] font-semibold text-navy/60">
          Scope{" "}
          <select
            value={region}
            onChange={(e) => setRegion(e.target.value)}
            className="rounded border border-navy/20 bg-white px-2 py-1 text-xs text-navy focus:outline-none focus:ring-2 focus:ring-teal"
          >
            <option value="">All states (national)</option>
            {regions.map((r) => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
        </label>
        <span className="flex items-center gap-1 rounded-full bg-teal/10 px-2 py-0.5 text-[10px] font-semibold text-teal-700">
          <span className="inline-block h-2 w-2 rounded-full bg-teal" /> FSIS food surveillance (OBSERVED)
        </span>
        <span className="flex items-center gap-1 rounded-full bg-navy/10 px-2 py-0.5 text-[10px] font-semibold text-navy/70">
          <span className="inline-block h-2 w-2 rounded-full bg-navy" /> CDC human outbreaks (OBSERVED, lagged)
        </span>
        {coverageLimited ? (
          <span className="rounded-full bg-slate-200 px-2 py-0.5 text-[10px] font-semibold text-slate-600">
            coverage limited
          </span>
        ) : null}
      </div>

      <DualTimeline series={series} />

      {/* Exploratory lead-lag — shown modestly */}
      <div className="rounded-lg border border-navy/10 bg-white p-4">
        <h3 className="mb-1 text-sm font-bold text-navy">Exploratory lead–lag (descriptive only)</h3>
        {leadLag ? (
          <p className="text-[11px] leading-relaxed text-navy/70">
            Across national annual series, the strongest descriptive correlation was{" "}
            <span className="font-semibold text-navy">{leadLag.correlation?.toFixed(2)}</span> at a{" "}
            <span className="font-semibold text-navy">{leadLag.lag_years}-year</span> lag
            {leadLag.ci_low != null && leadLag.ci_high != null ? (
              <> (95% range {leadLag.ci_low.toFixed(2)} to {leadLag.ci_high.toFixed(2)})</>
            ) : null}
            , permutation p = {leadLag.p_value_permutation?.toFixed(3)}.{" "}
            <span className="italic text-navy/50">
              {leadLag.note} This is a correlation on roughly a decade of annual points — it does not
              establish that either signal predicts or causes the other.
            </span>
          </p>
        ) : (
          <p className="text-[11px] italic text-navy/60">
            Not computed for this pathogen — human-outbreak coverage is too limited to support even an
            exploratory correlation. Shown as descriptive context only.
          </p>
        )}
      </div>

      <p className="text-[10px] italic text-navy/50">
        OBSERVED USDA FSIS laboratory sampling (food/animal) and CDC NORS foodborne-outbreak reports
        (human), state × year, overlap window 2013–2023. CDC NORS is modeled as available ~365 days
        after the event year and is never used to predict FSIS. The two systems corroborate one
        another as One Health context; this is not evidence of a same-strain link or of food-to-illness
        causation, and no sub-state or individual human estimate is produced. Later FSIS years without a
        CDC counterpart are shown as not-available, never zero.
      </p>
    </div>
  );
}

/** Dependency-free dual-axis timeline: FSIS positivity (teal) + CDC outbreaks (navy bars). */
function DualTimeline({ series }: { series: YearPoint[] }) {
  const W = 680;
  const H = 180;
  const padX = 34;
  const padY = 16;
  const maxFsis = Math.max(...series.map((p) => p.fsis_positivity ?? 0), 0.01);
  const maxNors = Math.max(...series.map((p) => p.nors_outbreaks ?? 0), 1);
  const n = series.length;
  const x = (i: number) => (n <= 1 ? padX : padX + (i * (W - 2 * padX)) / (n - 1));
  const yF = (v: number) => H - padY - (v / maxFsis) * (H - 2 * padY);
  const yN = (v: number) => H - padY - (v / maxNors) * (H - 2 * padY);
  const barW = Math.max(4, (W - 2 * padX) / Math.max(n, 1) * 0.5);

  const fsisPath = series
    .map((p, i) => (p.fsis_positivity == null ? null : `${x(i)},${yF(p.fsis_positivity)}`))
    .filter(Boolean)
    .map((pt, i) => `${i === 0 ? "M" : "L"}${pt}`)
    .join(" ");

  return (
    <div className="rounded-lg border border-navy/10 bg-white p-4">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="FSIS vs CDC annual timeline">
        {/* CDC: coverage-limited years get a faint grey band; true-zero years get
            a baseline tick; years with outbreaks get a bar. */}
        {series.map((p, i) => {
          const cx = x(i);
          if (p.nors_outbreaks == null) {
            // no CDC coverage this year -> faint hatched band
            return (
              <rect
                key={`g${p.year}`}
                x={cx - barW / 2}
                y={padY}
                width={barW}
                height={H - 2 * padY}
                fill="#94a3b8"
                opacity={0.1}
              />
            );
          }
          if (p.nors_outbreaks === 0) {
            // true zero reported -> short baseline tick (not an empty gap)
            return (
              <line
                key={`z${p.year}`}
                x1={cx - barW / 2}
                x2={cx + barW / 2}
                y1={H - padY}
                y2={H - padY}
                stroke="#0f172a"
                strokeWidth={2}
                opacity={0.35}
              />
            );
          }
          return (
            <rect
              key={`b${p.year}`}
              x={cx - barW / 2}
              y={yN(p.nors_outbreaks)}
              width={barW}
              height={Math.max(0, H - padY - yN(p.nors_outbreaks))}
              fill="#1e3a5f"
              opacity={0.8}
            />
          );

        })}

        {/* FSIS positivity line (teal) */}
        <path d={fsisPath} fill="none" stroke="#0d9488" strokeWidth={1.75} />
        {series.map((p, i) =>
          p.fsis_positivity == null ? null : (
            <circle key={`c${p.year}`} cx={x(i)} cy={yF(p.fsis_positivity)} r={2.5} fill="#0d9488" />
          ),
        )}
        {/* year axis labels (sparse) */}
        {series.map((p, i) =>
          i % Math.ceil(n / 6) === 0 ? (
            <text key={`t${p.year}`} x={x(i)} y={H - 2} fontSize="9" textAnchor="middle" fill="#64748b">
              {p.year}
            </text>
          ) : null,
        )}
      </svg>
      <div className="mt-1 flex items-center justify-between text-[10px] text-navy/50">
        <span className="text-teal-700">— FSIS positivity (left, max {formatRisk(maxFsis)})</span>
        <span className="text-navy/60">▪ CDC outbreaks (right, max {maxNors})</span>
      </div>
      <p className="mt-1 text-[10px] italic text-navy/40">
        A bar = outbreaks reported that year; a baseline tick = zero outbreaks reported (CDC covered,
        none occurred); a faint grey band = CDC coverage limited/unavailable that year. A missing bar is
        never fabricated data.
      </p>

    </div>
  );
}

export default OneHealthInsights;
