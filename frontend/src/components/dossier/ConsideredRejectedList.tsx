import React from "react";
import type { ConsideredAndRejected } from "../../api/types";

/**
 * ConsideredRejectedList — the "paths we considered but didn't take"
 * ledger. Renders each entry as three short fields (path, why_compelling,
 * why_rejected) so the user can see how the agent reasoned its way out
 * of each branch.
 *
 * Day-3 scaffold; no collapse, no filter.
 */

export interface ConsideredRejectedListProps {
  items: ConsideredAndRejected[];
}

export function ConsideredRejectedList({
  items,
}: ConsideredRejectedListProps) {
  if (!items || items.length === 0) return null;

  return (
    <section className="space-y-4">
      <h2 className="font-mono text-xs uppercase tracking-wide text-ink-faint">
        Considered and rejected ({items.length})
      </h2>
      <ul className="space-y-6 list-none p-0 m-0">
        {items.map((item) => (
          <li
            key={item.id}
            className="border-t border-rule pt-4 first:border-t-0 first:pt-0"
          >
            <div className="font-serif text-base text-ink leading-snug">
              <s className="text-ink-muted">{item.path}</s>
            </div>
            <dl className="mt-2 space-y-2">
              {item.why_compelling && item.why_compelling.trim().length > 0 ? (
                <div>
                  <dt className="font-mono text-xs uppercase tracking-wide text-ink-faint">
                    Why it was compelling
                  </dt>
                  <dd className="mt-0.5 font-serif text-sm text-ink-muted leading-relaxed">
                    {item.why_compelling}
                  </dd>
                </div>
              ) : null}
              {item.why_rejected && item.why_rejected.trim().length > 0 ? (
                <div>
                  <dt className="font-mono text-xs uppercase tracking-wide text-ink-faint">
                    Why it was rejected
                  </dt>
                  <dd className="mt-0.5 font-serif text-sm text-ink-muted leading-relaxed">
                    {item.why_rejected}
                  </dd>
                </div>
              ) : null}
            </dl>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default ConsideredRejectedList;
