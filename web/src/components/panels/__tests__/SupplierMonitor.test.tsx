import { describe, it, expect } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import type { EstablishmentSurveillanceRecord } from "../../../types/artifacts";
import SupplierMonitor from "../SupplierMonitor";
import { installArtifactFetch } from "../../../test/renderHelpers";

function rec(over: Partial<EstablishmentSurveillanceRecord>): EstablishmentSurveillanceRecord {
  return {
    artifact_version: "0.1.0",
    module_id: "S03",
    method_version: "s03.v1",
    pathogen: "Salmonella",
    commodity: "raw_poultry",
    geography_level: "establishment (sampling location)",
    region: "GA",
    establishment_id: "1000",
    establishment_number: null,
    establishment_name: "Test Plant A",
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
    county: null,
    fips_code: null,
    city: null,
    predictive_status: "descriptive_only",
    status: "OBSERVED",
    availability_status: "available",
    unavailable_reason: null,
    fiscal_years: [2015, 2026],
    generated_at: "2027-01-01T00:00:00Z",
    ...over,
  };
}

const ROWS: EstablishmentSurveillanceRecord[] = [
  rec({ establishment_id: "1000", establishment_name: "High Support Plant", region: "GA", eb_posterior: 0.29, support_status: "ok", county: "Elbert County", fips_code: "13105", city: "Elberton", latitude: 34.098, longitude: -82.838, coordinates_status: "available" }),
  rec({ establishment_id: "1001", establishment_name: "Mid Support Plant", region: "TX", eb_posterior: 0.18, support_status: "ok", sample_n: 90, positive_n: 15, value: 0.167 }),
  rec({ establishment_id: "2000", establishment_name: "Thinly Tested Plant", region: "GA", support_status: "low_support", sample_n: 6, positive_n: 3, value: 0.5, eb_posterior: 0.15, ci_low: 0.03, ci_high: 0.34 }),
];

describe("SupplierMonitor", () => {
  it("ranks well-sampled establishments by EB posterior with a likely range", async () => {
    installArtifactFetch({ establishment_surveillance: ROWS });
    render(<SupplierMonitor />);
    await waitFor(() =>
      expect(screen.getByText(/highest eb positivity/i)).toBeInTheDocument(),
    );
    expect(screen.getByText("High Support Plant", { exact: false })).toBeInTheDocument();
    // a likely range (credible interval) is shown
    expect(screen.getAllByText(/likely/i).length).toBeGreaterThan(0);
  });

  it("separates low-support establishments as uncertain, not safe", async () => {
    installArtifactFetch({ establishment_surveillance: ROWS });
    render(<SupplierMonitor />);
    await waitFor(() => expect(screen.getByText(/highest eb positivity/i)).toBeInTheDocument());
    // the low-support section exists and uses the uncertain-not-safe wording
    expect(screen.getByText(/insufficient testing — uncertain, not safe/i)).toBeInTheDocument();
    expect(screen.getByText("Thinly Tested Plant", { exact: false })).toBeInTheDocument();
  });

  it("shows an honest facility-locations summary with real county and coordinate", async () => {
    installArtifactFetch({ establishment_surveillance: ROWS });
    render(<SupplierMonitor />);
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /^facility locations$/i })).toBeInTheDocument(),
    );
    // the honest MPI-join caveat is present
    expect(
      screen.getByText(/processing or sampling site/i),
    ).toBeInTheDocument();
    // a matched establishment shows its real county + coordinate
    expect(screen.getAllByText(/elbert county/i).length).toBeGreaterThan(0);
  });


  it("filters the list by state", async () => {
    installArtifactFetch({ establishment_surveillance: ROWS });
    render(<SupplierMonitor />);
    await waitFor(() => expect(screen.getByText("Mid Support Plant", { exact: false })).toBeInTheDocument());
    // select TX — the GA high-support plant should drop out of the ranked list
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "TX" } });
    await waitFor(() =>
      expect(screen.queryByText("High Support Plant", { exact: false })).not.toBeInTheDocument(),
    );
    expect(screen.getByText("Mid Support Plant", { exact: false })).toBeInTheDocument();
  });

  it("degrades to an honest empty state when the artifact is missing", async () => {
    installArtifactFetch({});
    render(<SupplierMonitor />);
    await waitFor(() =>
      expect(screen.getByText(/could not load establishment_surveillance/i)).toBeInTheDocument(),
    );
  });
});
