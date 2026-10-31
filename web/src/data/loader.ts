/**
 * Artifact data-loading layer (Req 15.1, 15.2, 15.3).
 *
 * All artifacts are static JSON served from `web/public/data`. Fetches are
 * resolved relative to `import.meta.env.BASE_URL` so the GitHub Pages base
 * path (`/VulneraSafe_AI/`) is respected and NO request ever targets a
 * non-local origin — the app's static guarantee (Req 15.2).
 */

/** Error that always names the artifact it failed on (Req 15.3). */
export class ArtifactLoadError extends Error {
  readonly artifact: string;
  readonly cause?: unknown;

  constructor(artifact: string, reason: string, cause?: unknown) {
    super(`Failed to load artifact "${artifact}": ${reason}`);
    this.name = "ArtifactLoadError";
    this.artifact = artifact;
    this.cause = cause;
  }
}

/**
 * Build the fully-qualified, same-origin URL for an artifact. BASE_URL always
 * ends with a trailing slash in Vite, so simple concatenation is safe.
 */
export function artifactUrl(name: string): string {
  const base = import.meta.env.BASE_URL ?? "/";
  return `${base}data/${name}.json`;
}

/**
 * Fetch and parse a single artifact by logical name (e.g. "manifest",
 * "risk_map"). Throws a typed {@link ArtifactLoadError} naming the artifact on
 * any failure: network/404 (missing/unreadable) or malformed JSON (invalid).
 */
export async function loadArtifact<T>(name: string): Promise<T> {
  const url = artifactUrl(name);

  let response: Response;
  try {
    response = await fetch(url);
  } catch (err) {
    throw new ArtifactLoadError(name, "artifact is unreadable (network error)", err);
  }

  if (!response.ok) {
    throw new ArtifactLoadError(
      name,
      `artifact is missing or unreadable (HTTP ${response.status})`,
    );
  }

  const text = await response.text();
  try {
    return JSON.parse(text) as T;
  } catch (err) {
    throw new ArtifactLoadError(name, "artifact is invalid (malformed JSON)", err);
  }
}
