/**
 * Status-tagging helper (Req 14.3).
 *
 * Every value-bearing display in the app (map features, time-series
 * points/legend, queue rows, recommendation cards, scenario metrics) must
 * carry EXACTLY ONE provenance tag — OBSERVED / PREDICTED / SIMULATED —
 * derived from the artifact record's own `status` field. This module centralises
 * reading that field so a status can never be invented, dropped, or doubled:
 *
 *   - `statusOf(record)` reads the `status` the Python layer wrote (never guesses).
 *   - `assertSingleStatus(...)` is a guard that throws unless there is exactly
 *     one valid tag, so a rendered value that is untagged (or ambiguously
 *     double-tagged) fails loudly in tests rather than silently misleading a user.
 *
 * Design reference: design.md "Labeling, theme, status (Req 14)";
 * Correctness Property 7 ("Exactly one status tag per displayed value").
 */

import type { StatusTag } from "./artifacts";

/** The three — and only three — valid provenance tags (Req 14.3). */
export const STATUS_TAGS: readonly StatusTag[] = [
  "OBSERVED",
  "PREDICTED",
  "SIMULATED",
] as const;

/** Any record that carries a provenance `status` field from the contract. */
export interface StatusBearing {
  status: StatusTag;
}

/** Type guard: is `value` one of the three valid status tags? */
export function isStatusTag(value: unknown): value is StatusTag {
  return (
    typeof value === "string" && (STATUS_TAGS as readonly string[]).includes(value)
  );
}

/**
 * Read the provenance status OFF a record. The status is never invented — it
 * is read verbatim from the artifact's `status` field. Throws if the field is
 * missing or is not one of the three valid tags, so an untagged value can
 * never reach the screen unnoticed (Req 14.3).
 */
export function statusOf(record: { status?: unknown } | null | undefined): StatusTag {
  const status = record?.status;
  if (!isStatusTag(status)) {
    throw new Error(
      `statusOf: record is missing a valid status tag (expected one of ${STATUS_TAGS.join(
        ", ",
      )}, got ${JSON.stringify(status)}). Every displayed value must carry exactly one status (Req 14.3).`,
    );
  }
  return status;
}

/**
 * Guard asserting that EXACTLY ONE status tag describes a displayed value
 * (Req 14.3 / Property 7). Pass the status (or statuses) attached to a single
 * rendered value; throws unless there is precisely one, and that one is valid.
 *
 * Accepts either a single value or an array (e.g. when a value is assembled
 * from several records that must agree on their provenance).
 */
export function assertSingleStatus(
  statuses: StatusTag | readonly StatusTag[],
  context = "displayed value",
): StatusTag {
  const list = Array.isArray(statuses) ? statuses : [statuses as StatusTag];

  if (list.length === 0) {
    throw new Error(
      `assertSingleStatus: ${context} has no status tag; exactly one is required (Req 14.3).`,
    );
  }

  const distinct = Array.from(new Set(list));
  if (distinct.length > 1) {
    throw new Error(
      `assertSingleStatus: ${context} carries multiple distinct status tags (${distinct.join(
        ", ",
      )}); exactly one is required (Req 14.3).`,
    );
  }

  const [only] = distinct;
  if (!isStatusTag(only)) {
    throw new Error(
      `assertSingleStatus: ${context} has an invalid status tag ${JSON.stringify(
        only,
      )}; must be one of ${STATUS_TAGS.join(", ")} (Req 14.3).`,
    );
  }

  return only;
}

/**
 * Convenience: read a record's status AND assert it is a single valid tag.
 * Use at a render site to guarantee the value about to be shown is tagged.
 */
export function requireStatus(
  record: { status?: unknown } | null | undefined,
  context = "displayed value",
): StatusTag {
  return assertSingleStatus(statusOf(record), context);
}
