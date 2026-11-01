import type { ReactNode } from "react";

/**
 * Side-by-side dashboard layout: a wide hero `left` (2/3) paired with a
 * narrower `right` rail (1/3) on large screens; stacks on mobile. Dumb layout
 * wrapper only.
 */

export interface TwoColumnProps {
  left: ReactNode;
  right: ReactNode;
  className?: string;
}

export function TwoColumn({ left, right, className }: TwoColumnProps) {
  return (
    <div
      data-testid="two-column"
      className={`grid grid-cols-1 gap-4 lg:grid-cols-3 ${className ?? ""}`}
    >
      <div className="lg:col-span-2">{left}</div>
      <div className="lg:col-span-1">{right}</div>
    </div>
  );
}

export default TwoColumn;
