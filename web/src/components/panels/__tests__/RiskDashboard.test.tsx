import { describe, it, expect } from "vitest";
import { screen, fireEvent, waitFor, within } from "@testing-library/react";
import type {
  AttentionQueueItem,
  Manifest,
  ObservedPositivityFeature,
  RiskMapFeature,
} from "../../../types/artifacts";
import RiskDashboard from "../RiskDashboard";
import { installArtifactFetch, renderWithSelection } from "../../../test/renderHelpers";

/**
 * Risk Dashboard component test (UI redesign, step 2).
 *
 * Uses the shared fixture-injection mechanism (installArtifactFetch) exactly
 * like the sibling panel tests. The honesty constraint is the headline
 * assertion: every KPI is derived from the loaded artifacts or shown as N/A,
 * and no number is fabricated.
 */

const MANIFEST: Manifest = {
  artifact_version: "0.1.0",
  generated_at: "2026-01-01T00:00:00Z",
  data_freshness: { fsis_lab: "2026-01-15", cdc: "2026-01-10" },
  pathogens: {
    Salmonella: {
      pathogen: "Salmonella",
      status: "predictive",
      temporal_resolution: "monthly",
      feasibility_factors: [],
    },
    Listeria: {
      pathogen: "Listeria",
      status: "non_predictive",
      temporal_resolution: "quarterly",
      feasibility_factors: [],
    },
  },
};

function mapFeature(over: Partial<RiskMapFeature>): RiskMapFeature {
  return {
    region: "CA",
    pathogen: "Salmonella",
    period: "2026-01",
    risk: 0.5,
    uncertainty: 0.1,
    status: "PREDICTED",
    data_freshness: "2026-01-15",
    ...over,
  };
}

// Salmonella: mean of [0.8, 0.2] = 0.5 -> "Moderate"; 1 state elevated
// (>= 0.5); highest-risk state TX at 0.8. Listeria: a single 0.1 feature so
// the pathogen switch visibly changes the KPIs.
const MAP: RiskMapFeature[] = [
  mapFeature({ region: "TX", pathogen: "Salmonella", risk: 0.8 }),
  mapFeature({ region: "NY", pathogen: "Salmonella", risk: 0.2 }),
  mapFeature({ region: "WA", pathogen: "Listeria", risk: 0.1, status: "OBSERVED" }),
];

const QUEUE: AttentionQueueItem[] = [
  {
    rank: 1,
    target_id: "t1",
    target_type: "establishment",
    region: "TX",
    pathogen: "Salmonella",
    risk: 0.8,
    triggering_condition: "elevated predicted risk",
    status: "PREDICTED",
  },
  {
    rank: 2,
    target_id: "t2",
    target_type: "establishment",
    region: "NY",
    pathogen: "Salmonella",
    risk: 0.6,
    triggering_condition: "rising trend",
    status: "PREDICTED",
  },
];

// Observed-positivity fixture (measured FSIS positivity with real sample counts)
// for the Observed-view assertions: TX measured at 0.30 from 40 samples, NY at
// 0.10 from 25 samples. These are MEASURED rows, never the predicted probability.
const OBSERVED: ObservedPositivityFeature[] = [
  {
    artifact_version: "0.1.0",
    module_id: "OBSERVEDPOS",
    pathogen: "Salmonella",
    commodity: "raw_poultry",
    region: "TX",
    period: "2026-01",
    positivity: 0.3,
    sample_n: 40,
    positive_n: 12,
    status: "OBSERVED",
    generated_at: "2026-01-01T00:00:00Z",
  },
  {
    artifact_version: "0.1.0",
    module_id: "OBSERVEDPOS",
    pathogen: "Salmonella",
    commodity: "raw_poultry",
    region: "NY",
    period: "2026-01",
    positivity: 0.1,
    sample_n: 25,
    positive_n: 3,
    status: "OBSERVED",
    generated_at: "2026-01-01T00:00:00Z",
  },
];

