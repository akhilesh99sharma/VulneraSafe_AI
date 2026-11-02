import { describe, it, expect } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import type {
  EstablishmentSurveillanceRecord,
  FacilityMapItem,
  FacilityMapCoverage,
} from "../../../types/artifacts";
import Facilities from "../Facilities";
import { installArtifactFetch, renderWithSelection } from "../../../test/renderHelpers";

/**
 * Facilities (unified S03 + Facility Map) wrapper test.
 *
 * Facilities is a THIN view switch: a List ⇄ Map toggle that mounts exactly one
 * child at a time — SupplierMonitor (S03, reads `establishment_surveillance`)
 * for "Supplier List" and FacilityMap (reads `facility_map`) for "Facility Map".
 * So the fixture provides BOTH artifacts, and the test proves only that the
 * toggle swaps which child (and which artifact-backed view) is shown. The
 * children's internals are covered by their own sibling tests and are not
 * re-exercised here.
 *
 * maplibre-gl is mocked to throw under jsdom (see setupTests.ts), so FacilityMap
 * deterministically renders its accessible FallbackGrid — its container keeps
 * data-testid="facility-map-view" and each placed row is a data-testid="facility-pin".
 *
 * Minimal schema-complete fixtures: a single available, well-supported S03 row
 * and a single placed (mpi_verified) facility row carrying its coverage block —
 * enough to render each child's body and prove the switch.
 */

const S03_ROW: EstablishmentSurveillanceRecord = {
  artifact_version: "0.1.0",
  module_id: "S03",
  method_version: "s03.v1",
  pathogen: "Salmonella",
  commodity: "raw_poultry",
  geography_level: "establishment (sampling location)",
  region: "GA",
  establishment_id: "1000",
  establishment_number: null,
  establishment_name: "High Support Plant",
  sample_n: 200,
  positive_n: 60,
  value: 0.3,
  eb_posterior: 0.29,
  ci_low: 0.23,
  ci_high: 0.36,
  ci_method: "beta_eb_95",
  peer_rate: 0.12,
  persistence: {
    repeated_positive_periods: 8,
    periods_supported: 20,
    last_supported_period: "2025-Q4",
    sampling_gaps: 1,
  },
  support_status: "ok",
  latitude: null,
  longitude: null,
  coordinates_status: "unavailable",
  predictive_status: "descriptive_only",
  status: "OBSERVED",
  availability_status: "available",
  unavailable_reason: null,
  fiscal_years: [2015, 2026],
  generated_at: "2027-01-01T00:00:00Z",
};

const SALMONELLA_COV: FacilityMapCoverage = {
  pathogen: "Salmonella",
  total_selected: 1,
  placed: 1,
  unplaced: 0,
  historical_candidate: 0,
  unresolved: 0,
  coverage_pct: 100.0,
  coverage_state: "computed",
};

const MAP_ROW: FacilityMapItem = {
  artifact_version: "0.1.0",
  module_id: "FACILITYMAP",
  method_version: "fm.v1",
  pathogen: "Salmonella",
  normalized_establishment_number: "1",
  establishment_id: "EST-1",
  establishment_number: "M1",
  establishment_name: "Verified Alpha Plant",
  state: "GA",
  county: "Fulton",
  fips_code: null,
  eb_posterior: 0.42,
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
  evidence_summary: "EB posterior 0.42 [0.2, 0.4]; 12/40 positive (OBSERVED, leakage-safe)",
  coverage: SALMONELLA_COV,
  human_review: true,
  status: "OBSERVED",
  generated_at: "2027-01-01T00:00:00Z",
};

function installBoth() {
  installArtifactFetch({
    establishment_surveillance: [S03_ROW],
    facility_map: [MAP_ROW],
  });
}

describe("Facilities (unified S03 + Facility Map)", () => {
  it("renders the panel and a view toggle with both buttons", () => {
    installBoth();
    renderWithSelection(<Facilities />);

    expect(screen.getByTestId("facilities")).toBeInTheDocument();
    expect(screen.getByTestId("facilities-view-toggle")).toBeInTheDocument();
    expect(screen.getByTestId("facilities-view-list")).toBeInTheDocument();
    expect(screen.getByTestId("facilities-view-map")).toBeInTheDocument();
  });

  it("defaults to the Facility Map view and does NOT show the S03 list", async () => {
    installBoth();
    renderWithSelection(<Facilities />);

    // Map is the default view: its button is pressed.
    expect(screen.getByTestId("facilities-view-map")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("facilities-view-list")).toHaveAttribute("aria-pressed", "false");

    // FacilityMap renders its accessible fallback grid under jsdom; its
    // container keeps data-testid="facility-map-view" and the placed row is a facility-pin.
    // FacilityMapView renders both the real map container and (while GL is not
    // ready under jsdom) an inline fallback grid, both carrying this testid, so
    // assert at least one is present.
    expect((await screen.findAllByTestId("facility-map-view")).length).toBeGreaterThanOrEqual(1);
    expect(await screen.findAllByTestId("facility-pin")).toHaveLength(1);

    // The S03 list title is absent while map is shown.
    expect(screen.queryByText(/establishments by EB positivity/i)).not.toBeInTheDocument();
  });

    it("switches to the Facility Map view when 'Facility Map' is clicked", async () => {
    installBoth();
    renderWithSelection(<Facilities />);

    fireEvent.click(screen.getByTestId("facilities-view-map"));

    expect(screen.getByTestId("facilities-view-map")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("facilities-view-list")).toHaveAttribute("aria-pressed", "false");

    // FacilityMap renders its accessible fallback grid under jsdom (maplibre-gl
    // is mocked to throw) — the container keeps data-testid="facility-map-view"
    // and the single placed row is a facility-pin.
    expect(await screen.findByTestId("facility-map-view")).toBeInTheDocument();
    const pins = await screen.findAllByTestId("facility-pin");
    expect(pins).toHaveLength(1);

    // The S03 list title is gone.
    expect(screen.queryByText(/establishments by EB positivity/i)).not.toBeInTheDocument();
  });

  it("switches back to the Supplier List view when 'Supplier List' is clicked", async () => {
    installBoth();
    renderWithSelection(<Facilities />);

    // Go to map...
    fireEvent.click(screen.getByTestId("facilities-view-map"));
    expect(await screen.findByTestId("facility-map-view")).toBeInTheDocument();

    // ...then back to the list.
    fireEvent.click(screen.getByTestId("facilities-view-list"));
    expect(screen.getByTestId("facilities-view-list")).toHaveAttribute("aria-pressed", "true");
    expect(await screen.findByText(/establishments by EB positivity/i)).toBeInTheDocument();
    expect(screen.queryByTestId("facility-map-view")).not.toBeInTheDocument();
    expect(screen.queryByTestId("facility-pin")).not.toBeInTheDocument();
  });
});
