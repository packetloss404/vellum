const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

/**
 * Return a humanized relative-time string for the given ISO timestamp.
 *   <  60s      → "just now"
 *   <  60m      → "Nm"
 *   <  24h      → "Nh"
 *   <  14d      → "Nd"  (also "yesterday" at exactly 1d)
 *   >= 14d      → "Mon D" (e.g. "Mar 4")
 */
export function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";

  const now = Date.now();
  const deltaSec = Math.max(0, Math.floor((now - then) / 1000));

  if (deltaSec < 60) return "just now";

  const deltaMin = Math.floor(deltaSec / 60);
  if (deltaMin < 60) return `${deltaMin}m ago`;

  const deltaHr = Math.floor(deltaMin / 60);
  if (deltaHr < 24) return `${deltaHr}h ago`;

  const deltaDay = Math.floor(deltaHr / 24);
  if (deltaDay === 1) return "yesterday";
  if (deltaDay < 14) return `${deltaDay}d ago`;

  const d = new Date(then);
  return `${MONTHS[d.getMonth()]} ${d.getDate()}`;
}
