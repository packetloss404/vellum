import React, { useState } from "react";
import type { ReasoningTrailEntry } from "../../api/types";
import { relativeTime } from "../../utils/time";

/**
 * ReasoningTrail — a collapsible "show your work" ledger. The agent's
 * append_reasoning calls land here: tagged strategy shifts, calibration
 * notes, premise-pushback beats. Collapsed by default; expanding reveals
 * the entries in order, tagged and timestamped, written in the agent's
 * own voice.
 *
 * Rendered minimally per the v1 product memory — no filtering, no search,
 * no chrome. If the trail is empty, the component renders nothing.
 */

export interface ReasoningTrailProps {
  entries: ReasoningTrailEntry[];
}

export function ReasoningTrail({ entries }: ReasoningTrailProps) {
  const [expanded, setExpanded] = useState(false);

  if (!entries || entries.length === 0) {
    return null;
  }

  const chevron = expanded ? "▾" : "▸";

  // Most recent last — the trail reads chronologically, like lab notes.
  const ordered = [...entries].sort(
    (a, b) =>
      new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
  );

  return (
    <div className="border-t border-rule pt-4">
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        aria-expanded={expanded}
        aria-label="Toggle reasoning trail"
        className="flex items-center gap-2 text-sm font-mono uppercase tracking-wide text-ink-muted hover:text-ink transition-colors"
      >
        <span aria-hidden="true" className="font-mono text-xs w-3 inline-block">
          {chevron}
        </span>
        <span>Reasoning trail ({entries.length})</span>
      </button>

      {expanded ? (
        <ol className="mt-4 space-y-4 list-none p-0">
          {ordered.map((entry) => (
            <li key={entry.id}>
              <div className="flex items-center gap-2 text-xs font-mono text-ink-faint mb-1">
                <span>{relativeTime(entry.created_at)}</span>
                {entry.tags && entry.tags.length > 0 ? (
                  <>
                    <span aria-hidden="true">·</span>
                    <span className="flex flex-wrap gap-1">
                      {entry.tags.map((t) => (
                        <span
                          key={t}
                          className="bg-surface-sunk text-ink-muted border border-rule rounded px-1.5 py-0.5"
                        >
                          {t}
                        </span>
                      ))}
                    </span>
                  </>
                ) : null}
              </div>
              <p className="font-serif text-sm text-ink-muted italic leading-relaxed">
                {entry.note}
              </p>
            </li>
          ))}
        </ol>
      ) : null}
    </div>
  );
}

export default ReasoningTrail;
