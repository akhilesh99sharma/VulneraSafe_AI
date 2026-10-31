import { describe, it, expect } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import type { ProgramProductStratum } from "../../../types/artifacts";
import PathogenExplorer from "../PathogenExplorer";
import { installArtifactFetch } from "../../../test/renderHelpers";

function rec(over: Partial<ProgramProductStratum>): ProgramProductStratum {
  return {
    artifact_version: "0.1.0",
    module_id: "S01",
    method_version: "s01.v1",
    pathogen: "Salmonella",
    commodity: "raw_poultry",
    dimension: "overall",
    source_column: null,
    category: "(all)",
    sample_n: 1000,
    positive_n: 116,
    value: 0.116,
    ci_low: 0.098,
    ci_high: 0.137,
    ci_method: "wilson_95",
    units: "fraction",
    status: "OBSERVED",
    availability_status: "available",
    unavailable_reason: null,
    fiscal_years: [2014, 2026],
    generated_at: "2026-01-01T00:00:00Z",
    ...over,
  };
}

const ROWS: ProgramProductStratum[] = [
  rec({ pathogen: "Salmonella", dimension: "overall" }),
  rec({ pathogen: "Salmonella", dimension: "product", source_column: "product_type", category: "BREAST", sample_n: 66090, positive_n: 7085, value: 0.107 }),
  rec({ pathogen: "STEC", commodity: "raw_beef", dimension: "overall", value: 0.003, positive_n: 3, sample_n: 1000 }),
  rec({ pathogen: "STEC", commodity: "raw_beef", dimension: "product", source_column: null, category: "(unavailable)", sample_n: null, positive_n: null, value: null, ci_low: null, ci_high: null, availability_status: "unavailable", unavailable_reason: "Raw beef (STEC) sampling records carry no product category." }),
];

describe("PathogenExplorer", () => {
  it("renders the selected pathogen's observed strata", async () => {
    installArtifactFetch({ multipathogen_program_product: ROWS });
    render(<PathogenExplorer />);
    await waitFor(() => expect(screen.getByText(/overall positivity/i)).toBeInTheDocument());
    // Salmonella product category renders
    expect(screen.getByText("BREAST")).toBeInTheDocument();
  });

  it("switching to STEC shows its product dimension as not available", async () => {
    installArtifactFetch({ multipathogen_program_product: ROWS });
    render(<PathogenExplorer />);
    await waitFor(() => expect(screen.getByText(/overall positivity/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /STEC/i }));
 
        // The STEC product dimension specifically reports its unavailable reason.
    await waitFor(() =>
      expect(
        screen.getByText(/raw beef \(stec\) sampling records carry no product category/i),
      ).toBeInTheDocument(),
    );
    // Salmonella-only category is gone after switching pathogen
    expect(screen.queryByText("BREAST")).not.toBeInTheDocument();
  });

  it("degrades to an honest empty state when the artifact is missing", async () => {
    installArtifactFetch({}); // artifact 404s
    render(<PathogenExplorer />);
    await waitFor(() =>
      expect(screen.getByText(/could not load multipathogen_program_product/i)).toBeInTheDocument(),
    );
  });
});
