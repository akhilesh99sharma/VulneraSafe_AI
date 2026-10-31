import { describe, it, expect, afterEach } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import type { RiskMapFeature, RiskTimeseriesPoint } from "../../../types/artifacts";
import CurrentRiskOverview from "../CurrentRiskOverview";
import { installArtifactFetch, renderWithSelection } from "../../../test/renderHelpers";

const MAP: RiskMapFeature[] = [
  {
    region: "TX",
    pathogen: "Salmonella",
    period: "2026-01",
    risk: 0.42,
    uncertainty: 0.08,
    status: "PREDICTED",
    data_freshness: "2026-01-15",
  },
  {
    region: "CA",
    pathogen: "Salmonella",
    period: "2026-01",
    risk: 0.2,
    uncertainty: 0.05,
    status: "PREDICTED",
    data_freshness: "2026-01-15",
  },
];

const TS: RiskTimeseriesPoint[] = [
  {
    pathogen: "Salmonella",
    commodity: "raw_poultry",
    region: "TX",
    period: "2025-12",
    value: 0.3,
    ci_low: 0.22,
    ci_high: 0.38,
    status: "PREDICTED",
  },
  {
    pathogen: "Salmonella",
    commodity: "raw_poultry",
    region: "TX",
    period: "2026-01",
    value: 0.42,
    ci_low: 0.34,
    ci_high: 0.5,
    status: "PREDICTED",
  },
];

afterEach(() => {
  // leave global stubs for the next installArtifactFetch to overwrite
});

/**
 * Find the grid region button for a given state. maplibre-gl is mocked to
 * throw under jsdom (see setupTests), so MapView deterministically renders its
 * accessible grid fallback whose buttons carry data-region.
 */
async function findRegionButton(region: string): Promise<HTMLElement> {
  const buttons = await screen.findAllByTestId("map-region");
  const match = buttons.find((b) => b.getAttribute("data-region") === region);
  if (!match) throw new Error(`no map-region button for ${region}`);
  return match;
}

describe("CurrentRiskOverview", () => {
  it("renders the map and prompts to select a region", async () => {
    installArtifactFetch({ risk_map: MAP, risk_timeseries: TS });
    renderWithSelection(<CurrentRiskOverview />);

    await waitFor(() =>
      expect(screen.getAllByTestId("map-view").length).toBeGreaterThanOrEqual(1),
    );
    expect(screen.getAllByTestId("map-region")).toHaveLength(2);
    // No region selected yet -> prompt.
    expect(screen.getByText(/select a region/i)).toBeInTheDocument();
  });

  it("updates the time-series when a region is selected (Req 12.2)", async () => {
    installArtifactFetch({ risk_map: MAP, risk_timeseries: TS });
    renderWithSelection(<CurrentRiskOverview />);

    // Let BOTH artifacts settle before interacting. risk_map and
    // risk_timeseries resolve on independent microtasks; the "select a region"
    // prompt only appears once risk_timeseries has loaded (its !region branch).
    // Waiting for it guarantees no late artifact resolve re-renders the map
    // grid between capturing the button and clicking it (which would otherwise
    // dispatch the click to a now-detached DOM node and drop the selection).
    await screen.findByText(/select a region/i);

    // Re-query the button immediately before clicking so the reference is live.
    fireEvent.click(await findRegionButton("TX"));

    await waitFor(() =>
      expect(screen.getByTestId("time-series")).toBeInTheDocument(),
    );
    expect(screen.getAllByTestId("time-series-point")).toHaveLength(2);
  });

  it("shows an empty-state naming the gap when a region has no dated data (Req 12.3)", async () => {
    installArtifactFetch({ risk_map: MAP, risk_timeseries: TS });
    // CA has no time-series points.
    renderWithSelection(<CurrentRiskOverview />, { region: "CA" });

    await waitFor(() =>
      expect(screen.getByText(/no dated data for this selection/i)).toBeInTheDocument(),
    );
    // Assert against the empty-state message, which uniquely names the CA gap
    // (avoids ambiguity with the map-label geography cell and grid button).
    expect(
      screen.getByText(
        /no surveillance or validated predictions for region "CA"/i,
      ),
    ).toBeInTheDocument();
  });

  it("degrades to a named empty-state when risk_map fails to load (Req 15.3)", async () => {
    installArtifactFetch({ risk_timeseries: TS }); // risk_map 404s
    renderWithSelection(<CurrentRiskOverview />);

    await waitFor(() =>
      expect(screen.getByText(/could not load risk_map/i)).toBeInTheDocument(),
    );
  });
});