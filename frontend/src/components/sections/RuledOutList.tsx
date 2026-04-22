import React, { useState } from "react";
import type { RuledOut } from "../../api/types";

/**
 * RuledOutList — a collapsible, lightweight ledger of things the agent
 * has eliminated from consideration. Collapsed by default; expanding
 * reveals a compact strikethrough list with terse reasons.
 */

export interface RuledOutListProps {
  ruledOut: RuledOut[];
}

export function RuledOutList({ ruledOut }: RuledOutListProps) {
  const [expanded, setExpanded] = useState(false);

  if (!ruledOut || ruledOut.length === 0) {
    return null;
  }

  const chevron = expanded ? "▾" : "▸";

  return (
    <div className="border-t border-rule pt-4">
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        aria-expanded={expanded}
        aria-label="Toggle ruled-out list"
        className="flex items-center gap-2 text-sm font-mono uppercase tracking-wide text-ink-muted hover:text-ink transition-colors"
      >
        <span aria-hidden="true" className="font-mono text-xs w-3 inline-block">
          {chevron}
        </span>
        <span>Ruled out ({ruledOut.length})</span>
      </button>

      {expanded ? (
        <ul className="mt-4 space-y-3 list-none">
          {ruledOut.map((item) => (
            <li key={item.id} className="font-serif">
              <s className="text-ink-muted">{item.subject}</s>
              <div className="text-sm text-ink-muted pl-4 mt-0.5">
                {item.reason}
              </div>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export default RuledOutList;
