import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import MapLabel from "../MapLabel";

/**
 * MapLabel tests (Req 14.1, 14.2).
 *
 * Asserts the risk-map label block renders all SIX mandatory fields — pathogen,
 * geography, reporting period, status, uncertainty, data freshness — and that a
 * field whose value is undefined shows an EXPLICIT not-available indicator
 * ("—" with title="not available") rather than an empty cell.
 */

describe("MapLabel", () => {
  it("renders all six mandatory label fields (Req 14.1)", () => {
    render(
      <MapLabel
        pathogen="Salmonella"
        geography="TX"
        period="2026-01"
        status="PREDICTED"
        uncertainty="± 8.0%"
        dataFreshness="2026-01-15"
      />,
    );

    // All six field cells are present.
    for (const id of [
      "map-label-pathogen",
      "map-label-geography",
      "map-label-period",
      "map-label-status",
      "map-label-uncertainty",
      "map-label-freshness",
    ]) {
      expect(screen.getByTestId(id)).toBeInTheDocument();
    }

    // Values are shown verbatim.
    expect(within(screen.getByTestId("map-label-pathogen")).getByText("Salmonella")).toBeInTheDocument();
    expect(within(screen.getByTestId("map-label-geography")).getByText("TX")).toBeInTheDocument();
    expect(within(screen.getByTestId("map-label-period")).getByText("2026-01")).toBeInTheDocument();
    expect(within(screen.getByTestId("map-label-uncertainty")).getByText("± 8.0%")).toBeInTheDocument();
    expect(within(screen.getByTestId("map-label-freshness")).getByText("2026-01-15")).toBeInTheDocument();

    // Status is rendered as exactly one StatusTag.
    const statusCell = screen.getByTestId("map-label-status");
    const tags = within(statusCell).getAllByTestId("status-tag");
    expect(tags).toHaveLength(1);
    expect(tags[0]).toHaveAttribute("data-status", "PREDICTED");

    // Nothing is marked not-available when every value is present.
    expect(screen.queryByTestId("map-label-na")).not.toBeInTheDocument();
  });

  it("shows an explicit not-available indicator for an undefined field (Req 14.2)", () => {
    render(
      <MapLabel
        pathogen="Listeria"
        geography="CA"
        // period omitted -> must show not-available, not a blank cell
        status="OBSERVED"
        uncertainty="± 3.0%"
        dataFreshness="2026-02-01"
      />,
    );

    const periodCell = screen.getByTestId("map-label-period");
    const na = within(periodCell).getByTestId("map-label-na");
    expect(na).toBeInTheDocument();
    // The indicator is explicit: a dash carrying a "not available" title/label.
    expect(na).toHaveTextContent("—");
    expect(na).toHaveAttribute("title", "not available");
  });

  it("renders a not-available indicator per missing field, incl. status (Req 14.2)", () => {
    // Everything undefined: all six fields fall back to the N/A indicator.
    render(<MapLabel />);
    const indicators = screen.getAllByTestId("map-label-na");
    expect(indicators).toHaveLength(6);
    for (const na of indicators) {
      expect(na).toHaveAttribute("title", "not available");
    }
    // No status tag should be rendered when status is absent.
    expect(screen.queryByTestId("status-tag")).not.toBeInTheDocument();
  });

  it("treats a blank/whitespace value as not-available rather than blank (Req 14.2)", () => {
    render(
      <MapLabel
        pathogen="STEC"
        geography="   "
        period="2026-Q1"
        status="SIMULATED"
        uncertainty="± 5.0%"
        dataFreshness="2026-03-01"
      />,
    );
    const geoCell = screen.getByTestId("map-label-geography");
    expect(within(geoCell).getByTestId("map-label-na")).toBeInTheDocument();
  });
});
