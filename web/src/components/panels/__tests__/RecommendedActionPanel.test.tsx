import { describe, it, expect } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import type { Recommendation } from "../../../types/artifacts";
import RecommendedActionPanel from "../RecommendedActionPanel";
import { installArtifactFetch, renderWithSelection } from "../../../test/renderHelpers";

const RECS: Recommendation[] = [
  {
    action: "Isolate inventory under confirmed recall",
    target_id: "LOT-A",
    rationale: "Lot matches a confirmed FSIS recall.",
    constraints: ["Never distribute a confirmed-recall lot", "Isolate recalled lots"],
    human_review_required: true,
    evidence_refs: ["FSIS Recall API"],
    uncertainty: null,
    alert_source: "REGULATORY",
    status: "OBSERVED",
  },
  {
    action: "Prioritize additional inspection",
    target_id: "LOT-B",
    rationale: "Elevated predicted Salmonella risk.",
    constraints: ["Within inspection budget"],
    human_review_required: false,
    evidence_refs: ["risk_timeseries"],
    uncertainty: 0.08,
    alert_source: "MODEL",
    status: "PREDICTED",
  },
];

describe("RecommendedActionPanel", () => {
  it("shows action, rationale, constraints, review indicator, and alert source (Req 12.7)", async () => {
    installArtifactFetch({ recommendations: RECS });
    renderWithSelection(<RecommendedActionPanel />);

    await waitFor(() =>
      expect(screen.getByTestId("recommendation-list")).toBeInTheDocument(),
    );
    const items = screen.getAllByTestId("recommendation-item");
    expect(items).toHaveLength(2);

    // Regulatory recommendation requires human review.
    expect(items[0]).toHaveTextContent(/isolate inventory/i);
    expect(items[0]).toHaveTextContent(/lot matches a confirmed/i);
    expect(screen.getByTestId("human-review-required")).toBeInTheDocument();

    // Alert badges distinguish source.
    const badges = screen.getAllByTestId("alert-badge");
    expect(badges.map((b) => b.getAttribute("data-source"))).toEqual([
      "REGULATORY",
      "MODEL",
    ]);
  });

  it("degrades to a named empty-state when recommendations fail to load (Req 15.3)", async () => {
    installArtifactFetch({}); // recommendations 404s
    renderWithSelection(<RecommendedActionPanel />);

    await waitFor(() =>
      expect(screen.getByText(/could not load recommendations/i)).toBeInTheDocument(),
    );
  });
});
