import type { ReactNode } from "react";

/**
 * A KPI stat card: a small tinted icon chip, an uppercase label, a big value,
 * an optional sub-line, and an optional trend arrow with readable text.
 *
 * Presentational only — no data, no business logic. Colors are restrained and
 * drawn only from the project's theme tokens (navy / teal / alert) plus the
 * soft-opacity backgrounds the existing panels already use.
 */

type Tone = "default" | "alert" | "info" | "teal";
type TrendDirection = "up" | "down" | "flat";

interface Trend {
  direction: TrendDirection;
  text: string;
}

export interface StatCardProps {
  label: string;
  value: ReactNode;
  /** Small line beneath the value (e.g. a denominator or context note). */
  sub?: ReactNode;
  icon?: ReactNode;
  trend?: Trend;
  tone?: Tone;
}

/** Left accent + icon-chip tints per tone, using theme tokens only. */
// Left accent + icon-chip tints per tone. KPI tones are DECORATIVE, so
// they use only navy/teal -- never the reserved alert (orange/red) palette,
// which Req 14.4 reserves for active alerts. Severity is conveyed by the
// card's VALUE text (e.g. "High") and any StatusTag, not by a decorative tint.
const TONE_STYLES: Record<Tone, { accent: string; chip: string }> = {
  default: { accent: "border-l-navy/30", chip: "bg-navy/10 text-navy" },
  alert: { accent: "border-l-navy/70", chip: "bg-navy/15 text-navy" },
  info: { accent: "border-l-teal/40", chip: "bg-teal/10 text-teal-600" },
  teal: { accent: "border-l-teal/40", chip: "bg-teal/10 text-teal-600" },
};

const TREND_GLYPH: Record<TrendDirection, string> = {
  up: "\u2191",
  down: "\u2193",
  flat: "\u2192",
};

/**
 * Trend tone stays restrained: up/down read as teal/navy (neutral movement),
 * and decorative red is avoided. Genuine alerts belong in the card `tone`.
 */
const TREND_TEXT: Record<TrendDirection, string> = {
  up: "text-teal-600",
  down: "text-navy/70",
  flat: "text-navy/50",
};

export function StatCard({ label, value, sub, icon, trend, tone = "default" }: StatCardProps) {
  const toneStyle = TONE_STYLES[tone];
  return (
    <div
      data-testid="stat-card"
      className={`rounded-xl border border-navy/10 border-l-4 bg-white px-4 py-3 shadow-sm ${toneStyle.accent}`}
    >
      <div className="flex items-start gap-3">
        {icon ? (
          <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${toneStyle.chip}`} aria-hidden>
            {icon}
          </span>
        ) : null}
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-navy/60">{label}</p>
          <p className="mt-0.5 text-2xl font-extrabold leading-tight text-navy">{value}</p>
          {sub ? <p className="mt-0.5 text-[11px] leading-relaxed text-navy/50">{sub}</p> : null}
          {trend ? (
            <p className={`mt-1 flex items-center gap-1 text-[11px] font-semibold ${TREND_TEXT[trend.direction]}`}>
              <span aria-hidden>{TREND_GLYPH[trend.direction]}</span>
              <span>{trend.text}</span>
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export default StatCard;
