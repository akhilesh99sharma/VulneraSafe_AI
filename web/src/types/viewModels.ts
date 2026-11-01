/**
 * View-model helpers for the five mandatory panels (Req 12).
 *
 * These are pure functions over the artifact contract types in
 * `./artifacts`. They keep panels thin: filtering by the shared selection,
 * ordering the attention queue, and formatting numbers/labels consistently.
 * No fabricated values are ever produced — a missing field yields an explicit
 * not-available marker, never an invented number (Req 14.2, 14.6).
 */

import type {
  AttentionQueueItem,
  Recommendation,
  RiskMapFeature,
  RiskTimeseriesPoint,
} from "./artifacts";

/** Explicit not-available marker used wherever a value is absent (Req 14.2). */
export const NOT_AVAILABLE = "N/A";

/** Format a 0..1 risk/probability as a percentage, or N/A when absent. */
export function formatRisk(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return NOT_AVAILABLE;
  }
  return `${(value * 100).toFixed(1)}%`;
}

/** Format a plain number to a fixed precision, or N/A when absent. */
export function formatNumber(
  value: number | null | undefined,
  digits = 2,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return NOT_AVAILABLE;
  }
  return value.toFixed(digits);
}

/**
 * Format a symmetric uncertainty value (± interval) as a percentage band, or
 * N/A when absent. Used by the Explanation / Evidence Panel (Req 12.8).
 */
export function formatUncertainty(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return NOT_AVAILABLE;
  }
  return `± ${(value * 100).toFixed(1)}%`;
}

/** Non-empty string or the not-available marker. */
export function orNotAvailable(value: string | null | undefined): string {
  return value && value.trim().length > 0 ? value : NOT_AVAILABLE;
}

/**
 * Filter risk-map features to the selected pathogen (null = all pathogens).
 * Region selection does not filter the map — it highlights a region instead.
 */
export function filterMapByPathogen(
  features: RiskMapFeature[],
  pathogen: string | null,
): RiskMapFeature[] {
  if (!pathogen) return features;
  return features.filter((f) => f.pathogen === pathogen);
}

/**
 * Build a `RiskMapFeature`-shaped list of OBSERVED latest-period positivity per
 * (pathogen, region) from the `risk_timeseries` artifact, for the map's
 * "Observed" view toggle.
 *
 * Honesty: this is a DIFFERENT quantity from the predicted `risk_map` — it is
 * the measured positivity of the chronologically LATEST point whose status is
 * "OBSERVED" for each (pathogen, region). States with no OBSERVED point simply
 * do not appear (the map renders them as neutral "No data"); no value is
 * fabricated. `risk` carries the observed `value`, `uncertainty` is the
 * half-width of the CI (`(ci_high - ci_low) / 2`) when both bounds are present
 * (else 0), and `status` is "OBSERVED" so every downstream label reads honestly.
 */
export function observedMapFromTimeseries(
  points: RiskTimeseriesPoint[],
): RiskMapFeature[] {
  // Keep only genuine OBSERVED points, then pick the latest period per key.
  const latest = new Map<string, RiskTimeseriesPoint>();
  for (const p of points) {
    if (p.status !== "OBSERVED") continue;
    const key = `${p.pathogen}\u0000${p.region}`;
    const prev = latest.get(key);
    if (!prev || p.period.localeCompare(prev.period) > 0) latest.set(key, p);
  }
  const features: RiskMapFeature[] = [];
  for (const p of latest.values()) {
    const hasCi =
      typeof p.ci_low === "number" &&
      typeof p.ci_high === "number" &&
      !Number.isNaN(p.ci_low) &&
      !Number.isNaN(p.ci_high);
    features.push({
      region: p.region,
      pathogen: p.pathogen,
      period: p.period,
      risk: p.value,
      uncertainty: hasCi ? (p.ci_high - p.ci_low) / 2 : 0,
      status: "OBSERVED",
      data_freshness: p.period,
    });
  }
  return features;
}

