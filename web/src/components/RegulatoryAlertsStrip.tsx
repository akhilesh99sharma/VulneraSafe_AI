import { useArtifact } from "../data/hooks";
import type { RegulatoryAlert } from "../types/artifacts";
import AlertBadge from "./AlertBadge";
import StatusTag from "./StatusTag";
import EmptyState from "./EmptyState";

/**
 * Regulatory Alerts strip (task 6.4 — Requirements 16.5, 16.6; design.md
 * "Regulatory Alerts strip" / correction 4).
 *
 * Renders verified official recalls from the `regulatory_alerts` artifact in a
 * dedicated, always-visible, visually DISTINCT strip (strong authoritative
 * navy + red accent) so a user never mistakes a verified recall for a model
 * guess. Each item carries an AlertBadge source="REGULATORY" — never "MODEL".
 *
 * CRITICAL REGULATORY-INDEPENDENCE INVARIANT (Req 16.5, 16.6):
 *   This strip depends ONLY on the `regulatory_alerts` artifact. It reads no
 *   model, recommendation, manifest, or uncertainty state, and MUST NOT be
 *   suppressed because a predictive uncertainty estimate is missing or a model
 *   artifact failed to load. Verified official recalls flow on an independent
 *   regulatory-evidence track. Do NOT add a dependency here on any model /
 *   recommendation / manifest hook — doing so would let missing model
 *   uncertainty hide a real recall, violating Req 16.6.
 *
 * Degradation: if the artifact is absent/empty/unreadable, the strip shows a
 * CALM empty state ("No active regulatory recalls") — never a loud error that
 * would hide the regulatory track or imply the system is broken.
 */

/**
 * An alert is an ILLUSTRATIVE placeholder (not a real recall) when its id is
 * prefixed "EXAMPLE" or its product string carries the "[EXAMPLE]" marker.
 * These are the seeds used when the live FSIS feed was unavailable; they must
 * be labeled unmistakably so a user never mistakes one for a real recall.
 */
function isPlaceholderAlert(alert: RegulatoryAlert): boolean {
  return (
    alert.recall_id.startsWith("EXAMPLE") || alert.product.includes("[EXAMPLE]")
  );
}

/** A single verified-recall card. */
function RecallCard({ alert }: { alert: RegulatoryAlert }) {
  const placeholder = isPlaceholderAlert(alert);
  return (
    <li
      data-testid="regulatory-alert-item"
      data-recall-id={alert.recall_id}
      data-placeholder={placeholder ? "true" : "false"}
      className="flex flex-col gap-2 rounded border-l-4 border-alert-danger bg-white p-3 shadow-sm ring-1 ring-navy/10"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          {/* REGULATORY (never MODEL) — authoritative, visually separated. */}
          <AlertBadge source="REGULATORY" />
          <StatusTag status={alert.status} />
          {placeholder ? (
            <span
              data-testid="regulatory-alert-example-tag"
              className="rounded bg-alert-warn/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-alert-warn"
            >
              EXAMPLE — not a real recall
            </span>
          ) : null}
        </div>
        <span className="font-mono text-xs font-semibold text-navy/70">
          {alert.recall_id}
        </span>
      </div>

      <p className="text-sm font-bold text-navy">{alert.product}</p>

      <dl className="grid grid-cols-[auto,1fr] gap-x-3 gap-y-1 text-xs">
        <dt className="font-semibold text-navy/60">Classification</dt>
        <dd className="font-semibold text-alert-danger">
          {alert.classification}
        </dd>

        <dt className="font-semibold text-navy/60">Date</dt>
        <dd className="text-navy">{alert.date}</dd>

        <dt className="font-semibold text-navy/60">
          Affected lot{alert.lot_ids.length === 1 ? "" : "s"}
        </dt>
        <dd className="text-navy">
          {alert.lot_ids.length > 0 ? (
            <span className="flex flex-wrap gap-1">
              {alert.lot_ids.map((lot) => (
                <span
                  key={lot}
                  className="rounded bg-navy/5 px-1.5 py-0.5 font-mono text-[11px] text-navy"
                >
                  {lot}
                </span>
              ))}
            </span>
          ) : (
            <span className="text-navy/50">Not specified</span>
          )}
        </dd>
      </dl>

      <a
        href={alert.source_url}
        target="_blank"
        rel="noreferrer noopener"
        data-testid="regulatory-alert-source-link"
        className="text-xs font-semibold text-teal-600 underline underline-offset-2 hover:text-navy"
      >
        View official source ↗
      </a>
    </li>
  );
}

export function RegulatoryAlertsStrip() {
  // Independent regulatory-evidence track: ONLY the regulatory_alerts artifact.
  // No model / recommendation / uncertainty state is read here (Req 16.5, 16.6).
  const { data, error } = useArtifact<RegulatoryAlert[]>("regulatory_alerts");

  const alerts = data ?? [];
  const hasPlaceholder = alerts.some(isPlaceholderAlert);

  // Absent, unreadable, or empty -> calm empty state, NOT an error that would
  // hide the regulatory track. A failed load is treated the same as "no active
  // recalls" so the strip stays present and unalarming (Req 16.6).
  const body =
    alerts.length === 0 || error ? (
      <EmptyState
        title="No active regulatory recalls"
        detail="Verified official recalls appear here the moment one is published. This track is independent of any model or prediction."
      />
    ) : (
      <>
        {hasPlaceholder ? (
          <div
            data-testid="regulatory-alerts-example-notice"
            role="alert"
            className="mb-3 rounded border-l-4 border-alert-warn bg-alert-warn/10 px-3 py-2 text-xs font-semibold text-alert-warn"
          >
            ⚠ Illustrative examples only — the live FSIS recall feed was
            unavailable in this environment. These are NOT real recalls.
          </div>
        ) : null}
        <ol
          data-testid="regulatory-alerts-list"
          className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3"
        >
          {alerts.slice(0, 6).map((alert) => (
            <RecallCard key={alert.recall_id} alert={alert} />
          ))}
        </ol>
        {alerts.length > 6 ? (
          <p className="mt-3 text-[11px] text-navy/50">Showing 6 of {alerts.length} current recalls for the tracked pathogens.</p>
        ) : null}
      </>
    );

  return (
    <section
      aria-label="Regulatory alerts"
      data-testid="regulatory-alerts-strip"
      // Strong authoritative styling, clearly distinct from any model-derived
      // alert surface: navy band with a red top accent.
      className="border-t-4 border-alert-danger/70 bg-white"
    >
      <div className="mx-auto max-w-7xl px-6 py-4">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <h2 className="text-sm font-bold uppercase tracking-wide text-navy">
            Current Recalls
          </h2>
          <span className="rounded bg-alert-danger/10 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-alert-danger">
            Verified official source
          </span>
          <span className="text-[11px] text-navy/50">
            Independent of model predictions · never suppressed by missing
            uncertainty
          </span>
        </div>
        {body}
      </div>
    </section>
  );
}

export default RegulatoryAlertsStrip;
