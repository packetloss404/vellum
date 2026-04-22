import type { ChangeLogEntry } from "../../api/types";
import { ChangeEntry } from "./ChangeEntry";

interface PlanDiffSidebarViewProps {
  entries: ChangeLogEntry[];
  isLoading?: boolean;
  error?: unknown;
  onMarkRead?: () => void;
  isMarking?: boolean;
}

const HEADER_LABEL = "Since your last visit";

export function PlanDiffSidebarView({
  entries,
  isLoading,
  error,
  onMarkRead,
  isMarking,
}: PlanDiffSidebarViewProps) {
  const hasEntries = entries.length > 0;

  return (
    <aside
      className="w-[320px] sticky top-6 self-start border-l border-rule pl-6"
      aria-label="Plan diff"
    >
      <h2 className="text-xs font-mono uppercase tracking-wide text-ink-faint mb-4">
        {HEADER_LABEL}
      </h2>

      {isLoading ? (
        <p className="text-xs font-mono text-ink-faint">Loading&hellip;</p>
      ) : error ? (
        <p className="text-xs font-mono text-state-blocked">
          Couldn&rsquo;t load changes.
        </p>
      ) : !hasEntries ? (
        <p className="text-xs font-serif italic text-ink-faint leading-relaxed">
          Nothing new since you were last here.
        </p>
      ) : (
        <>
          <ol className="space-y-5 list-none p-0 m-0">
            {entries.map((entry) => (
              <ChangeEntry key={entry.id} entry={entry} />
            ))}
          </ol>

          {onMarkRead !== undefined ? (
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
        </>
      )}
    </aside>
  );
}

export default PlanDiffSidebarView;
