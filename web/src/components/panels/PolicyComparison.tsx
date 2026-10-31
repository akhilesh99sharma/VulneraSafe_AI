import { useState } from "react";
import { useArtifact } from "../../data/hooks";
import type {
  ScenarioComparison,
  ScenarioEntry,
  ScenarioPolicyMetric,
} from "../../types/artifacts";
import StatusTag from "../StatusTag";
import PanelShell, { ArtifactBody } from "./PanelShell";

/**
 * A/B/C Policy Comparison (Layer 3, Req 11).
 *
 * For each SIMULATED operational scenario it compares three policies on
 * IDENTICAL inputs:
 *   A = business-as-usual, B = model-informed safety, C = B + food-access-aware.
 * Every cell shows the computed metric value with its diff-vs-A and an
 * uncertainty range; metrics that cannot be validly computed show "not valid"
 * with the recorded reason. All operational outcomes are SIMULATED — no observed
 * illness reduction is claimed.
 */

const POLICY_LABEL: Record<string, string> = {
  A: "A · Business-as-usual",
  B: "B · Model-informed safety",
  C: "C · Safety + food-access",
};

const METRIC_LABEL: Record<string, string> = {
  inspection_workload: "Inspection workload",
  priority_review_coverage: "Priority-review coverage",
  retrospective_positive_test_capture: "Retrospective positive-test capture",
  inventory_availability: "Inventory availability",
  compliant_food_delivered: "Compliant food delivered",
  supply_disruptions: "Supply disruptions",
  high_need_community_service: "High-need community service",
};

function fmt(v: number | null): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  if (Math.abs(v) >= 1000) return Math.round(v).toLocaleString();
  if (Number.isInteger(v)) return String(v);
  return v.toFixed(3);
}

function fmtDiff(v: number | null): { text: string; cls: string } {
  if (v === null || v === undefined || Number.isNaN(v)) return { text: "", cls: "" };
  if (v === 0) return { text: "±0", cls: "text-navy/40" };
  const up = v > 0;
  return {
    text: `${up ? "▲" : "▼"} ${fmt(Math.abs(v))}`,
    cls: up ? "text-teal-700" : "text-slate-600",
  };
}

function Cell({ m, isBaseline }: { m: ScenarioPolicyMetric | undefined; isBaseline: boolean }) {
  if (!m) return <td className="px-3 py-2 text-navy/30">—</td>;
  if (!m.valid) {
    return (
      <td className="px-3 py-2">
        <span className="text-[11px] italic text-navy/40" title={m.not_valid_reason ?? ""}>
          not valid
        </span>
      </td>
    );
  }
  const diff = fmtDiff(m.diff_vs_a);
  return (
    <td className="px-3 py-2 align-top">
      <div className="font-semibold text-navy">{fmt(m.value)}</div>
      {!isBaseline && diff.text ? (
        <div className={`text-[10px] font-medium ${diff.cls}`}>{diff.text} vs A</div>
      ) : null}
      {m.ci_low !== null && m.ci_high !== null ? (
        <div className="text-[9px] text-navy/40">
          [{fmt(m.ci_low)}, {fmt(m.ci_high)}]
        </div>
      ) : null}
    </td>
  );
}

