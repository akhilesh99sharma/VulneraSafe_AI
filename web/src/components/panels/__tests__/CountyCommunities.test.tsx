import { describe, it, expect } from "vitest";
import { screen, fireEvent, within } from "@testing-library/react";
import type { CountyCommunityImpactRecord, LensPriority } from "../../../types/artifacts";
import CountyCommunities from "../CountyCommunities";
import { installArtifactFetch, renderWithSelection } from "../../../test/renderHelpers";

/**
 * County Communities web-tab test (county-community-impact spec, Task 6.3 /
 * Req 12.1, 12.4, 12.5).
 *
 * maplibre-gl is mocked under jsdom (see setupTests.ts); CountyCommunities does
 * not mount a real map — it reuses the MapView fallback idea as an accessible
 * selector grid with data-testid="map-view" and one data-testid="county-row"
 * button per ranked county (carrying data-county={county_fips}). Every
 * assertion below exercises that jsdom-testable grid.
 *
 * Fixtures carry the FULL CountyCommunityImpactRecord shape (every field
 * present) so they are schema-complete:
 *   status="OBSERVED", module_id="S07", geography_level="county",
 *   resolution_label="county vulnerability x state-level hazard".
 * Five lenses per record: elderly_65plus/low_income/low_access AVAILABLE with a
 * vulnerability_component + priority_score; under5/pregnancy unavailable with
 * null component/score + a stated reason (never fabricated).
 *
 * Salmonella fixture (the pathogen most assertions use):
 *   - 2 available CA counties (same state) sharing an IDENTICAL state-level
 *     hazard (hazard_positivity + hazard_component) but DIFFERENT vulnerability,
 *     so the same-state invariant is visible and the lens ranking differs.
 *   - 1 unavailable county with no state hazard (reason mentions "hazard").
 *   - 1 unavailable county with no vulnerability profile (reason mentions
 *     "vulnerability profile").
 * Listeria + STEC carry a couple of minimal available rows so pathogen
 * switching has data.
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

/** The three data-backed lenses + the two honest-unavailable lenses. */
function lensesAvailable(vuln: {
  elderly: number;
  income: number;
  access: number;
}, prio: { elderly: number; income: number; access: number }): LensPriority[] {
  return [
    lens("elderly_65plus", true, vuln.elderly, prio.elderly),
    lens("low_income", true, vuln.income, prio.income),
    lens("low_access", true, vuln.access, prio.access),
    lens("under5", false, null, null),
    lens("pregnancy", false, null, null),
  ];
}

const SALMONELLA_SENS = {
  default_top: ["06001", "06037"],
  alt_top: ["06037", "06001"],
  rank_stable: false,
  note: "The ranking is weight-dependent; no single weighting is definitive.",
};

function rec(over: Partial<CountyCommunityImpactRecord>): CountyCommunityImpactRecord {
  return {
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
    lenses: lensesAvailable(
      { elderly: 0.9, income: 0.5, access: 0.4 },
      { elderly: 0.84, income: 0.68, access: 0.64 },
    ),
    weight_sensitivity: SALMONELLA_SENS,
    contextual_count_note:
      "Illustrative only — people who could be affected IF exposed, never an illness or observed-exposure count.",
    status: "OBSERVED",
    availability_status: "available",
    unavailable_reason: null,
    generated_at: "2027-01-01T00:00:00Z",
    ...over,
  };
}

// Two available CA (same state) counties: IDENTICAL state-level hazard,
// DIFFERENT vulnerability so the ranking (and ordering) differs by lens.
const CA_ALAMEDA = rec({
  county_fips: "06001",
  county_name: "Alameda",
  state: "CA",
  hazard_positivity: 0.2,
  hazard_component: 0.8,
  affected_population_context: 125000,
  lenses: lensesAvailable(
    { elderly: 0.9, income: 0.4, access: 0.3 },
    { elderly: 0.84, income: 0.64, access: 0.6 },
  ),
});

const CA_LA = rec({
  county_fips: "06037",
  county_name: "Los Angeles",
  state: "CA",
  // SAME state-level hazard as Alameda (same state + pathogen).
  hazard_positivity: 0.2,
  hazard_component: 0.8,
  affected_population_context: 980000,
  lenses: lensesAvailable(
    { elderly: 0.2, income: 0.95, access: 0.9 },
    { elderly: 0.6, income: 0.86, access: 0.84 },
  ),
});

// Unavailable: no state-level hazard for this pathogen (retained, not dropped).
const TX_NO_HAZARD = rec({
  county_fips: "48201",
  county_name: "Harris",
  state: "TX",
  hazard_positivity: null,
  hazard_component: null,
  affected_population_context: null,
  lenses: lensesAvailable(
    { elderly: 0.5, income: 0.5, access: 0.5 },
    { elderly: 0.5, income: 0.5, access: 0.5 },
  ),
  availability_status: "unavailable",
  unavailable_reason: "State has no hazard for this pathogen.",
});

