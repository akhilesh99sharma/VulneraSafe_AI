import { useState } from "react";
import type { FormEvent } from "react";
import PanelShell from "./PanelShell";

/**
 * Scenario Builder (Req 12.5, 12.6).
 *
 * Provides user-adjustable controls for inspection budget, inventory supply,
 * delays, and food-access. Submitting a value outside its defined valid range
 * is rejected: an inline message names the invalid control and its accepted
 * range, and the previously-valid values are retained (Req 12.6). Current
 * accepted values are exposed via `onApply` for later wiring to the
 * `scenario_results` artifact (task 6.3).
 */

export interface ScenarioValues {
  /** Inspection budget as top-K prioritized targets. */
  inspectionBudget: number;
  /** Inventory supply as a fraction of nominal (0..1). */
  inventorySupply: number;
  /** Reporting / logistics delay in days. */
  delayDays: number;
  /** Food-access weighting for High_Need_Communities (0..1). */
  foodAccess: number;
}

interface ControlSpec {
  key: keyof ScenarioValues;
  label: string;
  min: number;
  max: number;
  step: number;
  unit?: string;
}

const CONTROLS: ControlSpec[] = [
  { key: "inspectionBudget", label: "Inspection budget (top-K)", min: 0, max: 100, step: 1 },
  { key: "inventorySupply", label: "Inventory supply", min: 0, max: 1, step: 0.05 },
  { key: "delayDays", label: "Delays", min: 0, max: 60, step: 1, unit: "days" },
  { key: "foodAccess", label: "Food-access weighting", min: 0, max: 1, step: 0.05 },
];

export const DEFAULT_SCENARIO: ScenarioValues = {
  inspectionBudget: 20,
  inventorySupply: 0.8,
  delayDays: 7,
  foodAccess: 0.5,
};

interface ScenarioBuilderProps {
  /** Called with the accepted values whenever a valid submission is applied. */
  onApply?: (values: ScenarioValues) => void;
  initial?: ScenarioValues;
}

function findControl(key: keyof ScenarioValues): ControlSpec {
  // CONTROLS is exhaustive over ScenarioValues, so this is always defined.
  return CONTROLS.find((c) => c.key === key) as ControlSpec;
}

export function ScenarioBuilder({ onApply, initial }: ScenarioBuilderProps) {
  // Last-known-good values (retained on rejected submissions, Req 12.6).
  const [applied, setApplied] = useState<ScenarioValues>(initial ?? DEFAULT_SCENARIO);
  // Draft (string) values bound to the inputs.
  const [draft, setDraft] = useState<Record<keyof ScenarioValues, string>>(() => ({
    inspectionBudget: String((initial ?? DEFAULT_SCENARIO).inspectionBudget),
    inventorySupply: String((initial ?? DEFAULT_SCENARIO).inventorySupply),
    delayDays: String((initial ?? DEFAULT_SCENARIO).delayDays),
    foodAccess: String((initial ?? DEFAULT_SCENARIO).foodAccess),
  }));
  const [errors, setErrors] = useState<Partial<Record<keyof ScenarioValues, string>>>({});

  function updateDraft(key: keyof ScenarioValues, value: string) {
    setDraft((d) => ({ ...d, [key]: value }));
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const nextErrors: Partial<Record<keyof ScenarioValues, string>> = {};
    const nextValues: ScenarioValues = { ...applied };

    (Object.keys(draft) as (keyof ScenarioValues)[]).forEach((key) => {
      const spec = findControl(key);
      const parsed = Number(draft[key]);
      const invalid =
        draft[key].trim() === "" ||
        Number.isNaN(parsed) ||
        parsed < spec.min ||
        parsed > spec.max;
      if (invalid) {
        nextErrors[key] = `Accepted range: ${spec.min}–${spec.max}${
          spec.unit ? ` ${spec.unit}` : ""
        }.`;
      } else {
        nextValues[key] = parsed;
      }
    });

    if (Object.keys(nextErrors).length > 0) {
      // Reject the whole submission: keep previously-valid values (Req 12.6).
      setErrors(nextErrors);
      return;
    }

    setErrors({});
    setApplied(nextValues);
    onApply?.(nextValues);
  }

  return (
    <PanelShell title="Scenario Builder"
      info="A what-if tool for the retailer: adjust inspection budget, inventory supply, delays, and food-access weighting to explore operational trade-offs. Operational inputs/outputs are SIMULATED.">
      <form data-testid="scenario-form" onSubmit={handleSubmit} className="flex flex-col gap-3" noValidate>
        {CONTROLS.map((spec) => {
          const error = errors[spec.key];
          const errorId = `scenario-error-${spec.key}`;
          return (
            <div key={spec.key} className="flex flex-col gap-1">
              <label
                htmlFor={`scenario-${spec.key}`}
                className="text-xs font-semibold text-navy"
              >
                {spec.label}
                <span className="ml-1 font-normal text-navy/50">
                  ({spec.min}–{spec.max}
                  {spec.unit ? ` ${spec.unit}` : ""})
                </span>
              </label>
              <input
                id={`scenario-${spec.key}`}
                name={spec.key}
                type="number"
                inputMode="decimal"
                min={spec.min}
                max={spec.max}
                step={spec.step}
                value={draft[spec.key]}
                aria-invalid={error ? true : undefined}
                aria-describedby={error ? errorId : undefined}
                onChange={(e) => updateDraft(spec.key, e.target.value)}
                className={`rounded border px-2 py-1 text-sm text-navy focus:outline-none focus:ring-2 focus:ring-teal ${
                  error ? "border-alert-danger" : "border-navy/20"
                }`}
              />
              {error ? (
                <p
                  id={errorId}
                  data-testid={`scenario-error-${spec.key}`}
                  role="alert"
                  className="text-[11px] font-medium text-alert-danger"
                >
                  {error}
                </p>
              ) : null}
            </div>
          );
        })}

        <div className="mt-1 flex items-center justify-between">
          <button
            type="submit"
            className="rounded bg-navy px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-navy-600 focus:outline-none focus:ring-2 focus:ring-teal"
          >
            Apply scenario
          </button>
          <p className="text-[11px] text-navy/60" data-testid="scenario-applied">
            Applied: K={applied.inspectionBudget} · supply=
            {applied.inventorySupply} · delay={applied.delayDays}d · access=
            {applied.foodAccess}
          </p>
        </div>
      </form>
    </PanelShell>
  );
}

export default ScenarioBuilder;
