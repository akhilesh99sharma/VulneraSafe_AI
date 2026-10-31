/**
 * Shared source of truth for the Vulnerable-Population Lens emphasis.
 *
 * The Vulnerable-Population Lens re-frames the dashboard around a vulnerable
 * group WITHOUT changing any hazard prediction (Layer 1 is untouched). The one
 * thing it legitimately changes is PRIORITIZATION order: the pathogens most
 * relevant to the selected group are surfaced first in the Prioritized
 * Attention Queue. Both the lens picker (`VulnerablePopulationLens`) and the
 * queue (`AttentionQueue`) read this map so the emphasized set never drifts
 * between the two components.
 *
 * Predicted risk values are NEVER altered by a lens — only the display order of
 * the already risk-ranked, pathogen-filtered list.
 */

import type { PopulationLens } from "../state/selection";

/**
 * Pathogens emphasized by each lens, highest relevance first. Keyed by the
 * non-null lens ids so every selectable lens has an entry.
 */
export const LENS_EMPHASIS: Record<Exclude<PopulationLens, null>, string[]> = {
  pregnancy: ["Listeria"],
  under5: ["STEC", "Salmonella"],
  elderly: ["Listeria", "Salmonella", "STEC"],
};
