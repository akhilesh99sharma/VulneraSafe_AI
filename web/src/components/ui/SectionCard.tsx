import type { ReactNode } from "react";

/**
 * A lighter dashboard section card (distinct from PanelShell): a header row with
 * a title, an optional info tooltip, and a right-aligned action, over a padded
 * body. Presentational only. Card chrome matches PanelShell's idiom.
 */

export interface SectionCardProps {
  title: ReactNode;
  subtitle?: ReactNode;
  /** Short plain-language explanation shown in a hover/focus (i) tooltip. */
  info?: string;
  /** Right-aligned header link/button (e.g. "View all \u2192"). */
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}

/** Accessible info marker: shows `text` on hover and keyboard focus. */
function InfoDot({ text }: { text: string }) {
  return (
    <span className="group relative inline-flex">
      <button
        type="button"
        aria-label="What is this section?"
        className="flex h-4 w-4 items-center justify-center rounded-full border border-navy/30 text-[10px] font-bold text-navy/60 hover:bg-navy/5 focus:outline-none focus:ring-2 focus:ring-teal"
      >
        i
      </button>
      <span
        role="tooltip"
        className="pointer-events-none absolute left-0 top-6 z-30 w-64 rounded-lg border border-navy/10 bg-navy px-3 py-2 text-[11px] leading-relaxed text-white opacity-0 shadow-lg transition group-hover:opacity-100 group-focus-within:opacity-100"
      >
        {text}
      </span>
    </span>
  );
}

export function SectionCard({ title, subtitle, info, action, children, className }: SectionCardProps) {
  return (
    <section
      data-testid="section-card"
      className={`flex flex-col rounded-xl border border-navy/10 bg-white shadow-sm ${className ?? ""}`}
    >
      <div className="flex items-start justify-between gap-2 border-b border-navy/5 px-4 py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <h2 className="text-sm font-bold text-navy">{title}</h2>
            {info ? <InfoDot text={info} /> : null}
          </div>
          {subtitle ? <p className="mt-0.5 text-[11px] text-navy/50">{subtitle}</p> : null}
        </div>
        {action ? <div className="shrink-0 text-xs font-semibold text-teal-600">{action}</div> : null}
      </div>
      <div className="flex-1 p-4">{children}</div>
    </section>
  );
}

export default SectionCard;
