import { useState } from "react";
import SupplierMonitor from "./SupplierMonitor";
import FacilityMap from "./FacilityMap";

/**
 * Facilities (unified S03 Supplier Monitor + Facility Map). A THIN wrapper that
 * merges the two former sub-tabs — "Supplier List" (SupplierMonitor, S03, reads
 * `establishment_surveillance`) and "Facility Map" (FacilityMap, reads
 * `facility_map`) — into a single Facilities surface with a List ⇄ Map VIEW
 * TOGGLE.
 *
 * The toggle is purely a view switch: it mounts exactly one child at a time and
 * NEVER alters any value. All honesty behavior comes unchanged from the
 * children: OBSERVED tagging, the uncertainty-aware EB-shrinkage ranking (list),
 * verified-vs-historical-candidate markers (map), and the shared "sampling
 * location / not the retailer's suppliers / not a contamination claim" framing.
 * The children still own their own hero header, pathogen pills and bodies, so
 * the wrapper deliberately adds NO second gradient hero — exactly one hero shows
 * on screen (the active child's).
 *
 * Views:
 *  - list -> S03 establishments ranked by uncertainty-aware EB positivity.
 *  - map  -> signal-bearing establishments plotted at their sampling location.
 */

type View = "list" | "map";

const VIEWS: Array<{ id: View; label: string; testid: string }> = [
  { id: "list", label: "Supplier List", testid: "facilities-view-list" },
  { id: "map", label: "Facility Map", testid: "facilities-view-map" },
];

export function Facilities() {
  const [view, setView] = useState<View>("map");

  return (
    <div data-testid="facilities">
      {/* Minimal toggle strip — intentionally NOT a gradient hero; the active
          child renders the single hero on screen. */}
      <div className="border-b border-navy/10 bg-surface-muted">
        <div className="mx-auto flex max-w-7xl flex-col gap-2 px-6 py-3">
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-xs font-semibold uppercase tracking-wide text-navy/60">
              View
            </span>
            <div
              data-testid="facilities-view-toggle"
              role="group"
              aria-label="Facilities view"
              className="flex gap-2"
            >
              {VIEWS.map((v) => {
                const on = v.id === view;
                return (
                  <button
                    key={v.id}
                    type="button"
                    data-testid={v.testid}
                    aria-pressed={on}
                    onClick={() => setView(v.id)}
                    className={`rounded-lg border px-4 py-1.5 text-sm font-semibold transition ${
                      on
                        ? "border-teal bg-teal text-white"
                        : "border-navy/15 bg-white text-navy/70 hover:border-navy/30"
                    }`}
                  >
                    {v.label}
                  </button>
                );
              })}
            </div>
          </div>
          <p className="text-[11px] leading-relaxed text-navy/60">
            Both views show FSIS establishments by their <span className="font-semibold text-navy">sampling
            location</span> — not the retailer&apos;s suppliers, not a contamination claim. The{" "}
            <span className="font-semibold text-navy">Supplier List</span> ranks by uncertainty-aware EB
            positivity (S03); the <span className="font-semibold text-navy">Facility Map</span> plots
            signal-bearing establishments (verified vs historical-candidate markers). Switching view only
            changes the view; no value changes.
          </p>
        </div>
      </div>

      {view === "map" ? <FacilityMap /> : <SupplierMonitor />}
    </div>
  );
}

export default Facilities;
