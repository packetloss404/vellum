/**
 * Ellipsis-truncate a string to at most `n` characters. No word-break — the
 * cut is mid-word if necessary. If `s.length <= n`, returns `s` unchanged.
 */
export function truncate(s: string, n: number): string {
  if (typeof s !== "string") return "";
  if (n <= 0) return "";
  if (s.length <= n) return s;
  if (n <= 1) return "…";
  return s.slice(0, n - 1).trimEnd() + "…";
}

/**
 * Title-case a string: first letter of each whitespace-delimited word
 * uppercased, all other letters lowercased.
 */
export function titleCase(s: string): string {
  if (typeof s !== "string") return "";
  return s
    .toLowerCase()
    .split(/(\s+)/)
    .map((part) => {
      if (/^\s+$/.test(part) || part.length === 0) return part;
      return part.charAt(0).toUpperCase() + part.slice(1);
    })
    .join("");
}
