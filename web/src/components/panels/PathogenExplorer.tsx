import { useMemo, useState } from "react";
import { useArtifact } from "../../data/hooks";
import type { ProgramProductStratum } from "../../types/artifacts";
import { formatRisk } from "../../types/viewModels";
import StatusTag from "../StatusTag";
import EmptyState from "../EmptyState";
import PanelShell, { ArtifactBody } from "./PanelShell";

/**
 * Pathogen Explorer (S01). Three first-class pathogen modules. For the selected
 * pathogen it shows OBSERVED positivity stratified by program, sample source,
 * and product/control category, each with a Wilson 95% "likely range". Every
 * number comes from the `multipathogen_program_product` artifact; no forecasts,
 * no fabricated values. A dimension the source cannot support (e.g. STEC
 * product) renders an explicit "not available" state.
 */

const PATHOGENS = ["Salmonella", "Listeria", "STEC"] as const;
type Pathogen = (typeof PATHOGENS)[number];

const DIMENSIONS: Array<{ id: string; label: string; help: string; noun: string }> = [
  { id: "program", label: "By sampling program", help: "The FSIS testing project the sample was collected under.", noun: "programs" },
  { id: "sample_source", label: "By sample source", help: "What was swabbed or collected (product vs. plant contact surface, species, etc.).", noun: "sources" },
  { id: "product", label: "By product / control category", help: "Product type (poultry) or RTE production alternative (Listeria).", noun: "product categories" },
];

const TOP_N = 10;
const MIN_N = 30; // groups below this are too small for a meaningful rate

type SortMode = "rate" | "size";

function Bar({
  value,
  max,
  baseline = null,
  ciLow = null,
  ciHigh = null,
}: {
  value: number;
  max: number;
  /** Overall pathogen positivity, drawn as a thin vertical baseline marker. */
  baseline?: number | null;
  /** 95% Wilson interval bounds, drawn as a faint navy band on the track. */
  ciLow?: number | null;
  ciHigh?: number | null;
}) {
  const clamp = (n: number) => Math.max(0, Math.min(100, n));
  const pct = max > 0 ? clamp((value / max) * 100) : 0;
  const showCi =
    max > 0 && ciLow !== null && ciLow !== undefined && ciHigh !== null && ciHigh !== undefined;
  const ciLeft = showCi ? clamp(((ciLow as number) / max) * 100) : 0;
  const ciRight = showCi ? clamp(((ciHigh as number) / max) * 100) : 0;
  const ciWidth = Math.max(0.5, ciRight - ciLeft);
  const showBase =
    max > 0 && baseline !== null && baseline !== undefined && !Number.isNaN(baseline);
  const basePct = showBase ? clamp(((baseline as number) / max) * 100) : 0;
  return (
    <div className="relative h-2.5 w-full overflow-hidden rounded-full bg-navy/10" aria-hidden>
      {showCi ? (
        <div
          className="absolute inset-y-0 rounded-full bg-navy/15"
          style={{ left: `${ciLeft}%`, width: `${ciWidth}%` }}
        />
      ) : null}
      <div className="absolute inset-y-0 left-0 rounded-full bg-teal" style={{ width: `${pct}%` }} />
      {showBase ? (
        <div
          className="absolute inset-y-0 w-px bg-navy/50"
          style={{ left: `${basePct}%` }}
        />
      ) : null}
    </div>
  );
}

/** Accessible info marker (local copy of the PanelShell/SectionCard idiom):
 * shows `text` on hover and keyboard focus. Kept local so the explorer does
 * not invent a new tooltip mechanism. */
function InfoDot({ text }: { text: string }) {
  return (
    <span className="group relative inline-flex">
      <button
        type="button"
        aria-label="What is this?"
        className="flex h-4 w-4 items-center justify-center rounded-full border border-navy/30 text-[10px] font-bold text-navy/60 hover:bg-navy/5 focus:outline-none focus:ring-2 focus:ring-teal"
      >
        i
      </button>
      <span
        role="tooltip"
        className="pointer-events-none absolute left-0 top-6 z-30 w-64 rounded-lg border border-navy/10 bg-navy px-3 py-2 text-[11px] leading-relaxed text-white opacity-0 shadow-lg transition group-hover:opacity-100 group-focus-within:opacity-100">
        {text}
      </span>
    </span>
  );
}

