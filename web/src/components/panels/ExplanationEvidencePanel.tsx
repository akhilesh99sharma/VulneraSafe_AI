import { useArtifact } from "../../data/hooks";
import { useSelection } from "../../state/selection";
import type { ProvenanceEntry, Recommendation } from "../../types/artifacts";
import {
  evaluateRecommendationGuard,
  findRecommendation,
  formatUncertainty,
  orNotAvailable,
} from "../../types/viewModels";
import EmptyState from "../EmptyState";
import StatusTag from "../StatusTag";
import PanelShell, { ArtifactBody } from "./PanelShell";

/**
 * Explanation / Evidence Panel (Req 12.8).
 *
 * For the recommendation currently selected in the Recommended Action Panel,
 * shows the source data (resolved from the recommendation's `evidence_refs`
 * against the `provenance` artifact), the uncertainty, and the limitations.
 * When nothing is selected, prompts the user to select a recommendation.
 */

export function ExplanationEvidencePanel() {
  const { recommendationTargetId } = useSelection();
  const recState = useArtifact<Recommendation[]>("recommendations");
  const provState = useArtifact<ProvenanceEntry[]>("provenance");

  return (
    <PanelShell title="Explanation / Evidence Panel"
      subtitle="Source data, uncertainty, and limitations"
      info="Select a recommendation to see WHY: its source dataset, coverage and access date, the quantified uncertainty, and the stated limitations. This is the audit trail behind each action.">
      <ArtifactBody
        state={recState}
        artifactName="recommendations"
        isEmpty={(recs) => recs.length === 0}
        emptyTitle="No recommendations to explain"
        emptyDetail="The recommendations artifact is present but empty."
        render={(recs) => {
          const rec = findRecommendation(recs, recommendationTargetId);
          if (!rec) {
            return (
              <EmptyState
                title="Select a recommendation"
                detail="Choose a recommendation to inspect its evidence, uncertainty, and limitations."
              />
            );
          }
          // Responsible-use guard (Req 16.5): a withheld MODEL rec never
          // renders its detail — mirror the Recommended Action Panel and show
          // the explanatory note instead.
          const guard = evaluateRecommendationGuard(rec);
          if (!guard.show) {
            return (
              <div
                data-testid="evidence-withheld"
                className="rounded border border-dashed border-navy/30 bg-surface-muted p-3 text-xs italic text-navy/70"
              >
                {guard.reason}
              </div>
            );
          }
          // Provenance may still be loading / failed independently.
          const provenance = provState.data ?? [];
          return <EvidenceDetail rec={rec} provenance={provenance} />;
        }}
      />
    </PanelShell>
  );
}

function EvidenceDetail({
  rec,
  provenance,
}: {
  rec: Recommendation;
  provenance: ProvenanceEntry[];
}) {
  // Resolve evidence references to provenance entries by source name/url.
  const resolved = rec.evidence_refs.map((ref) => ({
    ref,
    entry: provenance.find((p) => p.source === ref || p.url === ref) ?? null,
  }));

  // Limitations are drawn only from recorded fields — never invented.
  const limitations = Array.from(
    new Set([
      ...rec.constraints,
      ...resolved.flatMap(({ entry }) => entry?.known_biases ?? []),
    ]),
  );

  return (
    <div className="flex flex-col gap-3 text-xs" data-testid="evidence-detail">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-navy">{rec.action}</p>
        <StatusTag status={rec.status} />
      </div>

      <section>
        <h3 className="font-semibold text-navy/60">Source data</h3>
        {resolved.length > 0 ? (
          <ul className="mt-1 flex flex-col gap-2">
            {resolved.map(({ ref, entry }, i) => (
              <li
                key={`${ref}-${i}`}
                data-testid="evidence-ref"
                className="rounded border border-navy/10 bg-surface-muted p-2"
              >
                <p className="font-semibold text-navy">{orNotAvailable(entry?.source ?? ref)}</p>
                {entry ? (
                  <dl className="mt-1 grid grid-cols-[auto,1fr] gap-x-2 gap-y-0.5 text-navy/80">
                    <dt className="text-navy/50">Coverage</dt>
                    <dd>
                      {orNotAvailable(entry.geographic_coverage)} ·{" "}
                      {orNotAvailable(entry.temporal_coverage)}
                    </dd>
                    <dt className="text-navy/50">Access date</dt>
                    <dd>{orNotAvailable(entry.access_date)}</dd>
                    <dt className="text-navy/50">License</dt>
                    <dd>{orNotAvailable(entry.license)}</dd>
                  </dl>
                ) : (
                  <p className="mt-1 italic text-navy/50">
                    Referenced evidence not found in the provenance artifact.
                  </p>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 italic text-navy/50">No evidence references recorded.</p>
        )}
      </section>

      <section>
        <h3 className="font-semibold text-navy/60">Uncertainty</h3>
        <p className="mt-1 text-navy" data-testid="evidence-uncertainty">
          {formatUncertainty(rec.uncertainty)}
        </p>
      </section>

      <section>
        <h3 className="font-semibold text-navy/60">Limitations</h3>
        {limitations.length > 0 ? (
          <ul className="mt-1 list-disc pl-5 text-navy">
            {limitations.map((lim, i) => (
              <li key={`limitation-${i}`}>{lim}</li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 italic text-navy/50">No limitations recorded.</p>
        )}
      </section>
    </div>
  );
}

export default ExplanationEvidencePanel;
