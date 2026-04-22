import { useMemo } from "react";
import type { ChangeLogEntry } from "../../api/types";
import { relativeTime } from "../../utils/time";
import {
  ChangeEntry,
  categoryOfKind,
  PLAN_DIFF_CATEGORY_LABEL,
  PLAN_DIFF_CATEGORY_ORDER,
  type PlanDiffCategory,
} from "./ChangeEntry";

/**
 * PlanDiffSidebarView — the "Since your last visit" sidebar.
 *
 * Purely presentational: the parent is responsible for handing us the
 * pre-visit snapshot of entries (so the /visit POST doesn't wipe them out
 * under us). See PlanDiffSidebar for the data-fetching shell.
 *
 * Entries are grouped by category (Plan & debrief, Sections, ...) in the
 * fixed PLAN_DIFF_CATEGORY_ORDER. Within a group, entries are shown
 * reverse-chronological (most recent first).
 */

interface PlanDiffSidebarViewProps {
  entries: ChangeLogEntry[];
  /** ISO of dossier.last_visited_at at the moment this sidebar took its
   *  snapshot. `null` means this is the user's first visit. `undefined`
   *  means "not known yet" (dossier still loading). */
  lastVisitedAt?: string | null;
  isLoading?: boolean;
  error?: unknown;
  onMarkRead?: () => void;
  isMarking?: boolean;
}

const HEADER_LABEL = "Since your last visit";

export function PlanDiffSidebarView({
  entries,
  lastVisitedAt,
  isLoading,
  error,
  onMarkRead,
  isMarking,
}: PlanDiffSidebarViewProps) {
  const grouped = useMemo(() => {
    const buckets = new Map<PlanDiffCategory, ChangeLogEntry[]>();
    for (const entry of entries) {
      const cat = categoryOfKind(entry.kind);
      const bucket = buckets.get(cat) ?? [];
      bucket.push(entry);
      buckets.set(cat, bucket);
    }
    // Sort each bucket reverse-chronological.
    for (const bucket of buckets.values()) {
      bucket.sort(
        (a, b) =>
          new Date(b.created_at).getTime() -
          new Date(a.created_at).getTime(),
      );
    }
    // Return in fixed category order, skipping empty.
    return PLAN_DIFF_CATEGORY_ORDER.map((cat) => ({
      category: cat,
      label: PLAN_DIFF_CATEGORY_LABEL[cat],
      entries: buckets.get(cat) ?? [],
    })).filter((g) => g.entries.length > 0);
  }, [entries]);

  const hasEntries = entries.length > 0;

  // Subtitle: "Last visited 3h ago", or "Your first visit" when null,
  // or nothing when undefined (still loading upstream).
  let subtitle: string | null = null;
  if (lastVisitedAt === null) {
    subtitle = "Your first visit";
  } else if (typeof lastVisitedAt === "string") {
    subtitle = `Last visited ${relativeTime(lastVisitedAt)}`;
  }

  return (
    <aside
      className="w-full max-w-[320px] self-start"
      aria-label="What changed since your last visit"
    >
      <div className="sticky top-6 bg-paper pb-3 -mb-1 z-10">
        <h2 className="font-serif text-lg text-ink leading-tight">
          {HEADER_LABEL}
        </h2>
        {subtitle ? (
          <p className="mt-1 font-mono text-[11px] text-ink-faint">
            {subtitle}
          </p>
        ) : null}
      </div>

      {isLoading ? (
        <p className="mt-4 text-xs font-mono text-ink-faint">Loading…</p>
      ) : error ? (
        <p className="mt-4 text-xs font-mono text-state-blocked">
          Couldn&rsquo;t load changes.
        </p>
      ) : !hasEntries ? (
        <p className="mt-4 font-serif italic text-sm text-ink-muted leading-relaxed">
          Nothing has moved since you were last here.
        </p>
      ) : (
        <div className="mt-4 space-y-6">
          {grouped.map((group) => (
            <section key={group.category} aria-label={group.label}>
              <h3 className="font-mono text-[10px] uppercase tracking-[0.12em] text-ink-faint mb-2">
                {group.label}
              </h3>
              <ol className="list-none p-0 m-0 [&>li]:py-2.5 [&>li]:border-t [&>li]:border-rule [&>li:first-child]:border-t-0 [&>li:first-child]:pt-0 [&>li:last-child]:pb-0">
                {group.entries.map((entry) => (
                  <ChangeEntry key={entry.id} entry={entry} />
                ))}
              </ol>
            </section>
          ))}
        </div>
      )}

      {hasEntries && onMarkRead !== undefined ? (
        <div className="mt-6 pt-4 border-t border-rule">
          <button
            type="button"
            onClick={onMarkRead}
            disabled={isMarking}
            className="font-sans text-xs text-accent hover:text-accent-hover disabled:text-ink-faint disabled:cursor-not-allowed transition-colors"
          >
            {isMarking ? "Marking…" : "Mark as read"}
          </button>
        </div>
      ) : null}
    </aside>
  );
}

export default PlanDiffSidebarView;
