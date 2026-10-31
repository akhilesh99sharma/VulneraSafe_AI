import { useEffect, useState } from "react";
import type { Manifest } from "../types/artifacts";
import { ArtifactLoadError, loadArtifact } from "./loader";

/**
 * React hooks over the artifact loader (Req 15.1, 15.3).
 *
 * Results are cached in a module-level map so each artifact is fetched at most
 * once per session. Each hook exposes `{ data, loading, error }`; panels read
 * `error` to show an `EmptyState` naming the failed artifact while OTHER
 * panels keep rendering their own successfully-loaded data (graceful
 * degradation).
 */

type CacheEntry = Promise<unknown>;
const cache = new Map<string, CacheEntry>();

/** Shared result shape for every artifact hook. */
export interface ArtifactState<T> {
  data: T | null;
  loading: boolean;
  error: ArtifactLoadError | null;
}

/**
 * Load (and cache) an artifact exactly once, returning the in-flight or
 * resolved promise. Rejected loads are evicted so a later retry can re-fetch.
 */
function getCached<T>(name: string): Promise<T> {
  const existing = cache.get(name);
  if (existing) return existing as Promise<T>;

  const promise = loadArtifact<T>(name).catch((err) => {
    cache.delete(name);
    throw err;
  });
  cache.set(name, promise);
  return promise;
}

/** Normalize any thrown value into an ArtifactLoadError naming the artifact. */
function toArtifactError(name: string, err: unknown): ArtifactLoadError {
  if (err instanceof ArtifactLoadError) return err;
  return new ArtifactLoadError(name, "unexpected error", err);
}

/** Generic artifact hook. `name` is the logical artifact name (no extension). */
export function useArtifact<T>(name: string): ArtifactState<T> {
  const [state, setState] = useState<ArtifactState<T>>({
    data: null,
    loading: true,
    error: null,
  });

  useEffect(() => {
    let active = true;
    setState({ data: null, loading: true, error: null });

    getCached<T>(name)
      .then((data) => {
        if (active) setState({ data, loading: false, error: null });
      })
      .catch((err: unknown) => {
        if (active)
          setState({ data: null, loading: false, error: toArtifactError(name, err) });
      });

    return () => {
      active = false;
    };
  }, [name]);

  return state;
}

/** Convenience hook for the top-level manifest that gates all panels. */
export function useManifest(): ArtifactState<Manifest> {
  return useArtifact<Manifest>("manifest");
}

/** Test/HMR helper: clear the module-level artifact cache. */
export function clearArtifactCache(): void {
  cache.clear();
}
