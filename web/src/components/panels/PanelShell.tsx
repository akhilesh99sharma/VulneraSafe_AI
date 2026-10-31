import type { ReactNode } from "react";
import EmptyState from "../EmptyState";
import type { ArtifactState } from "../../data/hooks";

/**
 * Consistent chrome for every mandatory panel (Req 12): a titled card with an
 * optional subtitle, an info tooltip, and a header accessory, plus graceful
 * loading / error / empty states so one panel degrades without affecting its
 * siblings (Req 15.3).
 */

interface PanelShellProps {
  title: string;
  subtitle?: string;
  /** Short plain-language explanation shown in a hover/focus (i) tooltip. */
  info?: string;
  accessory?: ReactNode;
  children: ReactNode;
  className?: string;
}

/** Accessible info marker: shows `text` on hover and keyboard focus. */
function InfoDot({ text }: { text: string }) {
  return (
    <span className="group relative inline-flex">
      <button
        type="button"
        aria-label="What is this panel?"
        className="flex h-4 w-4 items-center justify-center rounded-full border border-navy/30 text-[10px] font-bold text-navy/60 hover:bg-navy/5 focus:outline-none focus:ring-2 focus:ring-teal"
      >
        i
      </button>
      <span
        role="tooltip"
        className="pointer-events-none absolute right-0 top-6 z-30 w-64 rounded-lg border border-navy/10 bg-navy px-3 py-2 text-[11px] leading-relaxed text-white opacity-0 shadow-lg transition group-hover:opacity-100 group-focus-within:opacity-100"
      >
        {text}
      </span>
    </span>
  );
}

export function PanelShell({ title, subtitle, info, accessory, children, className }: PanelShellProps) {
  return (
    <section
      data-testid="panel"
      data-panel={title}
      className={`flex flex-col rounded-xl border border-navy/10 bg-white shadow-sm transition hover:shadow ${className ?? ""}`}
    >
      <div className="flex items-start justify-between gap-2 border-b border-navy/5 px-4 py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <h2 className="text-sm font-bold text-navy">{title}</h2>
            {info ? <InfoDot text={info} /> : null}
          </div>
          {subtitle ? <p className="mt-0.5 text-[11px] text-navy/50">{subtitle}</p> : null}
        </div>
        {accessory ?? null}
      </div>
      <div className="flex-1 p-4">{children}</div>
    </section>
  );
}

export function ArtifactBody<T>({
  state,
  artifactName,
  isEmpty,
  emptyTitle,
  emptyDetail,
  render,
}: {
  state: ArtifactState<T>;
  artifactName: string;
  isEmpty?: (data: T) => boolean;
  emptyTitle: string;
  emptyDetail?: string;
  render: (data: T) => ReactNode;
}): ReactNode {
  if (state.loading) {
    return <EmptyState title="Loading…" detail={`Fetching ${artifactName}.`} />;
  }
  if (state.error) {
    return <EmptyState title={`Could not load ${artifactName}`} detail={state.error.message} />;
  }
  if (!state.data || (isEmpty ? isEmpty(state.data) : false)) {
    return <EmptyState title={emptyTitle} detail={emptyDetail} />;
  }
  return <>{render(state.data)}</>;
}

export default PanelShell;
