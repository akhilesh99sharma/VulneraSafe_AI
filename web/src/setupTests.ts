import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
});

// Deterministic maplibre-gl mock for the jsdom test environment.
//
// jsdom has no WebGL, so a real `new maplibregl.Map(...)` neither renders nor
// drives its async `load`/`setTimeout` lifecycle predictably. MapView is built
// to degrade to an accessible, clickable grid fallback when the GL map is
// unavailable (its `catch { setUseGrid(true) }` path). By making the mocked
// Map constructor throw synchronously we force that fallback deterministically
// in every test, removing a jsdom timing race (the GL container could flip
// `glReady` mid-interaction and unmount the grid button before a click landed).
// This changes nothing about the assertions — tests still click a real
// `map-region` button and assert the time-series renders — only the
// environment is made deterministic. The real maplibre-gl is untouched in the
// browser build.
vi.mock("maplibre-gl", () => {
  class MockMap {
    constructor() {
      throw new Error("maplibre-gl disabled under jsdom (test fallback)");
    }
  }
  return {
    default: { Map: MockMap },
    Map: MockMap,
  };
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