/**
 * SectionTabs — a secondary (sub-tab) strip used inside a top-level section
 * that holds more than one view. Presentational / controlled: the parent owns
 * the active id and handles changes.
 *
 * Renders real <button type="button"> pills with an underline accent for the
 * active sub-tab, matching the app's navy/teal aesthetic. Each button exposes
 * aria-pressed + aria-current and a data-testid of `subtab-${id}`; the container
 * is data-testid="section-tabs".
 */

export interface SectionTab {
  id: string;
  label: string;
}

export interface SectionTabsProps {
  tabs: ReadonlyArray<SectionTab>;
  active: string;
  onChange: (id: string) => void;
  className?: string;
}

export function SectionTabs({ tabs, active, onChange, className }: SectionTabsProps) {
  return (
    <div
      data-testid="section-tabs"
      role="tablist"
      aria-label="Section views"
      className={`mx-auto flex max-w-7xl flex-wrap gap-1 border-b border-navy/10 px-6 ${className ?? ""}`}
    >
      {tabs.map((t) => {
        const on = t.id === active;
        return (
          <button
            key={t.id}
            type="button"
            role="tab"
            data-testid={`subtab-${t.id}`}
            aria-pressed={on}
            aria-current={on ? "page" : undefined}
            onClick={() => onChange(t.id)}
            className={`-mb-px rounded-t-md border-b-2 px-3 py-2 text-sm font-semibold transition ${
              on
                ? "border-teal bg-teal/5 text-navy"
                : "border-transparent text-navy/60 hover:bg-navy/5 hover:text-navy"
            }`}
          >
            {t.label}
          </button>
        );
      })}
    </div>
  );
}

export default SectionTabs;
