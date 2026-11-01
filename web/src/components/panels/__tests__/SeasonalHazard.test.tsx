import { describe, it, expect } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import type { SeasonalHazardRecord } from "../../../types/artifacts";
import SeasonalHazard from "../SeasonalHazard";
import { installArtifactFetch } from "../../../test/renderHelpers";

/**
 * Web component test for the S02 Seasonal Patterns panel (Req 7.2, 7.3, 7.4).
 *
 * The panel reads the `seasonal_hazard_patterns` artifact through
 * `useArtifact`, which fetches `/data/seasonal_hazard_patterns.json`. We inject
 * a fixture through the shared `installArtifactFetch` helper exactly like the
 * sibling `VulnerableCommunities.test.tsx` does — a fake `fetch` resolves the
 * artifact name to our in-test fixture array, and the module-level loader cache
 * is cleared first. No map / maplibre is involved, so the panel renders cleanly
 * under jsdom.
 */

/** Build one SeasonalHazardRecord with realistic exporter-shaped defaults. */
function rec(over: Partial<SeasonalHazardRecord>): SeasonalHazardRecord {
  return {
    artifact_version: "0.1.0",
    module_id: "S02",
    method_version: "s02.v1",
    pathogen: "Salmonella",
    commodity: "raw_poultry",
    view: "month",
    bucket_label: "01",
    sample_n: 1200,
    positive_n: 48,
    rate: 0.04,
    ci_low: 0.03,
    ci_high: 0.052,
    ci_method: "wilson_95",
    seasonal_index: 1.0,
    overall_rate: 0.04,
    is_peak: false,
    trend_method: "ordinal_year_ols_slope",
    trend_slope: 0.004,
    trend_years_used: [2019, 2020, 2021],
    trend_availability_status: "available",
    trend_unavailable_reason: null,
    pattern_label: "historical seasonal pattern",
    status: "OBSERVED",
    availability_status: "available",
    unavailable_reason: null,
    periods_read_count: 84,
    generated_at: "2027-01-01T00:00:00Z",
    ...over,
  };
}

// A distinctive gate reason we can assert lands inside an unavailable-note.
const MONTH_GATE_REASON =
  "month bucket below minimum-sample gate (n=11 < 30); not fabricated.";

// --- Salmonella rows ---------------------------------------------------------
// Months: 03 is the available peak (8.2%), 07 available (4.1%), 11 gated.
const SALMONELLA_MONTHS: SeasonalHazardRecord[] = [
  rec({ view: "month", bucket_label: "03", rate: 0.082, ci_low: 0.07, ci_high: 0.095, is_peak: true, sample_n: 1500, positive_n: 123 }),
  rec({ view: "month", bucket_label: "07", rate: 0.041, ci_low: 0.033, ci_high: 0.05, is_peak: false, sample_n: 1300, positive_n: 53 }),
  rec({
    view: "month",
    bucket_label: "11",
    rate: null,
    ci_low: null,
    ci_high: null,
    seasonal_index: null,
    is_peak: false,
    sample_n: 11,
    positive_n: null,
    availability_status: "unavailable",
    unavailable_reason: MONTH_GATE_REASON,
  }),
];

// Quarters: Q1 available peak (7.5%), Q2 available (5.2%), Q3 gated, Q4 available (3.0%).
const SALMONELLA_QUARTERS: SeasonalHazardRecord[] = [
  rec({ view: "quarter", bucket_label: "Q1", rate: 0.075, ci_low: 0.066, ci_high: 0.085, is_peak: true, sample_n: 4200, positive_n: 315 }),
  rec({ view: "quarter", bucket_label: "Q2", rate: 0.052, ci_low: 0.044, ci_high: 0.061, is_peak: false, sample_n: 4000, positive_n: 208 }),
  rec({
    view: "quarter",
    bucket_label: "Q3",
    rate: null,
    ci_low: null,
    ci_high: null,
    seasonal_index: null,
    is_peak: false,
    sample_n: 18,
    positive_n: null,
    availability_status: "unavailable",
    unavailable_reason: "quarter bucket below minimum-sample gate (n=18 < 30); not fabricated.",
  }),
  rec({ view: "quarter", bucket_label: "Q4", rate: 0.03, ci_low: 0.023, ci_high: 0.039, is_peak: false, sample_n: 3800, positive_n: 114 }),
];

