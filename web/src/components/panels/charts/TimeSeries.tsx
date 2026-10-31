import type { RiskTimeseriesPoint } from "../../../types/artifacts";
import { formatRisk } from "../../../types/viewModels";

/**
 * Inline-SVG risk time-series (Req 12.1) with a Y-axis percentage scale,
 * gridlines, and a legend distinguishing the risk line from the shaded 95%
 * uncertainty band. Plots risk over ISO periods for one selected region.
 */

export interface TimeSeriesProps {
  points: RiskTimeseriesPoint[];
  ariaLabel: string;
}

const WIDTH = 560;
const HEIGHT = 200;
const PAD_L = 42;
const PAD_R = 16;
const PAD_T = 14;
const PAD_B = 34;

function scaleX(i: number, n: number): number {
  if (n <= 1) return PAD_L + (WIDTH - PAD_L - PAD_R) / 2;
  return PAD_L + (i * (WIDTH - PAD_L - PAD_R)) / (n - 1);
}
function scaleY(value: number): number {
  const clamped = Math.min(1, Math.max(0, value));
  return PAD_T + (1 - clamped) * (HEIGHT - PAD_T - PAD_B);
}

const Y_TICKS = [0, 0.25, 0.5, 0.75, 1.0];

export function TimeSeries({ points, ariaLabel }: TimeSeriesProps) {
  const n = points.length;
  const line = points.map((p, i) => `${scaleX(i, n)},${scaleY(p.value)}`).join(" ");
  const bandTop = points.map((p, i) => `${scaleX(i, n)},${scaleY(p.ci_high)}`);
  const bandBottom = points.map((p, i) => `${scaleX(i, n)},${scaleY(p.ci_low)}`).reverse();
  const band = [...bandTop, ...bandBottom].join(" ");
  const last = points[n - 1];

  // Thin the x labels so they do not collide (show ~6 across).
  const labelStep = Math.max(1, Math.ceil(n / 6));

  return (
    <figure data-testid="time-series" className="w-full">
      {/* Legend */}
      <figcaption className="mb-1 flex items-center gap-4 text-[11px] text-navy/70">
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-4 rounded bg-teal" /> Predicted risk
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-4 rounded-sm" style={{ backgroundColor: "rgba(15,155,142,0.18)" }} /> 95% uncertainty
        </span>
      </figcaption>

      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label={ariaLabel}
        className="h-auto w-full"
        preserveAspectRatio="xMidYMid meet"
      >
        {/* Y gridlines + % labels */}
        {Y_TICKS.map((t) => {
          const y = scaleY(t);
          return (
            <g key={t}>
              <line x1={PAD_L} y1={y} x2={WIDTH - PAD_R} y2={y} stroke="rgba(15,39,66,0.08)" strokeWidth={1} />
              <text x={PAD_L - 6} y={y + 3} textAnchor="end" fontSize="10" fill="rgba(15,39,66,0.55)">
                {Math.round(t * 100)}%
              </text>
            </g>
          );
        })}

        {/* Axes */}
        <line x1={PAD_L} y1={HEIGHT - PAD_B} x2={WIDTH - PAD_R} y2={HEIGHT - PAD_B} stroke="rgba(15,39,66,0.25)" />
        <line x1={PAD_L} y1={PAD_T} x2={PAD_L} y2={HEIGHT - PAD_B} stroke="rgba(15,39,66,0.25)" />

        {/* Y-axis title */}
        <text x={12} y={HEIGHT / 2} fontSize="10" fill="rgba(15,39,66,0.6)"
          transform={`rotate(-90 12 ${HEIGHT / 2})`} textAnchor="middle">
          Elevated-risk probability
        </text>

        {/* X-axis title */}
        <text x={WIDTH / 2} y={HEIGHT - 2} fontSize="10" fill="rgba(15,39,66,0.6)" textAnchor="middle">
          Reporting period
        </text>

        {/* Uncertainty band */}
        {n > 1 ? <polygon points={band} fill="rgba(15,155,142,0.18)" /> : null}

        {/* Risk line */}
        {n > 1 ? <polyline points={line} fill="none" stroke="#0f9b8e" strokeWidth={2} /> : null}

        {/* Points + x labels */}
        {points.map((p, i) => (
          <g key={p.period}>
            <circle
              cx={scaleX(i, n)} cy={scaleY(p.value)} r={n === 1 ? 4 : 2.5}
              fill="#0f2742" data-testid="time-series-point" data-period={p.period}
            >
              <title>{`${p.period}: ${formatRisk(p.value)}`}</title>
            </circle>
            {i % labelStep === 0 || i === n - 1 ? (
              <text x={scaleX(i, n)} y={HEIGHT - PAD_B + 14} fontSize="9" fill="rgba(15,39,66,0.55)" textAnchor="middle">
                {p.period}
              </text>
            ) : null}
          </g>
        ))}
      </svg>

      <figcaption className="mt-1 flex justify-between text-[11px] text-navy/70">
        <span>{points[0]?.period ?? ""}</span>
        {last ? <span className="font-semibold text-navy">latest {formatRisk(last.value)}</span> : null}
        <span>{last?.period ?? ""}</span>
      </figcaption>
    </figure>
  );
}

export default TimeSeries;
