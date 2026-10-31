import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import PerformanceLabel from "../PerformanceLabel";

/**
 * PerformanceLabel chip render tests (Task 7.1 — Req 16.8).
 *
 * Asserts the chip distinguishes historical from prospective performance and
 * carries the kind as a data attribute so metric displays can tag each measure.
 * (Authored but not executed — node/npm unavailable.)
 */

const ALERT_COLOR =
  /\b(?:bg|text|border|ring|from|to|via)-(?:alert-(?:warn|danger)|red|orange|amber|rose|yellow)(?:-\d{2,3})?\b/;

describe("PerformanceLabel (Req 16.8)", () => {
  it("renders the historical label and kind", () => {
    render(<PerformanceLabel kind="historical" />);
    const chip = screen.getByTestId("performance-label");
    expect(chip).toHaveAttribute("data-kind", "historical");
    expect(chip).toHaveTextContent(/historical/i);
  });

  it("renders the prospective label and kind", () => {
    render(<PerformanceLabel kind="prospective" />);
    const chip = screen.getByTestId("performance-label");
    expect(chip).toHaveAttribute("data-kind", "prospective");
    expect(chip).toHaveTextContent(/prospective/i);
  });

  it("shows an optional note", () => {
    render(<PerformanceLabel kind="prospective" note="PR-AUC" />);
    expect(screen.getByTestId("performance-label")).toHaveTextContent(/PR-AUC/);
  });

  it("is a neutral provenance chip — uses no reserved alert color", () => {
    const { container } = render(<PerformanceLabel kind="historical" />);
    for (const el of container.querySelectorAll("*")) {
      expect(el.className?.toString() ?? "").not.toMatch(ALERT_COLOR);
    }
  });
});