/**
 * Select the time-series for a given region (and optional pathogen), sorted
 * chronologically by ISO period string. Returns [] when there is no dated
 * data for the selection so the panel can show an empty-state (Req 12.3).
 */
export function timeseriesForRegion(
  points: RiskTimeseriesPoint[],
  region: string | null,
  pathogen: string | null,
): RiskTimeseriesPoint[] {
  const filtered = points.filter((p) => {
    if (region && p.region !== region) return false;
    if (pathogen && p.pathogen !== pathogen) return false;
    return true;
  });
  return [...filtered].sort((a, b) => a.period.localeCompare(b.period));
}

/**
 * Order attention-queue items highest → lowest priority (Req 12.4). Lower
 * `rank` means higher priority, so ascending rank is highest-first. Ties fall
 * back to higher risk first. Does not mutate the input.
 */
export function orderAttentionQueue(
  items: AttentionQueueItem[],
): AttentionQueueItem[] {
  return [...items].sort((a, b) => {
    if (a.rank !== b.rank) return a.rank - b.rank;
    return b.risk - a.risk;
  });
}

/**
 * Filter attention-queue items by the selected pathogen (null = all), keeping
 * priority order. Applied after {@link orderAttentionQueue}.
 */
export function filterAttentionByPathogen(
  items: AttentionQueueItem[],
  pathogen: string | null,
): AttentionQueueItem[] {
  if (!pathogen) return items;
  return items.filter((i) => i.pathogen === pathogen);
}

/**
 * Responsible-use guard mirroring the Python
 * `withhold_unsupported_model_recommendation` in `src/responsible.py`
 * (Req 16.4, 16.5, 16.6).
 *
 * A MODEL recommendation whose `uncertainty` is null/NaN OR whose
 * `evidence_refs` is empty must be WITHHELD — the UI renders an explanatory
 * "withheld — insufficient evidence/uncertainty" note instead of the
 * recommendation. A REGULATORY recommendation is ALWAYS shown (the regulatory
 * track is independent of model uncertainty). The Python exporter normally
 * drops unsupported MODEL recs before they reach the artifact; this guard is
 * the belt-and-suspenders mirror so the UI never renders one even if present.
 */

/** Explanatory note shown in place of a withheld MODEL recommendation. */
export const WITHHELD_NOTE =
  "Withheld — insufficient evidence/uncertainty: this model-generated recommendation cannot be shown because required supporting evidence or a quantified uncertainty measure is unavailable.";

function hasQuantifiedUncertainty(value: number | null | undefined): boolean {
  return value !== null && value !== undefined && !Number.isNaN(value);
}

function hasSupportingEvidence(refs: string[] | null | undefined): boolean {
  return Array.isArray(refs) && refs.some((r) => r && r.trim().length > 0);
}

/**
 * Decide whether a recommendation may be shown. Returns `{ show: true }` when
 * it may render, or `{ show: false, reason }` with the explanatory note when a
 * MODEL recommendation lacks uncertainty or evidence. REGULATORY always shows.
 */
export function evaluateRecommendationGuard(
  rec: Recommendation,
): { show: true } | { show: false; reason: string } {
  if (rec.alert_source === "REGULATORY") {
    return { show: true };
  }
  const ok =
    hasQuantifiedUncertainty(rec.uncertainty) &&
    hasSupportingEvidence(rec.evidence_refs);
  return ok ? { show: true } : { show: false, reason: WITHHELD_NOTE };
}

/** Convenience boolean form of {@link evaluateRecommendationGuard}. */
export function isRecommendationShowable(rec: Recommendation): boolean {
  return evaluateRecommendationGuard(rec).show;
}

/** Find the recommendation currently selected for the Evidence Panel. */
export function findRecommendation(
  recommendations: Recommendation[],
  targetId: string | null,
): Recommendation | null {
  if (!targetId) return null;
  return recommendations.find((r) => r.target_id === targetId) ?? null;
}

/** Simple ascending-magnitude domain for a risk color/opacity scale (0..1). */
export function riskToIntensity(risk: number): number {
  if (Number.isNaN(risk)) return 0;
  return Math.min(1, Math.max(0, risk));
}