// --- Listeria rows (clearly different numbers so the selector test is real) --
// Month 09 available peak (1.5%); Quarter Q3 available peak (1.2%).
const LISTERIA_MONTHS: SeasonalHazardRecord[] = [
  rec({
    pathogen: "Listeria",
    commodity: "rte",
    view: "month",
    bucket_label: "09",
    rate: 0.015,
    ci_low: 0.009,
    ci_high: 0.023,
    overall_rate: 0.013,
    is_peak: true,
    trend_slope: -0.001,
    sample_n: 900,
    positive_n: 14,
  }),
];
const LISTERIA_QUARTERS: SeasonalHazardRecord[] = [
  rec({
    pathogen: "Listeria",
    commodity: "rte",
    view: "quarter",
    bucket_label: "Q3",
    rate: 0.012,
    ci_low: 0.008,
    ci_high: 0.018,
    overall_rate: 0.013,
    is_peak: true,
    trend_slope: -0.001,
    sample_n: 2600,
    positive_n: 31,
  }),
];

const ROWS: SeasonalHazardRecord[] = [
  ...SALMONELLA_MONTHS,
  ...SALMONELLA_QUARTERS,
  ...LISTERIA_MONTHS,
  ...LISTERIA_QUARTERS,
];

describe("SeasonalHazard", () => {
  it("renders available buckets with their rate/CI and both chart containers", async () => {
    installArtifactFetch({ seasonal_hazard_patterns: ROWS });
    render(<SeasonalHazard />);

    // The month and quarter chart containers render.
    await waitFor(() => expect(screen.getByTestId("month-chart")).toBeInTheDocument());
    expect(screen.getByTestId("quarter-chart")).toBeInTheDocument();

    // An available bucket's pooled-positivity rate text appears. formatRisk
    // renders 0..1 as a percentage: Salmonella Q1 (0.075) -> "7.5%" and the
    // available peak month 03 (0.082) -> "8.2%".
    expect(screen.getByText("8.2%")).toBeInTheDocument();
    expect(screen.getByText("7.5%")).toBeInTheDocument();
  });

  it("shows the unavailable-note carrying the reason for a gated bucket", async () => {
    installArtifactFetch({ seasonal_hazard_patterns: ROWS });
    render(<SeasonalHazard />);

    await waitFor(() => expect(screen.getByTestId("month-chart")).toBeInTheDocument());

    // There are several unavailable-note elements (gated month + gated quarter);
    // the distinctive month-gate reason appears inside one of them.
    const notes = screen.getAllByTestId("unavailable-note");
    expect(notes.length).toBeGreaterThan(0);
    const withReason = notes.filter((n) => n.textContent?.includes(MONTH_GATE_REASON));
    expect(withReason.length).toBeGreaterThan(0);
  });

  it("switches the displayed statistics when the pathogen selector changes", async () => {
    installArtifactFetch({ seasonal_hazard_patterns: ROWS });
    render(<SeasonalHazard />);

    // Salmonella is the default: its distinctive rate 8.2% is shown and the
    // Listeria-only rate 1.5% is absent.
    await waitFor(() => expect(screen.getByText("8.2%")).toBeInTheDocument());
    expect(screen.queryByText("1.5%")).not.toBeInTheDocument();

    // Click the Listeria button inside the pathogen selector.
    const selector = screen.getByTestId("pathogen-selector");
    fireEvent.click(within(selector).getByRole("button", { name: /^Listeria$/ }));

    // The displayed statistics update to the Listeria values; Salmonella's
    // 8.2% is gone.
    await waitFor(() => expect(screen.getByText("1.5%")).toBeInTheDocument());
    expect(screen.queryByText("8.2%")).not.toBeInTheDocument();
  });

  it("labels the peak callout a historical seasonal pattern, not a forecast or prediction", async () => {
    installArtifactFetch({ seasonal_hazard_patterns: ROWS });
    render(<SeasonalHazard />);

    const peak = await screen.findByTestId("peak-season");
    expect(peak.textContent ?? "").toContain("historical seasonal pattern");
    expect(peak.textContent ?? "").not.toMatch(/forecast|prediction/i);
  });
});
