/**
 * PerformanceLabel chip (Task 7.1 — Req 16.8; design.md "Historical vs
 * prospective").
 *
 * Tags a reported performance measure as either `historical` (an association
 * measured on past data) or `prospective` (forward-looking predictive
 * performance) so a viewer can never mistake a backward-looking association
 * for prospective skill. Mirrors the Python `label_performance` tagging in
 * `src/responsible.py`.
 *
 * This is a neutral provenance-style chip on the navy/teal scientific theme —
 * it is NOT an alert, so it must never use the reserved orange/red alert
 * colors (themeDiscipline test).
 */

export type PerformanceKind = "historical" | "prospective";

interface PerformanceLabelProps {
  kind: PerformanceKind;
  /** Optional clarifying text shown alongside the chip (e.g. the metric name). */
  note?: string;
}

const STYLES: Record<PerformanceKind, string> = {
  historical: "bg-navy/5 text-navy border border-navy/30",
  prospective: "bg-teal/10 text-teal-700 border border-teal/40",
};

const LABELS: Record<PerformanceKind, string> = {
  historical: "Historical",
  prospective: "Prospective",
};

export function PerformanceLabel({ kind, note }: PerformanceLabelProps) {
  return (
    <span
      data-testid="performance-label"
      data-kind={kind}
      title={
        kind === "historical"
          ? "Association measured on historical data"
          : "Forward-looking prospective predictive performance"
      }
      className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${STYLES[kind]}`}
    >
      {LABELS[kind]}
      {note ? (
        <span className="font-normal normal-case text-navy/60">· {note}</span>
      ) : null}
    </span>
  );
}

export default PerformanceLabel;
