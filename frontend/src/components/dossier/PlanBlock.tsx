import React from "react";
import type { InvestigationPlan } from "../../api/types";
import { Card } from "../common/Card";
import { Pill } from "../common/Pill";

/**
 * PlanBlock — renders the agent's investigation plan.
 *
 * If the plan is unapproved we show a quiet "awaiting approval" banner
 * and a <div data-slot="plan-approval" /> where another agent's approval
 * component mounts. We never render approve/redirect UI ourselves — that
 * belongs to the plan-approval owner.
 *
 * Status pill colors piggy-back on the existing section-state palette:
 *   planned     → provisional
 *   in_progress → provisional
 *   completed   → confident
 *   abandoned   → blocked
 */

export interface PlanBlockProps {
  plan?: InvestigationPlan | null;
}

type PlanStatus = "planned" | "in_progress" | "completed" | "abandoned";

function statusPillState(
  status: PlanStatus,
): "confident" | "provisional" | "blocked" {
  switch (status) {
    case "completed":
      return "confident";
    case "abandoned":
      return "blocked";
    default:
      return "provisional";
  }
}

export function PlanBlock({ plan }: PlanBlockProps) {
  if (!plan) return null;
  if (!plan.items || plan.items.length === 0) return null;

  const approved = !!plan.approved_at;

  return (
    <Card className="space-y-5">
      <div className="flex items-center justify-between gap-3">
        <h2 className="font-mono text-xs uppercase tracking-wide text-ink-faint">
          Investigation plan
        </h2>
        {approved ? (
          <Pill variant="accent">approved</Pill>
        ) : (
          <Pill variant="attention">awaiting approval</Pill>
        )}
      </div>

      {!approved ? (
        <>
          <p className="text-sm font-serif italic text-ink-muted">
            Plan drafted — awaiting approval.
          </p>
          {/* Mount point for the plan-approval component owned by another agent. */}
          <div data-slot="plan-approval" />
        </>
      ) : null}

      {plan.rationale && plan.rationale.trim().length > 0 ? (
        <p className="font-serif text-base text-ink-muted leading-relaxed whitespace-pre-wrap">
          {plan.rationale}
        </p>
      ) : null}

      <ol className="space-y-4 list-none p-0 m-0">
        {plan.items.map((item, idx) => {
          const status = item.status as PlanStatus;
          return (
            <li
              key={item.id}
              className="border-t border-rule pt-4 first:border-t-0 first:pt-0"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="font-serif text-base text-ink leading-snug">
                    <span className="font-mono text-xs text-ink-faint mr-2">
                      {String(idx + 1).padStart(2, "0")}
                    </span>
                    {item.question}
                  </div>
                  {item.rationale && item.rationale.trim().length > 0 ? (
                    <p className="mt-1 text-sm font-serif text-ink-muted leading-relaxed">
                      {item.rationale}
                    </p>
                  ) : null}
                </div>
                <div className="shrink-0 pt-0.5 flex flex-col items-end gap-1">
                  <Pill variant="state" state={statusPillState(status)}>
                    {status.replace(/_/g, " ")}
                  </Pill>
                  {item.as_sub_investigation ? (
                    <span className="text-[10px] font-mono uppercase tracking-wide text-ink-faint">
                      sub-investigation
                    </span>
                  ) : null}
                </div>
              </div>
              {item.expected_sources && item.expected_sources.length > 0 ? (
                <div className="mt-2 text-xs font-mono text-ink-faint">
                  expects: {item.expected_sources.join(", ")}
                </div>
              ) : null}
            </li>
          );
        })}
      </ol>
    </Card>
  );
}

export default PlanBlock;
