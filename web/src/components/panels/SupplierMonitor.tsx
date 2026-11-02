import { useMemo, useState } from "react";
import { useArtifact } from "../../data/hooks";
import type { EstablishmentSurveillanceRecord } from "../../types/artifacts";
import { formatRisk } from "../../types/viewModels";
import StatusTag from "../StatusTag";
import EmptyState from "../EmptyState";
import PanelShell, { ArtifactBody } from "./PanelShell";

/**
 * Supplier Monitor (S03). For each pathogen it ranks FSIS establishments by an
 * uncertainty-aware beta-binomial Empirical Bayes posterior positivity (partially
 * pooled toward the pathogen peer rate) with a 95% credible interval, plus
 * persistence evidence. The central rule: low testing is NEVER safety — a
 * thinly-sampled establishment is shrunk toward the peer rate, shown with a wide
 * interval, and separated as low-support, never "clean". Identity is FSIS-published
 * only (id, name, state); geography is sampling location; no supplier/retailer
 * relationship is implied; positivity is surveillance signal, not contamination.
 * Every number comes from the `establishment_surveillance` artifact.
 */

const PATHOGENS = ["Salmonella", "Listeria", "STEC"] as const;
type Pathogen = (typeof PATHOGENS)[number];

const TOP_N = 15;

function Bar({ value, max }: { value: number; max: number }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-navy/10" aria-hidden>
      <div className="h-full rounded-full bg-teal" style={{ width: `${pct}%` }} />
    </div>
  );
}

export function SupplierMonitor() {
  const state = useArtifact<EstablishmentSurveillanceRecord[]>("establishment_surveillance");
  const [pathogen, setPathogen] = useState<Pathogen>("Salmonella");
  const [region, setRegion] = useState<string>("");

  return (
    <div className="mx-auto max-w-7xl px-6 py-6">
      <section className="mb-6 overflow-hidden rounded-2xl bg-gradient-to-br from-navy via-navy-600 to-teal-600 px-6 py-10 text-white">
        <span className="inline-block rounded-full bg-white/10 px-3 py-1 text-xs font-semibold text-teal-500 ring-1 ring-white/20">
          Establishment surveillance · Uncertainty-aware ranking
        </span>
        <h1 className="mt-4 text-3xl font-extrabold tracking-tight sm:text-4xl">Supplier Monitor</h1>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-white/80">
          FSIS establishments ranked by a statistically honest positivity estimate that shrinks
          thinly-tested plants toward the peer rate. These are OBSERVED historical surveillance
          figures with stated uncertainty — never a forecast, never a claim a plant's product is
          contaminated, and never a statement that any establishment supplies this retailer.
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

      {/* How to read this */}
      <div className="mb-5 rounded-lg border border-navy/10 bg-surface-muted px-4 py-3 text-[11px] leading-relaxed text-navy/70">
        <span className="font-semibold text-navy">How to read this:</span> each establishment's{" "}
        <span className="font-semibold">estimate</span> is a shrinkage (Empirical Bayes) positivity, pulled toward
        the pathogen's peer rate in proportion to how little it was tested, with a 95%{" "}
        <span className="font-semibold">likely range</span>. A plant tested only a few times is uncertain, not safe —
        so low-support plants are listed separately and never ranked as clean.{" "}
        <span className="italic">Geography is the establishment's own sampling location, not where its product was
        sold or where anyone became ill. A high rate is a surveillance signal to look closer, not proof of
        contamination.</span>
      </div>

      <PanelShell
        title={`${pathogen} — establishments by EB positivity`}
        subtitle="OBSERVED FSIS surveillance · Empirical-Bayes estimate · 95% likely range"
        info="Each establishment's positivity is partially pooled toward the pathogen peer rate (beta-binomial EB). Ranking uses the shrunk estimate, so a thinly-tested plant cannot top the list on a spurious rate. Descriptive surveillance only — not a forecast or contamination claim."
      >
        <ArtifactBody
          state={state}
          artifactName="establishment_surveillance"
          isEmpty={(rows) => rows.length === 0}
          emptyTitle="No establishment surveillance data available"
          emptyDetail="The establishment_surveillance artifact is present but empty. Run: python -m src.analysis.establishment_surveillance && python -m src.artifacts.exporter"
          render={(rows) => (
            <MonitorBody rows={rows} pathogen={pathogen} region={region} setRegion={setRegion} />
          )}
        />
      </PanelShell>
    </div>
  );
}

