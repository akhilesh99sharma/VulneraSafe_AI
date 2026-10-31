/**
 * Shown for missing-data and artifact-load-failure cases (Req 15.3, 14.5).
 * Keeps graceful degradation visible: a panel whose artifact failed to load
 * renders this instead of crashing, while other panels still render.
 */

interface EmptyStateProps {
  title: string;
  detail?: string;
}

export function EmptyState({ title, detail }: EmptyStateProps) {
  return (
    <div
      data-testid="empty-state"
      role="status"
      className="flex flex-col items-center justify-center rounded border border-dashed border-navy/20 bg-surface-muted px-6 py-10 text-center"
    >
      <p className="text-sm font-semibold text-navy">{title}</p>
      {detail ? (
        <p className="mt-1 max-w-prose text-xs text-gray-500">{detail}</p>
      ) : null}
    </div>
  );
}

export default EmptyState;
