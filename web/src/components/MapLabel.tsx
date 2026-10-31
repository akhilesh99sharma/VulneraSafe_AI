import type { ReactNode } from "react";
import type { StatusTag as StatusTagValue } from "../types/artifacts";
import { NOT_AVAILABLE } from "../types/viewModels";
import StatusTag from "./StatusTag";

/**
 * Risk-map label block (Req 14.1, 14.2).
 *
 * Every risk map in the app MUST be headed by this block, which names the six
 * mandatory fields:
 *   1. pathogen
 *   2. geography
 *   3. reporting period
 *   4. model-or-surveillance status (rendered as a single StatusTag, Req 14.3)
 *   5. uncertainty
 *   6. data freshness
 *
 * None of the six may be left blank (Req 14.1). For any field whose value is
 * unavailable, an EXPLICIT not-available indicator ("—" with a
 * `title="not available"`) is rendered rather than an empty cell (Req 14.2).
 * No value is ever fabricated — callers pass the artifact's own values and a
 * missing one becomes the not-available indicator, never an invented number
 * (Req 14.6).
 *
 * This is a reusable header so later analytical views (multi-pathogen explorer,
 * Vulnerable Population Lens, forecast replay) can label their maps identically.
 */

export interface MapLabelProps {
  /** Pathogen the map depicts (e.g. "Salmonella"). */
  pathogen?: string | null;
  /** Geography covered (e.g. "US states", "FSIS regions", a selected region). */
  geography?: string | null;
  /** Reporting period (ISO month/quarter string). */
  period?: string | null;
  /**
   * Model-or-surveillance status for the map as a whole. When present it is
   * rendered as a single StatusTag (OBSERVED = surveillance, PREDICTED = model,
   * SIMULATED = scenario). When absent, a not-available indicator is shown.
   */
  status?: StatusTagValue | null;
  /**
   * Preformatted uncertainty string (e.g. "± 8.0%"). The caller formats it via
   * `formatUncertainty` so a missing value already arrives as the N/A marker.
   */
  uncertainty?: string | null;
  /** Data-freshness marker (e.g. the latest observation date). */
  dataFreshness?: string | null;
}

/** Explicit not-available indicator for a missing field (Req 14.2). */
function NotAvailable() {
  return (
    <span
      data-testid="map-label-na"
      title="not available"
      aria-label="not available"
      className="text-navy/40"
    >
      —
    </span>
  );
}

/** Render a text value, or the not-available indicator when it is absent. */
function fieldValue(value: string | null | undefined): ReactNode {
  if (value === null || value === undefined) return <NotAvailable />;
  const trimmed = value.trim();
  if (trimmed.length === 0 || trimmed === NOT_AVAILABLE) return <NotAvailable />;
  return <span className="font-semibold text-navy">{trimmed}</span>;
}

/** One labeled cell in the label block. */
function Field({
  label,
  testId,
  children,
}: {
  label: string;
  testId: string;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col" data-testid={testId}>
      <dt className="text-[10px] uppercase tracking-wide text-navy/50">{label}</dt>
      <dd className="text-xs">{children}</dd>
    </div>
  );
}

export function MapLabel({
  pathogen,
  geography,
  period,
  status,
  uncertainty,
  dataFreshness,
}: MapLabelProps) {
  return (
    <dl
      data-testid="map-label"
      aria-label="Risk map labels"
      className="mb-3 grid grid-cols-2 gap-x-4 gap-y-2 rounded border border-navy/10 bg-surface-muted px-3 py-2 sm:grid-cols-3"
    >
      <Field label="Pathogen" testId="map-label-pathogen">
        {fieldValue(pathogen)}
      </Field>

      <Field label="Geography" testId="map-label-geography">
        {fieldValue(geography)}
      </Field>

      <Field label="Reporting period" testId="map-label-period">
        {fieldValue(period)}
      </Field>

      <Field label="Status" testId="map-label-status">
        {status ? <StatusTag status={status} /> : <NotAvailable />}
      </Field>

      <Field label="Uncertainty" testId="map-label-uncertainty">
        {fieldValue(uncertainty)}
      </Field>

      <Field label="Source data accessed" testId="map-label-freshness">
        {fieldValue(dataFreshness)}
      </Field>
    </dl>
  );
}

export default MapLabel;
