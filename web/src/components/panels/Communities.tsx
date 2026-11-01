import { useState } from "react";
import VulnerableCommunities from "./VulnerableCommunities";
import CountyCommunities from "./CountyCommunities";

/**
 * Communities (unified S06 + S07). A THIN wrapper that merges the two former
 * sub-tabs — "By State" (Vulnerable Communities, S06) and "By County" (County
 * Communities, S07) — into a single Communities surface with a State ⇄ County
 * RESOLUTION TOGGLE.
 *
 * The toggle is purely a view switch: it mounts exactly one child at a time and
 * NEVER alters any value. All honesty behavior — OBSERVED tagging, the
 * read-only-hazard framing, the "lens reprioritizes only" rule, unavailable
 * honesty, and the county-resolution-mismatch banner — comes unchanged from the
 * children, which still own their own hero header, pathogen pills, lens
 * selector and bodies. The wrapper deliberately adds NO second gradient hero,
 * so exactly one hero shows on screen (the active child's).
 *
 * Resolutions:
 *  - state  -> S06: state hazard × state-level community vulnerability.
 *  - county -> S07: county-level vulnerability × its STATE's surveillance
 *              hazard — a documented resolution mismatch, surfaced in full by
 *              CountyCommunities' own high-visibility banner.
 */

type Resolution = "state" | "county";

const RESOLUTIONS: Array<{ id: Resolution; label: string; testid: string }> = [
  { id: "state", label: "By State", testid: "resolution-state" },
  { id: "county", label: "By County", testid: "resolution-county" },
];

export function Communities() {
  const [resolution, setResolution] = useState<Resolution>("state");

  return (
    <div data-testid="communities">
      {/* Minimal toggle strip — intentionally NOT a gradient hero; the active
          child renders the single hero on screen. */}
      <div className="border-b border-navy/10 bg-surface-muted">
        <div className="mx-auto flex max-w-7xl flex-col gap-2 px-6 py-3">
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-xs font-semibold uppercase tracking-wide text-navy/60">
              Resolution
            </span>
            <div
              data-testid="resolution-toggle"
              role="group"
              aria-label="Communities resolution"
              className="flex gap-2"
            >
              {RESOLUTIONS.map((r) => {
                const on = r.id === resolution;
                return (
                  <button
                    key={r.id}
                    type="button"
                    data-testid={r.testid}
                    aria-pressed={on}
                    onClick={() => setResolution(r.id)}
                    className={`rounded-lg border px-4 py-1.5 text-sm font-semibold transition ${
                      on
                        ? "border-teal bg-teal text-white"
                        : "border-navy/15 bg-white text-navy/70 hover:border-navy/30"
                    }`}
                  >
                    {r.label}
                  </button>
                );
              })}
            </div>
          </div>
          <p className="text-[11px] leading-relaxed text-navy/60">
            <span className="font-semibold text-navy">By State</span> shows state hazard × state-level
            community vulnerability (S06).{" "}
            <span className="font-semibold text-navy">By County</span> overlays county-level
            vulnerability with its <span className="font-semibold">STATE's</span> surveillance hazard
            (S07) — a documented resolution mismatch, not a county-measured hazard. Switching
            resolution only changes the view; no value changes.
          </p>
        </div>
      </div>

      {resolution === "county" ? <CountyCommunities /> : <VulnerableCommunities />}
    </div>
  );
}

export default Communities;
