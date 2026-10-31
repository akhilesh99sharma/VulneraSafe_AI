import type { StatusTag as StatusTagValue } from "../types/artifacts";

/**
 * Renders exactly one provenance badge for a displayed value (Req 14.3):
 *   OBSERVED  — empirical / surveillance data        (navy, authoritative)
 *   PREDICTED — model output                          (teal)
 *   SIMULATED — synthetic / scenario data             (neutral slate, hatched —
 *                                                       clearly not real, but NOT
 *                                                       the reserved alert color)
 *
 * Exactly one tag is rendered per instance. None of the three use orange/red:
 * that palette is reserved strictly for active alert conditions (Req 14.4), so
 * a provenance tag never borrows the alert color decoratively.
 */

interface StatusTagProps {
  status: StatusTagValue;
}

const STYLES: Record<StatusTagValue, string> = {
  OBSERVED: "bg-navy/10 text-navy border-navy/30",
  PREDICTED: "bg-teal/10 text-teal-600 border-teal/30",
  // Neutral slate (not amber/orange) + dashed border reads as "synthetic / not
  // real" without using the reserved alert palette (Req 14.4).
  SIMULATED: "bg-slate-100 text-slate-600 border-slate-400 border-dashed",
};

export function StatusTag({ status }: StatusTagProps) {
  return (
    <span
      data-testid="status-tag"
      data-status={status}
      className={`inline-flex items-center rounded border px-2 py-0.5 text-xs font-semibold uppercase tracking-wide ${STYLES[status]}`}
    >
      {status}
    </span>
  );
}

export default StatusTag;
