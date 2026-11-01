/**
 * Single source of truth for risk bucketing + band colors.
 *
 * Risk is a 0..1 PREDICTED next-period elevated-positivity probability. It is
 * bucketed into named bands by fixed thresholds, and each band is shaded from
 * the TEAL ramp (never orange/red — theme discipline, Req 14.4). Both the
 * MapView choropleth/legend and the Risk Dashboard top-states pills import from
 * here so the bucketing + colors are identical in every place a risk is shown.
 */

import { riskToIntensity } from "../../../types/viewModels";

/** Grey used wherever a risk is absent ("No data"). */
export const NO_DATA_COLOR = "#e5e7eb";

/** Teal ramp stops (intensity 0..1 → hex). Teal/navy/neutral only. */
const TEAL_RAMP: Array<[number, string]> = [
  [0.0, "#e6f6f4"],
  [0.2, "#b3e3dd"],
  [0.4, "#6fcabf"],
  [0.6, "#2fa99b"],
  [0.8, "#0f8578"],
  [1.0, "#0b5f55"],
];

function lerpHex(a: string, b: string, t: number): string {
  const pa = [1, 3, 5].map((i) => parseInt(a.slice(i, i + 2), 16));
  const pb = [1, 3, 5].map((i) => parseInt(b.slice(i, i + 2), 16));
  const clamped = Math.max(0, Math.min(1, t));
  const ch = pa.map((c, i) => Math.round(c + (pb[i] - c) * clamped));
  return `#${ch.map((c) => c.toString(16).padStart(2, "0")).join("")}`;
}

/** Interpolated teal color for a 0..1 risk (used for choropleth fills + pills). */
export function colorForRisk(risk: number): string {
  const r = riskToIntensity(risk);
  let lo = TEAL_RAMP[0];
  let hi = TEAL_RAMP[TEAL_RAMP.length - 1];
  for (let i = 0; i < TEAL_RAMP.length - 1; i++) {
    if (r >= TEAL_RAMP[i][0] && r <= TEAL_RAMP[i + 1][0]) {
      lo = TEAL_RAMP[i];
      hi = TEAL_RAMP[i + 1];
      break;
    }
  }
  const span = hi[0] - lo[0] || 1;
  return lerpHex(lo[1], hi[1], (r - lo[0]) / span);
}

/**
 * Named risk band for a 0..1 probability. "No data" when null/undefined/NaN.
 * Thresholds: >=0.8 Very high, >=0.6 High, >=0.4 Moderate, >=0.2 Low,
 * >0 Very low, else No data.
 */
export function riskBandLabel(risk: number | null | undefined): string {
  if (risk === null || risk === undefined || Number.isNaN(risk)) return "No data";
  if (risk >= 0.8) return "Very high";
  if (risk >= 0.6) return "High";
  if (risk >= 0.4) return "Moderate";
  if (risk >= 0.2) return "Low";
  if (risk > 0) return "Very low";
  return "No data";
}

/** A legend band: display label + a representative midpoint color swatch. */
export interface RiskBand {
  label: string;
  /** Midpoint risk whose teal color represents the band (null ⇒ grey). */
  color: string;
}

/**
 * Ordered discrete legend bands (highest → lowest), matching
 * {@link riskBandLabel}. Each colored band uses the teal color of its midpoint;
 * "No data" uses the neutral grey.
 */
export const RISK_BANDS: RiskBand[] = [
  { label: "Very high", color: colorForRisk(0.9) },
  { label: "High", color: colorForRisk(0.7) },
  { label: "Moderate", color: colorForRisk(0.5) },
  { label: "Low", color: colorForRisk(0.3) },
  { label: "Very low", color: colorForRisk(0.1) },
  { label: "No data", color: NO_DATA_COLOR },
];
