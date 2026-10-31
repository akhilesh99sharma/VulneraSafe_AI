import type { AlertSource } from "../types/artifacts";

/**
 * Visually distinguishes a verified regulatory recall from a model-derived
 * alert (Req 16.5, 16.6) so a regulatory recall never reads as a model guess:
 *   REGULATORY — strong, authoritative (navy background, red accent border)
 *   MODEL      — softer, advisory (teal, subdued)
 */

interface AlertBadgeProps {
  source: AlertSource;
}

const STYLES: Record<AlertSource, string> = {
  REGULATORY:
    "bg-navy text-white border-l-4 border-alert-danger shadow-sm font-bold",
  MODEL: "bg-teal/10 text-teal-600 border border-teal/40 font-medium",
};

const LABELS: Record<AlertSource, string> = {
  REGULATORY: "Regulatory Recall",
  MODEL: "Model Alert",
};

export function AlertBadge({ source }: AlertBadgeProps) {
  return (
    <span
      data-testid="alert-badge"
      data-source={source}
      className={`inline-flex items-center rounded px-2.5 py-1 text-xs uppercase tracking-wide ${STYLES[source]}`}
    >
      {LABELS[source]}
    </span>
  );
}

export default AlertBadge;
