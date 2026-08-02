import { describe, it, expect } from "vitest";
import { cx } from "./cx";

describe("cx", () => {
  it("joins truthy class strings with a space", () => {
    expect(cx("base", "conditional", "always")).toBe("base conditional always");
  });

  it("filters out false, undefined, null, and empty strings", () => {
    expect(cx("base", false, undefined, null, "", "always")).toBe("base always");
  });

  it("returns an empty string when no truthy inputs are given", () => {
    expect(cx(false, undefined, null, "")).toBe("");
  });

  it("handles a single string", () => {
    expect(cx("only")).toBe("only");
  });
});
