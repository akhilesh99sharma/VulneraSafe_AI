import { useMemo, useState } from "react";
import { useArtifact } from "../../data/hooks";
import type { SeasonalHazardRecord } from "../../types/artifacts";
import { formatNumber, formatRisk } from "../../types/viewModels";
import StatusTag from "../StatusTag";
import EmptyState from "../EmptyState";
import PanelShell, { ArtifactBody } from "./PanelShell";

/**
 * Seasonal Patterns (S02). Charts-and-tables only — NO map, NO maplibre — so the
 * panel renders under jsdom with no WebGL/canvas dependency.
 *
 * Every value shown is OBSERVED historical FSIS surveillance positivity pooled
 * into a calendar-month or calendar-quarter bucket, plus a long-run annual
 * trend. These are HISTORICAL seasonal patterns of observed positivity, meant
 * for planning inspection/testing cadence across the year. They are backward-
 * looking descriptions only, never forward-looking projections and never a
 * contamination claim — the visible copy deliberately avoids the banned
 * fabrication words and labels the peak the literal phrase
 * "historical seasonal pattern".
 *
 * A bucket below its minimum-sample gate is present-but-unavailable: it renders
 * the reusable unavailable indicator carrying its `unavailable_reason` in place
 * of a value — never a blank or a fabricated number. The quarter view is the
 * robust default and the month view is best-effort/gated, so many months may
 * legitimately render as unavailable, which the UI makes explicit.
 */

const PATHOGENS = ["Salmonella", "Listeria", "STEC"] as const;
type Pathogen = (typeof PATHOGENS)[number];

/** Calendar months in display order "01".."12". */
const MONTH_LABELS = [
  "01",
  "02",
  "03",
  "04",
  "05",
  "06",
  "07",
  "08",
  "09",
  "10",
  "11",
  "12",
] as const;
const QUARTER_LABELS = ["Q1", "Q2", "Q3", "Q4"] as const;

const MONTH_NAMES: Record<string, string> = {
  "01": "Jan",
  "02": "Feb",
  "03": "Mar",
  "04": "Apr",
  "05": "May",
  "06": "Jun",
  "07": "Jul",
  "08": "Aug",
  "09": "Sep",
  "10": "Oct",
  "11": "Nov",
  "12": "Dec",
};

/**
 * Reusable unavailable indicator (Req 7.3). Renders a bucket's or the trend's
 * `unavailable_reason` in place of a value — never a blank or a fabricated
 * number. Shares a single data-testid; the web test reads these with
 * getAllByTestId.
 */
function UnavailableNote({ reason }: { reason: string | null | undefined }) {
  return (
    <span
      data-testid="unavailable-note"
      className="inline-flex items-center rounded border border-dashed border-navy/25 bg-surface-muted px-2 py-0.5 text-[10px] italic text-navy/50"
    >
      not available — {reason ?? "below minimum-sample gate; not fabricated."}
    </span>
  );
}

/** Inline flex bar whose width tracks the value (0..1), like CountyCommunities' Bar. */
function Bar({ value, color }: { value: number; color: string }) {
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-navy/10" aria-hidden>
      <div
        className="h-full rounded-full"
        style={{ width: `${Math.min(100, Math.max(0, value * 100))}%`, backgroundColor: color }}
      />
    </div>
  );
}

