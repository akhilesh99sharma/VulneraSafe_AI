import { describe, it, expect } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import type { ActionQueueItem } from "../../../types/artifacts";
import SurveillanceActions from "../SurveillanceActions";
import { installArtifactFetch } from "../../../test/renderHelpers";

function rec(over: Partial<ActionQueueItem>): ActionQueueItem {
  return {
    artifact_version: "0.1.0",
    module_id: "ACTIONQ",
    method_version: "aq.v1",
    rank: 1,
    pathogen: "Salmonella",
    commodity: "raw_poultry",
    action: "Prioritize testing / heightened monitoring for Salmonella in GA next period",
    action_category: "prioritize_testing",
    target_type: "state",
    target: "GA",
    source_module: "S04",
    triggering_signal: "Emerging signal: GA positivity exceeded its prior-only expected band",
    evidence_summary: "observed 0.4 vs expected<= 0.2; 40/100 positive (OBSERVED, leakage-safe)",
    corroboration_note: null,
    human_review: true,
    status: "OBSERVED",
    availability_status: "available",
    generated_at: "2027-01-01T00:00:00Z",
    ...over,
  };
}

const ROWS: ActionQueueItem[] = [
  rec({ rank: 1, source_module: "S04", pathogen: "Salmonella", target: "GA" }),
  rec({ rank: 2, source_module: "S03", pathogen: "Listeria", target: "Good Plant (CA)",
        action: "Request supplier verification / additional testing for Good Plant (CA)",
        action_category: "request_supplier_verification", target_type: "establishment",
        triggering_signal: "Elevated shrinkage-estimated Listeria positivity",
        evidence_summary: "EB posterior 0.3 [0.2, 0.4]; 6/20 positive" }),
  rec({ rank: 3, source_module: "S06", pathogen: "STEC", target: "DE",
        action: "When allocating raw_beef, protect access in DE (elevated STEC hazard + high need)",
        action_category: "protect_access",
        corroboration_note: "CDC NORS recorded 2 foodborne STEC outbreak(s) in DE over 2013-2023 — corroboration only, not a causal link." }),
];

describe("SurveillanceActions", () => {
  it("renders the ranked actions with evidence and human-review chips", async () => {
    installArtifactFetch({ action_queue: ROWS });
    render(<SurveillanceActions />);
    await waitFor(() => expect(screen.getByText(/suggested actions from surveillance/i)).toBeInTheDocument());
    expect(screen.getByText(/Prioritize testing .* Salmonella in GA/i)).toBeInTheDocument();
    // every action shows a human-review chip
    expect(screen.getAllByText(/human review/i).length).toBeGreaterThanOrEqual(3);
    // evidence shown
    expect(screen.getAllByText(/Evidence:/i).length).toBeGreaterThanOrEqual(3);
  });

  it("states it is distinct from the SIMULATED optimizer panel", async () => {
    installArtifactFetch({ action_queue: ROWS });
    render(<SurveillanceActions />);
    await waitFor(() =>
      expect(screen.getByText(/separate from the dashboard's recommended action panel/i)).toBeInTheDocument(),
    );
    expect(screen.getByText(/corroboration, never as a trigger/i)).toBeInTheDocument();
  });

  it("filters by source module", async () => {
    installArtifactFetch({ action_queue: ROWS });
    render(<SurveillanceActions />);
    await waitFor(() => expect(screen.getByText(/Good Plant \(CA\)/i)).toBeInTheDocument());
    // select S06 only -> the S03 establishment action drops out
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "S06" } });
    await waitFor(() =>
      expect(screen.queryByText(/Good Plant \(CA\)/i)).not.toBeInTheDocument(),
    );
    expect(screen.getByText(/protect access in DE/i)).toBeInTheDocument();
  });

  it("shows non-causal corroboration context when present", async () => {
    installArtifactFetch({ action_queue: ROWS });
    render(<SurveillanceActions />);
    await waitFor(() =>
      expect(screen.getByText(/corroboration only, not a causal link/i)).toBeInTheDocument(),
    );
  });

  it("degrades to an honest empty state when the artifact is missing", async () => {
    installArtifactFetch({});
    render(<SurveillanceActions />);
    await waitFor(() =>
      expect(screen.getByText(/could not load action_queue/i)).toBeInTheDocument(),
    );
  });
});