import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import ScenarioBuilder from "../ScenarioBuilder";

/**
 * Scenario Builder is self-contained (no artifacts), so it renders without the
 * selection provider or a fetch stub.
 */
describe("ScenarioBuilder", () => {
  it("applies valid values and reports them via onApply (Req 12.5)", () => {
    const onApply = vi.fn();
    render(<ScenarioBuilder onApply={onApply} />);

    fireEvent.change(screen.getByLabelText(/inspection budget/i), {
      target: { value: "35" },
    });
    fireEvent.submit(screen.getByTestId("scenario-form"));

    expect(onApply).toHaveBeenCalledTimes(1);
    expect(onApply.mock.calls[0][0]).toMatchObject({ inspectionBudget: 35 });
    expect(screen.getByTestId("scenario-applied")).toHaveTextContent("K=35");
  });

  it("rejects out-of-range input, shows the accepted range, and retains prior valid values (Req 12.6)", () => {
    const onApply = vi.fn();
    render(<ScenarioBuilder onApply={onApply} />);

    // Budget max is 100 -> 150 is out of range.
    fireEvent.change(screen.getByLabelText(/inspection budget/i), {
      target: { value: "150" },
    });
    fireEvent.submit(screen.getByTestId("scenario-form"));

    // Rejected: callback not fired, inline error names the accepted range.
    expect(onApply).not.toHaveBeenCalled();
    const error = screen.getByTestId("scenario-error-inspectionBudget");
    expect(error).toHaveTextContent(/0.*100/);
    // Previously-valid applied value is retained (default 20).
    expect(screen.getByTestId("scenario-applied")).toHaveTextContent("K=20");
  });

  it("rejects the whole submission if any one control is invalid", () => {
    const onApply = vi.fn();
    render(<ScenarioBuilder onApply={onApply} />);

    // valid budget but invalid food-access (> 1)
    fireEvent.change(screen.getByLabelText(/inspection budget/i), {
      target: { value: "40" },
    });
    fireEvent.change(screen.getByLabelText(/food-access/i), {
      target: { value: "5" },
    });
    fireEvent.submit(screen.getByTestId("scenario-form"));

    expect(onApply).not.toHaveBeenCalled();
    expect(screen.getByTestId("scenario-error-foodAccess")).toBeInTheDocument();
    // Applied values unchanged.
    expect(screen.getByTestId("scenario-applied")).toHaveTextContent("K=20");
  });
});
