import { useState } from "react";
import type { PremiseChallenge } from "../../api/types";
import { relativeTime } from "../../utils/time";

/**
 * PremiseChallengeBlock — "stop and reconsider" surface. Sits between the
 * Hero and the WorkingTheoryBlock. When the agent has recorded a premise
 * challenge, the dossier opens with this prompt: the original question,
 * a safer reframe, and (on expand) the hidden assumptions, why answering
 * now is risky, and the evidence required before answering.
 *
 * Collapsed by default when present: original_question + safer_reframe +
 * expand toggle. When no challenge is set, renders a subtle empty-state
 * line so the surface is discoverable but quiet.
 *
 * Left-border accent: rusty red (border-state-blocked). This surface
 * means "the framing itself may be wrong" — a harder stop than amber
 * provisional-ness. The blocked token already encodes "stuck, reconsider"
 * in the design system, so it carries the right connotation without
 * shouting.
 */

interface Props {
  challenge?: PremiseChallenge | null;
}

function EmptyState() {
  return (
    <section aria-label="Premise challenge">
      <div className="border-l-2 border-rule pl-4 py-2">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.12em] text-ink-faint m-0">
          Premise challenge
        </h2>
        <p className="mt-1 font-serif italic text-sm text-ink-muted leading-relaxed m-0">
          The agent hasn&rsquo;t recorded a premise challenge yet.
        </p>
      </div>
    </section>
  );
}

export function PremiseChallengeBlock({ challenge }: Props) {
  const [expanded, setExpanded] = useState(false);
  if (!challenge) return <EmptyState />;

  const hasAssumptions =
    challenge.hidden_assumptions && challenge.hidden_assumptions.length > 0;
  const hasEvidence =
    challenge.required_evidence_before_answering &&
    challenge.required_evidence_before_answering.length > 0;
  const hasRiskParagraph =
    !!challenge.why_answering_now_is_risky &&
    challenge.why_answering_now_is_risky.trim().length > 0;

  return (
    <section
      aria-label="Premise challenge"
      className="border-l-2 border-state-blocked pl-4 py-1"
    >
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.12em] text-ink-faint m-0">
          Premise challenge
        </h2>
        <time
          dateTime={challenge.updated_at}
          className="font-mono text-[11px] text-ink-faint shrink-0"
          title={new Date(challenge.updated_at).toLocaleString()}
        >
          {relativeTime(challenge.updated_at)}
        </time>
      </div>
      <p className="mt-2 font-serif text-lg text-ink leading-snug m-0">
        {challenge.original_question}
      </p>
      {challenge.safer_reframe && challenge.safer_reframe.trim().length > 0 ? (
        <p className="mt-2 font-serif italic text-base text-ink-muted leading-snug m-0">
          {challenge.safer_reframe}
        </p>
      ) : null}
      <div className="mt-2 flex items-center gap-4">
        <button
          type="button"
          onClick={() => setExpanded((e) => !e)}
          aria-expanded={expanded}
          className="font-mono text-[11px] text-ink-faint hover:text-accent transition-colors"
        >
          {expanded ? "hide assumptions" : "show assumptions"}
        </button>
      </div>
      {expanded ? (
        <div className="mt-4 space-y-3 max-w-prose">
          {hasAssumptions ? (
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-ink-faint mb-1">
                Hidden assumptions
              </div>
              <ul className="list-disc pl-5 space-y-1 m-0">
                {challenge.hidden_assumptions.map((a, idx) => (
                  <li
                    key={idx}
                    className="font-serif text-sm text-ink leading-relaxed"
                  >
                    {a}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {hasRiskParagraph ? (
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-ink-faint mb-1">
                Why answering now is risky
              </div>
              <p className="font-serif text-sm text-ink leading-relaxed m-0">
                {challenge.why_answering_now_is_risky}
              </p>
            </div>
          ) : null}
          {hasEvidence ? (
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-ink-faint mb-1">
                Required evidence before answering
              </div>
              <ul className="list-disc pl-5 space-y-1 m-0">
                {challenge.required_evidence_before_answering.map((e, idx) => (
                  <li
                    key={idx}
                    className="font-serif text-sm text-ink leading-relaxed"
                  >
                    {e}
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

export default PremiseChallengeBlock;