// Unavailable: no county vulnerability profile (retained, not dropped).
const NY_NO_VULN = rec({
  county_fips: "36061",
  county_name: "New York",
  state: "NY",
  hazard_positivity: 0.3,
  hazard_component: 0.9,
  affected_population_context: null,
  total_population: null,
  elderly_65plus_share: null,
  low_income_share: null,
  low_access_share: null,
  lenses: [
    lens("elderly_65plus", true, null, null),
    lens("low_income", true, null, null),
    lens("low_access", true, null, null),
    lens("under5", false, null, null),
    lens("pregnancy", false, null, null),
  ],
  availability_status: "unavailable",
  unavailable_reason: "No county vulnerability profile.",
});

// Minimal Listeria + STEC available rows so pathogen switching has data.
const LISTERIA_SENS = {
  default_top: ["17031"],
  alt_top: ["17031"],
  rank_stable: true,
  note: "The ranking is weight-dependent; no single weighting is definitive.",
};
const STEC_SENS = {
  default_top: ["04013"],
  alt_top: ["04013"],
  rank_stable: true,
  note: "The ranking is weight-dependent; no single weighting is definitive.",
};

const LISTERIA_COOK = rec({
  pathogen: "Listeria",
  county_fips: "17031",
  county_name: "Cook",
  state: "IL",
  hazard_positivity: 0.1,
  hazard_component: 0.5,
  affected_population_context: 410000,
  acs_vintage: "ACS5 2022",
  atlas_vintage: "FARA/LRAM 2019",
  lenses: lensesAvailable(
    { elderly: 0.7, income: 0.6, access: 0.55 },
    { elderly: 0.58, income: 0.54, access: 0.52 },
  ),
  weight_sensitivity: LISTERIA_SENS,
});

const STEC_MARICOPA = rec({
  pathogen: "STEC",
  county_fips: "04013",
  county_name: "Maricopa",
  state: "AZ",
  hazard_positivity: 0.15,
  hazard_component: 0.6,
  affected_population_context: 530000,
  acs_vintage: "ACS5 2022",
  atlas_vintage: "FARA/LRAM 2019",
  lenses: lensesAvailable(
    { elderly: 0.4, income: 0.5, access: 0.45 },
    { elderly: 0.48, income: 0.54, access: 0.51 },
  ),
  weight_sensitivity: STEC_SENS,
});

const ROWS: CountyCommunityImpactRecord[] = [
  CA_ALAMEDA,
  CA_LA,
  TX_NO_HAZARD,
  NY_NO_VULN,
  LISTERIA_COOK,
  STEC_MARICOPA,
];

