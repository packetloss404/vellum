import { describe, it, expect } from "vitest";
import { truncate, titleCase } from "./format";

describe("truncate", () => {
  it("returns input unchanged when s.length <= n", () => {
    expect(truncate("hello", 10)).toBe("hello");
    expect(truncate("hello", 5)).toBe("hello");
  });

  it("returns '' for non-string", () => {
    expect(truncate(null as unknown as string, 10)).toBe("");
    expect(truncate(undefined as unknown as string, 10)).toBe("");
    expect(truncate(123 as unknown as string, 10)).toBe("");
  });

  it("returns '…' when n <= 1", () => {
    expect(truncate("hello world", 1)).toBe("…");
    expect(truncate("hello world", 0)).toBe("");
    expect(truncate("hello world", -1)).toBe("");
  });

  it("truncates and appends ellipsis", () => {
    expect(truncate("supercalifragilistic", 8)).toBe("superca…");
    expect(truncate("hello world", 6)).toBe("hello…");
    expect(truncate("hello world", 8)).toBe("hello w…");
  });
});

describe("titleCase", () => {
  it("lowercases then capitalizes first letter of each word", () => {
    expect(titleCase("hello world")).toBe("Hello World");
    expect(titleCase("HELLO WORLD")).toBe("Hello World");
    expect(titleCase("hello WORLD")).toBe("Hello World");
  });

  it("preserves whitespace (multiple spaces, tabs)", () => {
    expect(titleCase("hello  world")).toBe("Hello  World");
  });

  it("returns '' for non-string or empty", () => {
    expect(titleCase("")).toBe("");
    expect(titleCase(null as unknown as string)).toBe("");
  });
});
