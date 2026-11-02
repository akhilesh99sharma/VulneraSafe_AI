import { describe, it, expect } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import type { HumanOutbreakComparison } from "../../../types/artifacts";
import OneHealthInsights from "../OneHealthInsights";
import { installArtifactFetch } from "../../../test/renderHelpers";

function rec(over: Partial<HumanOutbreakComparison>): HumanOutbreakComparison {
  return {
    artifact_version: "0.1.0",
    module_id: "S05",
    method_version: "s05.v1",
    dataset_sources: "CDC NORS (5xkq-dg7x); USDA FSIS",
    source_accessed_at: "2027-01-01",
    pathogen: "Salmonella",
    commodity: "raw_poultry",
    geography_level: "state",
    region: "GA",
    period: "2015",
    fsis_sample_n: 100,
    fsis_positive_n: 12,
    fsis_positivity: 0.12,
    fsis_ci_low: 0.07,
    fsis_ci_high: 0.2,
    nors_outbreak_count: 2,
    nors_illness_count: 40,
    nors_hospitalization_count: 7,
    nors_death_count: 1,
    nors_available_from_year: 2016,
    availability_lag_days: 365,
    lead_lag: {
      lag_years: 0,
      correlation: 0.54,
      p_value_permutation: 0.095,
      ci_low: 0.22,
      ci_high: 0.83,
      exploratory: true,
      note: "Exploratory descriptive lead-lag only.",
    },
    coverage_status: "ok",
    comparison_status: "CORROBORATION",
    no_causal_link_note: "Corroboration only; not causal.",
    units: "counts",
    status: "OBSERVED",
    availability_status: "available",
    unavailable_reason: null,
    fiscal_years: [2015, 2016],
    generated_at: "2027-01-01T00:00:00Z",
    ...over,
  };
}

const SALM: HumanOutbreakComparison[] = [
  rec({ region: "GA", period: "2015", nors_outbreak_count: 2, nors_hospitalization_count: 7, nors_death_count: 1 }),
  rec({ region: "GA", period: "2016", nors_outbreak_count: 0, nors_hospitalization_count: 0, nors_death_count: 0 }), // true zero
  rec({ region: "TX", period: "2015", nors_outbreak_count: 1, nors_hospitalization_count: 3, nors_death_count: 0, fsis_positive_n: 8, fsis_positivity: 0.08 }),
];

// Listeria: coverage limited, null counts (incl. null outcomes), no lead-lag.
const LIST: HumanOutbreakComparison[] = [
  rec({
    pathogen: "Listeria", commodity: "rte", region: "CA", period: "2014",
    coverage_status: "coverage_limited", nors_outbreak_count: null, nors_illness_count: null,
    nors_hospitalization_count: null, nors_death_count: null,
    lead_lag: null, fsis_positivity: 0.004, fsis_positive_n: 2, fsis_sample_n: 500,
  }),
];

const ROWS = [...SALM, ...LIST];

describe("OneHealthInsights", () => {
  it("renders the dual FSIS/CDC timeline with both source badges", async () => {
    installArtifactFetch({ one_health_human_comparison: ROWS });
    render(<OneHealthInsights />);
    await waitFor(() =>
      expect(screen.getByText(/fsis food surveillance vs\. cdc human outbreaks/i)).toBeInTheDocument(),
    );
    expect(screen.getByText(/FSIS food surveillance \(OBSERVED\)/i)).toBeInTheDocument();
    expect(screen.getByText(/CDC human outbreaks \(OBSERVED, lagged\)/i)).toBeInTheDocument();
  });

  it("shows a prominent no-causal-link explanation", async () => {
    installArtifactFetch({ one_health_human_comparison: ROWS });
    render(<OneHealthInsights />);
    await waitFor(() =>
      expect(screen.getByText(/corroboration, not causation/i)).toBeInTheDocument(),
    );
  });

  it("reports the exploratory lead-lag modestly, not as a finding", async () => {
    installArtifactFetch({ one_health_human_comparison: ROWS });
    render(<OneHealthInsights />);
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /exploratory lead.lag/i })).toBeInTheDocument(),
    );
    // the modest caveat must be present
    expect(screen.getByText(/does not establish that either signal predicts or causes/i)).toBeInTheDocument();
  });

  it("shows the coverage-limited state for a sparse pathogen with no lead-lag", async () => {
    installArtifactFetch({ one_health_human_comparison: ROWS });
    render(<OneHealthInsights />);
    await waitFor(() => expect(screen.getByText(/fsis food surveillance vs/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /^Listeria$/ }));
    await waitFor(() =>
      expect(screen.getByText(/human-outbreak coverage is too limited/i)).toBeInTheDocument(),
    );
    expect(screen.getByText("coverage limited")).toBeInTheDocument();

  });

  it("surfaces OBSERVED NORS hospitalizations and deaths as human-impact context", async () => {
    installArtifactFetch({ one_health_human_comparison: ROWS });
    render(<OneHealthInsights />);
    await waitFor(() => expect(screen.getByText(/observed human-impact context/i)).toBeInTheDocument());
    // national Salmonella scope: hospitalizations 7+0+3 = 10, deaths 1+0+0 = 1
    expect(screen.getByTestId("nors-hospitalizations")).toHaveTextContent("10");
    expect(screen.getByTestId("nors-deaths")).toHaveTextContent("1");
    // honest corroboration-only caption is present near the figures
    expect(
      screen.getByText(/not causally linked to the food-positivity signal/i),
    ).toBeInTheDocument();
  });

  it("shows N/A (never a fabricated zero) for coverage-limited outcome figures", async () => {
    installArtifactFetch({ one_health_human_comparison: ROWS });
    render(<OneHealthInsights />);
    await waitFor(() => expect(screen.getByText(/fsis food surveillance vs/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /^Listeria$/ }));
    await waitFor(() => expect(screen.getByText(/observed human-impact context/i)).toBeInTheDocument());
    expect(screen.getByTestId("nors-hospitalizations")).toHaveTextContent("N/A");
    expect(screen.getByTestId("nors-deaths")).toHaveTextContent("N/A");
  });

  it("degrades to an honest empty state when the artifact is missing", async () => {
    installArtifactFetch({});
    render(<OneHealthInsights />);
    await waitFor(() =>
      expect(screen.getByText(/could not load one_health_human_comparison/i)).toBeInTheDocument(),
    );
  });
});