describe("CountyCommunities", () => {
  it("renders via useArtifact(county_community_impact) with the prominent resolution-mismatch label", async () => {
    installArtifactFetch({ county_community_impact: ROWS });
    renderWithSelection(<CountyCommunities />);

    // Container is present immediately; the artifact load resolves the body.
    expect(screen.getByTestId("county-communities")).toBeInTheDocument();

    // Await the async artifact load through the ranked grid.
    await screen.findByTestId("map-view");

    // The prominent resolution label carries the county-vulnerability x
    // state-level-hazard mismatch framing (Req 1.6). The phrases appear across
    // the heading and body of the banner, so assert on the label's full text
    // content (robust to the text being split across child elements).
    const label = screen.getByTestId("resolution-label");
    expect(label).toBeInTheDocument();
    expect(label).toHaveTextContent(/county vulnerability/i);
    expect(label).toHaveTextContent(/state-level hazard/i);
    expect(label).toHaveTextContent(/STATE's/i);
    // Honest framing: it is NOT a county-measured hazard.
    expect(label).toHaveTextContent(/not a county-measured hazard/i);
  });

  it("ranks available Salmonella counties by the lens priority_score desc; both same-state counties share one state-level hazard; unavailable counties are not rows", async () => {
    installArtifactFetch({ county_community_impact: ROWS });
    renderWithSelection(<CountyCommunities />);

    await screen.findByTestId("map-view");
    const rows = screen.getAllByTestId("county-row");

    // Only the 2 available CA counties render as county-row (the no-hazard and
    // no-vuln counties are retained but not ranked).
    expect(rows).toHaveLength(2);
    const fipsInOrder = rows.map((r) => r.getAttribute("data-county"));
    expect(fipsInOrder).not.toContain("48201"); // no state hazard
    expect(fipsInOrder).not.toContain("36061"); // no vuln profile

    // Default lens is elderly_65plus: Alameda (0.84) ranks above LA (0.60).
    expect(fipsInOrder).toEqual(["06001", "06037"]);

    // Both same-state counties carry the shared state-level hazard: each row
    // shows the "state-level hazard" labeled context. (The hazard_component is
    // identical across the two CA rows; the label appears once per row.)
    for (const r of rows) {
      expect(within(r).getByText(/state-level hazard/i)).toBeInTheDocument();
    }

    // Switching to the low-income lens reorders: LA (0.86) now leads Alameda
    // (0.64), proving the lens reprioritizes while the hazard is per-county.
    fireEvent.click(screen.getByRole("button", { name: /low-income tracts/i }));
    const reordered = screen
      .getAllByTestId("county-row")
      .map((r) => r.getAttribute("data-county"));
    expect(reordered).toEqual(["06037", "06001"]);
  });

  it("shows the honest unavailable-counties summary with no-hazard vs no-vulnerability counts", async () => {
    installArtifactFetch({ county_community_impact: ROWS });
    renderWithSelection(<CountyCommunities />);

    await screen.findByTestId("map-view");

    // Summary of counties retained but not shown (Req 5.5): 1 with no state
    // hazard, 1 with no vulnerability profile.
    const summary = screen.getByText(/counties are unavailable for Salmonella/i);
    expect(summary).toBeInTheDocument();
    expect(summary).toHaveTextContent(/not dropped or fabricated/i);
    expect(summary).toHaveTextContent(/no state-level hazard/i);
    expect(summary).toHaveTextContent(/no county vulnerability profile/i);
  });

  it("switching to an unavailable lens shows the honest not-available panel; switching back restores the ranked list; pathogen switch updates the list", async () => {
    installArtifactFetch({ county_community_impact: ROWS });
    renderWithSelection(<CountyCommunities />);

    await screen.findByTestId("map-view");

    // under-5 lens is unavailable -> honest panel, no ranked grid.
    fireEvent.click(screen.getByRole("button", { name: /children under 5/i }));
    expect(screen.getByText(/this lens is not available/i)).toBeInTheDocument();
    expect(screen.queryByTestId("map-view")).not.toBeInTheDocument();

    // Back to a data-backed lens -> ranked grid returns.
    fireEvent.click(screen.getByRole("button", { name: /low food-access tracts/i }));
    expect(screen.getByTestId("map-view")).toBeInTheDocument();
    expect(screen.getAllByTestId("county-row")).toHaveLength(2);

    // Pathogen switch to Listeria updates the ranked list to Listeria rows.
    fireEvent.click(screen.getByRole("button", { name: /^Listeria$/i }));
    const listeriaRows = screen.getAllByTestId("county-row");
    expect(listeriaRows.map((r) => r.getAttribute("data-county"))).toEqual(["17031"]);

    // STEC switch updates again.
    fireEvent.click(screen.getByRole("button", { name: /STEC/i }));
    const stecRows = screen.getAllByTestId("county-row");
    expect(stecRows.map((r) => r.getAttribute("data-county"))).toEqual(["04013"]);
  });

  it("selecting a county-row opens its affected-population detail with the illustrative note, shows OBSERVED, and never says PREDICTED/SIMULATED", async () => {
    installArtifactFetch({ county_community_impact: ROWS });
    renderWithSelection(<CountyCommunities />);

    await screen.findByTestId("map-view");

    // OBSERVED provenance tag is present; no PREDICTED/SIMULATED for S07.
    const tags = screen.getAllByTestId("status-tag");
    expect(tags.length).toBeGreaterThanOrEqual(1);
    expect(tags.every((t) => t.getAttribute("data-status") === "OBSERVED")).toBe(true);
    expect(screen.queryByText(/PREDICTED/)).not.toBeInTheDocument();
    expect(screen.queryByText(/SIMULATED/)).not.toBeInTheDocument();

    // Select Alameda -> detail line with affected-population context + the
    // "could be affected IF exposed" illustrative note.
    const alameda = screen
      .getAllByTestId("county-row")
      .find((r) => r.getAttribute("data-county") === "06001")!;
    fireEvent.click(alameda);
    expect(screen.getByText(/people could be affected IF exposed/i)).toBeInTheDocument();
    expect(screen.getByText(/Affected-population context/i)).toBeInTheDocument();
    // affected_population_context 125000 renders via formatNumber(_, 0) -> "125000".
    expect(screen.getByText(/125000/)).toBeInTheDocument();
  });

  it("degrades to an EmptyState naming county_community_impact when the artifact is missing", async () => {
    installArtifactFetch({});
    renderWithSelection(<CountyCommunities />);

    expect(
      await screen.findByText(/could not load county_community_impact/i),
    ).toBeInTheDocument();
  });
});
