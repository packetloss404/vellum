import React from "react";
import type { DecisionPoint, DecisionOption } from "../../api/types";
import { Card } from "../common/Card";
import { Pill } from "../common/Pill";
import { useResolveDecisionPoint } from "../../api/hooks";
import { relativeTime } from "../../utils/time";

/**
 * DecisionPointItem — a "DECIDE" block. The agent presents a pivot point
 * with 2+ options (one optionally `recommended`) and a short take. The
 * user resolves it by clicking an option card; we send `chosen = label`.
 *
 * Once resolved, collapses to a one-line "Decided: X" summary.
 */

export interface DecisionPointItemProps {
  item: DecisionPoint;
  dossierId: string;
}

export function DecisionPointItem({ item, dossierId }: DecisionPointItemProps) {
  const resolved = !!item.resolved_at;
  const mutation = useResolveDecisionPoint();

  if (resolved) {
    return (
      <Card className="border-l-4 border-l-accent">
        <div className="flex items-center justify-between gap-4">
          <div className="flex-1 min-w-0 font-serif text-sm text-ink-muted truncate">
            <span className="text-ink">{item.title}</span>
            {item.chosen ? (
              <>
                <span className="mx-2 text-ink-faint">·</span>
                <span className="text-ink">Decided: {item.chosen}</span>
              </>
            ) : null}
          </div>
          {item.resolved_at ? (
            <span className="text-xs text-ink-faint font-mono shrink-0">
              {relativeTime(item.resolved_at)}
            </span>
          ) : null}
        </div>
      </Card>
    );
  }

  function handleChoose(option: DecisionOption) {
    if (mutation.isPending) return;
    mutation.mutate({
      dossierId,
      decisionPointId: item.id,
      chosen: option.label,
    });
  }

  // Which label is currently being submitted, so we can mute the other
  // options and show a subtle indicator next to the selected one.
  const pendingLabel =
    mutation.isPending && mutation.variables
      ? mutation.variables.chosen
      : null;

  return (
    <Card className="border-l-4 border-l-accent">
      <div className="flex items-center justify-between gap-3 mb-3">
        <Pill variant="attention" className="uppercase tracking-wide">
          DECIDE
        </Pill>
        <span className="text-xs text-ink-faint font-mono">
          {relativeTime(item.created_at)}
        </span>
      </div>

      <p className="text-lg font-serif text-ink leading-relaxed">
        {item.title}
      </p>

      {item.recommendation ? (
        <p className="mt-2 italic text-ink-muted text-sm font-serif">
          <span className="not-italic font-mono text-xs text-ink-faint uppercase tracking-wide mr-1">
            Agent's take:
          </span>
          {item.recommendation}
        </p>
      ) : null}

      <div className="mt-4 space-y-2">
        {item.options.map((option, idx) => {
          const isPending = pendingLabel === option.label;
          return (
            <button
              key={`${option.label}-${idx}`}
              type="button"
              onClick={() => handleChoose(option)}
              disabled={mutation.isPending}
              className="w-full text-left p-4 border border-rule rounded bg-surface hover:bg-surface-sunk transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
            >
              <div className="flex items-center gap-2">
                <div className="font-serif text-base text-ink flex-1">
                  {option.label}
                </div>
                {option.recommended ? (
                  <span className="font-mono text-xs text-accent bg-paper border border-rule rounded px-2 py-0.5">
                    recommended
                  </span>
                ) : null}
                {isPending ? (
                  <span className="font-mono text-xs text-ink-faint">
                    sending…
                  </span>
                ) : null}
              </div>
              <div className="text-sm text-ink-muted mt-1 font-serif">
                {option.implications}
              </div>
            </button>
          );
        })}
      </div>

      {mutation.isError ? (
        <p className="mt-3 text-xs text-state-blocked font-sans">
          Couldn't record that choice — try again.
        </p>
      ) : null}
    </Card>
  );
}

export default DecisionPointItem;
