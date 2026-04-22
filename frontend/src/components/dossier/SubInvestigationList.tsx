import React from "react";
import type {
  SubInvestigation,
  SubInvestigationState,
} from "../../api/types";
import { Pill } from "../common/Pill";
import { relativeTime } from "../../utils/time";

/**
 * SubInvestigationList — read-only roll-up of branches the agent spun
 * off during the investigation. Each entry shows scope, state, and the
 * return_summary if one has been recorded.
 *
 * Day-3 scaffold; no drill-in, no filtering.
 */

export interface SubInvestigationListProps {
  subs: SubInvestigation[];
}

function statePillState(
  state: SubInvestigationState,
): "confident" | "provisional" | "blocked" {
  switch (state) {
    case "delivered":
      return "confident";
    case "blocked":
    case "abandoned":
      return "blocked";
    default:
      return "provisional";
  }
}

export function SubInvestigationList({ subs }: SubInvestigationListProps) {
  if (!subs || subs.length === 0) return null;

  // Newest-spawned first, for a stable reverse-chron read.
  const ordered = [...subs].sort(
    (a, b) =>
      new Date(b.started_at).getTime() - new Date(a.started_at).getTime(),
  );

  return (
    <section className="space-y-4">
      <h2 className="font-mono text-xs uppercase tracking-wide text-ink-faint">
        Sub-investigations ({subs.length})
      </h2>
      <ul className="space-y-5 list-none p-0 m-0">
        {ordered.map((sub) => {
          const hasSummary =
            sub.return_summary && sub.return_summary.trim().length > 0;
          return (
            <li
              key={sub.id}
              className="border-t border-rule pt-4 first:border-t-0 first:pt-0"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="font-serif text-base text-ink leading-snug">
                    {sub.scope}
                  </div>
                  <div className="mt-1 text-xs font-mono text-ink-faint">
                    started {relativeTime(sub.started_at)}
                    {sub.completed_at ? (
                      <>
                        {" · "}
                        finished {relativeTime(sub.completed_at)}
                      </>
                    ) : null}
                  </div>
                </div>
                <Pill variant="state" state={statePillState(sub.state)}>
                  {sub.state}
                </Pill>
              </div>
              {hasSummary ? (
                <p className="mt-2 font-serif text-sm text-ink-muted leading-relaxed whitespace-pre-wrap">
                  {sub.return_summary}
                </p>
              ) : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export default SubInvestigationList;
