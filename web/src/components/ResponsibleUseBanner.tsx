/**
 * Responsible-Use banner (Task 7.1 — Req 16.1, 16.2, 16.3; design.md
 * "Responsible-Use and Guardrails").
 *
 * A prominent, always-visible statement that VulneraSafe AI is decision
 * support only — not a regulatory determination or outbreak declaration — and
 * that consequential actions require human review. Placed in the App shell so
 * the framing is visible from every view.
 *
 * This copy mirrors the Python `DISCLAIMERS` dict in `src/responsible.py`; the
 * two layers must assert the same constraints. The banner is informational
 * framing (navy/teal scientific theme) and is NOT an alert, so it must never
 * use the reserved orange/red alert colors (themeDiscipline test).
 */

export function ResponsibleUseBanner() {
  return (
    <aside
      aria-label="Responsible-use notice"
      data-testid="responsible-use-banner"
      className="border-b border-teal/30 bg-teal/5"
    >
      <div className="mx-auto max-w-7xl px-6 py-2">
        <p className="text-xs leading-relaxed text-navy">
          <span className="font-semibold uppercase tracking-wide text-teal-700">
            Decision support only ·{" "}
          </span>
          VulneraSafe AI is{" "}
          <span className="font-semibold">
            not a regulatory determination or outbreak declaration
          </span>{" "}
          and does not replace laboratory confirmation or epidemiologic
          investigation. A model alert never establishes contamination, and
          predicted risk never declares a product safe or unsafe. Every
          consequential action requires{" "}
          <span className="font-semibold">human review</span> before acting.
        </p>
      </div>
    </aside>
  );
}

export default ResponsibleUseBanner;
