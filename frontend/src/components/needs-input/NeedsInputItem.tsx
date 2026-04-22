import React, { useState } from "react";
import type { NeedsInput } from "../../api/types";
import { Card } from "../common/Card";
import { Pill } from "../common/Pill";
import { useResolveNeedsInput } from "../../api/hooks";
import { relativeTime } from "../../utils/time";

/**
 * NeedsInputItem — the hero "NEEDS YOU" block.
 *
 * An open item renders the agent's question in large serif type with a
 * reply textarea and a single primary action ("Send to dossier"). A
 * resolved item (answered_at set) renders a compact post-mortem with the
 * original question struck through and the user's answer beneath.
 */

export interface NeedsInputItemProps {
  item: NeedsInput;
  dossierId: string;
}

export function NeedsInputItem({ item, dossierId }: NeedsInputItemProps) {
  const resolved = !!item.answered_at;

  // Hooks must be called unconditionally — keep them at the top regardless
  // of the resolved/open branch below.
  const [answer, setAnswer] = useState("");
  const mutation = useResolveNeedsInput();

  if (resolved) {
    return (
      <Card className="border-l-4 border-l-attention">
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            <p className="text-base font-serif text-ink-muted line-through leading-relaxed">
              {item.question}
            </p>
            {item.answer ? (
              <div className="mt-3">
                <div className="text-xs font-mono uppercase tracking-wide text-ink-faint">
                  Your answer:
                </div>
                <p className="mt-1 font-serif text-sm text-ink whitespace-pre-wrap">
                  {item.answer}
                </p>
              </div>
            ) : null}
          </div>
          {item.answered_at ? (
            <span className="text-xs text-ink-faint font-mono shrink-0">
              {relativeTime(item.answered_at)}
            </span>
          ) : null}
        </div>
      </Card>
    );
  }

  const trimmed = answer.trim();
  const canSubmit = trimmed.length > 0 && !mutation.isPending;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    mutation.mutate(
      { dossierId, needsInputId: item.id, answer: trimmed },
      {
        // Keep local state until the parent re-renders without this item.
        // If the mutation fails, the textarea content is preserved so the
        // user can retry without retyping.
        onSuccess: () => setAnswer(""),
      }
    );
  }

  return (
    <Card className="border-l-4 border-l-attention">
      <div className="flex items-center justify-between gap-3 mb-3">
        <Pill variant="attention" className="uppercase tracking-wide">
          NEEDS YOU
        </Pill>
        <span className="text-xs text-ink-faint font-mono">
          {relativeTime(item.created_at)}
        </span>
      </div>

      <p className="text-2xl font-serif text-ink leading-snug">
        {item.question}
      </p>

      <form onSubmit={handleSubmit} className="mt-4">
        <textarea
          value={answer}
          onChange={(e) => setAnswer(e.target.value)}
          rows={3}
          placeholder="Answer in a sentence or two…"
          disabled={mutation.isPending}
          aria-label="Your answer"
          className="w-full font-serif text-base bg-surface border border-rule rounded px-3 py-2 text-ink placeholder:text-ink-faint focus:outline-none focus:border-accent resize-y disabled:opacity-60"
        />

        <div className="mt-3 flex items-center justify-end gap-3">
          {mutation.isError ? (
            <span className="text-xs text-state-blocked font-sans">
              Couldn't send — try again.
            </span>
          ) : null}
          <button
            type="submit"
            disabled={!canSubmit}
            className="bg-accent text-paper font-sans text-sm rounded px-4 py-2 hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {mutation.isPending ? "Sending…" : "Send to dossier"}
          </button>
        </div>
      </form>
    </Card>
  );
}

export default NeedsInputItem;
