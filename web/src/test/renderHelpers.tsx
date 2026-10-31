import type { ReactElement } from "react";
import { render } from "@testing-library/react";
import { vi } from "vitest";
import { SelectionProvider } from "../state/selection";
import type { Selection } from "../state/selection";
import { clearArtifactCache } from "../data/hooks";

/**
 * Shared helpers for panel render tests (task 6.2 companion to 6.1).
 *
 * The artifact loader calls the global `fetch` and caches results in a
 * module-level map, so each test installs a fake `fetch` and clears the cache
 * first. `artifactMap` maps a logical artifact name ("risk_map") to the JSON
 * value its `/data/<name>.json` URL should resolve to; any name not present
 * resolves to a 404 so panels exercise their load-failure path.
 */

export function installArtifactFetch(artifactMap: Record<string, unknown>): void {
  clearArtifactCache();
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const match = url.match(/data\/([^/]+)\.json$/);
    const name = match?.[1];
    if (name && name in artifactMap) {
      return new Response(JSON.stringify(artifactMap[name]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response("not found", { status: 404 });
  });
  // jsdom has no fetch; assign it for the loader to use.
  vi.stubGlobal("fetch", fetchMock);
}

/** Render a UI node inside a SelectionProvider with optional initial selection. */
export function renderWithSelection(
  ui: ReactElement,
  initial?: Partial<Selection>,
) {
  return render(<SelectionProvider initial={initial}>{ui}</SelectionProvider>);
}
