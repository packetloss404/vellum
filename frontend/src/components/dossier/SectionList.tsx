import React, { useState } from "react";
import type { Section } from "../../api/types";
import { Pill } from "../common/Pill";
import { truncate } from "../../utils/format";
import { relativeTime } from "../../utils/time";

/**
 * SectionList — the read-only section browser on the day-3 detail page.
 *
 * Day 3 is a functional scaffold: each row shows title + state + a
 * truncated content preview; clicking expands the row to reveal the
 * full content in a pre-wrap block. Day 4 replaces this with a proper
 * typeset renderer.
 *
 * Ordered by Section.order (float; fractional values used for mid-list
 * inserts — stable sort is fine).
 */

export interface SectionListProps {
  sections: Section[];
}

const PREVIEW_LEN = 200;

function SectionRow({ section }: { section: Section }) {
  const [expanded, setExpanded] = useState(false);
  const hasContent = (section.content ?? "").trim().length > 0;
  const preview = hasContent ? truncate(section.content, PREVIEW_LEN) : "";
  const chevron = expanded ? "▾" : "▸";

  return (
    <li className="border-t border-rule pt-5 first:border-t-0 first:pt-0">
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        aria-expanded={expanded}
        className="w-full text-left group"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span
                aria-hidden="true"
                className="font-mono text-xs w-3 inline-block text-ink-faint"
              >
                {chevron}
              </span>
              <h3 className="font-serif text-lg text-ink leading-snug group-hover:text-accent transition-colors">
                {section.title}
              </h3>
            </div>
            <div className="mt-1 pl-5 text-xs font-mono text-ink-faint flex flex-wrap items-center gap-x-2">
              <span>{section.type.replace(/_/g, " ")}</span>
              <span aria-hidden="true">·</span>
              <span>{relativeTime(section.last_updated)}</span>
            </div>
          </div>
          <Pill variant="state" state={section.state}>
            {section.state}
          </Pill>
        </div>
      </button>

      {!expanded && hasContent ? (
        <p className="mt-2 pl-5 text-sm font-serif text-ink-muted leading-relaxed">
          {preview}
        </p>
      ) : null}

      {expanded ? (
        <div className="mt-3 pl-5">
          {hasContent ? (
            <pre className="font-serif text-base text-ink leading-relaxed whitespace-pre-wrap m-0">
              {section.content}
            </pre>
          ) : (
            <p className="italic text-ink-faint font-serif">(no content yet)</p>
          )}
        </div>
      ) : null}
    </li>
  );
}

export function SectionList({ sections }: SectionListProps) {
  if (!sections || sections.length === 0) return null;

  const ordered = [...sections].sort((a, b) => a.order - b.order);

  return (
    <section className="space-y-4">
      <h2 className="font-mono text-xs uppercase tracking-wide text-ink-faint">
        Sections ({sections.length})
      </h2>
      <ul className="space-y-5 list-none p-0 m-0">
        {ordered.map((s) => (
          <SectionRow key={s.id} section={s} />
        ))}
      </ul>
    </section>
  );
}

export default SectionList;
