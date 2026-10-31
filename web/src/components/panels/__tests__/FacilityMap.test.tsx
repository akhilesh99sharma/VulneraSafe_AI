import { describe, it, expect } from "vitest";
import { screen, fireEvent, within } from "@testing-library/react";
import type { FacilityMapItem, FacilityMapCoverage } from "../../../types/artifacts";
import FacilityMap from "../FacilityMap";
import { installArtifactFetch, renderWithSelection } from "../../../test/renderHelpers";

/**
 * Facility Map web-tab test (facility-map spec, Task 6.3 / Req 12.3).
 *
 * maplibre-gl is mocked to throw under jsdom (see setupTests.ts), so
 * FacilityMapView deterministically renders its accessible FallbackGrid: one
 * data-testid="facility-pin" button per PLACED establishment (a row carrying a
 * real numeric lat AND lon). Every assertion below exercises that fallback.
 *
 * The fixture carries the full FacilityMapItem shape (all 36 fields) so it is
 * schema-complete. Two pathogens are used:
 *   Salmonella: 2 mpi_verified placed + 1 historical_candidate placed (total 3)
 *   Listeria:   1 historical_candidate WITHOUT coords + 1 unresolved (total 2)
 * Each row carries its per-pathogen coverage block verbatim (never recomputed).
 */

/** Per-pathogen coverage blocks, consistent with the fixture rows below. */
const SALMONELLA_COV: FacilityMapCoverage = {
  pathogen: "Salmonella",
  total_selected: 3,
  placed: 2,
  unplaced: 1,
  historical_candidate: 1,
  unresolved: 0,
  coverage_pct: 66.7,
  coverage_state: "computed",
};

const LISTERIA_COV: FacilityMapCoverage = {
  pathogen: "Listeria",
  total_selected: 2,
  placed: 0,
  unplaced: 2,
  historical_candidate: 1,
  unresolved: 1,
  coverage_pct: 0.0,
  coverage_state: "computed",
};

function row(over: Partial<FacilityMapItem>): FacilityMapItem {
  return {
    artifact_version: "0.1.0",
    module_id: "FACILITYMAP",
    method_version: "fm.v1",
    pathogen: "Salmonella",
    normalized_establishment_number: "1",
    establishment_id: "EST-1",
    establishment_number: "M1",
    establishment_name: "Facility One",
    state: "GA",
    county: null,
    fips_code: null,
    eb_posterior: 0.3,
    ci_low: 0.2,
    ci_high: 0.4,
    sample_n: 40,
    positive_n: 12,
    support_status: "ok",
    source_selection: "s03",
    placement_status: "placed",
    location_status: "mpi_verified",
    match_method: "fsis_mpi_establishment_id",
    match_confidence: "verified",
    verified_against_fsis_id: true,
    historical_inspection_number: null,
    historical_address: null,
    coordinate_source: "FSIS MPI Directory (published)",
    evidence_urls: [],
    lat: 33.75,
    lon: -84.39,
    address: "123 Poultry Rd, Atlanta, GA",
    unplaced_reason: null,
    evidence_summary: "EB posterior 0.3 [0.2, 0.4]; 12/40 positive (OBSERVED, leakage-safe)",
    coverage: SALMONELLA_COV,
    human_review: true,
    status: "OBSERVED",
    generated_at: "2027-01-01T00:00:00Z",
    ...over,
  };
}

const VERIFIED_A = row({
  normalized_establishment_number: "1",
  establishment_id: "EST-1",
  establishment_number: "M1",
  establishment_name: "Verified Alpha Plant",
  state: "GA",
  county: "Fulton",
  eb_posterior: 0.42,
  lat: 33.75,
  lon: -84.39,
});

const VERIFIED_B = row({
  normalized_establishment_number: "2",
  establishment_id: "EST-2",
  establishment_number: "M2",
  establishment_name: "Verified Beta Plant",
  state: "TX",
  county: null,
  eb_posterior: 0.31,
  lat: 29.76,
  lon: -95.37,
});

