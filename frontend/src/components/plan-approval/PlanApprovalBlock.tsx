import React, { useState } from "react";
import type { DecisionPoint, DossierFull } from "../../api/types";
import { Card } from "../common/Card";
import { Pill } from "../common/Pill";
import { useResolveDecisionPoint, useStartAgent } from "../../api/hooks";
import { relativeTime } from "../../utils/time";

/**
 * PlanApprovalBlock — the "APPROVE THE PLAN" surface.
 *
 * Day-3 flow: intake seeds a starter `investigation_plan`. The agent, on
 * first turn, flags a `decision_point` with `kind === "plan_approval"`
 * asking the user to approve the drafted plan (or redirect it). The block
 * below is the user's single affordance for that gate.
 *
 * Rendering rules (in priority order):
 *   1. If `dossier.investigation_plan` is null/undefined → render nothing.
 *      (Intake hasn't seeded a plan — not our surface.)
 *   2. If the plan already has `approved_at` set → render a compact,
 *      button-less "Plan approved {relative date}" line. We keep the
 *      breadcrumb on-page so the user remembers how the work was scoped.
 *   3. Plan drafted, unapproved, matching decision_point present → render
 *      the full deliberation: plan rationale, numbered items, Approve +
 *      Redirect buttons. Redirect expands a textarea; submitting sends
 *      `chosen = "Redirect: <text>"`.
 *   4. Plan drafted, unapproved, NO matching decision_point → the agent
 *      hasn't yet reached the gate. Show a quiet "waiting" state with a
 *      Resume button that nudges the agent forward (POST /agent/start).
 *
 * The "matching" decision_point is the most recent UNRESOLVED point where
 * `kind === "plan_approval"`. For backward-compat with dossiers/agents that
 * predate the `kind` field, we fall back to a title regex (contains
 * "approve" or "plan", case-insensitive) — the parallel backend agent is
 * adding `kind` concurrently, so this fallback is temporary but harmless.
 */

export interface PlanApprovalBlockProps {
  dossier: DossierFull;
  /**
   * Optional callback fired after a successful Approve/Redirect resolve.
   * The parent usually doesn't need this (React Query invalidation handles
   * the refetch) but it's here for parents that want to, e.g., scroll the
   * page or focus a sub-element once the gate clears.
   */
  onResolved?: (point: DecisionPoint) => void;
  /**
   * Active work_session_id to attribute the change_log entry to. Optional
   * — the backend defaults to no session if omitted.
   */
  workSessionId?: string;
}

function matchesPlanApproval(point: DecisionPoint): boolean {
  if (point.kind === "plan_approval") return true;
  // Fallback for pre-`kind`-field backends (title heuristic).
  if (point.kind === undefined) {
    const t = point.title.toLowerCase();
    return t.includes("approve") || t.includes("plan");
  }
  return false;
}

function findPlanApprovalPoint(
  points: DecisionPoint[] | undefined,
): DecisionPoint | undefined {
  if (!points || points.length === 0) return undefined;
  const candidates = points.filter(
    (p) => p.resolved_at == null && matchesPlanApproval(p),
  );
  if (candidates.length === 0) return undefined;
  // Most recent first.
  candidates.sort(
    (a, b) =>
      new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );
  return candidates[0];
}

