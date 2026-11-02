import { useMemo, useState } from "react";
import { useArtifact } from "../../data/hooks";
import type { HumanOutbreakComparison } from "../../types/artifacts";
import { formatNumber, formatRisk } from "../../types/viewModels";
import EmptyState from "../EmptyState";
import PanelShell, { ArtifactBody } from "./PanelShell";

/**
 * One Health Insights (S05) - the SIGNAL-VALIDATION page. It stress-tests the
 * FSIS food-surveillance signal the rest of the app is built on by placing it
 * beside an INDEPENDENT system: CDC NORS human foodborne-outbreak reports, per
 * pathogen x state x year. STRICTLY corroboration: NORS is modeled available
 * ~365 days after the event and is never used to predict FSIS; no same-strain
 * link, no food-to-illness causation, no sub-state/county human estimate. All
 * numbers come from the one_health_human_comparison artifact.
 */

const PATHOGENS = ["Salmonella", "Listeria", "STEC"] as const;
type Pathogen = (typeof PATHOGENS)[number];

/** Small accessible info marker (hover/focus), reused idiom; navy/teal only. */
function InfoDot({ text }: { text: string }) {
  return (
    <span className="group relative inline-flex align-middle">
      <button
        type="button"
        aria-label="More info"
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

export function OneHealthInsights() {
  const state = useArtifact<HumanOutbreakComparison[]>("one_health_human_comparison");
  const [pathogen, setPathogen] = useState<Pathogen>("Salmonella");
  const [region, setRegion] = useState<string>("");

  return (
    <div className="mx-auto max-w-7xl px-6 py-6">
      <section className="mb-6 overflow-hidden rounded-2xl bg-gradient-to-br from-navy via-navy-600 to-teal-600 px-6 py-10 text-white">
        <span className="inline-block rounded-full bg-white/10 px-3 py-1 text-xs font-semibold text-teal-500 ring-1 ring-white/20">
          One Health - does the signal hold up?
        </span>
        <h1 className="mt-4 text-3xl font-extrabold tracking-tight sm:text-4xl">One Health &amp; Data</h1>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-white/80">
          Every other view trusts the FSIS food-testing signal. Here we stress-test it: we place that
          signal beside an INDEPENDENT system - CDC NORS human foodborne-outbreak reports - per state and
          year. If the two move together, the food signal has real-world corroboration. They never prove
          one caused the other.
        </p>
      </section>

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

      <div className="mb-5 rounded-lg border border-teal/30 bg-teal/5 px-4 py-3 text-[11px] leading-relaxed text-navy/80">
        <span className="font-semibold text-teal-700">Corroboration, not causation.</span>{" "}
        The FSIS line (food testing) and the CDC bars (human outbreaks) are two independent surveillance
        systems. Seeing them move together - or apart - is context, not proof that contaminated food caused
        an outbreak or vice versa. CDC outbreak data is reported with a long delay (modeled here as ~365
        days), so it is never used to predict the food-testing signal. Geography is state-level only; no
        county or individual human estimate is produced.
      </div>

      <PanelShell
        title={`${pathogen} - FSIS food surveillance vs. CDC human outbreaks`}
        subtitle="One Health corroboration - state x year - CDC lagged ~365 days"
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
  nors_hospitalizations: number | null;
  nors_deaths: number | null;
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
  const scope = region ? available.filter((r) => r.region === region) : available;

  const series: YearPoint[] = useMemo(() => {
    const byYear = new Map<number, YearPoint>();
    for (const r of scope) {
      if (!/^\d+$/.test(r.period)) continue;
      const y = Number(r.period);
      const pt = byYear.get(y) ?? {
        year: y, fsis_positivity: null, fsis_sample_n: 0,
        nors_outbreaks: null, nors_illnesses: null,
        nors_hospitalizations: null, nors_deaths: null,
        coverage: r.coverage_status,
      };
      if (r.fsis_sample_n && r.fsis_positive_n != null) {
        const priorPos = (pt.fsis_positivity ?? 0) * pt.fsis_sample_n;
        pt.fsis_sample_n += r.fsis_sample_n;
        pt.fsis_positivity = pt.fsis_sample_n ? (priorPos + r.fsis_positive_n) / pt.fsis_sample_n : null;
      }
      if (r.nors_outbreak_count != null) pt.nors_outbreaks = (pt.nors_outbreaks ?? 0) + r.nors_outbreak_count;
      if (r.nors_illness_count != null) pt.nors_illnesses = (pt.nors_illnesses ?? 0) + r.nors_illness_count;
      if (r.nors_hospitalization_count != null) pt.nors_hospitalizations = (pt.nors_hospitalizations ?? 0) + r.nors_hospitalization_count;
      if (r.nors_death_count != null) pt.nors_deaths = (pt.nors_deaths ?? 0) + r.nors_death_count;
      if (r.coverage_status === "ok") pt.coverage = "ok";
      byYear.set(y, pt);
    }
    return Array.from(byYear.values()).sort((a, b) => a.year - b.year);
  }, [scope]);

  const leadLag = available.find((r) => r.lead_lag)?.lead_lag ?? null;
  const coverageLimited = available.some((r) => r.coverage_status === "coverage_limited");

  const norsTotals = useMemo(() => {
    const sum = (pick: (p: YearPoint) => number | null): number | null => {
      let acc: number | null = null;
      for (const p of series) { const v = pick(p); if (v != null) acc = (acc ?? 0) + v; }
      return acc;
    };
    return {
      outbreaks: sum((p) => p.nors_outbreaks),
      illnesses: sum((p) => p.nors_illnesses),
      hospitalizations: sum((p) => p.nors_hospitalizations),
      deaths: sum((p) => p.nors_deaths),
    };
  }, [series]);

  const years = series.map((p) => p.year);
  const yearRange = years.length ? `${years[0]}-${years[years.length - 1]}` : "n/a";
  const coveredYears = series.filter((p) => p.coverage === "ok").length;

  if (unavailable) {
    return <EmptyState title={`${pathogen} - not available`} detail={unavailable.unavailable_reason ?? "Comparison unavailable."} />;
  }
  if (available.length === 0 || series.length === 0) {
    return <EmptyState title="No comparison data for this pathogen" detail={`No overlapping FSIS/CDC cells for ${pathogen}.`} />;
  }

  return (
    <div className="flex flex-col gap-5">
      {/* GLANCE strip - frames the validation question with key stats */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <GlanceStat label="Overlap window" value={yearRange} sub={`${coveredYears} yr CDC-covered`} />
        <GlanceStat label="Outbreaks (scope)" value={norsTotals.outbreaks == null ? "N/A" : formatNumber(norsTotals.outbreaks, 0)} sub="CDC NORS, OBSERVED" />
        <GlanceStat label="Illnesses (scope)" value={norsTotals.illnesses == null ? "N/A" : formatNumber(norsTotals.illnesses, 0)} sub="CDC NORS, OBSERVED" />
        <MoveTogetherStat leadLag={leadLag} />
      </div>

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
            {regions.map((r) => (<option key={r} value={r}>{r}</option>))}
          </select>
        </label>
        <span className="flex items-center gap-1 rounded-full bg-teal/10 px-2 py-0.5 text-[10px] font-semibold text-teal-700">
          <span className="inline-block h-2 w-2 rounded-full bg-teal" /> FSIS food surveillance (OBSERVED)
        </span>
        <span className="flex items-center gap-1 rounded-full bg-navy/10 px-2 py-0.5 text-[10px] font-semibold text-navy/70">
          <span className="inline-block h-2 w-2 rounded-full bg-navy" /> CDC human outbreaks (OBSERVED, lagged)
        </span>
        {coverageLimited ? (
          <span className="rounded-full bg-slate-200 px-2 py-0.5 text-[10px] font-semibold text-slate-600">coverage limited</span>
        ) : null}
        <InfoDot text="CDC NORS outbreak reports are modeled as available ~365 days after the event year, so they are never used to predict the FSIS food signal. A coverage-limited scope shows N/A rather than a fabricated zero." />
      </div>

      <DualTimeline series={series} />

      {/* OBSERVED CDC NORS human-impact context */}
      <div className="rounded-lg border border-navy/10 bg-white p-4" data-testid="nors-human-impact">
        <h3 className="mb-1 flex items-center gap-1.5 text-sm font-bold text-navy">
          Observed human-impact context (CDC NORS)
          <InfoDot text="Reported CDC NORS outbreak outcomes summed across the selected scope and overlap window. Corroboration context only - never a prediction and never causally linked to the food-positivity signal." />
        </h3>
        <p className="mb-3 text-[11px] leading-relaxed text-navy/60">
          Reported outbreak outcomes across the selected scope and overlap window. Shown as corroboration context, not a prediction.
        </p>
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <NorsStat label="Outbreaks" value={norsTotals.outbreaks} testid="nors-outbreaks" tone="muted" />
          <NorsStat label="Illnesses" value={norsTotals.illnesses} testid="nors-illnesses" tone="muted" />
          <NorsStat label="Hospitalizations" value={norsTotals.hospitalizations} testid="nors-hospitalizations" tone="strong" />
          <NorsStat label="Deaths" value={norsTotals.deaths} testid="nors-deaths" tone="strong" />
        </dl>
        <p className="mt-3 text-[10px] italic leading-relaxed text-navy/50">
          Observed CDC NORS outbreak outcomes (hospitalizations and deaths among outbreak-associated
          illnesses) - corroboration only, not causally linked to the food-positivity signal. A
          coverage-limited scope shows N/A rather than a fabricated zero.
        </p>
      </div>

      {/* Exploratory lead-lag */}
      <div className="rounded-lg border border-navy/10 bg-white p-4">
        <h3 className="mb-1 flex items-center gap-1.5 text-sm font-bold text-navy">
          Exploratory lead-lag (descriptive only)
          <InfoDot text="A single descriptive correlation between the two annual series at the best-fitting year offset. Computed with a permutation p-value and bootstrap interval on ~a decade of annual points. It is exploratory and descriptive, never a prediction or a causal claim." />
        </h3>
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
              {leadLag.note} This is a correlation on roughly a decade of annual points - it does not
              establish that either signal predicts or causes the other.
            </span>
          </p>
        ) : (
          <p className="text-[11px] italic text-navy/60">
            Not computed for this pathogen - human-outbreak coverage is too limited to support even an
            exploratory correlation. Shown as descriptive context only.
          </p>
        )}
      </div>

      <p className="text-[10px] italic text-navy/50">
        OBSERVED USDA FSIS laboratory sampling (food/animal) and CDC NORS foodborne-outbreak reports
        (human), state x year, overlap window 2013-2023. CDC NORS is modeled as available ~365 days
        after the event year and is never used to predict FSIS. The two systems corroborate one
        another as One Health context; this is not evidence of a same-strain link or of food-to-illness
        causation, and no sub-state or individual human estimate is produced. Later FSIS years without a
        CDC counterpart are shown as not-available, never zero.
      </p>
    </div>
  );
}

/** A compact glance metric for the top strip. Navy/teal only. */
function GlanceStat({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="rounded-xl border border-navy/10 bg-white px-3 py-2.5">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-navy/50">{label}</p>
      <p className="mt-0.5 text-xl font-extrabold text-navy">{value}</p>
      <p className="text-[10px] text-navy/45">{sub}</p>
    </div>
  );
}

/** Honest "do they move together?" glance tile derived ONLY from the exploratory
 * lead-lag. Never implies prediction/causation; the strength bar encodes |r| and
 * the direction word encodes the sign, both explicitly flagged exploratory. */
function MoveTogetherStat({ leadLag }: { leadLag: HumanOutbreakComparison["lead_lag"] }) {
  if (!leadLag || leadLag.correlation == null) {
    return <GlanceStat label="Signals move together?" value="N/A" sub="coverage too limited" />;
  }
  const r = leadLag.correlation;
  const mag = Math.min(1, Math.abs(r));
  const dir = r > 0.05 ? "same direction" : r < -0.05 ? "opposite direction" : "little relation";
  const lagYears = leadLag.lag_years ?? 0;
  const lagWord = lagYears === 0 ? "same year" : `${Math.abs(lagYears)}-yr lag`;
  return (
    <div className="rounded-xl border border-teal/20 bg-teal/5 px-3 py-2.5">
      <p className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-teal-700">
        Signals move together?
        <InfoDot text="Derived only from the exploratory lead-lag correlation. Direction = sign of r, strength = |r|. Exploratory and descriptive - NOT a prediction and NOT a causal claim." />
      </p>
      <p className="mt-0.5 text-sm font-extrabold text-navy">{dir}</p>
      <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-navy/10" aria-hidden>
        <div className="h-full rounded-full bg-teal" style={{ width: `${Math.round(mag * 100)}%` }} />
      </div>
      <p className="mt-0.5 text-[10px] text-navy/45">r = {r.toFixed(2)} - {lagWord} - exploratory</p>
    </div>
  );
}

/** One OBSERVED CDC NORS outcome figure. Null (coverage-limited) renders as N/A,
 * never a fabricated zero. tone="strong" visually weights deaths/hospitalizations. */
function NorsStat({
  label,
  value,
  testid,
  tone = "muted",
}: {
  label: string;
  value: number | null;
  testid: string;
  tone?: "muted" | "strong";
}) {
  const strong = tone === "strong";
  return (
    <div className={`rounded-lg border px-3 py-2 ${strong ? "border-teal/30 bg-teal/5" : "border-navy/10 bg-navy/5"}`}>
      <dt className="text-[10px] font-semibold uppercase tracking-wide text-navy/50">{label}</dt>
      <dd className={`mt-0.5 font-bold text-navy ${strong ? "text-2xl" : "text-lg"}`} data-testid={testid}>
        {value == null ? "N/A" : formatNumber(value, 0)}
      </dd>
    </div>
  );
}

/** Dependency-free dual-axis timeline with hover: FSIS positivity (teal line) +
 * CDC outbreaks (navy bars). Hovering a year reveals exact OBSERVED values. */
function DualTimeline({ series }: { series: YearPoint[] }) {
  const [hoverYear, setHoverYear] = useState<number | null>(null);
  const W = 760;
  const H = 260;
  const padX = 48;
  const padY = 24;
  const maxFsis = Math.max(...series.map((p) => p.fsis_positivity ?? 0), 0.01);
  const maxNors = Math.max(...series.map((p) => p.nors_outbreaks ?? 0), 1);
  const n = series.length;
  const x = (i: number) => (n <= 1 ? padX : padX + (i * (W - 2 * padX)) / (n - 1));
  const yF = (v: number) => H - padY - (v / maxFsis) * (H - 2 * padY);
  const yN = (v: number) => H - padY - (v / maxNors) * (H - 2 * padY);
  const barW = Math.max(6, (W - 2 * padX) / Math.max(n, 1) * 0.5);
  const hovered = hoverYear == null ? null : series.find((p) => p.year === hoverYear) ?? null;

  const fsisPath = series
    .map((p, i) => (p.fsis_positivity == null ? null : `${x(i)},${yF(p.fsis_positivity)}`))
    .filter(Boolean)
    .map((pt, i) => `${i === 0 ? "M" : "L"}${pt}`)
    .join(" ");

  return (
    <div className="rounded-lg border border-navy/10 bg-white p-4">
      <div className="relative">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="FSIS positivity vs CDC outbreaks annual timeline">
          {/* horizontal gridlines */}
          {[0.25, 0.5, 0.75, 1].map((f) => (
            <line key={f} x1={padX} x2={W - padX} y1={padY + f * (H - 2 * padY)} y2={padY + f * (H - 2 * padY)} stroke="#0f2742" strokeWidth={0.5} opacity={0.08} />
          ))}
          {/* axis titles */}
          <text x={6} y={padY - 8} fontSize="9" fill="#0d9488" fontWeight="bold">FSIS %</text>
          <text x={W - padX + 6} y={padY - 8} fontSize="9" fill="#1e3a5f" fontWeight="bold" textAnchor="end">CDC #</text>
          {/* CDC bars / coverage bands / zero ticks + hover hit-areas */}
          {series.map((p, i) => {
            const cx = x(i);
            const isHover = p.year === hoverYear;
            const bar = p.nors_outbreaks == null ? (
              <rect key={`g${p.year}`} x={cx - barW / 2} y={padY} width={barW} height={H - 2 * padY} fill="#94a3b8" opacity={0.1} />
            ) : p.nors_outbreaks === 0 ? (
              <line key={`z${p.year}`} x1={cx - barW / 2} x2={cx + barW / 2} y1={H - padY} y2={H - padY} stroke="#0f172a" strokeWidth={2} opacity={0.35} />
            ) : (
              <rect key={`b${p.year}`} x={cx - barW / 2} y={yN(p.nors_outbreaks)} width={barW} height={Math.max(0, H - padY - yN(p.nors_outbreaks))} fill="#1e3a5f" opacity={isHover ? 1 : 0.8} />
            );
            return (
              <g key={`col${p.year}`}>
                {bar}
                <rect
                  x={cx - (W - 2 * padX) / Math.max(n, 1) / 2}
                  y={padY}
                  width={(W - 2 * padX) / Math.max(n, 1)}
                  height={H - 2 * padY}
                  fill="transparent"
                  onMouseEnter={() => setHoverYear(p.year)}
                  onMouseLeave={() => setHoverYear(null)}
                  style={{ cursor: "pointer" }}
                />
              </g>
            );
          })}
          {/* FSIS positivity line + points */}
          <path d={fsisPath} fill="none" stroke="#0d9488" strokeWidth={2} />
          {series.map((p, i) =>
            p.fsis_positivity == null ? null : (
              <circle key={`c${p.year}`} cx={x(i)} cy={yF(p.fsis_positivity)} r={p.year === hoverYear ? 4 : 2.5} fill="#0d9488" />
            ),
          )}
          {/* hover guide line */}
          {hovered ? (
            <line x1={x(series.indexOf(hovered))} x2={x(series.indexOf(hovered))} y1={padY} y2={H - padY} stroke="#0f2742" strokeWidth={1} opacity={0.25} />
          ) : null}
          {/* year axis labels (sparse) */}
          {series.map((p, i) =>
            i % Math.ceil(n / 8) === 0 ? (
              <text key={`t${p.year}`} x={x(i)} y={H - 4} fontSize="9" textAnchor="middle" fill="#64748b">{p.year}</text>
            ) : null,
          )}
        </svg>
        {hovered ? (
          <div className="pointer-events-none absolute left-1/2 top-0 -translate-x-1/2 rounded-lg border border-navy/10 bg-navy px-3 py-2 text-[11px] text-white shadow-lg">
            <span className="font-bold">{hovered.year}</span>
            <span className="ml-2 text-teal-300">FSIS {hovered.fsis_positivity == null ? "N/A" : formatRisk(hovered.fsis_positivity)}</span>
            <span className="ml-1 text-white/60">(n={formatNumber(hovered.fsis_sample_n, 0)})</span>
            <span className="ml-2">CDC {hovered.nors_outbreaks == null ? "no coverage" : `${hovered.nors_outbreaks} outbreak${hovered.nors_outbreaks === 1 ? "" : "s"}`}</span>
            {hovered.nors_illnesses != null ? <span className="ml-1 text-white/70">- {formatNumber(hovered.nors_illnesses, 0)} ill</span> : null}
          </div>
        ) : null}
      </div>
      <div className="mt-1 flex items-center justify-between text-[10px] text-navy/50">
        <span className="text-teal-700">FSIS positivity (left axis, max {formatRisk(maxFsis)})</span>
        <span className="text-navy/60">CDC outbreaks (right axis, max {maxNors})</span>
      </div>
      <p className="mt-1 text-[10px] italic text-navy/40">
        Hover a year for exact values. A bar = outbreaks reported that year; a baseline tick = zero
        outbreaks reported (CDC covered, none occurred); a faint grey band = CDC coverage
        limited/unavailable that year. A missing bar is never fabricated data.
      </p>
    </div>
  );
}

export default OneHealthInsights;