export function PathogenExplorer() {
  const state = useArtifact<ProgramProductStratum[]>("multipathogen_program_product");
  const [pathogen, setPathogen] = useState<Pathogen>("Salmonella");
  const [sortMode, setSortMode] = useState<SortMode>("rate");

  // Per-pathogen OVERALL positivity (the dimension==="overall" row), read straight
  // from the artifact so the at-a-glance strip never fabricates a number.
  const overallByPathogen = useMemo(() => {
    const rows = state.data ?? [];
    const m: Record<string, ProgramProductStratum | undefined> = {};
    for (const p of PATHOGENS) {
      m[p] = rows.find((r) => r.pathogen === p && r.dimension === "overall");
    }
    return m;
  }, [state.data]);

  return (
    <div className="mx-auto max-w-7xl px-6 py-6">
      {/* Slim hero + cross-pathogen at-a-glance */}
      <section className="mb-6 overflow-hidden rounded-2xl bg-gradient-to-br from-navy via-navy-600 to-teal-600 px-6 py-6 text-white">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="min-w-0">
            <span className="inline-block rounded-full bg-white/10 px-3 py-1 text-[11px] font-semibold text-teal-500 ring-1 ring-white/20">
              Data-driven food safety · OBSERVED surveillance · not a forecast
            </span>
            <h1 className="mt-3 text-2xl font-extrabold tracking-tight sm:text-3xl">Pathogen Explorer</h1>
            <p className="mt-1 max-w-xl text-[13px] leading-relaxed text-white/80">
              Observed FSIS positivity by program, sample source and product. Historical lab
              results — never a claim that any product is contaminated.
            </p>
          </div>
          <dl className="grid grid-cols-3 gap-2 text-center" aria-label="Overall observed positivity by pathogen">
            {PATHOGENS.map((p) => {
              const o = overallByPathogen[p];
              const on = p === pathogen;
              return (
                <button
                  key={p}
                  type="button"
                  onClick={() => setPathogen(p)}
                  aria-label={`${p} overall positivity`}
                  aria-pressed={on}
                  className={`min-w-[84px] rounded-xl border px-3 py-2 text-left transition ${
                    on ? "border-teal bg-white/10 ring-1 ring-teal" : "border-white/15 hover:border-white/40"
                  }`}
                >
                  <dt className="truncate text-[10px] font-semibold uppercase tracking-wide text-white/70">
                    {p === "STEC" ? "STEC" : p}
                  </dt>
                  <dd className="text-lg font-extrabold text-white">
                    {o && o.value !== null ? formatRisk(o.value) : "n‑a"}
                  </dd>
                  <dd className="text-[10px] text-white/60">
                    {o && o.sample_n ? `${o.sample_n.toLocaleString()} tests` : "—"}
                  </dd>
                </button>
              );
            })}
          </dl>
        </div>
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

      {/* How to read this page — explains the likely range once */}
      <div className="mb-5 rounded-lg border border-navy/10 bg-surface-muted px-4 py-3 text-[11px] leading-relaxed text-navy/70">
        <span className="font-semibold text-navy">How to read this:</span> each row shows a group's{" "}
        <span className="font-semibold">positivity</span> (share of valid tests that came back positive), the raw{" "}
        <span className="font-semibold">positives / tests</span> behind it, and a{" "}
        <span className="font-semibold">likely range</span> in brackets. The likely range is a 95% confidence interval:
        with many tests it is narrow (we are quite sure of the rate); with few tests it is wide (we are not).
        Groups with fewer than {MIN_N} tests are hidden as statistical noise.{" "}
        <span className="italic">Breakdowns by state and by establishment are addressed separately in the map
        views and the establishment-surveillance module (where sampling-intensity bias can be handled properly),
        not here.</span>
      </div>

      <PanelShell
        title={`${pathogen} — observed positivity by stratum`}
        subtitle="OBSERVED FSIS surveillance · 95% likely range"
        info="Each bar is the share of valid diagnostic tests that were positive for the selected pathogen, within that program / source / product group. Non-diagnostic and canceled results are excluded. OBSERVED history only — not a prediction."
        accessory={
          <div className="flex items-center gap-1 text-[10px]">
            <span className="text-navy/40">Sort:</span>
            <button
              type="button"
              onClick={() => setSortMode("rate")}
              aria-pressed={sortMode === "rate"}
              className={`rounded px-2 py-0.5 font-semibold transition ${
                sortMode === "rate" ? "bg-navy text-white" : "border border-navy/20 text-navy/60"
              }`}
            >
              Highest positivity
            </button>
            <button
              type="button"
              onClick={() => setSortMode("size")}
              aria-pressed={sortMode === "size"}
              className={`rounded px-2 py-0.5 font-semibold transition ${
                sortMode === "size" ? "bg-navy text-white" : "border border-navy/20 text-navy/60"
              }`}
            >
              Most tested
            </button>
          </div>
        }
      >
        <ArtifactBody
          state={state}
          artifactName="multipathogen_program_product"
          isEmpty={(rows) => rows.length === 0}
          emptyTitle="No stratification data available"
          emptyDetail="The multipathogen_program_product artifact is present but empty. Run: python -m src.artifacts.exporter"
          render={(rows) => <ExplorerBody rows={rows} pathogen={pathogen} sortMode={sortMode} />}
        />
      </PanelShell>
    </div>
  );
}

