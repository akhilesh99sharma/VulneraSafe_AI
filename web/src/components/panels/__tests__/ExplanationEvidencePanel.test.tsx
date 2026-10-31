import { describe, it, expect } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import type { ProvenanceEntry, Recommendation } from "../../../types/artifacts";
import ExplanationEvidencePanel from "../ExplanationEvidencePanel";
import { installArtifactFetch, renderWithSelection } from "../../../test/renderHelpers";

const RECS: Recommendation[] = [
  {
    action: "Prioritize additional inspection",
    target_id: "LOT-B",
    rationale: "Elevated predicted Salmonella risk.",
    constraints: ["Within inspection budget"],
    human_review_required: false,
    evidence_refs: ["FSIS lab sampling"],
    uncertainty: 0.08,
    alert_source: "MODEL",
    status: "PREDICTED",
  },
];

const PROV: ProvenanceEntry[] = [
  {
    source: "FSIS lab sampling",
    url: "https://example.gov/fsis",
    access_date: "2026-01-15",
    license: "US-PD",
    geographic_coverage: "US states",
    temporal_coverage: "2014-2026",
    checksum: "abc123",
    total_samples: 1000,
    positive_count: 42,
    missingness: { region: 0.0 },
    known_biases: ["sampling program skew"],
    notes: "",
  },
];

describe("ExplanationEvidencePanel", () => {
  it("prompts to select a recommendation when none is selected", async () => {
    installArtifactFetch({ recommendations: RECS, provenance: PROV });
    renderWithSelection(<ExplanationEvidencePanel />);

    await waitFor(() =>
      expect(screen.getByText(/select a recommendation/i)).toBeInTheDocument(),
    );
  });

  it("shows source data, uncertainty, and limitations for the selection (Req 12.8)", async () => {
    installArtifactFetch({ recommendations: RECS, provenance: PROV });
    renderWithSelection(<ExplanationEvidencePanel />, {
      recommendationTargetId: "LOT-B",
    });

    await waitFor(() =>
      expect(screen.getByTestId("evidence-detail")).toBeInTheDocument(),
    );
    // Source data resolved from provenance.
    expect(screen.getByTestId("evidence-ref")).toHaveTextContent("FSIS lab sampling");
    expect(screen.getByTestId("evidence-ref")).toHaveTextContent("US-PD");
    // Uncertainty formatted as a band.
    expect(screen.getByTestId("evidence-uncertainty")).toHaveTextContent("8.0%");
    // Limitations combine constraints + known biases.
    expect(screen.getByText(/within inspection budget/i)).toBeInTheDocument();
    expect(screen.getByText(/sampling program skew/i)).toBeInTheDocument();
  });

  it("renders even if provenance fails to load (evidence ref shown without detail)", async () => {
    installArtifactFetch({ recommendations: RECS }); // provenance 404s
    renderWithSelection(<ExplanationEvidencePanel />, {
      recommendationTargetId: "LOT-B",
    });

    await waitFor(() =>
      expect(screen.getByTestId("evidence-detail")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("evidence-uncertainty")).toHaveTextContent("8.0%");
  });
});
