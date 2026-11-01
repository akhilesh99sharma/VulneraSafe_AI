import { describe, it, expect } from "vitest";
import { screen, fireEvent, waitFor, within } from "@testing-library/react";
import type {
  AttentionQueueItem,
  Manifest,
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