describe("RiskDashboard", () => {
  it("renders the page header", async () => {
    installArtifactFetch({ manifest: MANIFEST, risk_map: MAP, attention_queue: QUEUE });
    renderWithSelection(<RiskDashboard />, { pathogen: "Salmonella" });
    expect(await screen.findByTestId("page-header")).toBeInTheDocument();
    expect(
      within(screen.getByTestId("page-header")).getByRole("heading", { name: "Risk Dashboard" }),
    ).toBeInTheDocument();
  });

  it("computes the national-risk KPI from real data (mean of [0.8,0.2] -> Moderate)", async () => {
    installArtifactFetch({ manifest: MANIFEST, risk_map: MAP, attention_queue: QUEUE });
    renderWithSelection(<RiskDashboard />, { pathogen: "Salmonella" });

    // Wait for the risk_map artifact to resolve and the national-risk KPI to
    // be computed from it.
    await waitFor(() => {
      const national = screen.getAllByTestId("stat-card")[0];
      expect(within(national).getByText("Moderate")).toBeInTheDocument();
    });
    const cards = screen.getAllByTestId("stat-card");
    expect(within(cards[0]).getByText(/mean across 2 states/i)).toBeInTheDocument();

    // Elevated-risk count: exactly one Salmonella state (TX 0.8) >= 0.5.
    expect(within(cards[1]).getByText("1")).toBeInTheDocument();

    // Highest-risk state: TX, with its risk formatted honestly.
    expect(within(cards[2]).getByText("TX")).toBeInTheDocument();
    expect(within(cards[2]).getByText("80.0%")).toBeInTheDocument();
  });

  it("switches pathogen via the pills and updates KPIs and top-states", async () => {
    installArtifactFetch({ manifest: MANIFEST, risk_map: MAP, attention_queue: QUEUE });
    renderWithSelection(<RiskDashboard />, { pathogen: "Salmonella" });

    // Top states initially carry the Salmonella leaders (after risk_map loads).
    await waitFor(() =>
      expect(
        within(screen.getByTestId("top-states")).getAllByTestId("top-state-row"),
      ).toHaveLength(2),
    );
    const topBefore = within(screen.getByTestId("top-states")).getAllByTestId("top-state-row");
    expect(topBefore.map((b) => b.getAttribute("data-region"))).toEqual(["TX", "NY"]);

    // Switch to Listeria: the single Listeria feature (WA, 0.1) takes over.
    fireEvent.click(screen.getByRole("button", { name: /^Listeria$/i }));
    const topAfter = within(screen.getByTestId("top-states")).getAllByTestId("top-state-row");
    expect(topAfter.map((b) => b.getAttribute("data-region"))).toEqual(["WA"]);

    // Listeria mean = 0.1 -> "Low" national-risk bucket (still honest, not High).
    const cards = screen.getAllByTestId("stat-card");
    expect(within(cards[0]).getByText("Low")).toBeInTheDocument();
  });

  it("renders each top-state row with a risk % pill and an uncertainty value", async () => {
    installArtifactFetch({ manifest: MANIFEST, risk_map: MAP, attention_queue: QUEUE });
    renderWithSelection(<RiskDashboard />, { pathogen: "Salmonella" });

    const topStates = await screen.findByTestId("top-states");
    await waitFor(() =>
      expect(within(topStates).getAllByTestId("top-state-row")).toHaveLength(2),
    );

    // The leader (TX, 0.8) shows its honest risk percentage inside the pill and
    // its stored ± uncertainty band (0.1 -> "± 10.0%"). Both are read from the
    // artifact, never fabricated.
    expect(within(topStates).getByText("80.0%")).toBeInTheDocument();
    expect(within(topStates).getAllByText("± 10.0%").length).toBeGreaterThanOrEqual(1);

    // The pill is accessible: its name carries the named band + percentage.
    expect(
      within(topStates).getByLabelText(/very high risk, 80\.0%/i),
    ).toBeInTheDocument();
  });

  it("renders the National Risk Trend as its own region below the hero", async () => {
    installArtifactFetch({ manifest: MANIFEST, risk_map: MAP, attention_queue: QUEUE });
    renderWithSelection(<RiskDashboard />, { pathogen: "Salmonella" });

    // The trend half is promoted into its own full-width panel.
    expect(
      await screen.findByRole("heading", { name: /national risk trend/i }),
    ).toBeInTheDocument();
  });

  it("switches the top-states header/column to Positivity + Samples in observed mode", async () => {
    installArtifactFetch({
      manifest: MANIFEST,
      risk_map: MAP,
      attention_queue: QUEUE,
      observed_positivity: OBSERVED,
    });
    renderWithSelection(<RiskDashboard />, { pathogen: "Salmonella" });

    // Predicted (default): headers read "Risk" + "Uncertainty".
    const topStates = await screen.findByTestId("top-states");
    await waitFor(() =>
      expect(within(topStates).getAllByTestId("top-state-row")).toHaveLength(2),
    );
    expect(within(topStates).getByRole("columnheader", { name: "Risk" })).toBeInTheDocument();
    expect(
      within(topStates).getByRole("columnheader", { name: "Uncertainty" }),
    ).toBeInTheDocument();

    // Flip to Observed: the measured positivity artifact drives the table.
    fireEvent.click(screen.getByTestId("view-observed"));

    await waitFor(() =>
      expect(
        within(screen.getByTestId("top-states")).getByRole("columnheader", {
          name: "Positivity",
        }),
      ).toBeInTheDocument(),
    );
    const observedTable = screen.getByTestId("top-states");
    // Header switches "Uncertainty" -> "Samples (n)".
    expect(
      within(observedTable).getByRole("columnheader", { name: "Samples (n)" }),
    ).toBeInTheDocument();
    expect(
      within(observedTable).queryByRole("columnheader", { name: "Uncertainty" }),
    ).not.toBeInTheDocument();

    // The third column now shows the REAL sample counts (40 for TX, 25 for NY),
    // read from observed_positivity — never fabricated.
    const thirdCols = within(observedTable).getAllByTestId("top-state-third-col");
    const texts = thirdCols.map((c) => c.textContent);
    expect(texts).toContain("40");
    expect(texts).toContain("25");
  });

  it("renders the CSV and JSON export buttons and clicking them does not throw", async () => {
    installArtifactFetch({ manifest: MANIFEST, risk_map: MAP, attention_queue: QUEUE });
    renderWithSelection(<RiskDashboard />, { pathogen: "Salmonella" });

    const csv = await screen.findByTestId("export-csv");
    const json = await screen.findByTestId("export-json");
    expect(csv).toBeInTheDocument();
    expect(json).toBeInTheDocument();

    // Wait for the risk_map to load so there are rows to export (buttons enable).
    await waitFor(() =>
      expect(
        within(screen.getByTestId("top-states")).getAllByTestId("top-state-row"),
      ).toHaveLength(2),
    );

    // Clicking either export must not throw under jsdom (URL.createObjectURL is
    // polyfilled in setupTests, and the handler guards a missing one anyway).
    expect(() => fireEvent.click(csv)).not.toThrow();
    expect(() => fireEvent.click(json)).not.toThrow();
  });

  it("highlights the top-states row for the selected region", async () => {
    installArtifactFetch({ manifest: MANIFEST, risk_map: MAP, attention_queue: QUEUE });
    renderWithSelection(<RiskDashboard />, { pathogen: "Salmonella" });

    const topStates = await screen.findByTestId("top-states");
    await waitFor(() =>
      expect(within(topStates).getAllByTestId("top-state-row")).toHaveLength(2),
    );

    // No region selected yet -> rows exist but none is highlighted.
    expect(
      within(topStates).getAllByTestId("top-state-row-tr").length,
    ).toBeGreaterThan(0);
    expect(
      within(topStates)
        .getAllByTestId("top-state-row-tr")
        .some((tr) => tr.getAttribute("data-selected") === "true"),
    ).toBe(false);

    // Click the TX row button -> that state's row becomes selected.
    const txButton = within(topStates)
      .getAllByTestId("top-state-row")
      .find((b) => b.getAttribute("data-region") === "TX")!;
    fireEvent.click(txButton);

    await waitFor(() => {
      const selectedRows = within(screen.getByTestId("top-states"))
        .getAllByTestId("top-state-row-tr")
        .filter((tr) => tr.getAttribute("data-selected") === "true");
      expect(selectedRows).toHaveLength(1);
    });
  });

  it("shows N/A for the national-risk KPI when the risk_map is empty (never fabricated)", async () => {
    installArtifactFetch({ manifest: MANIFEST, risk_map: [], attention_queue: [] });
    renderWithSelection(<RiskDashboard />, { pathogen: "Salmonella" });

    // Top-states falls back to an honest empty note rather than an empty table.
    await waitFor(() =>
      expect(
        within(screen.getByTestId("top-states")).getByText(/no states to rank/i),
      ).toBeInTheDocument(),
    );
    const cards = screen.getAllByTestId("stat-card");
    // National risk + highest-risk state are both N/A with no features.
    expect(within(cards[0]).getByText("N/A")).toBeInTheDocument();
    expect(within(cards[2]).getByText("N/A")).toBeInTheDocument();
  });
});