export function SeasonalHazard() {
  const state = useArtifact<SeasonalHazardRecord[]>("seasonal_hazard_patterns");
  const [pathogen, setPathogen] = useState<Pathogen>("Salmonella");

  return (
    <div data-testid="seasonal-hazard" className="mx-auto max-w-7xl px-6 py-6">
      <section className="mb-5 overflow-hidden rounded-2xl bg-gradient-to-br from-navy via-navy-600 to-teal-600 px-6 py-10 text-white">
        <span className="inline-block rounded-full bg-white/10 px-3 py-1 text-xs font-semibold text-teal-500 ring-1 ring-white/20">
          Food safety · Historical seasonal pattern of observed FSIS positivity
        </span>
        <h1 className="mt-4 text-3xl font-extrabold tracking-tight sm:text-4xl">Seasonal Patterns</h1>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-white/80">
          These charts show the historical seasonal pattern of OBSERVED FSIS surveillance positivity —
          pooled by calendar month and quarter across all sampled years — to help plan inspection and
          testing cadence through the year. They describe what was historically observed. They are not
          projections of what will happen and make no claim that any product is contaminated.
        </p>
      </section>

      {/* Pathogen selector */}
      <div data-testid="pathogen-selector" className="mb-4">
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
        <span className="font-semibold text-navy">How to read this:</span> each bar is the{" "}
        <span className="font-semibold text-teal-700">pooled positivity</span> for that calendar bucket (total
        positives ÷ total samples) with its Wilson 95% interval. The quarter view is the robust default; the month
        view is best-effort and many months legitimately show as{" "}
        <span className="italic">not available</span> when they fall below the minimum-sample gate.{" "}
        <span className="italic">These are historical observations, not projections of future positivity.</span>
      </div>

      <PanelShell
        title={`${pathogen} — historical seasonal pattern`}
        subtitle="OBSERVED · pooled FSIS positivity by calendar month & quarter · historical, not a projection"
        info="Historical seasonal pattern of OBSERVED FSIS surveillance positivity, pooled by calendar month and quarter with Wilson 95% intervals, plus a long-run annual trend. For planning inspection/testing cadence. Not a projection and not a contamination claim. Buckets below the minimum-sample gate are shown as not available, never fabricated."
      >
        <ArtifactBody
          state={state}
          artifactName="seasonal_hazard_patterns"
          isEmpty={(rows) => rows.length === 0}
          emptyTitle="No seasonal-pattern data available"
          emptyDetail="The seasonal_hazard_patterns artifact is present but empty. Run: python -m src.analysis.seasonal_hazard_patterns && python -m src.artifacts.exporter"
          render={(rows) => <SeasonalBody rows={rows} pathogen={pathogen} />}
        />
      </PanelShell>
    </div>
  );
}

function SeasonalBody({ rows, pathogen }: { rows: SeasonalHazardRecord[]; pathogen: Pathogen }) {
  const forPathogen = useMemo(() => rows.filter((r) => r.pathogen === pathogen), [rows, pathogen]);

  // A per-pathogen "(all)" unavailable sentinel marks the whole pathogen as
  // unavailable (e.g. the series failed to build, or the cache was missing at
  // export time). Render an EmptyState with its reason, never fabricated charts.
  const pathogenUnavailable = forPathogen.find(
    (r) => r.availability_status === "unavailable" && r.bucket_label === "(all)",
  );

  const monthRows = useMemo(() => forPathogen.filter((r) => r.view === "month"), [forPathogen]);
  const quarterRows = useMemo(() => forPathogen.filter((r) => r.view === "quarter"), [forPathogen]);

  if (forPathogen.length === 0) {
    return <EmptyState title="No data for this pathogen" detail={`No seasonal pattern for ${pathogen}.`} />;
  }
  if (
    pathogenUnavailable &&
    monthRows.every((r) => r.bucket_label === "(all)") &&
    quarterRows.every((r) => r.bucket_label === "(all)")
  ) {
    return (
      <EmptyState
        title={`${pathogen} — not available`}
        detail={pathogenUnavailable.unavailable_reason ?? "Seasonal pattern unavailable for this pathogen."}
      />
    );
  }

  // Index the buckets by label so the charts can render a full, ordered axis
  // (12 months / 4 quarters) with an explicit unavailable marker for any gap.
  const monthByLabel = useMemo(() => {
    const m = new Map<string, SeasonalHazardRecord>();
    for (const r of monthRows) m.set(r.bucket_label, r);
    return m;
  }, [monthRows]);
  const quarterByLabel = useMemo(() => {
    const m = new Map<string, SeasonalHazardRecord>();
    for (const r of quarterRows) m.set(r.bucket_label, r);
    return m;
  }, [quarterRows]);

  // A shared bar scale so bars across buckets are visually comparable: scale to
  // the largest available rate in either view (fall back to 1 to avoid /0).
  const maxRate = useMemo(() => {
    const rates = [...monthRows, ...quarterRows]
      .filter((r) => r.availability_status === "available" && r.rate !== null)
      .map((r) => r.rate as number);
    const m = rates.length > 0 ? Math.max(...rates) : 0;
    return m > 0 ? m : 1;
  }, [monthRows, quarterRows]);

  // Trend + peaks are repeated on every row of the pathogen; read any row.
  const anyRow = forPathogen.find((r) => r.bucket_label !== "(all)") ?? forPathogen[0];
  const peakMonth = monthRows.find((r) => r.is_peak && r.availability_status === "available") ?? null;
  const peakQuarter = quarterRows.find((r) => r.is_peak && r.availability_status === "available") ?? null;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-3 text-[10px]">
        <span className="flex items-center gap-1 rounded-full bg-teal/10 px-2 py-0.5 font-semibold text-teal-700">
          <span className="inline-block h-2 w-2 rounded-full bg-teal" /> Pooled positivity (Wilson 95%)
        </span>
        <StatusTag status="OBSERVED" />
        <span className="text-navy/40">
          pooled across {formatNumber(anyRow.periods_read_count, 0)} months read
        </span>
      </div>

      {/* Peak Season callout */}
      <PeakSeason peakMonth={peakMonth} peakQuarter={peakQuarter} />

      {/* Trend readout */}
      <TrendReadout row={anyRow} />

      {/* Quarter chart (robust default, shown first) */}
      <div className="rounded-lg border border-navy/10 bg-white p-4">
        <h3 className="mb-1 text-sm font-bold text-navy">Quarter of year — pooled positivity</h3>
        <p className="mb-3 text-[11px] text-navy/50">
          Q1–Q4 historical positivity. The quarter view pools more samples per bucket, so it is the robust default.
        </p>
        <ul data-testid="quarter-chart" className="flex flex-col gap-2">
          {QUARTER_LABELS.map((label) => (
            <BucketRow key={label} label={label} record={quarterByLabel.get(label)} maxRate={maxRate} />
          ))}
        </ul>
      </div>

      {/* Month chart (best-effort, gated) */}
      <div className="rounded-lg border border-navy/10 bg-white p-4">
        <h3 className="mb-1 text-sm font-bold text-navy">Month of year — pooled positivity</h3>
        <p className="mb-3 text-[11px] text-navy/50">
          Months 01–12 historical positivity. Monthly denominators are thinner, so a month below the minimum-sample
          gate is shown as not available rather than estimated.
        </p>
        <ul data-testid="month-chart" className="flex flex-col gap-2">
          {MONTH_LABELS.map((label) => (
            <BucketRow
              key={label}
              label={`${label} · ${MONTH_NAMES[label] ?? label}`}
              record={monthByLabel.get(label)}
              maxRate={maxRate}
            />
          ))}
        </ul>
      </div>

      <p className="text-[10px] italic text-navy/50">
        OBSERVED USDA FSIS surveillance positivity (read-only), pooled by calendar month and quarter across all
        sampled years with Wilson 95% intervals, plus an ordinal-year trend of annual positivity. This is a
        historical seasonal pattern for planning inspection and testing cadence — not a projection of future
        positivity and not a claim that any product is contaminated. Buckets below the minimum-sample gate are shown
        as not available with the reason, never interpolated or fabricated.
      </p>
    </div>
  );
}