export function PlanApprovalBlock({
  dossier,
  onResolved,
  workSessionId,
}: PlanApprovalBlockProps) {
  const plan = dossier.dossier.investigation_plan;
  const dossierId = dossier.dossier.id;

  // Hooks must be called unconditionally — keep them at the top regardless
  // of which branch renders.
  const [redirectOpen, setRedirectOpen] = useState(false);
  const [redirectNote, setRedirectNote] = useState("");
  const resolver = useResolveDecisionPoint();
  const starter = useStartAgent();

  // Branch 1: no plan → nothing to approve.
  if (!plan) return null;

  // Branch 2: already approved → compact breadcrumb.
  if (plan.approved_at) {
    return (
      <Card className="border-l-4 border-l-state-confident">
        <div className="flex items-center justify-between gap-4">
          <p className="font-serif text-sm text-ink">
            <span className="font-mono text-xs uppercase tracking-wide text-state-confident mr-2">
              Plan approved
            </span>
            <span className="text-ink-muted">
              {relativeTime(plan.approved_at)}
            </span>
          </p>
          {plan.revision_count > 0 ? (
            <span className="text-xs text-ink-faint font-mono shrink-0">
              revised {plan.revision_count}×
            </span>
          ) : null}
        </div>
      </Card>
    );
  }

  const point = findPlanApprovalPoint(dossier.decision_points);

  // Branch 4: plan drafted but agent hasn't flagged the gate yet.
  if (!point) {
    return (
      <Card className="border-l-4 border-l-rule-strong">
        <div className="flex items-center justify-between gap-3 mb-3">
          <Pill variant="default" className="uppercase tracking-wide">
            PLAN DRAFTED
          </Pill>
          <span className="text-xs text-ink-faint font-mono">
            {relativeTime(plan.drafted_at)}
          </span>
        </div>
        <p className="font-serif text-base text-ink-muted leading-relaxed">
          Waiting for the agent to request approval.
        </p>
        <div className="mt-4 flex items-center justify-end gap-3">
          {starter.isError ? (
            <span className="text-xs text-state-blocked font-sans">
              Couldn't resume — try again.
            </span>
          ) : null}
          <button
            type="button"
            onClick={() => {
              if (starter.isPending) return;
              starter.mutate({ dossierId });
            }}
            disabled={starter.isPending}
            className="border border-rule rounded px-4 py-2 font-sans text-sm text-ink hover:bg-surface-sunk transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {starter.isPending ? "Resuming…" : "Resume"}
          </button>
        </div>
      </Card>
    );
  }

  // Branch 3: the full deliberation surface.
  const trimmed = redirectNote.trim();
  const canSubmitRedirect = trimmed.length > 0 && !resolver.isPending;
  const pendingChoice =
    resolver.isPending && resolver.variables ? resolver.variables.chosen : null;
  const approvePending = pendingChoice === "Approve";
  const redirectPending =
    pendingChoice !== null && pendingChoice !== "Approve";

  function resolveWith(chosen: string) {
    if (resolver.isPending) return;
    resolver.mutate(
      {
        dossierId,
        decisionPointId: point!.id,
        chosen,
        workSessionId,
      },
      {
        onSuccess: (resolved) => {
          setRedirectOpen(false);
          setRedirectNote("");
          onResolved?.(resolved);
        },
      },
    );
  }

  function handleApprove() {
    resolveWith("Approve");
  }

  function handleRedirectSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmitRedirect) return;
    resolveWith(`Redirect: ${trimmed}`);
  }

  return (
    <Card className="border-l-4 border-l-accent">
      <div className="flex items-center justify-between gap-3 mb-4">
        <Pill variant="accent" className="uppercase tracking-wide">
          APPROVE THE PLAN
        </Pill>
        <span className="text-xs text-ink-faint font-mono">
          drafted {relativeTime(plan.drafted_at)}
        </span>
      </div>

      <p className="text-lg font-serif text-ink leading-relaxed">
        {point.title}
      </p>

      {plan.rationale ? (
        <p className="mt-3 italic text-ink-muted font-serif leading-relaxed">
          {plan.rationale}
        </p>
      ) : null}

      {plan.items.length > 0 ? (
        <ol className="mt-6 space-y-5 list-none pl-0">
          {plan.items.map((item, idx) => (
            <li key={item.id} className="flex gap-4">
              <span className="font-serif text-ink-faint text-base shrink-0 w-6 text-right pt-0.5">
                {idx + 1}.
              </span>
              <div className="flex-1 min-w-0">
                <p className="font-serif font-semibold text-ink leading-snug">
                  {item.question}
                  {item.as_sub_investigation ? (
                    <span className="ml-2 font-mono text-[10px] uppercase tracking-wide text-accent bg-accent-bg border border-rule rounded px-1.5 py-0.5 align-middle">
                      sub-investigation
                    </span>
                  ) : null}
                </p>
                {item.rationale ? (
                  <p className="mt-1 italic text-ink-muted font-serif text-sm leading-relaxed">
                    {item.rationale}
                  </p>
                ) : null}
                {item.expected_sources && item.expected_sources.length > 0 ? (
                  <ul className="mt-2 space-y-0.5">
                    {item.expected_sources.map((src, sidx) => (
                      <li
                        key={`${item.id}-src-${sidx}`}
                        className="font-mono text-xs text-ink-faint"
                      >
                        <span className="text-ink-faint mr-1.5">·</span>
                        {src}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            </li>
          ))}
        </ol>
      ) : null}

      {/* Action row: Approve (primary) + Redirect (secondary). */}
      {!redirectOpen ? (
        <div className="mt-8 flex items-center justify-end gap-3">
          {resolver.isError ? (
            <span className="text-xs text-state-blocked font-sans">
              Couldn't record that — try again.
            </span>
          ) : null}
          <button
            type="button"
            onClick={() => setRedirectOpen(true)}
            disabled={resolver.isPending}
            className="border border-rule rounded px-4 py-2 font-sans text-sm text-ink hover:bg-surface-sunk transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Redirect
          </button>
          <button
            type="button"
            onClick={handleApprove}
            disabled={resolver.isPending}
            className="bg-accent text-paper font-sans text-sm rounded px-5 py-2 hover:bg-accent-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {approvePending ? "Approving…" : "Approve"}
          </button>
        </div>
      ) : (
        <form onSubmit={handleRedirectSubmit} className="mt-8">
          <label className="block font-mono text-xs uppercase tracking-wide text-ink-faint mb-2">
            What would you change?
          </label>
          <AutoGrowTextarea
            value={redirectNote}
            onChange={setRedirectNote}
            disabled={resolver.isPending}
            placeholder="Tell the agent what to adjust…"
          />
          <div className="mt-4 flex items-center justify-end gap-3">
            {resolver.isError ? (
              <span className="text-xs text-state-blocked font-sans">
                Couldn't send — try again.
              </span>
            ) : null}
            <button
              type="button"
              onClick={() => {
                if (resolver.isPending) return;
                setRedirectOpen(false);
                setRedirectNote("");
              }}
              disabled={resolver.isPending}
              className="font-sans text-sm text-ink-muted hover:text-ink transition-colors disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!canSubmitRedirect}
              className="bg-accent text-paper font-sans text-sm rounded px-5 py-2 hover:bg-accent-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {redirectPending ? "Sending…" : "Send redirect"}
            </button>
          </div>
        </form>
      )}
    </Card>
  );
}

/**
 * AutoGrowTextarea — resizes to fit its content on every change. We use the
 * "set to auto, read scrollHeight, set to scrollHeight" trick so the
 * textarea shrinks as well as grows. Kept local to this module since no
 * other surface currently needs it.
 */
function AutoGrowTextarea({
  value,
  onChange,
  disabled,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
  placeholder?: string;
}) {
  const ref = React.useRef<HTMLTextAreaElement | null>(null);

  React.useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }, [value]);

  return (
    <textarea
      ref={ref}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
      placeholder={placeholder}
      rows={3}
      aria-label="Redirect note"
      className="w-full font-serif text-base leading-relaxed bg-surface border border-rule rounded px-3 py-2 text-ink placeholder:text-ink-faint focus:outline-none focus:border-accent resize-none overflow-hidden disabled:opacity-60"
    />
  );
}

export default PlanApprovalBlock;
