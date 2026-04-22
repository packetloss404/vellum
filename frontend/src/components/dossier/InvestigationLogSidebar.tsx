import React from "react";
import {
  useInvestigationLog,
  useInvestigationLogCounts,
} from "../../api/hooks";
import type { InvestigationLogEntry } from "../../api/types";
import { relativeTime } from "../../utils/time";

/**
 * InvestigationLogSidebar — the sticky right rail on the dossier detail
 * page. Header is a mono counts line ("47 sources · 3 sub-investigations
 * · 2 artifacts") pulled from /investigation-log/counts; body is the 20
 * most recent log entries, each a small "type + summary + ts" block.
 *
 * Read-only scaffold for day 3.
 */

const ENTRY_LIMIT = 20;

interface InvestigationLogSidebarProps {
  dossierId: string;
}

function formatCountsHeader(counts: Record<string, number> | undefined): string {
  if (!counts) return "…";
  const sources = counts.source_consulted ?? counts.sources ?? 0;
  const subs =
    counts.sub_investigation_spawned ??
    counts.sub_investigations ??
    counts.sub_investigation_returned ??
    0;
  const artifacts = counts.artifact_added ?? counts.artifacts ?? 0;
  return `${sources} sources · ${subs} sub-investigations · ${artifacts} artifacts`;
}

function LogRow({ entry }: { entry: InvestigationLogEntry }) {
  return (
    <li className="border-t border-rule pt-3 first:border-t-0 first:pt-0">
      <div className="flex items-center justify-between gap-2 text-xs font-mono text-ink-faint">
        <span className="truncate">{entry.entry_type.replace(/_/g, " ")}</span>
        <span className="shrink-0">{relativeTime(entry.created_at)}</span>
      </div>
      <p className="mt-1 font-serif text-sm text-ink-muted leading-relaxed">
        {entry.summary}
      </p>
    </li>
  );
}

export function InvestigationLogSidebar({
  dossierId,
}: InvestigationLogSidebarProps) {
  const counts = useInvestigationLogCounts(dossierId);
  const log = useInvestigationLog(dossierId);

  // The backend route supports a `limit` arg; the hook doesn't currently
  // thread it through, so we slice on the client. Cheap at 20 entries and
  // keeps the hook API small.
  const recent = (log.data ?? [])
    .slice()
    .sort(
      (a, b) =>
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
    )
    .slice(0, ENTRY_LIMIT);

  return (
    <aside className="sticky top-6 self-start">
      <div className="font-mono text-xs uppercase tracking-wide text-ink-faint mb-3">
        Investigation log
      </div>
      <div className="font-mono text-xs text-ink-muted mb-5 leading-snug">
        {formatCountsHeader(counts.data)}
      </div>

      {log.isLoading ? (
        <div className="font-mono text-xs text-ink-faint">Loading…</div>
      ) : log.error ? (
        <div className="font-mono text-xs text-state-blocked">
          Couldn't load log.
        </div>
      ) : recent.length === 0 ? (
        <div className="font-serif text-sm italic text-ink-faint">
          No log entries yet.
        </div>
      ) : (
        <ul className="space-y-3 list-none p-0 m-0">
          {recent.map((entry) => (
            <LogRow key={entry.id} entry={entry} />
          ))}
        </ul>
      )}
    </aside>
  );
}

export default InvestigationLogSidebar;