function MonitorBody({
  rows,
  pathogen,
  region,
  setRegion,
}: {
  rows: EstablishmentSurveillanceRecord[];
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

  const filtered = region ? available.filter((r) => r.region === region) : available;

  if (unavailable) {
    return (
      <EmptyState
        title={`${pathogen} — not available`}
        detail={unavailable.unavailable_reason ?? "Establishment series unavailable for this pathogen."}
      />
    );
  }
  if (available.length === 0) {
    return <EmptyState title="No data for this pathogen" detail={`No establishments recorded for ${pathogen}.`} />;
  }

  const ranked = filtered
    .filter((r) => r.support_status === "ok")
    .sort((a, b) => (b.eb_posterior ?? 0) - (a.eb_posterior ?? 0));
  const lowSupport = filtered.filter((r) => r.support_status === "low_support");

  const years = available[0]?.fiscal_years ?? [];
  const yearLabel = years.length ? `${years[0]}–${years[years.length - 1]}` : "—";
  const peer = available.find((r) => r.peer_rate != null)?.peer_rate ?? null;
  const maxEb = Math.max(...ranked.map((r) => r.eb_posterior ?? 0), 0.0001);
  const coordCount = filtered.filter((r) => r.latitude != null && r.longitude != null).length;

  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? ranked : ranked.slice(0, TOP_N);

  return (
    <div className="flex flex-col gap-5">
      {/* Context row */}
      <div className="flex flex-wrap items-center gap-4 rounded-lg border border-navy/10 bg-surface-muted p-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-navy/50">Peer (pooled) rate</p>
          <p className="text-2xl font-extrabold text-navy">{peer === null ? "—" : formatRisk(peer)}</p>
        </div>
        <div className="text-xs text-navy/60">
          <div>Establishments ranked: <span className="font-semibold text-navy">{ranked.length}</span></div>
          <div>Low-support (not ranked): <span className="font-semibold text-navy">{lowSupport.length}</span></div>
          <div>Fiscal years: <span className="font-semibold text-navy">{yearLabel}</span></div>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <label className="text-[11px] font-semibold text-navy/60">
            State{" "}
            <select
              value={region}
              onChange={(e) => setRegion(e.target.value)}
              className="rounded border border-navy/20 bg-white px-2 py-1 text-xs text-navy focus:outline-none focus:ring-2 focus:ring-teal"
            >
              <option value="">All states</option>
              {regions.map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
          </label>
          <StatusTag status="OBSERVED" />
        </div>
      </div>

      {/* Ranked list */}
      <div className="rounded-lg border border-navy/10 bg-white p-4">
        <div className="mb-1 flex items-center justify-between gap-2">
          <h3 className="text-sm font-bold text-navy">Highest EB positivity (well-sampled establishments)</h3>
          <span className="text-[10px] text-navy/40">{ranked.length} ranked</span>
        </div>
        <p className="mb-3 text-[11px] text-navy/50">
          Ranked by the shrinkage estimate, not the raw rate. The likely range widens when an establishment has
          fewer tests.
        </p>
        {ranked.length === 0 ? (
          <p className="text-xs italic text-navy/60">No establishment in this selection clears the support threshold.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {shown.map((r) => (
              <EstRow key={r.establishment_id} r={r} max={maxEb} />
            ))}
          </ul>
        )}
        {ranked.length > TOP_N ? (
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="mx-auto mt-3 block rounded-lg border border-navy/20 px-4 py-1.5 text-xs font-semibold text-navy/70 transition hover:bg-surface-muted"
          >
            {expanded ? `Show top ${TOP_N} only` : `Show all ${ranked.length}`}
          </button>
        ) : null}
      </div>

      {/* Low-support, de-emphasized, never "safe" */}
      {lowSupport.length > 0 ? (
        <div className="rounded-lg border border-dashed border-navy/20 bg-white p-4">
          <h3 className="text-sm font-bold text-navy">Insufficient testing — uncertain, not safe</h3>
          <p className="mb-2 text-[11px] text-navy/50">
            {lowSupport.length} establishment(s) with too few tests to rank confidently. Shown for completeness
            with their (heavily shrunk) estimate and wide interval — a low count is absence of evidence, never
            evidence of safety.
          </p>
          <ul className="flex flex-col gap-2">
            {lowSupport.slice(0, 10).map((r) => (
              <EstRow key={r.establishment_id} r={r} max={maxEb} muted />
            ))}
          </ul>
          {lowSupport.length > 10 ? (
            <p className="mt-2 text-[10px] italic text-navy/40">…and {lowSupport.length - 10} more low-support establishments.</p>
          ) : null}
        </div>
      ) : null}

      {/* Facility locations */}
      <div className="rounded-lg border border-navy/10 bg-white p-4">
        <h3 className="mb-1 text-sm font-bold text-navy">Facility locations</h3>
        <p className="text-[11px] leading-relaxed text-navy/60">
          <span className="font-semibold text-navy">{coordCount}</span> of {filtered.length}{" "}
          establishment{filtered.length === 1 ? "" : "s"} in this selection carry a verified county and
          coordinate joined from the FSIS Meat, Poultry &amp; Egg Inspection (MPI) establishment directory on
          establishment id. These mark the processing or sampling site — never where a product was sold and
          never where anyone became ill. The remainder had no directory match and are shown without a
          location rather than a fabricated one.
        </p>
      </div>

      <p className="text-[10px] italic text-navy/50">
        OBSERVED USDA FSIS routine-surveillance sampling, establishment level, fiscal years {yearLabel}. Estimate =
        beta-binomial Empirical-Bayes positivity shrunk toward the pathogen peer rate; likely range is the 95%
        credible interval. Identity is FSIS-published (id, name, state) only. Establishment geography is a sampling
        site, never a product destination, an illness location, or a stated supplier relationship. Surveillance
        signal, not a contamination determination.
      </p>
    </div>
  );
}

function EstRow({
  r,
  max,
  muted = false,
}: {
  r: EstablishmentSurveillanceRecord;
  max: number;
  muted?: boolean;
}) {
  const p = r.persistence;
  const name = r.establishment_name ?? `Establishment ${r.establishment_id}`;
  return (
    <li className="grid grid-cols-[1fr,auto] items-center gap-x-3 gap-y-1">
      <div className="min-w-0">
        <p className={`truncate text-xs font-medium ${muted ? "text-navy/50" : "text-navy"}`} title={name}>
          {name} <span className="text-navy/40">· {r.region}</span>
        </p>
        {r.county || r.city ? (
          <p className="truncate text-[10px] text-navy/45" title={[r.city, r.county].filter(Boolean).join(", ")}>
            {[r.city, r.county].filter(Boolean).join(", ")}
            {r.latitude != null && r.longitude != null ? (
              <span className="text-navy/35"> · {r.latitude.toFixed(3)}, {r.longitude.toFixed(3)}</span>
            ) : null}
          </p>
        ) : null}
        <Bar value={r.eb_posterior ?? 0} max={max} />
      </div>
      <div className="text-right text-xs">
        <span className={`font-bold ${muted ? "text-navy/50" : "text-navy"}`}>
          {r.eb_posterior === null ? "—" : formatRisk(r.eb_posterior)}
        </span>
        <div className="text-[10px] text-navy/50">
          {r.positive_n ?? "—"}/{r.sample_n ?? "—"} positive
          {r.ci_low !== null && r.ci_high !== null ? (
            <span title="95% credible interval (beta posterior): wide when the establishment has few tests.">
              {" "}· likely {formatRisk(r.ci_low)}–{formatRisk(r.ci_high)}
            </span>
          ) : null}
          {p && p.repeated_positive_periods != null ? (
            <span className="text-navy/40">
              {" "}· {p.repeated_positive_periods} positive quarter{p.repeated_positive_periods === 1 ? "" : "s"}
              {p.last_supported_period ? ` (last ${p.last_supported_period})` : ""}
            </span>
          ) : null}
        </div>
      </div>
    </li>
  );
}

export default SupplierMonitor;
