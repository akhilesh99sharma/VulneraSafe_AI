import StatusTag from "../StatusTag";
import { STATUS_TAGS } from "../../types/status";

/**
 * Status + alert-color legend (Req 14.3, 14.4).
 *
 * A compact key that tells the user how to read the two visual systems in the
 * app so tags are never ambiguous:
 *   1. The three provenance tags — OBSERVED / PREDICTED / SIMULATED — each shown
 *      via the real {@link StatusTag} so the legend swatch matches what appears
 *      on every value-bearing display (Req 14.3).
 *   2. The meaning of the reserved alert color: orange/red appears ONLY on an
 *      active alert condition (regulatory recall, human-review-required, a
 *      genuine high-risk threshold) and never decoratively (Req 14.4).
 *
 * Placed in the App shell footer so it is always available for interpreting
 * tags without competing with the panels for attention.
 */

const TAG_MEANINGS: Record<string, string> = {
  OBSERVED: "Empirical surveillance data.",
  PREDICTED: "Model output.",
  SIMULATED: "Synthetic scenario data — not real observations.",
};

export function StatusLegend() {
  return (
    <section
      data-testid="status-legend"
      aria-label="Legend: status tags and alert color"
      className="border-t border-navy/10 bg-surface-muted"
    >
      <div className="mx-auto flex max-w-7xl flex-col gap-3 px-6 py-4 text-xs text-navy/80 sm:flex-row sm:flex-wrap sm:items-center sm:gap-6">
        <span className="font-semibold uppercase tracking-wide text-navy/60">
          Legend
        </span>

        {STATUS_TAGS.map((tag) => (
          <span key={tag} className="flex items-center gap-2" data-testid="legend-status">
            <StatusTag status={tag} />
            <span>{TAG_MEANINGS[tag]}</span>
          </span>
        ))}

        <span className="flex items-center gap-2" data-testid="legend-alert">
          <span
            // The ONLY decorative-looking swatch is itself an explanation of the
            // reserved alert color, not a decorative use of it.
            aria-hidden="true"
            className="inline-block h-3 w-3 rounded-sm border-l-4 border-alert-danger bg-alert-danger/10"
          />
          <span>
            Orange / red marks an <span className="font-semibold">active alert</span>{" "}
            only — a verified regulatory recall, a required human review, or a
            genuine high-risk threshold. It is never decorative.
          </span>
        </span>
      </div>
    </section>
  );
}

export default StatusLegend;