const CANDIDATE_PLACED = row({
  normalized_establishment_number: "3",
  establishment_id: "EST-3",
  establishment_number: "M3",
  establishment_name: "Candidate Placed Plant",
  state: "CA",
  county: null,
  eb_posterior: 0.28,
  source_selection: "both",
  placement_status: "historical_candidate",
  location_status: "historical_candidate",
  match_method: "historical_name_state_address",
  match_confidence: "probable",
  verified_against_fsis_id: false,
  historical_inspection_number: "M44857 / P44857",
  historical_address: "900 Historic Ave, Fresno, CA",
  coordinate_source: "external geocode",
  evidence_urls: ["https://example.gov/fsis/historical/est-3"],
  lat: 36.74,
  lon: -119.77,
  address: null,
  unplaced_reason: null,
});

const CANDIDATE_NOCOORDS = row({
  pathogen: "Listeria",
  normalized_establishment_number: "4",
  establishment_id: "EST-4",
  establishment_number: "M4",
  establishment_name: "Candidate NoCoords Plant",
  state: "OH",
  county: null,
  eb_posterior: 0.22,
  source_selection: "s03",
  placement_status: "unplaced",
  location_status: "historical_candidate",
  match_method: "historical_name_state_address",
  match_confidence: "probable",
  verified_against_fsis_id: false,
  historical_inspection_number: "M12345 / P12345",
  historical_address: "55 Archive St, Columbus, OH",
  coordinate_source: null,
  evidence_urls: ["https://example.gov/fsis/historical/est-4"],
  lat: null,
  lon: null,
  address: null,
  unplaced_reason: "no geocodable address for historical candidate",
  coverage: LISTERIA_COV,
});

const UNRESOLVED = row({
  pathogen: "Listeria",
  normalized_establishment_number: "5",
  establishment_id: "EST-5",
  establishment_number: "M5",
  establishment_name: "Unresolved Plant",
  state: "PA",
  county: null,
  eb_posterior: 0.19,
  source_selection: "action_queue",
  placement_status: "unplaced",
  location_status: "unresolved",
  match_method: null,
  match_confidence: null,
  verified_against_fsis_id: false,
  historical_inspection_number: null,
  historical_address: null,
  coordinate_source: null,
  evidence_urls: [],
  lat: null,
  lon: null,
  address: null,
  unplaced_reason: "establishment number not found in MPI Directory",
  coverage: LISTERIA_COV,
});

const ROWS: FacilityMapItem[] = [
  VERIFIED_A,
  VERIFIED_B,
  CANDIDATE_PLACED,
  CANDIDATE_NOCOORDS,
  UNRESOLVED,
];