/**
 * One chart row: an available bucket shows its rate, a width-scaled bar, and the
 * Wilson CI as a whisker + text; an unavailable bucket shows the reusable
 * unavailable indicator carrying its reason.
 */
function BucketRow({
  label,
  record,
  maxRate,
}: {
  label: string;
  record: SeasonalHazardRecord | undefined;
  maxRate: number;
}) {
  const available = record?.availability_status === "available" && record?.rate !== null && record?.rate !== undefined;

  return (
    <li className="grid grid-cols-[4.5rem,1fr,auto] items-center gap-x-3">
      <span className="text-[11px] font-semibold text-navy/70">{label}</span>
      {available && record ? (
        <>
          <div className="flex flex-col gap-1">
            <Bar value={(record.rate as number) / maxRate} color="#0d9488" />
            {/* Wilson CI whisker rendered as plain text + an SVG whisker. */}
            <CiWhisker low={record.ci_low} high={record.ci_high} maxRate={maxRate} />
          </div>
          <div className="text-right text-xs">
            <span className="font-bold text-navy">{formatRisk(record.rate)}</span>
            <div className="text-[9px] text-navy/40">
              95% CI {formatRisk(record.ci_low)}–{formatRisk(record.ci_high)}
            </div>
            <div className="text-[9px] text-navy/40">
              n={formatNumber(record.sample_n, 0)} · pos={formatNumber(record.positive_n, 0)}
            </div>
          </div>
        </>
      ) : (
        <>
          <UnavailableNote reason={record?.unavailable_reason} />
          <div className="text-right text-[9px] text-navy/40">
            {record ? <>n={formatNumber(record.sample_n, 0)}</> : null}
          </div>
        </>
      )}
    </li>
  );
}