function ExplorerBody({
  rows,
  pathogen,
  sortMode,
}: {
  rows: ProgramProductStratum[];
  pathogen: Pathogen;
  sortMode: SortMode;
}) {
  const forPathogen = useMemo(() => rows.filter((r) => r.pathogen === pathogen), [rows, pathogen]);
  const overall = forPathogen.find((r) => r.dimension === "overall") ?? null;

  if (forPathogen.length === 0) {
    return <EmptyState title="No data for this pathogen" detail={`No strata recorded for ${pathogen}.`} />;
  }

  const years = overall?.fiscal_years ?? [];
  const yearLabel = years.length ? `${years[0]}–${years[years.length - 1]}` : "—";

  return (
    <div className="flex flex-col gap-5">
      {/* Overall metric card */}
      {overall ? (
        <div className="flex flex-wrap items-center gap-4 rounded-lg border border-navy/10 bg-surface-muted p-4">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wide text-navy/50">Overall positivity</p>
            <p className="text-2xl font-extrabold text-navy">
              {overall.value === null ? "not available" : formatRisk(overall.value)}
            </p>
          </div>
          <div className="text-xs text-navy/60">
            <div>Valid tests: <span className="font-semibold text-navy">{overall.sample_n?.toLocaleString() ?? "—"}</span></div>
            <div>Positives: <span className="font-semibold text-navy">{overall.positive_n?.toLocaleString() ?? "—"}</span></div>
            <div>Fiscal years: <span className="font-semibold text-navy">{yearLabel}</span></div>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <StatusTag status={overall.status} />
            <span className="text-[10px] text-navy/40">pooled across all years</span>
          </div>
        </div>
      ) : null}

      {/* One section per dimension */}
      {DIMENSIONS.map((dim) => (
        <DimensionSection key={dim.id} rows={forPathogen} dim={dim} sortMode={sortMode} pathogen={pathogen} />
      ))}

      <p className="text-[10px] italic text-navy/50">
        OBSERVED USDA FSIS establishment sampling, pooled across fiscal years {yearLabel}. Positivity = positive ÷
        valid diagnostic tests; non-diagnostic and canceled results excluded. FSIS establishment geography is a
        processing-site, never a consumer or infection location. This is surveillance history, not a forecast or a
        contamination determination.
      </p>
    </div>
  );
}

/** Build one honest plain-English takeaway sentence from the ranked categories. */
function takeaway(dim: { noun: string }, cats: ProgramProductStratum[], pathogen: string): string | null {
  const real = cats.filter((c) => c.category !== "(unspecified)" && c.value !== null);
  if (real.length < 2) return null;
  const byRate = [...real].sort((a, b) => (b.value ?? 0) - (a.value ?? 0));
  const top = byRate[0];
  const bottom = byRate[byRate.length - 1];
  if ((top.value ?? 0) <= (bottom.value ?? 0)) return null;
  return (
    `Among ${pathogen} ${dim.noun}, “${top.category.toLowerCase()}” had the highest observed positivity ` +
    `(${formatRisk(top.value)}), versus “${bottom.category.toLowerCase()}” at the low end (${formatRisk(bottom.value)}). ` +
    `Positivity clearly varies by ${dim.noun.replace(/s$/, "")} — not a contamination claim, just where positives concentrated historically.`
  );
}

