import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import ResponsibleUseBanner from "../ResponsibleUseBanner";

/**
 * ResponsibleUseBanner render tests (Task 7.1 — Req 16.1, 16.2, 16.3).
 *
 * Asserts the banner prominently states the decision-support framing: not a
 * regulatory determination / outbreak declaration, and consequential actions
 * require human review. (Authored but not executed — node/npm unavailable.)
 */

// Alert-family colors are reserved for active alerts; the banner is framing,
// not an alert, so it must use none of them (mirrors themeDiscipline test).
const ALERT_COLOR =
  /\b(?:bg|text|border|ring|from|to|via)-(?:alert-(?:warn|danger)|red|orange|amber|rose|yellow)(?:-\d{2,3})?\b/;

describe("ResponsibleUseBanner (Req 16.1-16.3)", () => {
  it("states decision support, not a regulatory determination / outbreak declaration", () => {
    render(<ResponsibleUseBanner />);
    const banner = screen.getByTestId("responsible-use-banner");
    expect(banner).toHaveTextContent(/decision support only/i);
    expect(banner).toHaveTextContent(/not a regulatory determination/i);
    expect(banner).toHaveTextContent(/outbreak declaration/i);
  });

  it("requires human review for consequential actions", () => {
    render(<ResponsibleUseBanner />);
    expect(
      screen.getByTestId("responsible-use-banner"),
    ).toHaveTextContent(/human review/i);
  });

  it("is framing, not an alert — uses no reserved alert color", () => {
    const { container } = render(<ResponsibleUseBanner />);
    for (const el of container.querySelectorAll("*")) {
      expect(el.className?.toString() ?? "").not.toMatch(ALERT_COLOR);
    }
  });
});
