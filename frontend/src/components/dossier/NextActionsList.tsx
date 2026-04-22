import React from "react";
import type { NextAction } from "../../api/types";

/**
 * NextActionsList — the "here's what's next" ordered list. Read-only on
 * day 3; a later agent will wire up complete/remove/reorder mutations.
 *
 * Ordered by priority ascending (1 is highest). Completed items render
 * with a strike-through but are kept in-line so the list still reads as
 * a single plan.
 */

export interface NextActionsListProps {
  items: NextAction[];
}

export function NextActionsList({ items }: NextActionsListProps) {
  if (!items || items.length === 0) return null;

  const ordered = [...items].sort((a, b) => {
    if (a.priority !== b.priority) return a.priority - b.priority;
    return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
  });

  return (
    <section className="space-y-4">
      <h2 className="font-mono text-xs uppercase tracking-wide text-ink-faint">
        Next actions ({items.length})
      </h2>
      <ol className="space-y-3 list-none p-0 m-0">
        {ordered.map((item, idx) => (
          <li key={item.id} className="flex items-start gap-3">
            <span className="font-mono text-xs text-ink-faint pt-1 w-5 shrink-0">
              {String(idx + 1).padStart(2, "0")}
            </span>
            <div className="min-w-0 flex-1">
              <p
                className={
                  item.completed
                    ? "font-serif text-base text-ink-muted line-through leading-snug"
                    : "font-serif text-base text-ink leading-snug"
                }
              >
                {item.action}
              </p>
              {item.rationale && item.rationale.trim().length > 0 ? (
                <p className="mt-0.5 text-sm font-serif text-ink-muted italic leading-relaxed">
                  {item.rationale}
                </p>
              ) : null}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

export default NextActionsList;
