import { useState } from "react";
import type { WorkingTheory, WorkingTheoryConfidence } from "../../api/types";
import { relativeTime } from "../../utils/time";

/**
 * WorkingTheoryBlock — the "if you had to decide right now, here's what I
 * think" block. Sits between the Hero and the Debrief.
 *
 * Collapsed by default when present: heading + recommendation + confidence
 * pill. Expanding shows `why` and `what_would_change_it`.
 *
 * When no theory is set yet, we render a subtle empty-state prompt so the
 * user knows the surface exists but the agent hasn't populated it —
 * keeping the page quiet rather than plastering a loud "no theory yet"
 * card.
 */

interface Props {
  theory?: WorkingTheory | null;
}

const CONFIDENCE_TONE: Record<
  WorkingTheoryConfidence,
  { pipClass: string; labelClass: string }
> = {
  high: {
    pipClass: "bg-state-confident",
    labelClass: "text-state-confident",
  },
  medium: {
    pipClass: "bg-state-provisional",
    labelClass: "text-state-provisional",
  },
  low: {
    pipClass: "bg-state-blocked",
    labelClass: "text-state-blocked",
  },
};

function ConfidencePill({ confidence }: { confidence: WorkingTheoryConfidence }) {
  const tone = CONFIDENCE_TONE[confidence];
  return (
    <span className="inline-flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.08em]">
      <span
        aria-hidden="true"
        className={`inline-block h-2 w-2 rounded-full ${tone.pipClass}`}
      />
      <span className={tone.labelClass}>{confidence} confidence</span>
    </span>
  );
}

function EmptyState() {
  return (
    <section aria-label="Working theory">
      <div className="border-l-2 border-rule pl-4 py-2">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.12em] text-ink-faint m-0">
          Current working theory
        </h2>
        <p className="mt-1 font-serif italic text-sm text-ink-muted leading-relaxed m-0">
          The agent hasn&rsquo;t formed one yet. It appears here once the
          agent has a tentative direction — typically after plan approval.
        </p>
      </div>
    </section>
  );
}

export function WorkingTheoryBlock({ theory }: Props) {
  const [expanded, setExpanded] = useState(false);
  if (!theory) return <EmptyState />;

  return (
    <section
      aria-label="Working theory"
      className="border-l-2 border-accent pl-4 py-1"
    >
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.12em] text-ink-faint m-0">
          Current working theory
        </h2>
        <time
          dateTime={theory.updated_at}
          className="font-mono text-[11px] text-ink-faint shrink-0"
          title={new Date(theory.updated_at).toLocaleString()}
        >
          {relativeTime(theory.updated_at)}
        </time>
      </div>
      <p className="mt-2 font-serif text-lg text-ink leading-snug m-0">
        {theory.recommendation}
      </p>
      <div className="mt-2 flex items-center gap-4">
        <ConfidencePill confidence={theory.confidence} />
        <button
          type="button"
          onClick={() => setExpanded((e) => !e)}
          aria-expanded={expanded}
          className="font-mono text-[11px] text-ink-faint hover:text-accent transition-colors"
        >
          {expanded ? "hide reasoning" : "show reasoning"}
        </button>
      </div>
      {expanded ? (
        <div className="mt-4 space-y-3 max-w-prose">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-ink-faint mb-1">
              Why this is the current theory
            </div>
            <p className="font-serif text-sm text-ink leading-relaxed m-0">
              {theory.why}
            </p>
          </div>
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-ink-faint mb-1">
              What would change it
            </div>
            <p className="font-serif text-sm text-ink leading-relaxed m-0">
              {theory.what_would_change_it}
            </p>
          </div>
          {theory.unresolved_assumptions && theory.unresolved_assumptions.length > 0 ? (
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-ink-faint mb-1">
                Unresolved assumptions
              </div>
              <ul className="list-none p-0 m-0 space-y-0.5">
                {theory.unresolved_assumptions.map((a, i) => (
                  <li
                    key={i}
                    className="font-serif text-sm text-ink-muted leading-relaxed pl-3 relative before:content-['·'] before:absolute before:left-0 before:text-ink-faint"
                  >
                    {a}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

export default WorkingTheoryBlock;
