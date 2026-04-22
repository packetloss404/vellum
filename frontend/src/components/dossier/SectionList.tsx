import React, { useMemo } from "react";
import type { Section } from "../../api/types";
import { SectionCard } from "./SectionCard";

/**
 * SectionList — the main analytic body of a dossier: findings,
 * recommendations, evidence, tradeoffs.
 *
 * Day 4: each Section is rendered by SectionCard as a typeset card
 * with state pip + type treatment. Ordered by Section.order (float;
 * mid-list inserts use fractional values — stable sort is fine).
 */

export interface SectionListProps {
  sections: Section[];
}

export function SectionList({ sections }: SectionListProps) {
  const ordered = useMemo(
    () => [...(sections ?? [])].sort((a, b) => a.order - b.order),
    [sections],
  );

  // Build id → title map so depends_on links can render human-readable
  // labels. Computed once per render.
  const titleById = useMemo(() => {
    const m = new Map<string, string>();
    for (const s of sections ?? []) m.set(s.id, s.title);
    return m;
  }, [sections]);

  return (
    <section className="space-y-4">
      <h2 className="font-mono text-xs uppercase tracking-wide text-ink-faint">
        Investigation findings
      </h2>
      {ordered.length === 0 ? (
        <p className="font-serif italic text-ink-muted">
          No sections written yet.
        </p>
      ) : (
        <div className="space-y-10">
          {ordered.map((s) => (
            <SectionCard key={s.id} section={s} titleById={titleById} />
          ))}
        </div>
      )}
    </section>
  );
}

export default SectionList;
