import { describe, it, expect } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import type { AttentionQueueItem } from "../../../types/artifacts";
import AttentionQueue from "../AttentionQueue";
import { installArtifactFetch, renderWithSelection } from "../../../test/renderHelpers";

const ITEMS: AttentionQueueItem[] = [
  {
    rank: 3,
    target_id: "LOT-C",
    target_type: "lot",
    region: "CA",
    pathogen: "Salmonella",
    risk: 0.2,
    triggering_condition: "elevated positivity",
    status: "PREDICTED",
  },
  {
    rank: 1,
    target_id: "LOT-A",
    target_type: "lot",
    region: "TX",
    pathogen: "Salmonella",
    risk: 0.6,
    triggering_condition: "confirmed recall nearby",
    status: "PREDICTED",
  },
  {
    rank: 2,
    target_id: "LOT-B",
    target_type: "store",
    region: "NY",
    pathogen: "Listeria",
    risk: 0.4,
    triggering_condition: "weather anomaly",
    status: "OBSERVED",
  },
];

describe("AttentionQueue", () => {
  it("orders items highest -> lowest priority by ascending rank (Req 12.4)", async () => {
    installArtifactFetch({ attention_queue: ITEMS });
    renderWithSelection(<AttentionQueue />);

    await waitFor(() =>
      expect(screen.getByTestId("attention-queue-list")).toBeInTheDocument(),
    );
    const rows = screen.getAllByTestId("attention-queue-item");
    expect(rows.map((r) => r.getAttribute("data-rank"))).toEqual(["1", "2", "3"]);
    // First row (rank 1 = the TX Salmonella item) shows its region/pathogen and trigger.
    expect(rows[0]).toHaveTextContent("Salmonella");
    expect(rows[0]).toHaveTextContent("TX");
    expect(rows[0]).toHaveTextContent(/confirmed recall nearby/i);
  });

  it("shows an empty-state when the artifact is empty", async () => {
    installArtifactFetch({ attention_queue: [] });
    renderWithSelection(<AttentionQueue />);

    await waitFor(() =>
      expect(screen.getByText(/no items to triage/i)).toBeInTheDocument(),
    );
  });

  it("filters by the selected pathogen", async () => {
    installArtifactFetch({ attention_queue: ITEMS });
    renderWithSelection(<AttentionQueue />, { pathogen: "Listeria" });

    await waitFor(() =>
      expect(screen.getByTestId("attention-queue-list")).toBeInTheDocument(),
    );
    const rows = screen.getAllByTestId("attention-queue-item");
    expect(rows).toHaveLength(1);
    // The one remaining row is the Listeria / NY item.
    expect(rows[0]).toHaveTextContent("Listeria");
    expect(rows[0]).toHaveTextContent("NY");
  });
});
