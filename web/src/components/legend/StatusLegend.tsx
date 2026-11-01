import StatusTag from "../StatusTag";
import { STATUS_TAGS } from "../../types/status";

/**
 * Status + alert-color legend (Req 14.3, 14.4).
 *
 * A compact key that tells the user how to read the two visual systems in the
 * app so tags are never ambiguous:
 *   1. The three provenance tags - OBSERVED / PREDICTED / SIMULATED - each shown
 *      via the real {@link StatusTag} so the legend swatch matches what appears
 *      on every value-bearing display (Req 14.3).
 *   2. The meaning of the reserved alert color: orange/red appears ONLY on an
 *      active alert condition (regulatory recall, human-review-required, a genuine
 *      high-risk threshold) and never decoratively (Req 14.4).
 *
 * Two presentation variants, sharing one set of rows and testids:
 *   - "footer" (default): a full-width horizontal bar with its own section chrome.
 *   - "rail": a compact vertically-stacked block for a narrow card body (e.g.
 *     under the Risk Dashboard top-states table), with no full-width wrapper.
 */

const TAG_MEANINGS: Record<string, string> = {
  OBSERVED: "Empirical surveillance data.",
  PREDICTED: "Model output.",
  SIMULATED: "Synthetic scenario data - not real observations.",
};

export interface StatusLegendProps {
  /** "footer" (default) = full-width bar; "rail" = compact stacked block. */
  variant?: "footer" | "rail" | "bare";
}

/** The shared legend rows (same testids in both variants). */
function LegendRows() {
  return (
    <>
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
          className="inline-block h-3 w-3 shrink-0 rounded-sm border-l-4 border-alert-danger bg-alert-danger/10"
        />
        <span>
          Orange / red marks an <span className="font-semibold">active alert</span>{" "}
          only{"\u2014"} a verified regulatory recall, a required human review, or a
          genuine high-risk threshold. It is never decorative.
        </span>
      </span>
    </>
  );
}

export function StatusLegend({ variant = "footer" }: StatusLegendProps = {}) {
  if (variant === "bare") {
    // Just the stacked rows - no section chrome or heading; the parent
    // SectionCard supplies the card and the "Legend" title.
    return (
      <div
        data-testid="status-legend"
        aria-label="Legend: status tags and alert color"
        className="flex flex-col gap-2 text-[11px] leading-relaxed text-navy/80"
      >
        <LegendRows />
      </div>
    );
  }

  if (variant === "rail") {
    // Compact, vertically-stacked block for a narrow card body - no full-width
    // wrapper or footer border. Same rows and testids as the footer variant.
    return (
      <section
        data-testid="status-legend"
        aria-label="Legend: status tags and alert color"
        className="flex flex-col gap-2 rounded-lg border border-navy/5 bg-surface-muted px-3 py-3 text-[11px] leading-relaxed text-navy/80"
      >
        <span className="font-semibold uppercase tracking-wide text-navy/60">
          Legend
        </span>
        <LegendRows />
      </section>
    );
  }

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
        <LegendRows />
      </div>
    </section>
  );
}

export default StatusLegend;
