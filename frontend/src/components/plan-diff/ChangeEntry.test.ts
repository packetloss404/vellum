import { describe, it, expect } from "vitest";
import { PLAN_DIFF_CATEGORY_ORDER } from "./ChangeEntry";

// The category order is load-bearing — the right-rail "since your last
// visit" sidebar groups change-log entries by category, and a reordering
// here would visibly shuffle the user's view. Pin the order.

describe("PLAN_DIFF_CATEGORY_ORDER", () => {
  it("has 7 categories in the documented order", () => {
    expect(PLAN_DIFF_CATEGORY_ORDER).toEqual([
      "plan_and_debrief",
      "sections",
      "sub_investigations",
      "artifacts",
      "flagged",
      "considered_and_rejected",
      "housekeeping",
    ]);
  });

  it("contains no duplicates", () => {
    const set = new Set(PLAN_DIFF_CATEGORY_ORDER);
    expect(set.size).toBe(PLAN_DIFF_CATEGORY_ORDER.length);
  });
});