describe("FacilityMap", () => {
  it("renders via useArtifact(facility_map) with coverage strip and the sourcing-scrutiny framing", async () => {
    installArtifactFetch({ facility_map: ROWS });
    renderWithSelection(<FacilityMap />);

    // Await the async artifact load through the coverage strip.
    const strip = await screen.findByTestId("coverage-strip");
    // placed/total across both pathogens: 2/5 and a measured percentage.
    expect(within(strip).getByText(/2\/5/)).toBeInTheDocument();
    expect(within(strip).getByText(/40\.0%/)).toBeInTheDocument();

    // Framing note: sourcing-scrutiny reference layer, NOT the retailer's
    // suppliers. Both phrases appear in the hero banner and the "how to read"
    // note, so assert at least one occurrence of each.
    expect(
      screen.getAllByText(/sourcing-scrutiny reference layer/i).length,
    ).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/NOT the retailer/i).length).toBeGreaterThanOrEqual(1);
  });

  it("plots only placed facilities as pins with distinct location-status markers", async () => {
    installArtifactFetch({ facility_map: ROWS });
    renderWithSelection(<FacilityMap />);

    const pins = await screen.findAllByTestId("facility-pin");
    // 3 placed rows (2 verified + 1 historical candidate with coords).
    expect(pins).toHaveLength(3);

    const statuses = pins.map((p) => p.getAttribute("data-location-status"));
    expect(statuses.filter((s) => s === "mpi_verified")).toHaveLength(2);
    expect(statuses.filter((s) => s === "historical_candidate")).toHaveLength(1);

    // The null-coord candidate and the unresolved row are NOT pins.
    const pinIds = pins.map((p) => p.getAttribute("data-establishment-id"));
    expect(pinIds).not.toContain("EST-4");
    expect(pinIds).not.toContain("EST-5");
  });

  it("filters: hiding historical candidates drops that pin; pathogen filter restricts rows", async () => {
    installArtifactFetch({ facility_map: ROWS });
    renderWithSelection(<FacilityMap />);

    await screen.findAllByTestId("facility-pin");
    expect(screen.getAllByTestId("facility-pin")).toHaveLength(3);

    // Hide historical candidates -> the placed candidate pin disappears,
    // the two verified pins remain.
    fireEvent.click(screen.getByTestId("status-toggle-historical_candidate"));
    const afterToggle = screen.getAllByTestId("facility-pin");
    expect(afterToggle).toHaveLength(2);
    expect(
      afterToggle.every((p) => p.getAttribute("data-location-status") === "mpi_verified"),
    ).toBe(true);

    // Re-enable, then exercise the pathogen filter: Listeria has no placed rows
    // (0 pins) but does carry 2 unplaced rows, so the panel still renders.
    fireEvent.click(screen.getByTestId("status-toggle-historical_candidate"));
    fireEvent.click(screen.getByRole("button", { name: /^Listeria$/i }));
    expect(screen.queryAllByTestId("facility-pin")).toHaveLength(0);
    // Listeria's unplaced rows surface in the unresolved section (they also
    // appear in the ranked list, so scope the assertion to that section).
    const listeriaUnresolved = screen.getByTestId("unresolved-section");
    expect(
      within(listeriaUnresolved).getByText(/Candidate NoCoords Plant/i),
    ).toBeInTheDocument();
    expect(
      within(listeriaUnresolved).getByText(/Unresolved Plant/i),
    ).toBeInTheDocument();

    // Switching to Salmonella restricts back to its 3 placed pins.
    fireEvent.click(screen.getByRole("button", { name: /^Salmonella$/i }));
    expect(screen.getAllByTestId("facility-pin")).toHaveLength(3);
  });

  it("selecting a facility shows its detail with the right provenance disclaimer", async () => {
    installArtifactFetch({ facility_map: ROWS });
    renderWithSelection(<FacilityMap />);

    // Wait for load, then select the historical candidate via its ranked-list
    // row -> identity-NOT-confirmed disclaimer + evidence anchor.
    const rankedRows = await screen.findAllByTestId("ranked-facility");
    const candidateRow = rankedRows.find(
      (r) => r.getAttribute("data-establishment-id") === "EST-3",
    )!;
    fireEvent.click(candidateRow);
    const candidateDetail = await screen.findByTestId("facility-detail");
    expect(within(candidateDetail).getByText(/identity NOT confirmed/i)).toBeInTheDocument();
    const anchor = within(candidateDetail).getByRole("link", {
      name: /example\.gov\/fsis\/historical\/est-3/i,
    });
    expect(anchor).toHaveAttribute("href", "https://example.gov/fsis/historical/est-3");

    // Close, then select a verified facility -> matched-to-FSIS-MPI text.
    fireEvent.click(within(candidateDetail).getByRole("button", { name: /close/i }));
    const verifiedRow = (await screen.findAllByTestId("ranked-facility")).find(
      (r) => r.getAttribute("data-establishment-id") === "EST-1",
    )!;
    fireEvent.click(verifiedRow);
    const verifiedDetail = await screen.findByTestId("facility-detail");
    expect(
      within(verifiedDetail).getByText(/Matched to the FSIS MPI Directory/i),
    ).toBeInTheDocument();
  });

  it("lists unplaced establishments with reasons and a human-review chip on surfaced rows", async () => {
    installArtifactFetch({ facility_map: ROWS });
    renderWithSelection(<FacilityMap />);

    const unresolved = await screen.findByTestId("unresolved-section");
    // Both Listeria unplaced rows appear (null-coord candidate + unresolved).
    expect(within(unresolved).getByText(/Candidate NoCoords Plant/i)).toBeInTheDocument();
    expect(within(unresolved).getByText(/Unresolved Plant/i)).toBeInTheDocument();
    // Stated reasons are read from the rows, never approximated.
    expect(
      within(unresolved).getByText(/establishment number not found in MPI Directory/i),
    ).toBeInTheDocument();
    expect(
      within(unresolved).getByText(/no geocodable address for historical candidate/i),
    ).toBeInTheDocument();

    // A human-review chip is present on surfaced facilities (ranked list rows).
    expect(screen.getAllByText(/Human review/i).length).toBeGreaterThanOrEqual(1);
  });

  it("degrades to an EmptyState naming facility_map when the artifact is missing", async () => {
    installArtifactFetch({});
    renderWithSelection(<FacilityMap />);

    expect(
      await screen.findByText(/could not load facility_map/i),
    ).toBeInTheDocument();
  });
});