function DimensionSection({
  rows,
  dim,
  sortMode,
  pathogen,
}: {
  rows: ProgramProductStratum[];
  dim: { id: string; label: string; help: string; noun: string };
  sortMode: SortMode;
  pathogen: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const inDim = rows.filter((r) => r.dimension === dim.id);
  const unavailable = inDim.find((r) => r.availability_status === "unavailable");
  const available = inDim.filter(
    (r) => r.availability_status === "available" && r.sample_n && r.sample_n > 0,
  );
  const kept = available.filter((r) => (r.sample_n ?? 0) >= MIN_N);
  const smallGroups = available.length - kept.length;

  // Separate the "(unspecified)" bucket so it never tops the ranking; it is
  // shown de-emphasized at the end rather than competing with real categories.
  const unspecified = kept.find((r) => r.category === "(unspecified)") ?? null;
  const realCats = kept.filter((r) => r.category !== "(unspecified)");

  const sorter =
    sortMode === "rate"
      ? (a: ProgramProductStratum, b: ProgramProductStratum) => (b.value ?? 0) - (a.value ?? 0)
      : (a: ProgramProductStratum, b: ProgramProductStratum) => (b.sample_n ?? 0) - (a.sample_n ?? 0);
  const ranked = [...realCats].sort(sorter);

  if (unavailable || (ranked.length === 0 && !unspecified)) {
    return (
      <div className="rounded-lg border border-dashed border-navy/20 bg-white p-4">
        <h3 className="text-sm font-bold text-navy">{dim.label}</h3>
        <p className="mt-1 text-xs italic text-navy/60">
          not available — {unavailable?.unavailable_reason ?? "no categories for this pathogen."}
        </p>
      </div>
    );
  }

  const shown = expanded ? ranked : ranked.slice(0, TOP_N);
  // The pathogen OVERALL positivity (read from its own "overall" row), drawn
  // as a thin baseline marker on each bar so groups read as above/below typical.
  const baseline = rows.find((r) => r.dimension === "overall")?.value ?? null;
  const maxVal = Math.max(...ranked.map((c) => c.value ?? 0), unspecified?.value ?? 0, 0.0001);
  const note = takeaway(dim, ranked, pathogen);

  return (
    <div className="rounded-lg border border-navy/10 bg-white p-4">
      <div className="mb-1 flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <h3 className="text-[15px] font-bold text-navy">{dim.label}</h3>
          <InfoDot text={dim.help} />
        </div>
        <span className="text-[10px] text-navy/40">
          {ranked.length} {dim.noun}
          {smallGroups > 0 ? ` · ${smallGroups} small (n<${MIN_N}) hidden` : ""}
        </span>
      </div>

      {/* Key finding (promoted) */}
      {note ? (
        <div className="mb-3 rounded-lg border border-teal/20 bg-teal/5 px-3 py-2.5">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-teal-700">Key finding</p>
          <p className="mt-0.5 text-[13px] leading-relaxed text-navy/80">{note}</p>
        </div>
      ) : null}
      {baseline !== null ? (
        <p className="mb-2 flex items-center gap-1.5 text-[10px] text-navy/50">
          <span className="inline-block h-3 w-px bg-navy/50" aria-hidden />
          Vertical marker = overall {pathogen} positivity ({formatRisk(baseline)}); teal bar = this group; faint band = 95% likely range.
        </p>
      ) : null}

      <ul className="flex flex-col gap-3">
        {shown.map((c) => (
          <Row key={`${dim.id}:${c.category}`} c={c} max={maxVal} baseline={baseline} />
        ))}
      </ul>

      {ranked.length > TOP_N ? (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="mx-auto mt-3 block rounded-lg border border-navy/20 px-4 py-1.5 text-xs font-semibold text-navy/70 transition hover:bg-surface-muted"
        >
          {expanded ? `Show top ${TOP_N} only` : `Show all ${ranked.length}`}
        </button>
      ) : null}

      {/* De-emphasized unspecified bucket, shown last with an honest note */}
      {unspecified ? (
        <div className="mt-3 border-t border-navy/5 pt-2">
          <Row c={unspecified} max={maxVal} muted />
          <p className="mt-1 text-[10px] italic text-navy/40">
            “(unspecified)” = records where this field was blank in the source data. Shown for completeness, not ranked.
          </p>
        </div>
      ) : null}
    </div>
  );
}

function Row({ c, max, muted = false, baseline = null }: { c: ProgramProductStratum; max: number; muted?: boolean; baseline?: number | null }) {
  return (
    <li className="grid grid-cols-[1fr,auto] items-center gap-x-3 gap-y-1">
      <div className="min-w-0">
        <p className={`truncate text-[13px] font-medium ${muted ? "text-navy/50" : "text-navy"}`} title={c.category}>
          {c.category}
        </p>
        <Bar value={c.value ?? 0} max={max} baseline={baseline} ciLow={c.ci_low} ciHigh={c.ci_high} />
      </div>
      <div className="text-right text-[13px]">
        <span className={`font-bold ${muted ? "text-navy/50" : "text-navy"}`}>
          {c.value === null ? "—" : formatRisk(c.value)}
        </span>
        <div className="text-[11px] text-navy/50">
          {c.positive_n?.toLocaleString() ?? "—"}/{c.sample_n?.toLocaleString() ?? "—"} positive
          {c.ci_low !== null && c.ci_high !== null ? (
            <span title="95% likely range: with many tests this is narrow (more certain); with few tests it is wide (less certain).">
              {" "}· likely {formatRisk(c.ci_low)}–{formatRisk(c.ci_high)}
            </span>
          ) : null}
        </div>
      </div>
    </li>
  );
}

export default PathogenExplorer;
