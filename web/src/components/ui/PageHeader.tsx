import type { ReactNode } from "react";

/**
 * The navy-gradient hero header for a dashboard page: breadcrumb, title,
 * subtitle, and a right-aligned status chip. Matches the gradient hero used by
 * the existing panels (from-navy via-navy-600 to-teal-600). Presentational only.
 */

export interface PageHeaderStatus {
  label: string;
  detail?: string;
  /** When true, a small teal dot signals a healthy / up-to-date state. */
  ok?: boolean;
}

export interface PageHeaderProps {
  title: string;
  subtitle?: ReactNode;
  /** Rendered as `Home > Risk Dashboard`. */
  breadcrumb?: string[];
  status?: PageHeaderStatus;
  /** Optional extra right-side content, beneath / beside the status chip. */
  children?: ReactNode;
}

export function PageHeader({ title, subtitle, breadcrumb, status, children }: PageHeaderProps) {
  return (
    <section
      data-testid="page-header"
      className="overflow-hidden rounded-2xl bg-gradient-to-br from-navy via-navy-600 to-teal-600 px-6 py-8 text-white"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          {breadcrumb && breadcrumb.length > 0 ? (
            <nav aria-label="Breadcrumb" className="text-xs text-white/60">
              {breadcrumb.map((crumb, i) => (
                <span key={`${crumb}-${i}`}>
                  {i > 0 ? <span aria-hidden className="mx-1.5">{"\u203A"}</span> : null}
                  <span>{crumb}</span>
                </span>
              ))}
            </nav>
          ) : null}
          <h1 className="mt-2 text-3xl font-extrabold tracking-tight sm:text-4xl">{title}</h1>
          {subtitle ? <p className="mt-2 max-w-2xl text-sm leading-relaxed text-white/80">{subtitle}</p> : null}
        </div>

        {status || children ? (
          <div className="flex flex-col items-start gap-2 sm:items-end">
            {status ? (
              <div className="flex items-center gap-2 rounded-full bg-white/10 px-3 py-1.5 text-xs font-semibold ring-1 ring-white/20">
                {status.ok ? <span aria-hidden className="h-2 w-2 shrink-0 rounded-full bg-teal-500" /> : null}
                <span>
                  {status.label}
                  {status.detail ? <span className="font-normal text-white/70"> {"\u00B7"} {status.detail}</span> : null}
                </span>
              </div>
            ) : null}
            {children}
          </div>
        ) : null}
      </div>
    </section>
  );
}

export default PageHeader;
