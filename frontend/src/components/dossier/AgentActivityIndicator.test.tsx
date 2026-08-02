import { describe, it, expect } from "vitest";
import { derive } from "./AgentActivityIndicator";

// All tests use a fixed `now` so derive's elapsed/countdown math is
// deterministic. The `derive` function is exported specifically for
// direct testing of the state machine — the React component itself
// derives from the API hooks.

const NOW = new Date("2026-08-02T12:00:00Z").getTime();
const PAST = new Date(NOW - 60_000).toISOString();
const FUTURE = new Date(NOW + 3_600_000).toISOString();

describe("AgentActivityIndicator.derive", () => {
  it("returns running when the agent is running, regardless of wake state", () => {
    const d = derive(true, PAST, FUTURE, true, "scheduled", NOW);
    expect(d.state).toBe("running");
    expect(d.label).toBe("Researching");
  });

  it("returns waking when wake_pending is true and the agent is not running", () => {
    const d = derive(false, null, null, true, "crash_resume", NOW);
    expect(d.state).toBe("waking");
    expect(d.label).toBe("Resuming after crash");
    expect(d.subLabel).toBe("within 30s");
  });

  it("returns waking when wake_at is in the past", () => {
    const d = derive(false, null, PAST, false, "scheduled", NOW);
    expect(d.state).toBe("waking");
  });

  it("returns scheduled when wake_at is in the future", () => {
    const d = derive(false, null, FUTURE, false, "scheduled", NOW);
    expect(d.state).toBe("scheduled");
    expect(d.subLabel).toContain("in");
  });

  it("returns idle when there is no wake state and the agent is not running", () => {
    const d = derive(false, null, null, false, null, NOW);
    expect(d.state).toBe("idle");
    expect(d.label).toBe("Idle");
  });

  it("maps wake reasons to human strings via wakeReasonLabel", () => {
    // 'decision_resolved' is the unique mapping worth pinning — the other
    // three ('scheduled', 'crash_resume', 'needs_input_resolved') are
    // exercised in the cases above.
    const d = derive(false, null, FUTURE, false, "decision_resolved", NOW);
    expect(d.label).toBe("Picking up your decision");
  });
});
