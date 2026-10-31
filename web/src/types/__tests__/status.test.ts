import { describe, it, expect } from "vitest";
import {
  STATUS_TAGS,
  assertSingleStatus,
  isStatusTag,
  requireStatus,
  statusOf,
} from "../status";
import type { RiskMapFeature } from "../artifacts";

/**
 * status helper tests (Req 14.3 / Correctness Property 7).
 *
 * The guard must guarantee EXACTLY ONE valid status tag per displayed value:
 *   - a record carrying a valid status returns it,
 *   - a record WITHOUT a status throws (an untagged value can never be shown),
 *   - a record with an invalid/double status throws.
 */

const TAGGED: Pick<RiskMapFeature, "status"> = { status: "PREDICTED" };

describe("isStatusTag", () => {
  it("accepts exactly the three valid tags", () => {
    for (const tag of STATUS_TAGS) {
      expect(isStatusTag(tag)).toBe(true);
    }
  });

  it("rejects anything else", () => {
    for (const bad of ["observed", "", "UNKNOWN", null, undefined, 1, {}]) {
      expect(isStatusTag(bad)).toBe(false);
    }
  });
});

describe("statusOf", () => {
  it("reads a valid status verbatim off the record", () => {
    expect(statusOf(TAGGED)).toBe("PREDICTED");
  });

  it("throws when a displayed value has no status (Req 14.3)", () => {
    // A record missing the status field must fail loudly, not render untagged.
    const untagged = { region: "TX", risk: 0.4 } as unknown as { status?: unknown };
    expect(() => statusOf(untagged)).toThrowError(/status/i);
  });

  it("throws on null/undefined records", () => {
    expect(() => statusOf(null)).toThrowError(/status/i);
    expect(() => statusOf(undefined)).toThrowError(/status/i);
  });

  it("throws when the status is not one of the three valid tags", () => {
    expect(() => statusOf({ status: "GUESSED" })).toThrowError(/status/i);
  });
});

describe("assertSingleStatus", () => {
  it("returns the single tag when exactly one is present", () => {
    expect(assertSingleStatus("OBSERVED")).toBe("OBSERVED");
    expect(assertSingleStatus(["SIMULATED"])).toBe("SIMULATED");
    // Agreeing duplicates collapse to the one distinct tag.
    expect(assertSingleStatus(["PREDICTED", "PREDICTED"])).toBe("PREDICTED");
  });

  it("flags an untagged value (empty) (Req 14.3)", () => {
    expect(() => assertSingleStatus([])).toThrowError(/no status tag/i);
  });

  it("flags a value carrying multiple distinct tags (Req 14.3)", () => {
    expect(() => assertSingleStatus(["OBSERVED", "PREDICTED"])).toThrowError(
      /multiple distinct status tags/i,
    );
  });
});

describe("requireStatus", () => {
  it("reads and asserts a single valid tag in one call", () => {
    expect(requireStatus(TAGGED, "map feature")).toBe("PREDICTED");
  });

  it("throws (flags) a rendered value with no status (Req 14.3)", () => {
    const untagged = { region: "CA" } as unknown as { status?: unknown };
    expect(() => requireStatus(untagged, "map feature")).toThrowError(/status/i);
  });
});
