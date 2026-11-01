import { useEffect, useState } from "react";
import { useArtifact } from "../../data/hooks";
import { useSelection } from "../../state/selection";
import type { AttentionQueueItem } from "../../types/artifacts";
import {
  filterAttentionByPathogen,
  formatRisk,
  orderAttentionQueue,
} from "../../types/viewModels";
import { LENS_EMPHASIS } from "../../types/lens";
import type { PopulationLens } from "../../state/selection";
import EmptyState from "../EmptyState";
import PanelShell, { ArtifactBody } from "./PanelShell";

/**
 * Prioritized Attention Queue (Req 12.4).
 *
 * Lists items highest -> lowest priority. Shows the top 5 by default and
 * reveals 10 more per "Load more" click so the panel stays compact while the
 * full ranked list remains reachable. A small risk meter makes the ranking
 * readable at a glance.
 */

const INITIAL_VISIBLE = 10;
const PAGE = 10;

/**
 * Human-readable label for each lens, used only for the honest re-ranking
 * banner. The emphasized pathogens themselves come from the shared
 * `LENS_EMPHASIS` map (one source of truth with the lens picker).
 */
const LENS_LABEL: Record<Exclude<PopulationLens, null>, string> = {
  pregnancy: "Pregnancy & newborns",
  under5: "Children under 5",
  elderly: "Adults 65+",
};

/**
 * STABLE re-rank for an active lens (Layer 2): items whose pathogen is in the
 * lens's emphasized set are surfaced first, preserving the existing risk order
 * within each group. This changes ONLY display order — never an item's `risk`
 * or `status`. When no lens is active, callers skip this and ordering is
 * identical to the risk-ranked, pathogen-filtered list.
 */
function reRankForLens(
  items: AttentionQueueItem[],
  lens: Exclude<PopulationLens, null>,
): AttentionQueueItem[] {
  const emphasized = new Set(LENS_EMPHASIS[lens]);
  const front: AttentionQueueItem[] = [];
  const back: AttentionQueueItem[] = [];
  for (const item of items) {
    (emphasized.has(item.pathogen) ? front : back).push(item);
  }
  return [...front, ...back];
}

/**
 * Is a `triggering_condition` just the auto-generated probability boilerplate?
 * The percentage is already shown on the row, so a machine restatement of it
 * (e.g. "predicted elevated-risk probability 0.82") is redundant noise and is
 * suppressed. A genuine human reason ("confirmed recall nearby", "weather
 * anomaly") is NOT boilerplate and is always shown. Case-insensitive.
 */
export function isBoilerplateTrigger(text: string | null | undefined): boolean {
  if (!text) return false;
  return text.toLowerCase().includes("predicted elevated-risk probability");
}

