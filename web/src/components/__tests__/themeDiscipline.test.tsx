import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { render, screen } from "@testing-library/react";
import StatusTag from "../StatusTag";
import MapLabel from "../MapLabel";
import StatusLegend from "../legend/StatusLegend";

/**
 * Theme / alert-color discipline (Req 14.4, 14.6).
 *
 * Orange/red (the `alert-*` tokens and the default amber/red/orange/rose/yellow
 * palettes) may be used ONLY on active-alert elements — verified regulatory
 * recalls, human-review-required, genuine high-risk thresholds, and form
 * validation errors (which are themselves alerts, role="alert"). This test:
 *
 *   1. Static check: scans component source and asserts any file using an
 *      alert-family color is one of the known alert-context files, so a new
 *      decorative use of orange/red fails CI.
 *   2. Prop-driven check: renders the provenance StatusTag in every state and
 *      asserts NONE of them apply an alert-family color class (a provenance tag
 *      is never an alert).
 */

const here = dirname(fileURLToPath(import.meta.url));
const COMPONENTS_DIR = join(here, "..");

// Alert-family color tokens: our reserved alert tokens + the Tailwind warm
// palettes that read as orange/red. `teal`, `navy`, `slate`, `gray` are safe.
const ALERT_COLOR = /\b(?:bg|text|border|ring|from|to|via)-(?:alert-(?:warn|danger)|red|orange|amber|rose|yellow)(?:-\d{2,3})?\b/;

/**
 * Files allowed to reference an alert-family color because they ARE the alert
 * surfaces (or explain the alert color). Any OTHER file that references an
 * alert color is a decorative use and fails this test (Req 14.4).
 */
const ALERT_CONTEXT_FILES = new Set<string>([
  "AlertBadge.tsx", // REGULATORY badge accent
  "RegulatoryAlertsStrip.tsx", // verified recall strip
  join("panels", "RecommendedActionPanel.tsx"), // human-review-required banner
  join("panels", "ScenarioBuilder.tsx"), // form validation error (role="alert")
  join("panels", "PolicyComparison.tsx"), // SIMULATED verified-recall warning banner
  join("legend", "StatusLegend.tsx"), // explains the alert color (not decorative)
  join("panels", "EmergingSignals.tsx"), // orange marks active emerging-anomaly states (Req 7.6)
  join("panels", "SurveillanceActions.tsx"), // orange marks human-review / prioritize-testing emphasis
  join("panels", "FacilityMap.tsx"), // historical-candidate + human-review emphasis use orange
]);


function walkTsx(dir: string, base = ""): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const abs = join(dir, entry);
    const rel = base ? join(base, entry) : entry;
    if (statSync(abs).isDirectory()) {
      if (entry === "__tests__") continue; // tests may name the colors freely
      out.push(...walkTsx(abs, rel));
    } else if (entry.endsWith(".tsx")) {
      out.push(rel);
    }
  }
  return out;
}

describe("theme discipline — static source scan (Req 14.4)", () => {
  it("only known alert-context files reference an alert-family color", () => {
    const offenders: string[] = [];
    for (const rel of walkTsx(COMPONENTS_DIR)) {
      const source = readFileSync(join(COMPONENTS_DIR, rel), "utf8");
      // Strip line comments so an explanatory comment never counts as usage.
      const code = source.replace(/\/\/.*$/gm, "");
      if (ALERT_COLOR.test(code) && !ALERT_CONTEXT_FILES.has(rel)) {
        offenders.push(rel);
      }
    }
    expect(offenders, `decorative alert-color use found in: ${offenders.join(", ")}`).toEqual([]);
  });
});

describe("theme discipline — StatusTag never uses an alert color (Req 14.4)", () => {
  it.each(["OBSERVED", "PREDICTED", "SIMULATED"] as const)(
    "the %s provenance tag applies no alert-family class",
    (status) => {
      render(<StatusTag status={status} />);
      const tag = screen.getByTestId("status-tag");
      expect(tag.className).not.toMatch(ALERT_COLOR);
    },
  );
});

describe("theme discipline — labels/legend are tag-colored, not alert-colored (Req 14.4)", () => {
  it("MapLabel status cell renders a StatusTag with no alert color", () => {
    render(<MapLabel status="SIMULATED" pathogen="STEC" />);
    const tag = screen.getByTestId("status-tag");
    expect(tag.className).not.toMatch(ALERT_COLOR);
  });

  it("StatusLegend swatches for the three tags use no alert color", () => {
    render(<StatusLegend />);
    for (const tag of screen.getAllByTestId("status-tag")) {
      expect(tag.className).not.toMatch(ALERT_COLOR);
    }
  });
});
