import { describe, it, expect } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import type { RegulatoryAlert } from "../../types/artifacts";
import RegulatoryAlertsStrip from "../RegulatoryAlertsStrip";
import { installArtifactFetch } from "../../test/renderHelpers";

/**
 * Render tests for the Regulatory Alerts strip (task 6.4 companion; Req 16.5,
 * 16.6). These assert the three contract guarantees:
 *   1. regulatory items render with the REGULATORY (not MODEL) badge,
 *   2. the strip still renders when NO model / recommendation / manifest
 *      artifacts exist (independence from model state), and
 *   3. an absent/empty artifact shows the calm empty state, not a loud error.
 *
 * The strip reads only `regulatory_alerts`, so these tests install ONLY that
 * artifact (every other artifact name 404s) to prove the independence.
 */

const ALERTS: RegulatoryAlert[] = [
  {
    recall_id: "EXAMPLE-0001",
    product: "[EXAMPLE] Ready-to-eat chicken breast strips, 10 oz pouches",
    lot_ids: ["EX-LOT-1180A", "EX-LOT-1180B"],
    classification: "Class I",
    date: "2026-01-10",
    source_url: "https://www.fsis.usda.gov/recalls",
    alert_source: "REGULATORY",
    status: "OBSERVED",
  },
  {
    recall_id: "EXAMPLE-0002",
    product: "[EXAMPLE] Raw ground beef chubs, 3 lb packages",
    lot_ids: ["EX-LOT-2207"],
    classification: "Class II",
    date: "2026-01-08",
    source_url: "https://www.fsis.usda.gov/recalls",
    alert_source: "REGULATORY",
    status: "OBSERVED",
  },
];

describe("RegulatoryAlertsStrip", () => {
  it("renders regulatory items with the REGULATORY badge (Req 16.6)", async () => {
    // Only the regulatory_alerts artifact exists — no model / recommendation /
    // manifest artifacts are installed, so they all 404.
    installArtifactFetch({ regulatory_alerts: ALERTS });
    render(<RegulatoryAlertsStrip />);

    await waitFor(() =>
      expect(screen.getByTestId("regulatory-alerts-list")).toBeInTheDocument(),
    );

    const items = screen.getAllByTestId("regulatory-alert-item");
    expect(items).toHaveLength(2);

    // Every item carries a REGULATORY badge — never a MODEL badge.
    const badges = screen.getAllByTestId("alert-badge");
    expect(badges).toHaveLength(2);
    for (const badge of badges) {
      expect(badge).toHaveAttribute("data-source", "REGULATORY");
    }
    expect(
      screen.queryByText(/model alert/i),
    ).not.toBeInTheDocument();

    // Recall details are surfaced: recall_id, product, classification, lots,
    // and the source link.
    expect(items[0]).toHaveTextContent("EXAMPLE-0001");
    expect(items[0]).toHaveTextContent(/ready-to-eat chicken breast strips/i);
    expect(items[0]).toHaveTextContent("Class I");
    expect(items[0]).toHaveTextContent("EX-LOT-1180A");
    const links = screen.getAllByTestId("regulatory-alert-source-link");
    expect(links[0]).toHaveAttribute(
      "href",
      "https://www.fsis.usda.gov/recalls",
    );
  });

  it("flags illustrative EXAMPLE placeholders with a notice and per-card tag", async () => {
    // These fixtures are EXAMPLE-prefixed placeholders (live FSIS feed
    // unavailable), so the strip must mark them unmistakably.
    installArtifactFetch({ regulatory_alerts: ALERTS });
    render(<RegulatoryAlertsStrip />);

    await waitFor(() =>
      expect(screen.getByTestId("regulatory-alerts-list")).toBeInTheDocument(),
    );

    // Prominent top notice that these are not real recalls.
    const notice = screen.getByTestId("regulatory-alerts-example-notice");
    expect(notice).toHaveTextContent(/illustrative examples only/i);
    expect(notice).toHaveTextContent(/not real recalls/i);

    // Each placeholder card carries an "EXAMPLE — not a real recall" tag and is
    // marked as a placeholder, without changing its real recall details.
    const tags = screen.getAllByTestId("regulatory-alert-example-tag");
    expect(tags).toHaveLength(2);
    const items = screen.getAllByTestId("regulatory-alert-item");
    expect(items[0]).toHaveAttribute("data-placeholder", "true");
  });

  it("shows no example notice when all recalls are real", async () => {
    const real: RegulatoryAlert[] = [
      {
        recall_id: "FSIS-2026-001",
        product: "Ready-to-eat chicken breast strips, 10 oz pouches",
        lot_ids: ["LOT-1180A"],
        classification: "Class I",
        date: "2026-01-10",
        source_url: "https://www.fsis.usda.gov/recalls",
        alert_source: "REGULATORY",
        status: "OBSERVED",
      },
    ];
    installArtifactFetch({ regulatory_alerts: real });
    render(<RegulatoryAlertsStrip />);

    await waitFor(() =>
      expect(screen.getByTestId("regulatory-alerts-list")).toBeInTheDocument(),
    );
    expect(
      screen.queryByTestId("regulatory-alerts-example-notice"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("regulatory-alert-example-tag"),
    ).not.toBeInTheDocument();
    // Real recall details still render (id / product / lots).
    const item = screen.getByTestId("regulatory-alert-item");
    expect(item).toHaveTextContent("FSIS-2026-001");
    expect(item).toHaveTextContent(/ready-to-eat chicken breast strips/i);
    expect(item).toHaveTextContent("LOT-1180A");
    expect(item).toHaveAttribute("data-placeholder", "false");
  });

  it("still renders when no model/recommendation artifacts exist (Req 16.5)", async () => {
    // Deliberately omit manifest, recommendations, model_metrics, etc. The
    // strip must NOT be suppressed by their absence.
    installArtifactFetch({ regulatory_alerts: ALERTS });
    render(<RegulatoryAlertsStrip />);

    // The strip container is present immediately, independent of model state.
    expect(screen.getByTestId("regulatory-alerts-strip")).toBeInTheDocument();

    await waitFor(() =>
      expect(screen.getAllByTestId("regulatory-alert-item")).toHaveLength(2),
    );
  });

  it("shows the calm empty state for an empty artifact (Req 16.6)", async () => {
    installArtifactFetch({ regulatory_alerts: [] });
    render(<RegulatoryAlertsStrip />);

    await waitFor(() =>
      expect(
        screen.getByText(/no active regulatory recalls/i),
      ).toBeInTheDocument(),
    );
    // Calm empty state, not a loud load error, and the strip is still present.
    expect(screen.getByTestId("regulatory-alerts-strip")).toBeInTheDocument();
    expect(
      screen.queryByTestId("regulatory-alerts-list"),
    ).not.toBeInTheDocument();
  });

  it("shows the calm empty state when the artifact is absent (Req 16.6)", async () => {
    // regulatory_alerts 404s -> treated as "no active recalls", not an error.
    installArtifactFetch({});
    render(<RegulatoryAlertsStrip />);

    await waitFor(() =>
      expect(
        screen.getByText(/no active regulatory recalls/i),
      ).toBeInTheDocument(),
    );
    expect(screen.getByTestId("regulatory-alerts-strip")).toBeInTheDocument();
  });
});
