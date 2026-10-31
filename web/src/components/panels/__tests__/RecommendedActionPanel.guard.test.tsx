import { describe, it, expect } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import type { Recommendation } from "../../../types/artifacts";
import RecommendedActionPanel from "../RecommendedActionPanel";
import {
  installArtifactFetch,
  renderWithSelection,
} from "../../../test/renderHelpers";

/**
 * Responsible-use guard render tests (Task 7.1 — Req 16.4, 16.5, 16.6).
 *
 * These mirror the Python `withhold_unsupported_model_recommendation` guard in
 * `src/responsible.py`:
 *   1. a MODEL rec without a quantified uncertainty renders the withheld note,
 *      NOT the recommendation;
 *   2. a MODEL rec without supporting evidence also renders the withheld note;
 *   3. a REGULATORY rec ALWAYS renders even with null uncertainty and no
 *      evidence (regulatory track is independent of model uncertainty);
 *   4. a shown recommendation displays supporting evidence, a quantified
 *      uncertainty measure, and a human-review indicator (Req 16.4).
 *
 * (NOTE: authored but not executed — node/npm is unavailable in this env.)
 */

function modelRec(overrides: Partial<Recommendation> = {}): Recommendation {
  return {
    action: "Prioritize additional inspection",
    target_id: "LOT-MODEL",
    rationale: "Elevated predicted Salmonella risk.",
    constraints: ["Within inspection budget"],
    human_review_required: true,
    evidence_refs: ["risk_timeseries"],
    uncertainty: 0.08,
    alert_source: "MODEL",
    status: "PREDICTED",
    ...overrides,
  };
}

function regulatoryRec(overrides: Partial<Recommendation> = {}): Recommendation {
  return {
    action: "Isolate inventory under confirmed recall",
    target_id: "LOT-REG",
    rationale: "Lot matches a confirmed FSIS recall.",
    constraints: ["Never distribute a confirmed-recall lot"],
    human_review_required: true,
    // Regulatory recs carry no model uncertainty and may carry no evidence
    // refs — they must still render.
    evidence_refs: [],
    uncertainty: null,
    alert_source: "REGULATORY",
    status: "OBSERVED",
    ...overrides,
  };
}

describe("RecommendedActionPanel — responsible-use guard (Req 16.5)", () => {
  it("withholds a MODEL rec with null uncertainty, showing the explanatory note", async () => {
    installArtifactFetch({
      recommendations: [modelRec({ uncertainty: null })],
    });
    renderWithSelection(<RecommendedActionPanel />);

    await waitFor(() =>
      expect(
        screen.getByText(/withheld for insufficient evidence or uncertainty/i),
      ).toBeInTheDocument(),
    );
    // The actionable item is NOT rendered.
    expect(
      screen.queryByTestId("recommendation-item"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(/insufficient evidence or uncertainty/i),
    ).toBeInTheDocument();
  });

  it("withholds a MODEL rec with empty evidence_refs", async () => {
    installArtifactFetch({
      recommendations: [modelRec({ evidence_refs: [] })],
    });
    renderWithSelection(<RecommendedActionPanel />);

    await waitFor(() =>
      expect(
        screen.getByText(/withheld for insufficient evidence or uncertainty/i),
      ).toBeInTheDocument(),
    );
    expect(
      screen.queryByTestId("recommendation-item"),
    ).not.toBeInTheDocument();
  });

  it("always renders a REGULATORY rec even with null uncertainty and no evidence (Req 16.6)", async () => {
    installArtifactFetch({ recommendations: [regulatoryRec()] });
    renderWithSelection(<RecommendedActionPanel />);

    await waitFor(() =>
      expect(screen.getByTestId("recommendation-item")).toBeInTheDocument(),
    );
    expect(
      screen.queryByTestId("recommendation-withheld"),
    ).not.toBeInTheDocument();
    const badge = screen.getByTestId("alert-badge");
    expect(badge).toHaveAttribute("data-source", "REGULATORY");
  });

  it("a shown rec displays evidence, quantified uncertainty, and human-review (Req 16.4)", async () => {
    installArtifactFetch({
      recommendations: [
        modelRec({ evidence_refs: ["FSIS lab sampling FY2024"], uncertainty: 0.12 }),
      ],
    });
    renderWithSelection(<RecommendedActionPanel />);

    await waitFor(() =>
      expect(screen.getByTestId("recommendation-item")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("recommendation-evidence")).toHaveTextContent(
      /FSIS lab sampling FY2024/i,
    );
    expect(screen.getByTestId("recommendation-uncertainty")).toHaveTextContent(
      /± 12\.0%/,
    );
    expect(screen.getByTestId("human-review-required")).toBeInTheDocument();
  });
});
