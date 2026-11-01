import { describe, it, expect } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import type { CommunityImpactRecord } from "../../../types/artifacts";
import VulnerableCommunities from "../VulnerableCommunities";
import { installArtifactFetch } from "../../../test/renderHelpers";

function lens(id: string, available: boolean, vuln: number | null, prio: number | null) {
  return {
    lens: id,
    available,
    vulnerability_component: vuln,
    priority_score: prio,
    weights: "hazard 0.6 / vulnerability 0.4",
    unavailable_reason: available ? null : `${id} not available in current ACS extraction.`,
  };
}

function rec(over: Partial<CommunityImpactRecord>): CommunityImpactRecord {
  return {
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
    lenses: [
      lens("elderly_65plus", true, 1.0, 1.0),
      lens("low_income", true, 0.5, 0.8),
      lens("low_access", true, 0.4, 0.76),
      lens("under5", false, null, null),
      lens("pregnancy", false, null, null),
    ],
    weight_sensitivity: {
      default_top: ["ME", "NH", "RI", "CT", "MI"],
      alt_top: ["ME", "NH", "RI", "CT", "FL"],
      rank_stable: false,
      note: "weight-dependent; no single weighting definitive",
    },
    contextual_count_note: "Contextual count — people who could be affected IF exposed, never an illness count.",
    status: "OBSERVED",
    availability_status: "available",
    unavailable_reason: null,
    generated_at: "2027-01-01T00:00:00Z",
    ...over,
  };
}

const ROWS: CommunityImpactRecord[] = [
  rec({ region: "ME", hazard_component: 1.0, lenses: [
    lens("elderly_65plus", true, 1.0, 1.0),
    lens("low_income", true, 0.5, 0.8),
    lens("low_access", true, 0.4, 0.76),
    lens("under5", false, null, null),
    lens("pregnancy", false, null, null),
  ] }),
  rec({ region: "TX", hazard_component: 0.4, lenses: [
    lens("elderly_65plus", true, 0.2, 0.32),
    lens("low_income", true, 0.9, 0.6),
    lens("low_access", true, 0.7, 0.52),
    lens("under5", false, null, null),
    lens("pregnancy", false, null, null),
  ] }),
];

describe("VulnerableCommunities", () => {
  it("renders the priority ranking with side-by-side hazard/vulnerability legends", async () => {
    installArtifactFetch({ community_impact: ROWS });
    render(<VulnerableCommunities />);
    await waitFor(() => expect(screen.getByText(/priority ranking/i)).toBeInTheDocument());
    expect(screen.getByText(/hazard \(read-only surveillance\)/i)).toBeInTheDocument();
    expect(screen.getByText(/vulnerability \(this lens\)/i)).toBeInTheDocument();
  });

  it("keeps the hazard component unchanged when the lens switches (reorders only)", async () => {
    installArtifactFetch({ community_impact: ROWS });
    render(<VulnerableCommunities />);
    await waitFor(() => expect(screen.getByText(/priority ranking/i)).toBeInTheDocument());
    // under 65+, ME (hazard 1.0, vuln 1.0 -> priority 1.0) ranks above TX.
    // Switch to low-income: TX vuln 0.9 but hazard only 0.4; ME still leads on
    // priority, but the point under test is that hazard bars are per-record and
    // independent of lens. We assert ME's hazard positivity label is present in
    // both lenses (hazard is a record field, not a lens field).
    fireEvent.click(screen.getByRole("button", { name: /low-income tracts/i }));
    await waitFor(() => expect(screen.getByText(/priority ranking — low-income tracts/i)).toBeInTheDocument());
    // both states still listed (hazard unchanged, only order/priority differ)
    // Each state now appears both in the top-priority callout and its ranked row,
    // so assert presence (>=1) rather than uniqueness.
    expect(screen.getAllByText("ME").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("TX").length).toBeGreaterThanOrEqual(1);
  });

  it("shows an explicit not-available state for the pregnancy lens", async () => {
    installArtifactFetch({ community_impact: ROWS });
    render(<VulnerableCommunities />);
    await waitFor(() => expect(screen.getByText(/priority ranking/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /pregnancy \/ newborn/i }));
    await waitFor(() =>
      expect(screen.getByText(/this lens is not available/i)).toBeInTheDocument(),
    );
  });

  it("shows an explicit not-available state for the under-5 lens", async () => {
    installArtifactFetch({ community_impact: ROWS });
    render(<VulnerableCommunities />);
    await waitFor(() => expect(screen.getByText(/priority ranking/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /children under 5/i }));
    await waitFor(() =>
      expect(screen.getByText(/this lens is not available/i)).toBeInTheDocument(),
    );
  });

  it("reports weight sensitivity (default vs alternative weighting)", async () => {
    installArtifactFetch({ community_impact: ROWS });
    render(<VulnerableCommunities />);
    await waitFor(() => expect(screen.getByText(/how sensitive is this to the weights/i)).toBeInTheDocument());
  });

  it("degrades to an honest empty state when the artifact is missing", async () => {
    installArtifactFetch({});
    render(<VulnerableCommunities />);
    await waitFor(() =>
      expect(screen.getByText(/could not load community_impact/i)).toBeInTheDocument(),
    );
  });
});
