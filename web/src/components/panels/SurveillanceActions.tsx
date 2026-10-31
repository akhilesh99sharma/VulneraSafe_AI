import { useMemo, useState } from "react";
import { useArtifact } from "../../data/hooks";
import type { ActionQueueItem } from "../../types/artifacts";
import StatusTag from "../StatusTag";
import EmptyState from "../EmptyState";
import PanelShell, { ArtifactBody } from "./PanelShell";

/**
 * Surveillance Actions. A ranked, human-review-gated decision surface derived
 * from the OBSERVED science-module signals (S01 Pathogen Explorer, S03 Supplier
 * Monitor, S04 Emerging Signals, S06 Vulnerable Communities). S05 CDC human
 * outbreaks appear only as non-causal corroboration context, never as a trigger.
 * Every action is retailer decision support (prioritize testing, request supplier
 * verification, protect access, scrutinize sourcing) with a visible Human-Review
 * gate — never a recall, contamination claim, or directive. This is distinct from
 * the base Dashboard's SIMULATED optimizer Recommended Action Panel.
 */

const PATHOGENS = ["Salmonella", "Listeria", "STEC"] as const;

const SOURCES: Array<{ id: string; label: string }> = [
  { id: "", label: "All sources" },
  { id: "S04", label: "Emerging Signals (S04)" },
  { id: "S03", label: "Supplier Monitor (S03)" },
  { id: "S06", label: "Vulnerable Communities (S06)" },
  { id: "S01", label: "Pathogen Explorer (S01)" },
];

const CATEGORY_STYLE: Record<string, string> = {
  prioritize_testing: "bg-orange-500/15 text-orange-700",
  request_supplier_verification: "bg-teal/15 text-teal-700",
  protect_access: "bg-navy/10 text-navy/70",
  scrutinize_sourcing: "bg-navy/10 text-navy/70",
  gather_information: "bg-navy/10 text-navy/70",
};

export function SurveillanceActions() {
  const state = useArtifact<ActionQueueItem[]>("action_queue");
  const [pathogen, setPathogen] = useState<string>("");
  const [source, setSource] = useState<string>("");

  return (
    <div className="mx-auto max-w-7xl px-6 py-6">
      <section className="mb-6 overflow-hidden rounded-2xl bg-gradient-to-br from-navy via-navy-600 to-teal-600 px-6 py-10 text-white">
        <span className="inline-block rounded-full bg-white/10 px-3 py-1 text-xs font-semibold text-teal-500 ring-1 ring-white/20">
          Analysis to action · Human-in-the-loop decision support
        </span>
        <h1 className="mt-4 text-3xl font-extrabold tracking-tight sm:text-4xl">Surveillance Actions</h1>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-white/80">
          A ranked list of suggested operational actions derived from the OBSERVED surveillance
          signals across the science modules. Each is a retailer decision-support suggestion with a
          human-review gate — never a directive, a contamination claim, or a recall.
        </p>
      </section>

      {/* filters */}
      <div className="mb-4 flex flex-wrap items-end gap-4">
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-navy/60">Pathogen</p>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              aria-pressed={pathogen === ""}
              onClick={() => setPathogen("")}
              className={`rounded-lg border px-3 py-1.5 text-xs font-semibold transition ${
                pathogen === "" ? "border-teal bg-teal text-white" : "border-navy/15 bg-white text-navy/70 hover:border-navy/30"
              }`}
            >
              All
            </button>
            {PATHOGENS.map((p) => {
              const on = p === pathogen;
              return (
                <button
                  key={p}
                  type="button"
                  aria-pressed={on}
                  onClick={() => setPathogen(p)}
                  className={`rounded-lg border px-3 py-1.5 text-xs font-semibold transition ${
                    on ? "border-teal bg-teal text-white" : "border-navy/15 bg-white text-navy/70 hover:border-navy/30"
                  }`}
                >
                  {p === "STEC" ? "STEC" : p}
                </button>
              );
            })}
          </div>
        </div>
        <label className="text-[11px] font-semibold text-navy/60">
          Source{" "}
          <select
            value={source}
            onChange={(e) => setSource(e.target.value)}
            className="rounded border border-navy/20 bg-white px-2 py-1 text-xs text-navy focus:outline-none focus:ring-2 focus:ring-teal"
          >
            {SOURCES.map((s) => (
              <option key={s.id} value={s.id}>{s.label}</option>
            ))}
          </select>
        </label>
      </div>

      {/* how to read / distinct-from-optimizer */}
      <div className="mb-5 rounded-lg border border-navy/10 bg-surface-muted px-4 py-3 text-[11px] leading-relaxed text-navy/70">
        <span className="font-semibold text-navy">How to read this:</span> each row is a{" "}
        <span className="font-semibold">suggested action</span> derived from an OBSERVED surveillance
        signal, ranked by signal strength, with its evidence shown. Every action requires{" "}
        <span className="font-semibold">human review</span> before any operational step — the tool
        supports judgment, it does not replace it.{" "}
        <span className="italic">This surface is derived from real surveillance and is separate from
        the Dashboard's Recommended Action Panel, which runs the SIMULATED allocation optimizer. CDC
        human-outbreak data appears only as non-causal corroboration, never as a trigger.</span>
      </div>

      <PanelShell
        title="Suggested actions from surveillance"
        subtitle="OBSERVED · ranked · human-review-gated"
        info="Ranked suggestions derived from the S01/S03/S04/S06 OBSERVED surveillance artifacts. Retailer decision support with a human-review gate; never a recall, contamination claim, or directive. S05 is corroboration only."
      >
        <ArtifactBody
          state={state}
          artifactName="action_queue"
          isEmpty={(rows) => rows.length === 0}
          emptyTitle="No suggested actions"
          emptyDetail="No gated surveillance signal currently qualifies for an action. An empty queue is an honest result. Run: python -m src.decision.action_queue && python -m src.artifacts.exporter"
          render={(rows) => <ActionsBody rows={rows} pathogen={pathogen} source={source} />}
        />
      </PanelShell>
    </div>
  );
}

