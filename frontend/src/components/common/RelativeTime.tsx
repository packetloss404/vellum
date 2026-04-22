import React from "react";
import { relativeTime } from "../../utils/time";

/**
 * RelativeTime — renders an ISO timestamp as a humanized relative string
 * ("3 hours ago", "yesterday", "Mar 4"), with the full timestamp available
 * on hover via the native title attribute.
 *
 * The component is a thin <time> wrapper. Callers that want a specific
 * prefix ("created 3h ago") should render their own text around it.
 */

export interface RelativeTimeProps {
  iso: string | null | undefined;
  className?: string;
  /** If set, replaces the humanized text (the raw ISO is still on `title`). */
  label?: string;
}

function formatFull(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  // Example: "2026-04-22 14:03 UTC" — brief, sortable, timezone-clear.
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ` +
    `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())} UTC`
  );
}

export function RelativeTime({ iso, className, label }: RelativeTimeProps) {
  if (!iso) return null;
  const text = label ?? relativeTime(iso);
  return (
    <time dateTime={iso} title={formatFull(iso)} className={className}>
      {text}
    </time>
  );
}

export default RelativeTime;
