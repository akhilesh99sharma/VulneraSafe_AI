import { createContext, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";

/**
 * Lifted selection state shared across the five mandatory panels (Req 12).
 *
 * A single React context holds the currently-selected pathogen, region, and
 * recommendation so that, for example, selecting a region in the Current Risk
 * Overview updates its time-series (Req 12.2) and selecting a recommendation
 * in the Recommended Action Panel drives the Explanation / Evidence Panel
 * (Req 12.8). The context carries only identifiers — panels read their own
 * artifacts via `useArtifact` and filter by these keys.
 */

export type PopulationLens = "pregnancy" | "under5" | "elderly" | null;

export interface Selection {
  /** Currently selected pathogen (e.g. "Salmonella"), or null for "all". */
  pathogen: string | null;
  /** Currently selected region code (e.g. a US state / FSIS region), or null. */
  region: string | null;
  /**
   * Identifier of the recommendation currently under inspection. We key on the
   * recommendation's `target_id` since the contract carries no dedicated id.
   */
  recommendationTargetId: string | null;
  /** Active vulnerable-population lens (Layer 2), or null for none. */
  lens: PopulationLens;
}

export interface SelectionContextValue extends Selection {
  setPathogen: (pathogen: string | null) => void;
  setRegion: (region: string | null) => void;
  setRecommendationTargetId: (targetId: string | null) => void;
  setLens: (lens: PopulationLens) => void;
}

const DEFAULT_SELECTION: Selection = {
  pathogen: null,
  region: null,
  recommendationTargetId: null,
  lens: null,
};

const SelectionContext = createContext<SelectionContextValue | null>(null);

interface SelectionProviderProps {
  children: ReactNode;
  /** Optional initial selection, primarily for tests. */
  initial?: Partial<Selection>;
}

export function SelectionProvider({ children, initial }: SelectionProviderProps) {
  const [pathogen, setPathogen] = useState<string | null>(
    initial?.pathogen ?? DEFAULT_SELECTION.pathogen,
  );
  const [region, setRegion] = useState<string | null>(
    initial?.region ?? DEFAULT_SELECTION.region,
  );
  const [recommendationTargetId, setRecommendationTargetId] = useState<string | null>(
    initial?.recommendationTargetId ?? DEFAULT_SELECTION.recommendationTargetId,
  );
  const [lens, setLens] = useState<PopulationLens>(
    initial?.lens ?? DEFAULT_SELECTION.lens,
  );

  const value = useMemo<SelectionContextValue>(
    () => ({
      pathogen,
      region,
      recommendationTargetId,
      lens,
      setPathogen,
      setRegion,
      setRecommendationTargetId,
      setLens,
    }),
    [pathogen, region, recommendationTargetId, lens],
  );

  return <SelectionContext.Provider value={value}>{children}</SelectionContext.Provider>;
}

/** Access the shared selection. Throws if used outside a {@link SelectionProvider}. */
export function useSelection(): SelectionContextValue {
  const ctx = useContext(SelectionContext);
  if (!ctx) {
    throw new Error("useSelection must be used within a <SelectionProvider>");
  }
  return ctx;
}