function ActionsBody({
  rows,
  pathogen,
  source,
}: {
  rows: ActionQueueItem[];
  pathogen: string;
  source: string;
}) {
  const filtered = useMemo(
    () =>
      rows
        .filter((r) => (pathogen ? r.pathogen === pathogen : true))
        .filter((r) => (source ? r.source_module === source : true))
        .sort((a, b) => a.rank - b.rank),
    [rows, pathogen, source],
  );

  if (filtered.length === 0) {
    return <EmptyState title="No actions for this filter" detail="Try a different pathogen or source." />;
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-[11px] text-navy/50">{filtered.length} suggested action(s), highest signal first.</p>
      <ul className="flex flex-col gap-2">
        {filtered.map((a) => (
          <li key={`${a.source_module}:${a.rank}:${a.target}`} className="rounded-lg border border-navy/10 bg-white p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="mb-1 flex flex-wrap items-center gap-2">
                  <span className="rounded-full bg-navy px-2 py-0.5 text-[10px] font-bold text-white">#{a.rank}</span>
                  <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${CATEGORY_STYLE[a.action_category] ?? "bg-navy/10 text-navy/70"}`}>
                    {a.action_category.replace(/_/g, " ")}
                  </span>
                  <span className="rounded-full border border-navy/15 px-2 py-0.5 text-[10px] font-semibold text-navy/60">
                    {a.source_module} · {a.pathogen}
                  </span>
                </div>
                <p className="text-sm font-semibold text-navy">{a.action}</p>
                <p className="mt-1 text-[11px] text-navy/60">
                  <span className="font-semibold text-navy/70">Why: </span>{a.triggering_signal}
                </p>
                <p className="mt-0.5 text-[10px] text-navy/50">
                  <span className="font-semibold">Evidence: </span>{a.evidence_summary}
                </p>
                {a.corroboration_note ? (
                  <p className="mt-1 rounded-md bg-navy/5 px-2 py-1 text-[10px] italic text-navy/50">
                    {a.corroboration_note}
                  </p>
                ) : null}
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1">
                <StatusTag status={a.status} />
                <span className="rounded-full bg-orange-500/15 px-2 py-0.5 text-[10px] font-bold text-orange-700">
                  ⚠ Human review
                </span>
              </div>
            </div>
          </li>
        ))}
      </ul>
      <p className="mt-1 text-[10px] italic text-navy/50">
        Suggestions derived from OBSERVED USDA FSIS surveillance (and ACS/Atlas vulnerability context),
        ranked by signal strength. Every action requires human review and is retailer decision support
        — never a recall, a determination that a product is contaminated or safe, or a regulatory
        directive. CDC human-outbreak data is shown only as non-causal, lagged corroboration.
      </p>
    </div>
  );
}

export default SurveillanceActions;