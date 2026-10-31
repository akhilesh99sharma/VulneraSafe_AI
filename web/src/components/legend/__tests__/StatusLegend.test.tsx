import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import StatusLegend from "../StatusLegend";

/**
 * StatusLegend tests (Req 14.3, 14.4).
 *
 * The legend must let a user interpret the two visual systems: the three
 * provenance tags and the reserved alert color.
 */

describe("StatusLegend", () => {
  it("explains all three provenance tags (Req 14.3)", () => {
    render(<StatusLegend />);
    const statuses = screen
      .getAllByTestId("status-tag")
      .map((el) => el.getAttribute("data-status"));
    expect(statuses).toEqual(
      expect.arrayContaining(["OBSERVED", "PREDICTED", "SIMULATED"]),
    );
    // One legend row per tag.
    expect(screen.getAllByTestId("legend-status")).toHaveLength(3);
  });

  it("explains that orange/red marks an active alert only (Req 14.4)", () => {
    render(<StatusLegend />);
    const alertRow = screen.getByTestId("legend-alert");
    expect(alertRow).toHaveTextContent(/active alert/i);
    expect(alertRow).toHaveTextContent(/never decorative/i);
  });
});
