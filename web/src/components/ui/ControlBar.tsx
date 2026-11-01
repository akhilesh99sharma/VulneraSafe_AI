import type { ReactNode } from "react";

/**
 * The single control-bar row: a white card holding labeled selector groups that
 * line up along their baseline. Plus the pathogen-pill selector and a labeled
 * control group. Presentational / controlled only — no internal state.
 */

export interface ControlBarProps {
  children: ReactNode;
  className?: string;
}

export function ControlBar({ children, className }: ControlBarProps) {
  return (
    <div
      data-testid="control-bar"
      className={`flex flex-wrap items-end gap-4 rounded-xl border border-navy/10 bg-white px-4 py-3 shadow-sm ${className ?? ""}`}
    >
      {children}
    </div>
  );
}

export interface ControlGroupProps {
  label: string;
  children: ReactNode;
  className?: string;
}

/** A tiny uppercase caption with its control beneath (e.g. "Time range"). */
export function ControlGroup({ label, children, className }: ControlGroupProps) {
  return (
    <div className={`flex flex-col gap-1 ${className ?? ""}`}>
      <span className="text-[11px] font-semibold uppercase tracking-wide text-navy/60">{label}</span>
      {children}
    </div>
  );
}

export interface PathogenPillsProps {
  value: string;
  onChange: (value: string) => void;
  options: readonly string[];
}

/**
 * Pathogen selector as pill buttons — teal when on, navy/15 border when off.
 * Markup mirrors the CountyCommunities / SupplierMonitor selector. Controlled.
 */
export function PathogenPills({ value, onChange, options }: PathogenPillsProps) {
  return (
    <div data-testid="pathogen-pills" className="flex flex-wrap gap-2">
      {options.map((p) => {
        const on = p === value;
        return (
          <button
            key={p}
            type="button"
            aria-pressed={on}
            onClick={() => onChange(p)}
            className={`rounded-lg border px-4 py-2 text-sm font-semibold transition ${
              on ? "border-teal bg-teal text-white" : "border-navy/15 bg-white text-navy/70 hover:border-navy/30"
            }`}
          >
            {p === "STEC" ? "STEC (E. coli)" : p}
          </button>
        );
      })}
    </div>
  );
}

export default ControlBar;