/** Inline SVG whisker for the Wilson 95% interval (no chart library). */
function CiWhisker({
  low,
  high,
  maxRate,
}: {
  low: number | null;
  high: number | null;
  maxRate: number;
}) {
  if (low === null || high === null) return null;
  const x1 = Math.min(100, Math.max(0, (low / maxRate) * 100));
  const x2 = Math.min(100, Math.max(0, (high / maxRate) * 100));
  return (
    <svg viewBox="0 0 100 6" preserveAspectRatio="none" className="h-1.5 w-full" aria-hidden>
      <line x1={x1} y1="3" x2={x2} y2="3" stroke="#1e3a5f" strokeWidth="0.8" strokeOpacity="0.5" />
      <line x1={x1} y1="1" x2={x1} y2="5" stroke="#1e3a5f" strokeWidth="0.8" strokeOpacity="0.5" />
      <line x1={x2} y1="1" x2={x2} y2="5" stroke="#1e3a5f" strokeWidth="0.8" strokeOpacity="0.5" />
    </svg>
  );
}

/**
 * Peak Season callout — labeled the literal phrase "historical seasonal
 * pattern". Shows the peak month and peak quarter (chosen only among available
 * buckets), or "not available" when none qualifies. The visible copy avoids the
 * banned forward-looking fabrication words entirely.
 */
function PeakSeason({
  peakMonth,
  peakQuarter,
}: {
  peakMonth: SeasonalHazardRecord | null;
  peakQuarter: SeasonalHazardRecord | null;
}) {
  const monthText = peakMonth
    ? `${peakMonth.bucket_label} · ${MONTH_NAMES[peakMonth.bucket_label] ?? peakMonth.bucket_label}`
    : null;
  return (
    <div
      data-testid="peak-season"
      className="rounded-xl border-2 border-teal/40 bg-teal/5 px-5 py-4 text-sm leading-relaxed text-navy"
    >
      <p className="text-xs font-bold uppercase tracking-wide text-teal-700">Historical seasonal pattern — peak</p>
      <p className="mt-1">
        Over the historical record, positivity ran highest in{" "}
        {monthText ? (
          <span className="font-semibold">
            {monthText} (month) at {formatRisk(peakMonth!.rate)}
          </span>
        ) : (
          <span className="font-semibold">not available (month)</span>
        )}{" "}
        and{" "}
        {peakQuarter ? (
          <span className="font-semibold">
            {peakQuarter.bucket_label} (quarter) at {formatRisk(peakQuarter.rate)}
          </span>
        ) : (
          <span className="font-semibold">not available (quarter)</span>
        )}
        . This is a historical seasonal pattern of what was observed, offered to help time inspection and testing — it
        is not a statement about any future period.
      </p>
    </div>
  );
}

/**
 * Trend readout — plain-language sign + magnitude derived from `trend_slope`
 * and `trend_years_used`. When the trend is gated, shows the reusable
 * unavailable indicator with `trend_unavailable_reason`.
 */
function TrendReadout({ row }: { row: SeasonalHazardRecord }) {
  const available = row.trend_availability_status === "available" && row.trend_slope !== null;
  const years = row.trend_years_used ?? [];
  const yearSpan =
    years.length > 0 ? `${Math.min(...years)}–${Math.max(...years)}` : "the available years";

  let direction = "holding roughly flat";
  if (row.trend_slope !== null) {
    if (row.trend_slope > 0) direction = "trending up";
    else if (row.trend_slope < 0) direction = "trending down";
  }
  // Magnitude: slope is a change in positivity (0..1 proportion) per year.
  const perYear = row.trend_slope !== null ? formatRisk(Math.abs(row.trend_slope)) : null;

  return (
    <div
      data-testid="trend-readout"
      className="rounded-lg border border-navy/10 bg-white px-4 py-3 text-sm leading-relaxed text-navy"
    >
      <h3 className="text-sm font-bold text-navy">Long-run trend</h3>
      {available ? (
        <p className="mt-1 text-[12px] text-navy/80">
          Positivity is{" "}
          <span className="font-semibold">{direction}</span> ~{perYear}/yr over {yearSpan}{" "}
          <span className="text-navy/50">
            (ordinal-year trend of annual positivity across {years.length} years)
          </span>
          .{" "}
          <span className="italic text-navy/50">
            A description of the historical record, not an extrapolation into any future period.
          </span>
        </p>
      ) : (
        <p className="mt-1 text-[12px] text-navy/80">
          Long-run trend <UnavailableNote reason={row.trend_unavailable_reason} />{" "}
          <span className="italic text-navy/50">
            — not enough distinct years to describe a trend honestly; nothing is estimated.
          </span>
        </p>
      )}
    </div>
  );
}

export default SeasonalHazard;
