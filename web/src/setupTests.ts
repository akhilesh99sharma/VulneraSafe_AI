// Vitest + Testing Library setup. Registers jest-dom matchers (e.g.
// toBeInTheDocument) and auto-cleans the DOM between tests.
import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
});

// jsdom lacks these URL methods that maplibre-gl touches at import time.
if (typeof window !== "undefined" && window.URL) {
  if (typeof window.URL.createObjectURL !== "function") {
    // @ts-expect-error jsdom polyfill
    window.URL.createObjectURL = () => "blob:mock";
  }
  if (typeof window.URL.revokeObjectURL !== "function") {
    // @ts-expect-error jsdom polyfill
    window.URL.revokeObjectURL = () => {};
  }
}

// jsdom does not implement IntersectionObserver. Landing.tsx's scroll-reveal
// hook constructs one at mount, so without this stub rendering <App> throws
// "ReferenceError: IntersectionObserver is not defined".
if (
  typeof globalThis !== "undefined" &&
  typeof (globalThis as any).IntersectionObserver === "undefined"
) {
  class IntersectionObserverStub {
    readonly root = null;
    readonly rootMargin = "";
    readonly thresholds: ReadonlyArray<number> = [];
    constructor(_cb?: unknown, _opts?: unknown) {}
    observe() {}
    unobserve() {}
    disconnect() {}
    takeRecords() {
      return [];
    }
  }
  // @ts-expect-error jsdom polyfill
  globalThis.IntersectionObserver = IntersectionObserverStub;
  if (typeof window !== "undefined") {
    // @ts-expect-error jsdom polyfill
    window.IntersectionObserver = IntersectionObserverStub;
  }
}

// jsdom does not implement HTMLCanvasElement.prototype.getContext. maplibre-gl
// touches it at map init; returning null lets it fall back gracefully to the
// accessible grid instead of throwing and flooding stderr.
if (
  typeof HTMLCanvasElement !== "undefined" &&
  typeof HTMLCanvasElement.prototype.getContext !== "function"
) {
  // @ts-expect-error jsdom polyfill — maplibre-gl touches getContext at map init
  HTMLCanvasElement.prototype.getContext = () => null;
}
