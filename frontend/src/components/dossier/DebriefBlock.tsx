import React from "react";
import type { Debrief } from "../../api/types";
import { relativeTime } from "../../utils/time";

/**
 * DebriefBlock — the two-minute "here's what I did, here's what I found"
 * block that lives immediately under the hero.
 *
 * Visual choice: no card fill, horizontal rules top and bottom. The debrief
 * reads like a printed case-file summary page — paper shows through, the
 * rules frame it. Four labeled fields (mono small-caps labels, serif
 * body), each generous enough to be read at a glance.
 *
 * Empty policy:
 *   - `debrief === null | undefined` → fine-print "hasn't posted" note.
 *   - debrief exists but all four fields blank → same fine-print note.
 *   - individual empty field → muted em-dash under the label (we keep
 *     the label so the shape of the four-field debrief is legible).
 */

export interface DebriefBlockProps {
  debrief?: Debrief | null;
}

const EMPTY = "—";

const FIELDS: Array<{ key: keyof Debrief; label: string }> = [
  { key: "what_i_did", label: "What I did" },
  { key: "what_i_found", label: "What I found" },
  { key: "what_you_should_do_next", label: "What you should do next" },
  { key: "what_i_couldnt_figure_out", label: "What I couldn't figure out" },
];

function valueFor(debrief: Debrief, key: keyof Debrief): string {
  const raw = debrief[key];
  if (typeof raw !== "string") return EMPTY;
  const trimmed = raw.trim();
  return trimmed.length > 0 ? trimmed : EMPTY;
}

function EmptyNote() {
  return (
    <div className="border-y border-rule py-4">
      <p className="font-mono text-xs text-ink-faint">
        The agent hasn&apos;t posted a debrief yet.
      </p>
    </div>
  );
}

export function DebriefBlock({ debrief }: DebriefBlockProps) {
  if (!debrief) {
    return <EmptyNote />;
  }

  const anyPopulated = FIELDS.some(
    ({ key }) =>
      typeof debrief[key] === "string" &&
      (debrief[key] as string).trim().length > 0,
  );
  if (!anyPopulated) {
    return <EmptyNote />;
  }

  return (
    <section className="border-y border-rule py-8">
      <dl className="space-y-7">
        {FIELDS.map(({ key, label }) => {
          const value = valueFor(debrief, key);
          const isEmpty = value === EMPTY;
          return (
            <div key={key}>
              <dt className="font-sans text-[11px] uppercase tracking-[0.14em] text-ink-faint mb-2">
                {label}
              </dt>
              <dd
                className={
                  isEmpty
                    ? "font-serif text-lg text-ink-faint"
                    : "font-serif text-lg text-ink leading-relaxed whitespace-pre-wrap"
                }
              >
                {value}
              </dd>
            </div>
          );
        })}
      </dl>
      {debrief.last_updated ? (
        <p className="mt-8 font-mono text-[11px] text-ink-faint">
          Last updated {relativeTime(debrief.last_updated)}
        </p>
      ) : null}
    </section>
  );
}

export default DebriefBlock;
