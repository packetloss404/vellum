import { describe, it, expect } from "vitest";
import { relativeTime } from "./time";

const NOW = new Date("2026-08-02T12:00:00Z").getTime();
const origNow = Date.now;

describe("relativeTime", () => {
  beforeEach(() => {
    Date.now = () => NOW;
  });
  afterEach(() => {
    Date.now = origNow;
  });

  it("returns 'just now' for a timestamp 0-59s in the past", () => {
    expect(relativeTime(new Date(NOW - 5_000).toISOString())).toBe("just now");
    expect(relativeTime(new Date(NOW - 0).toISOString())).toBe("just now");
    expect(relativeTime(new Date(NOW - 59_000).toISOString())).toBe("just now");
  });

  it("returns 'Nm ago' for 1-59 minutes", () => {
    expect(relativeTime(new Date(NOW - 60_000).toISOString())).toBe("1m ago");
    expect(relativeTime(new Date(NOW - 30 * 60_000).toISOString())).toBe("30m ago");
    expect(relativeTime(new Date(NOW - 59 * 60_000).toISOString())).toBe("59m ago");
  });

  it("returns 'Nh ago' for 1-23 hours", () => {
    expect(relativeTime(new Date(NOW - 60 * 60_000).toISOString())).toBe("1h ago");
    expect(relativeTime(new Date(NOW - 12 * 3600_000).toISOString())).toBe("12h ago");
  });

  it("returns 'yesterday' for exactly 1d", () => {
    expect(relativeTime(new Date(NOW - 24 * 3600_000).toISOString())).toBe("yesterday");
  });

  it("returns 'Nd ago' for 2-13 days", () => {
    expect(relativeTime(new Date(NOW - 2 * 86400_000).toISOString())).toBe("2d ago");
    expect(relativeTime(new Date(NOW - 13 * 86400_000).toISOString())).toBe("13d ago");
  });

  it("returns 'Mon D' for >= 14 days", () => {
    const fourWeeksAgo = new Date(NOW - 28 * 86400_000);
    const expected = `${["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][fourWeeksAgo.getMonth()]} ${fourWeeksAgo.getDate()}`;
    expect(relativeTime(fourWeeksAgo.toISOString())).toBe(expected);
  });

  it("returns '' for an invalid ISO string", () => {
    expect(relativeTime("not-an-iso")).toBe("");
    expect(relativeTime("")).toBe("");
  });
});
