import { describe, it, expect } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import type { EmergingRiskStratum } from "../../../types/artifacts";
import EmergingSignals from "../EmergingSignals";
import { installArtifactFetch } from "../../../test/renderHelpers";

function rec(over: Partial<EmergingRiskStratum>): EmergingRiskStratum {
  return {
    artifact_version: "0.1.0",
    module_id: "S04",
    method_version: "s04.v1",
    pathogen: "Salmonella",
    commodity: "raw_poultry",
    geography_level: "state (sampling location)",
    region: "AA",
    period: "2020-Q1",
    period_start: "2020-01-01",
    sample_n: 100,
    positive_n: 10,
    value: 0.1,
    ci_low: 0.05,
    ci_high: 0.17,
    ci_method: "wilson_95",
    trailing_baseline: 0.08,
    baseline_high: 0.12,
    persistent_score: 0.2,
    retro_anomaly: false,
    retro_threshold: 0.12,
    support_status: "ok",
    prospective_alert: null,
    prospective_status: "not_shown_did_not_beat_persistence",
    prospective_eval: {
      precision: 0.077,
      recall: 0.059,
      alert_volume: 13,
      lead_time_periods: 1.0,
      availability_lag_note: "exploratory",
      beat_persistence: false,
    },
    status: "OBSERVED",
    availability_status: "available",
    unavailable_reason: null,
    fiscal_years: [2019, 2020],
    generated_at: "2026-01-01T00:00:00Z",
    ...over,
  };
}

// State "HI" is persistent (high score) and has an emerging flag in 2020-Q2.
// State "LO" is a low-support cell that must never read as "normal".
const ROWS: EmergingRiskStratum[] = [
  rec({ region: "HI", period: "2020-Q1", period_start: "2020-01-01", persistent_score: 0.6, retro_anomaly: false }),
  rec({ region: "HI", period: "2020-Q2", period_start: "2020-04-01", persistent_score: 0.6, value: 0.3, retro_anomaly: true, retro_threshold: 0.15 }),
  rec({ region: "MD", period: "2020-Q1", period_start: "2020-01-01", persistent_score: 0.1, retro_anomaly: false }),
  rec({ region: "MD", period: "2020-Q2", period_start: "2020-04-01", persistent_score: 0.1, retro_anomaly: false }),
  rec({ region: "LO", period: "2020-Q2", period_start: "2020-04-01", persistent_score: null, sample_n: 7, positive_n: 0, value: 0, trailing_baseline: null, baseline_high: null, retro_anomaly: null, retro_threshold: null, support_status: "low_support" }),
];

describe("EmergingSignals", () => {
  it("shows the honest 'no forecast' note when no forecast validated", async () => {
    installArtifactFetch({ emerging_risk: ROWS });
    render(<EmergingSignals />);
    await waitFor(() =>
      expect(screen.getByText(/no forward-looking forecast is shown/i)).toBeInTheDocument(),
    );
    // Default persistent view ranks HI above MD.
    expect(screen.getByText(/most persistently elevated states/i)).toBeInTheDocument();
  });

  it("toggles to the emerging view and lists the quarter's flagged states", async () => {
    installArtifactFetch({ emerging_risk: ROWS });
    render(<EmergingSignals />);
    await waitFor(() => expect(screen.getByText(/most persistently elevated states/i)).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /^Emerging$/ }));

    // Scrubber defaults to the latest period (2020-Q2); HI is flagged there.
    await waitFor(() =>
      expect(screen.getByText(/emerging signals in 2020-Q2/i)).toBeInTheDocument(),
    );
    // HI appears as a flagged (emerging) state; MD (not flagged) does not get a badge row.
    expect(screen.getAllByText("emerging").length).toBeGreaterThan(0);
    expect(screen.getByText("HI")).toBeInTheDocument();
  });

  it("scrubbing to an earlier quarter removes a later anomaly (no future peek)", async () => {
    installArtifactFetch({ emerging_risk: ROWS });
    render(<EmergingSignals />);
    await waitFor(() => expect(screen.getByText(/most persistently elevated states/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /^Emerging$/ }));
    await waitFor(() => expect(screen.getByText(/emerging signals in 2020-Q2/i)).toBeInTheDocument());

    // Move the scrubber to the first period (2020-Q1): HI's anomaly is in Q2,
    // so Q1 should show no emerging flags.
    const scrubber = screen.getByRole("slider", { name: /select quarter/i });
    fireEvent.change(scrubber, { target: { value: "0" } });

    await waitFor(() =>
      expect(screen.getByText(/emerging signals in 2020-Q1/i)).toBeInTheDocument(),
    );
    expect(screen.getByText(/no state showed a statistically unusual increase in 2020-Q1/i)).toBeInTheDocument();
  });

  it("degrades to an honest empty state when the artifact is missing", async () => {
    installArtifactFetch({});
    render(<EmergingSignals />);
    await waitFor(() =>
      expect(screen.getByText(/could not load emerging_risk/i)).toBeInTheDocument(),
    );
  });
});