function ScenarioTable({ scenario }: { scenario: ScenarioEntry }) {
  const policies = scenario.policies;
  const metricByPolicy = (policy: string, metric: string) =>
    policies.find((p) => p.policy === policy)?.metrics.find((m) => m.metric === metric);
  const metricNames = policies[0]?.metrics.map((m) => m.metric) ?? [];
  const policiesTie = policies
    .filter((p) => p.policy !== "A")
    .every((p) => p.metrics.every((m) => (m.diff_vs_a ?? 0) === 0));

  return (
    <div className="flex flex-col gap-3">
      <div>
        <h3 className="text-sm font-bold text-navy">{scenario.title}</h3>
        <p className="mt-1 text-[11px] leading-relaxed text-navy/60">{scenario.description}</p>
        {scenario.verified_recall && !scenario.live_official_recall ? (
          <p className="mt-2 rounded-md border-l-4 border-alert-warn bg-alert-warn/10 px-2 py-1 text-[11px] text-navy">
            ⚠ {scenario.recall_labeling_note ?? "SIMULATED verified-evidence recall — not a live official regulatory alert."}
          </p>
        ) : null}
      </div>

      {policiesTie ? (
        <p className="rounded-md border border-navy/15 bg-surface-muted px-3 py-2 text-[11px] leading-relaxed text-navy/70">
          In this scenario all three policies produce the SAME outcome — it is
          dominated by the mandatory recall isolation, which every policy must
          perform identically (safety is never traded away). Model-informed and
          food-access-aware policies diverge where discretionary effort matters,
          e.g. the Salmonella limited-inspection scenario.
        </p>
      ) : null}
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-xs">
          <thead>
            <tr className="border-b border-navy/10 text-left">
              <th className="px-3 py-2 font-semibold text-navy/60">Metric</th>
              {policies.map((p) => (
                <th key={p.policy} className="px-3 py-2 font-semibold text-navy">
                  <div className="flex items-center gap-1">
                    {POLICY_LABEL[p.policy] ?? p.policy}
                  </div>
                  <StatusTag status={p.status} />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {metricNames.map((metric, i) => (
              <tr key={metric} className={i % 2 ? "bg-surface-muted/50" : ""}>
                <td className="px-3 py-2 font-medium text-navy/70">
                  {METRIC_LABEL[metric] ?? metric}
                </td>
                {policies.map((p) => (
                  <Cell
                    key={p.policy}
                    m={metricByPolicy(p.policy, metric)}
                    isBaseline={p.policy === "A"}
                  />
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="text-[10px] italic text-navy/50">
        All operational outcomes are SIMULATED. Policy A is the diff-vs-A baseline.
        Values in [brackets] are 95% uncertainty ranges. No observed illness
        reduction is claimed; safety constraints are never relaxed for cost or access.
      </p>
    </div>
  );
}

export function PolicyComparison() {
  const state = useArtifact<ScenarioComparison>("scenario_results");
  const [idx, setIdx] = useState<number | null>(null);

  return (
    <PanelShell
      title="Policy Comparison (A / B / C)"
      subtitle="Three policies on identical SIMULATED inputs"
      className="lg:col-span-2"
      info="Compares business-as-usual (A), model-informed safety (B), and safety + food-access-aware (C) on identical SIMULATED operational inputs for three scenarios. Each cell shows the metric, its change vs policy A, and a 95% uncertainty range. Operational outcomes are SIMULATED — no observed illness reduction is claimed."
    >
      <ArtifactBody
        state={state}
        artifactName="scenario_results"
        isEmpty={(d) => !d.scenarios || d.scenarios.length === 0}
        emptyTitle="No scenarios available"
        emptyDetail="The scenario_results artifact is present but has no scenarios."
        render={(data) => {
          const scenarios = data.scenarios;
          const hasDivergence = (s: ScenarioEntry) =>
            s.policies.some((p) =>
              p.policy !== "A" &&
              p.metrics.some((m) => m.valid && (m.diff_vs_a ?? 0) !== 0),
            );
          // Default to the first scenario where the policies actually differ,
          // so the comparison's value is visible immediately.
          const defaultIdx = Math.max(0, scenarios.findIndex(hasDivergence));
          const sel = idx ?? defaultIdx;
          const current = scenarios[Math.min(sel, scenarios.length - 1)];
          return (
            <div className="flex flex-col gap-4">
              <div className="flex flex-wrap gap-2">
                {scenarios.map((s, i) => (
                  <button
                    key={s.scenario_id}
                    type="button"
                    aria-pressed={i === sel}
                    onClick={() => setIdx(i)}
                    className={`rounded-lg border px-3 py-1.5 text-xs font-semibold transition ${
                      i === sel
                        ? "border-navy bg-navy text-white"
                        : "border-navy/15 bg-white text-navy/70 hover:border-navy/30"
                    }`}
                  >
                    {s.pathogen}
                    <span className="ml-1 font-normal opacity-70">
                      {s.scenario_id.replace(/_/g, " ")}
                    </span>
                  </button>
                ))}
              </div>
              <ScenarioTable scenario={current} />
            </div>
          );
        }}
      />
    </PanelShell>
  );
}

export default PolicyComparison;
