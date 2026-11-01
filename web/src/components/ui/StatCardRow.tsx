import type { ReactNode } from "react";

/**
 * Responsive grid wrapper for a row of StatCards: four across on desktop,
 * two on small screens, stacked on mobile. Dumb layout only.
 */

export interface StatCardRowProps {
  children: ReactNode;
  className?: string;
}

export function StatCardRow({ children, className }: StatCardRowProps) {
  return (
    <div
      data-testid="stat-card-row"
      className={`grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4 ${className ?? ""}`}
    >
      {children}
    </div>
  );
}

export default StatCardRow;
