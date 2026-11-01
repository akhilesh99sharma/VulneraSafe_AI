import { describe, it, expect } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import App from "../App";
import { installArtifactFetch } from "../test/renderHelpers";
import type { Manifest } from "../types/artifacts";

const MANIFEST: Manifest = {
  artifact_version: "0.1.0",
  generated_at: "2026-01-01T00:00:00Z",
  data_freshness: { fsis_lab: "2026-01-15" },
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

describe("App", () => {
  // After the Step-3 IA redesign the five mandatory panels span two sections:
  // the Risk Dashboard section holds Current Risk Overview + Prioritized
  // Attention Queue (inside RiskDashboard); the Decision Actions section holds
  // Scenario Builder, Recommended Action Panel and Explanation / Evidence Panel
  // as sub-tabs. This test proves all five are present and reachable.
  it("keeps all five mandatory panels reachable across the new sections", async () => {
    installArtifactFetch({ manifest: MANIFEST });
    render(<App />);

    // Risk Dashboard section: two mandatory panels.
    fireEvent.click(screen.getByTestId("tab-dashboard"));
    await waitFor(() =>
      expect(screen.getByText(/artifact version/i)).toBeInTheDocument(),
    );
    for (const title of ["Current Risk Overview", "Prioritized Attention Queue"]) {
      expect(screen.getByRole("heading", { name: title })).toBeInTheDocument();
    }

    // Decision Actions section: the remaining three mandatory panels, each on
    // its own sub-tab. Navigate the sub-tab strip to reach each one.
    fireEvent.click(screen.getByTestId("tab-actions"));

    fireEvent.click(screen.getByTestId("subtab-scenario"));
    expect(
      screen.getByRole("heading", { name: "Scenario Builder" }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("subtab-recommended"));
    expect(
      screen.getByRole("heading", { name: "Recommended Action Panel" }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("subtab-evidence"));
    expect(
      screen.getByRole("heading", { name: "Explanation / Evidence Panel" }),
    ).toBeInTheDocument();
  });

  it("populates the pathogen selector from the manifest", async () => {
    installArtifactFetch({ manifest: MANIFEST });
    render(<App />);
    // The manifest-driven pathogen select still lives on the Risk Dashboard.
    fireEvent.click(screen.getByTestId("tab-dashboard"));

    const select = (await screen.findByTestId(
      "pathogen-select",
    )) as HTMLSelectElement;
    const options = Array.from(select.options).map((o) => o.value);
    expect(options).toEqual(["", "Salmonella", "Listeria"]);
  });

  it("still renders panels when the manifest fails to load (graceful degradation)", async () => {
    installArtifactFetch({}); // manifest 404s
    render(<App />);
    fireEvent.click(screen.getByTestId("tab-dashboard"));

    await waitFor(() =>
      expect(screen.getByText(/could not load the data manifest/i)).toBeInTheDocument(),
    );
    // Panels themselves still mount. The RiskDashboard panel lives on this
    // section now (Scenario Builder moved to Decision Actions), so assert its
    // Current Risk Overview heading renders despite the manifest failure.
    expect(
      screen.getByRole("heading", { name: "Current Risk Overview" }),
    ).toBeInTheDocument();
  });
});
