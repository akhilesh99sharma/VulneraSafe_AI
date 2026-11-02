import { useState } from "react";
import SurveillanceActions from "./SurveillanceActions";
import RecommendedActionPanel from "./RecommendedActionPanel";
import ExplanationEvidencePanel from "./ExplanationEvidencePanel";
import ScenarioBuilder from "./ScenarioBuilder";
import PolicyComparison from "./PolicyComparison";

/**
 * Decision Actions - the decision layer as a guided three-step flow (Act /
 * Decide / Plan) behind a slim navigation strip (same idiom as the other
 * sections' sub-tab strips, so the active step's own hero reads as the page
 * title rather than competing with a second header).
 *
 *   Step 1 - Act    : Surveillance Actions (OBSERVED signal-derived worklist).
 *   Step 2 - Decide : Recommended Actions with the selected one's evidence/
 *                     audit trail stacked beneath (PREDICTED model layer).
 *   Step 3 - Plan   : Scenario Builder + A/B/C Policy Comparison (SIMULATED).
 *
 * The action SOURCES stay distinct and labeled; every item keeps its
 * human-review gate. No directive, recall, or contamination claim.
 */

type Step = "act" | "decide" | "plan";

const STEPS: Array<{ id: Step; n: number; label: string; blurb: string }> = [
  { id: "act", n: 1, label: "Surveillance Actions", blurb: "observed" },
  { id: "decide", n: 2, label: "Recommendations", blurb: "predicted" },
  { id: "plan", n: 3, label: "Policy Planning", blurb: "simulated" },
];

export function DecisionActions() {
  const [step, setStep] = useState<Step>("act");

  return (
    <div data-testid="decision-actions">
      {/* Slim workflow nav strip - section navigation, not a second header. */}
      <div className="border-b border-navy/10 bg-surface-muted">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-3 px-6 py-3">
          <span className="text-xs font-semibold uppercase tracking-wide text-navy/60">Workflow</span>
          <div data-testid="decision-steps" role="tablist" aria-label="Decision workflow steps" className="flex flex-wrap gap-2">
            {STEPS.map((s) => {
              const on = s.id === step;
              return (
                <button
                  key={s.id}
                  type="button"
                  role="tab"
                  aria-selected={on}
                  data-testid={`step-${s.id}`}
                  onClick={() => setStep(s.id)}
                  className={`flex items-center gap-2 rounded-lg border px-3 py-1.5 transition ${
                    on ? "border-teal bg-teal text-white" : "border-navy/15 bg-white text-navy/70 hover:border-navy/30"
                  }`}
                >
                  <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-bold ${on ? "bg-white/20 text-white" : "bg-navy text-white"}`}>{s.n}</span>
                  <span className="text-sm font-bold">{s.label}</span>
                  <span className={`text-[10px] uppercase tracking-wide ${on ? "text-white/70" : "text-navy/40"}`}>{s.blurb}</span>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {step === "act" ? (
        <SurveillanceActions />
      ) : step === "decide" ? (
        <DecideStep />
      ) : (
        <PlanStep />
      )}
    </div>
  );
}

/** Step 2 - Decide: the model's recommendations as a list, with the selected
 * one's full evidence/audit trail stacked directly beneath it (master-detail,
 * not a side-by-side echo). The recommendation card is a compact summary
 * (action, rationale, constraints, review gate); the evidence drawer below is
 * the ONLY place source data, uncertainty and limitations are shown. */
function DecideStep() {
  return (
    <div className="mx-auto max-w-7xl px-6 py-6">
      <section className="mb-6 overflow-hidden rounded-2xl bg-gradient-to-br from-navy via-navy-600 to-teal-600 px-6 py-10 text-white">
        <span className="inline-block rounded-full bg-white/10 px-3 py-1 text-xs font-semibold text-teal-500 ring-1 ring-white/20">
          Analysis to action
        </span>
        <h1 className="mt-4 text-3xl font-extrabold tracking-tight sm:text-4xl">Recommendations</h1>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-white/80">
          PREDICTED, safety-constrained model recommendations, distinct from the OBSERVED surveillance worklist. Select one to see its full audit trail (source, uncertainty, limitations) below. A recommendation lacking evidence or uncertainty is withheld, never shown.
        </p>
      </section>
      <div className="flex flex-col gap-5">
        <RecommendedActionPanel />
        <ExplanationEvidencePanel />
      </div>
    </div>
  );
}

/** Step 3 - Plan: illustrative planning controls (Scenario Builder) beside the
 * precomputed A/B/C Policy Comparison (SIMULATED outcomes, its own selector). */
function PlanStep() {
  return (
    <div className="mx-auto max-w-7xl px-6 py-6">
      <section className="mb-6 overflow-hidden rounded-2xl bg-gradient-to-br from-navy via-navy-600 to-teal-600 px-6 py-10 text-white">
        <span className="inline-block rounded-full bg-white/10 px-3 py-1 text-xs font-semibold text-teal-500 ring-1 ring-white/20">
          Decision support
        </span>
        <h1 className="mt-4 text-3xl font-extrabold tracking-tight sm:text-4xl">Policy Planning</h1>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-white/80">
          Compare three policies, business-as-usual (A), model-informed safety (B), and safety plus food-access-aware (C), on identical SIMULATED inputs. All operational outcomes are SIMULATED; no observed illness reduction is claimed.
        </p>
      </section>
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div className="lg:col-span-1">
          <ScenarioBuilder />
        </div>
        <div className="lg:col-span-2">
          <PolicyComparison />
        </div>
      </div>
    </div>
  );
}

export default DecisionActions;
