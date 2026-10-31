import { useArtifact } from "../../data/hooks";
import { useSelection } from "../../state/selection";
import type { Recommendation } from "../../types/artifacts";
import {
  evaluateRecommendationGuard,
  formatUncertainty,
} from "../../types/viewModels";
import AlertBadge from "../AlertBadge";
import StatusTag from "../StatusTag";
import PanelShell, { ArtifactBody } from "./PanelShell";

/**
 * Recommended Action Panel (Req 12.7, 16.4, 16.5).
 *
 * Reads the `recommendations` artifact and, for each recommendation, shows the
 * action, its rationale, the governing constraints, supporting evidence, a
 * quantified uncertainty measure, and a clear Human_Review-required indicator
 * (Req 16.4). An AlertBadge distinguishes the alert source (MODEL vs
 * REGULATORY). Selecting a recommendation sets the shared selection so the
 * Explanation / Evidence Panel can show its detail (Req 12.8).
 *
 * RESPONSIBLE-USE GUARD (Req 16.5, mirrors `src/responsible.py`
 * `withhold_unsupported_model_recommendation`): a MODEL recommendation whose
 * `uncertainty` is null OR whose `evidence_refs` is empty is NEVER rendered as
 * a recommendation — an explanatory "withheld — insufficient
 * evidence/uncertainty" note is shown in its place. A REGULATORY recommendation
 * always renders. The guard lives in `evaluateRecommendationGuard` so the panel
 * and the Explanation / Evidence Panel apply exactly the same rule.
 */

export function RecommendedActionPanel() {
  const { recommendationTargetId, setRecommendationTargetId } = useSelection();
  const state = useArtifact<Recommendation[]>("recommendations");

  return (
    <PanelShell title="Recommended Action Panel"
      subtitle="Safety-constrained actions · human review flagged"
      info="Concrete retailer actions. Model-prioritization actions are PREDICTED (with uncertainty + evidence); operational actions are SIMULATED from the safety-constrained optimizer. A model recommendation lacking evidence or uncertainty is withheld rather than shown.">
      <ArtifactBody
        state={state}
        artifactName="recommendations"
        isEmpty={(recs) => recs.length === 0}
        emptyTitle="No recommendations to show"
        emptyDetail="The recommendations artifact is present but empty."
        render={(recs) => {
          // Responsible-use guard (Req 16.5): an unsupported MODEL rec is
          // WITHHELD. Rather than rendering a wall of "withheld" cards, we drop
          // them from the list and report the count honestly in a footnote.
          const showable = recs.filter((r) => evaluateRecommendationGuard(r).show);
          const withheldCount = recs.length - showable.length;
          return (
          <div className="flex flex-col gap-3">
          {withheldCount > 0 ? (
            <p className="rounded-md bg-navy/5 px-3 py-1.5 text-[11px] text-navy/60">
              Showing <span className="font-semibold text-navy">{showable.length}</span> actionable
              recommendation{showable.length === 1 ? "" : "s"}.{" "}
              <span className="font-semibold">{withheldCount}</span> model-generated
              recommendation{withheldCount === 1 ? " was" : "s were"} withheld for
              insufficient evidence or uncertainty (responsible-use guard).
            </p>
          ) : null}
          <ul data-testid="recommendation-list" className="flex flex-col gap-3">
            {showable.map((rec, i) => {
              const selected = rec.target_id === recommendationTargetId;
              return (
                <li key={`${rec.target_id}:${rec.action}:${i}`}>
                  <button
                    type="button"
                    data-testid="recommendation-item"
                    data-target-id={rec.target_id}
                    aria-pressed={selected}
                    onClick={() => setRecommendationTargetId(rec.target_id)}
                    className={`w-full rounded border p-3 text-left transition focus:outline-none focus:ring-2 focus:ring-teal ${
                      selected
                        ? "border-teal bg-teal/5"
                        : "border-navy/10 bg-surface-muted hover:border-navy/30"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-sm font-semibold text-navy">{rec.action}</p>
                      <div className="flex shrink-0 items-center gap-1">
                        <AlertBadge source={rec.alert_source} />
                        <StatusTag status={rec.status} />
                      </div>
                    </div>

                    <p className="mt-1 text-xs text-navy/60">
                      Target: <span className="font-semibold">{rec.target_id}</span>
                    </p>

                    <p className="mt-2 text-xs text-navy">
                      <span className="font-semibold text-navy/60">Rationale: </span>
                      {rec.rationale}
                    </p>

                    <div className="mt-2">
                      <p className="text-xs font-semibold text-navy/60">
                        Governing constraints
                      </p>
                      {rec.constraints.length > 0 ? (
                        <ul className="mt-1 list-disc pl-5 text-xs text-navy">
                          {rec.constraints.map((c, i) => (
                            <li key={`${rec.target_id}-constraint-${i}`}>{c}</li>
                          ))}
                        </ul>
                      ) : (
                        <p className="mt-1 text-xs italic text-navy/50">
                          None recorded.
                        </p>
                      )}
                    </div>

                    <div className="mt-2">
                      <p className="text-xs font-semibold text-navy/60">
                        Supporting evidence
                      </p>
                      {rec.evidence_refs.length > 0 ? (
                        <ul
                          data-testid="recommendation-evidence"
                          className="mt-1 list-disc pl-5 text-xs text-navy"
                        >
                          {rec.evidence_refs.map((ref, i) => (
                            <li key={`${rec.target_id}-evidence-${i}`}>{ref}</li>
                          ))}
                        </ul>
                      ) : (
                        <p className="mt-1 text-xs italic text-navy/50">
                          None recorded.
                        </p>
                      )}
                    </div>

                    <p
                      data-testid="recommendation-uncertainty"
                      className="mt-2 text-xs text-navy"
                    >
                      <span className="font-semibold text-navy/60">
                        Uncertainty:{" "}
                      </span>
                      {formatUncertainty(rec.uncertainty)}
                    </p>

                    <div className="mt-2">
                      {rec.human_review_required ? (
                        <span
                          data-testid="human-review-required"
                          className="inline-flex items-center gap-1 rounded border-l-4 border-alert-warn bg-alert-warn/10 px-2 py-1 text-xs font-bold text-navy"
                        >
                          ⚠ Human review required before action
                        </span>
                      ) : (
                        <span
                          data-testid="human-review-not-required"
                          className="inline-flex items-center rounded bg-surface px-2 py-1 text-xs font-medium text-navy/60"
                        >
                          Human review not required
                        </span>
                      )}
                    </div>
                  </button>
                </li>
              );
            })}
          </ul>
          </div>
          );
        }}
      />
    </PanelShell>
  );
}

export default RecommendedActionPanel;
