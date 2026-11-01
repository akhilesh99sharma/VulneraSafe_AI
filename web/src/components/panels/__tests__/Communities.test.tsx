import { describe, it, expect } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import type {
  CommunityImpactRecord,
  CountyCommunityImpactRecord,
  LensPriority,
} from "../../../types/artifacts";
import Communities from "../Communities";
import { installArtifactFetch, renderWithSelection } from "../../../test/renderHelpers";

/**
 * Communities (unified S06 + S07) wrapper test.
 *
 * Communities is a THIN view switch: a resolution toggle that mounts exactly
 * one child at a time — VulnerableCommunities (S06, reads `community_impact`)
 * for "By State" and CountyCommunities (S07, reads `county_community_impact`)
 * for "By County". So the fixture provides BOTH artifacts, and the test proves
 * only that the toggle swaps which child (and which artifact-backed view) is
 * shown. The children's internals are covered by their own sibling tests and
 * are not re-exercised here.
 *
 * Minimal schema-complete fixtures: a single available state row for
 * community_impact and a single available county row for
 * county_community_impact — enough to render each child's body and prove the
 * switch.
 */

function lens(
  id: string,
  available: boolean,
  vuln: number | null,
  prio: number | null,
): LensPriority {
  return {
    lens: id,
    available,
    vulnerability_component: vuln,
    priority_score: prio,
    weights: "hazard 0.6 / vulnerability 0.4",
    unavailable_reason: available
      ? null
      : `${id} is not in the current ACS extraction and is not fabricated.`,
  };
}

const LENSES: LensPriority[] = [
  lens("elderly_65plus", true, 0.9, 0.84),
  lens("low_income", true, 0.5, 0.68),
  lens("low_access", true, 0.4, 0.64),
  lens("under5", false, null, null),
  lens("pregnancy", false, null, null),
];

const STATE_ROW: CommunityImpactRecord = {
  artifact_version: "0.1.0",
  module_id: "S06",
  method_version: "s06.v1",
  pathogen: "Salmonella",
  commodity: "raw_poultry",
  geography_level: "state",
  region: "ME",
  hazard_component: 1.0,
  hazard_positivity: 0.2,
  total_population: 1362000,
  affected_population_context: 250000,
  elderly_65plus_share: 0.21,
  low_income_tract_share: 0.3,
  low_access_tract_share: 0.18,
  under5_share: null,
  acs_vintage: "ACS5 2022",
  atlas_vintage: "FARA/LRAM 2019",
  lenses: LENSES,
  weight_sensitivity: {
    default_top: ["ME", "NH"],
    alt_top: ["NH", "ME"],
    rank_stable: false,
    note: "weight-dependent; no single weighting definitive",
  },
  contextual_count_note:
    "Contextual count — people who could be affected IF exposed, never an illness count.",
  status: "OBSERVED",
  availability_status: "available",
  unavailable_reason: null,
  generated_at: "2027-01-01T00:00:00Z",
};

const COUNTY_ROW: CountyCommunityImpactRecord = {
  artifact_version: "0.1.0",
  module_id: "S07",
  method_version: "s07.v1",
  pathogen: "Salmonella",
  commodity: "raw_poultry",
  county_fips: "06001",
  county_name: "Alameda",
  state: "CA",
  geography_level: "county",
  resolution_label: "county vulnerability x state-level hazard",
  hazard_positivity: 0.2,
  hazard_component: 0.8,
  rank: null,
  affected_population_context: 125000,
  total_population: 1600000,
  elderly_65plus_share: 0.16,
  low_income_share: 0.3,
  low_access_share: 0.18,
  under5_share: null,
  acs_vintage: "ACS5 2022",
  atlas_vintage: "FARA/LRAM 2019",
  lenses: LENSES,
  weight_sensitivity: {
    default_top: ["06001"],
    alt_top: ["06001"],
    rank_stable: true,
    note: "The ranking is weight-dependent; no single weighting is definitive.",
  },
  contextual_count_note:
    "Illustrative only — people who could be affected IF exposed, never an illness or observed-exposure count.",
  status: "OBSERVED",
  availability_status: "available",
  unavailable_reason: null,
  generated_at: "2027-01-01T00:00:00Z",
};

function installBoth() {
  installArtifactFetch({
    community_impact: [STATE_ROW],
    county_community_impact: [COUNTY_ROW],
  });
}

describe("Communities (unified S06 + S07)", () => {
  it("renders the panel and a resolution toggle with both buttons", () => {
    installBoth();
    renderWithSelection(<Communities />);

    expect(screen.getByTestId("communities")).toBeInTheDocument();
    expect(screen.getByTestId("resolution-toggle")).toBeInTheDocument();
    expect(screen.getByTestId("resolution-state")).toBeInTheDocument();
    expect(screen.getByTestId("resolution-county")).toBeInTheDocument();
  });

  it("defaults to the State (S06) view and does NOT show the county resolution-mismatch banner", async () => {
    installBoth();
    renderWithSelection(<Communities />);

    // State is the default resolution: its button is pressed.
    expect(screen.getByTestId("resolution-state")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("resolution-county")).toHaveAttribute("aria-pressed", "false");

    // The S06 state body renders (its "hazard × community vulnerability" title).
    expect(await screen.findByText(/hazard × community vulnerability/i)).toBeInTheDocument();

    // The county-only resolution-mismatch banner and S07 container are absent.
    expect(screen.queryByTestId("resolution-label")).not.toBeInTheDocument();
    expect(screen.queryByTestId("county-communities")).not.toBeInTheDocument();
  });

  it("switches to the County (S07) view when 'By County' is clicked — the resolution-mismatch banner appears", async () => {
    installBoth();
    renderWithSelection(<Communities />);

    fireEvent.click(screen.getByTestId("resolution-county"));

    expect(screen.getByTestId("resolution-county")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("resolution-state")).toHaveAttribute("aria-pressed", "false");

    // S07 container + its county-vulnerability × state-level-hazard banner.
    expect(await screen.findByTestId("county-communities")).toBeInTheDocument();
    const label = screen.getByTestId("resolution-label");
    expect(label).toBeInTheDocument();
    expect(label).toHaveTextContent(/county vulnerability/i);
    expect(label).toHaveTextContent(/state-level hazard/i);
  });

  it("switches back to the State (S06) view when 'By State' is clicked", async () => {
    installBoth();
    renderWithSelection(<Communities />);

    // Go to county...
    fireEvent.click(screen.getByTestId("resolution-county"));
    expect(await screen.findByTestId("county-communities")).toBeInTheDocument();

    // ...then back to state.
    fireEvent.click(screen.getByTestId("resolution-state"));
    expect(screen.getByTestId("resolution-state")).toHaveAttribute("aria-pressed", "true");
    expect(await screen.findByText(/hazard × community vulnerability/i)).toBeInTheDocument();
    expect(screen.queryByTestId("county-communities")).not.toBeInTheDocument();
    expect(screen.queryByTestId("resolution-label")).not.toBeInTheDocument();
  });
});
