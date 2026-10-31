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
  it("renders all five mandatory panels", async () => {
    installArtifactFetch({ manifest: MANIFEST });
    render(<App />);
    fireEvent.click(screen.getByTestId("tab-dashboard"));

    await waitFor(() =>
      expect(screen.getByText(/artifact version/i)).toBeInTheDocument(),
    );

    const titles = [
      "Current Risk Overview",
      "Prioritized Attention Queue",
      "Scenario Builder",
      "Recommended Action Panel",
      "Explanation / Evidence Panel",
    ];
    for (const title of titles) {
      expect(
        screen.getByRole("heading", { name: title }),
      ).toBeInTheDocument();
    }
  });

  it("populates the pathogen selector from the manifest", async () => {
    installArtifactFetch({ manifest: MANIFEST });
    render(<App />);
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
    // Panels themselves still mount.
    expect(
      screen.getByRole("heading", { name: "Scenario Builder" }),
    ).toBeInTheDocument();
  });
});