export function AttentionQueue() {
  const { pathogen, lens } = useSelection();
  const state = useArtifact<AttentionQueueItem[]>("attention_queue");
  const [visible, setVisible] = useState(INITIAL_VISIBLE);

  // Reset the window whenever the pathogen filter OR the active lens changes.
  useEffect(() => setVisible(INITIAL_VISIBLE), [pathogen, lens]);

  // Emphasized pathogen set for the active lens (empty when no lens) — used to
  // tag cards and compose the honest re-ranking banner.
  const emphasizedSet = lens ? new Set(LENS_EMPHASIS[lens]) : null;

  return (
    <PanelShell title="Prioritized Attention Queue"
      subtitle="Highest predicted-risk states first"
      info="A ranked worklist by PREDICTED risk (highest first) — where to focus limited attention. Every item is a model prioritization, never a claim that a specific product is contaminated.">
      <ArtifactBody
        state={state}
        artifactName="attention_queue"
        isEmpty={(items) => items.length === 0}
        emptyTitle="No items to triage"
        emptyDetail="The attention_queue artifact is present but empty."
        render={(items) => {
          const filtered = filterAttentionByPathogen(orderAttentionQueue(items), pathogen);
          // When a lens is active, STABLE-SORT emphasized pathogens to the
          // front (risk order preserved within each group). With no lens, the
          // ordering is identical to the risk-ranked, pathogen-filtered list.
          const ordered = lens ? reRankForLens(filtered, lens) : filtered;
          if (ordered.length === 0) {
            return (
              <EmptyState
                title="No items for the selected pathogen"
                detail={`No attention-queue items for ${pathogen}.`}
              />
            );
          }
          const shown = ordered.slice(0, visible);
          const remaining = ordered.length - shown.length;
          const nextBatch = Math.min(PAGE, remaining);
          return (
            <div className="flex flex-col gap-2.5">
              <p
                data-testid="attention-provenance-note"
                className="text-[11px] leading-relaxed text-navy/50"
              >
                All items are model prioritizations (PREDICTED), never
                contamination claims.
              </p>
              {lens ? (
                <div
                  data-testid="attention-lens-banner"
                  className="rounded-lg border border-teal/30 bg-teal/5 px-3 py-2 text-[11px] leading-relaxed text-navy/80"
                >
                  Re-ranked for the{" "}
                  <span className="font-semibold text-navy">{LENS_LABEL[lens]}</span>{" "}
                  lens —{" "}
                  <span className="font-semibold text-navy">
                    {LENS_EMPHASIS[lens].join(", ")}
                  </span>{" "}
                  surfaced first. Predicted risk values are unchanged; only
                  prioritization order reflects who is most vulnerable.
                </div>
              ) : null}

              <div className="flex items-center justify-between text-[11px] text-navy/60">
                <span>
                  Showing <span className="font-semibold text-navy">{shown.length}</span> of{" "}
                  <span className="font-semibold text-navy">{ordered.length}</span>
                </span>
                <span className="rounded-full bg-navy/5 px-2 py-0.5 font-semibold text-navy/70">
                  ranked by predicted risk
                </span>
              </div>

              <ol data-testid="attention-queue-list" className="flex flex-col gap-2">
                {shown.map((item) => (
                  <li
                    key={`${item.rank}:${item.target_id}`}
                    data-testid="attention-queue-item"
                    data-rank={item.rank}
                    className="rounded-lg border border-navy/10 bg-white p-3 shadow-sm transition hover:border-navy/20 hover:shadow"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex min-w-0 items-center gap-2">
                        <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-navy text-[11px] font-bold text-white">
                          {item.rank}
                        </span>
                        <div className="min-w-0">
                          <p className="flex items-center gap-1.5 truncate text-sm font-semibold text-navy">
                            <span className="truncate">
                              {item.pathogen} · {item.region}
                            </span>
                            {emphasizedSet?.has(item.pathogen) ? (
                              <span
                                data-testid="attention-emphasized-tag"
                                className="shrink-0 rounded-full border border-teal/40 bg-teal/10 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-teal-700"
                              >
                                emphasized
                              </span>
                            ) : null}
                          </p>
                        </div>
                      </div>
                      <span className="shrink-0 text-sm font-bold text-navy">
                        {formatRisk(item.risk)}
                      </span>
                    </div>
                    {isBoilerplateTrigger(item.triggering_condition) ? null : (
                      <p className="mt-1.5 text-[11px] leading-relaxed text-navy/60">
                        {item.triggering_condition}
                      </p>
                    )}
                  </li>
                ))}
              </ol>

              {remaining > 0 ? (
                <button
                  type="button"
                  data-testid="attention-load-more"
                  onClick={() => setVisible((v) => v + PAGE)}
                  className="mx-auto rounded-lg border border-teal/40 bg-teal/5 px-4 py-2 text-xs font-semibold text-teal-700 transition hover:bg-teal/10"
                >
                  Load {nextBatch} more · {remaining} remaining
                </button>
              ) : ordered.length > INITIAL_VISIBLE ? (
                <button
                  type="button"
                  data-testid="attention-collapse"
                  onClick={() => setVisible(INITIAL_VISIBLE)}
                  className="mx-auto rounded-lg border border-navy/20 px-4 py-2 text-xs font-semibold text-navy/70 transition hover:bg-surface-muted"
                >
                  Show top {INITIAL_VISIBLE} only
                </button>
              ) : null}
            </div>
          );
        }}
      />
    </PanelShell>
  );
}

export default AttentionQueue;
