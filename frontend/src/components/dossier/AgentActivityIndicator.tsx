import { useEffect, useState } from "react";
import { useAgentStatus, useResumeState } from "../../api/hooks";

/**
 * AgentActivityIndicator — a live "what is the agent doing right now" pill.
 *
 * Four stable states, in priority order:
 *
 *   running      agent has an in-flight task in the orchestrator. Pulsing
 *                amber dot. "Researching — 42s" (elapsed from started_at).
 *   waking      scheduler will pick this up on the next tick (wake_pending
 *                true, or wake_at <= now). Steady amber dot. Labels with the
 *                wake reason when known.
 *   scheduled   wake_at is in the future. Quiet neutral dot. "Waking in
 *                2h 14m" counts down in real time.
 *   idle        nothing in flight, nothing pending. Hidden unless
 *                `showIdle` is set — the hero area is busy, and an "idle"
 *                pill right after a user action is noise.
 *
 * Polls every 3s via the two underlying hooks. Doesn't own any fetching of
 * its own. Safe to mount multiple times on a page.
 */

interface Props {
  dossierId: string;
  /** When true, render a muted "idle" pill even with nothing going on.
   *  Defaults to false so quiet dossiers don't carry visual weight. */
  showIdle?: boolean;
}

type IndicatorState = "running" | "waking" | "scheduled" | "idle";

interface Derived {
  state: IndicatorState;
  label: string;
  subLabel?: string;
}

function formatElapsed(sinceIso: string, now: number): string {
  const start = new Date(sinceIso).getTime();
  const secs = Math.max(0, Math.floor((now - start) / 1000));
  if (secs < 60) return `${secs}s`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ${secs % 60}s`;
  const hours = Math.floor(mins / 60);
  return `${hours}h ${mins % 60}m`;
}

function formatCountdown(targetIso: string, now: number): string {
  const target = new Date(targetIso).getTime();
  const secs = Math.max(0, Math.floor((target - now) / 1000));
  if (secs < 60) return `${secs}s`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  const rem = mins % 60;
  return rem > 0 ? `${hours}h ${rem}m` : `${hours}h`;
}

function wakeReasonLabel(reason: string | null | undefined): string {
  switch (reason) {
    case "scheduled":
      return "Waking";
    case "crash_resume":
      return "Resuming after crash";
    case "needs_input_resolved":
      return "Picking up your answer";
    case "decision_resolved":
      return "Picking up your decision";
    default:
      return "Waking";
  }
}

function derive(
  running: boolean,
  startedAt: string | null | undefined,
  wakeAt: string | null | undefined,
  wakePending: boolean,
  wakeReason: string | null | undefined,
  now: number,
): Derived {
  if (running) {
    return {
      state: "running",
      label: "Researching",
      subLabel: startedAt ? formatElapsed(startedAt, now) : undefined,
    };
  }
  // Effective wake-now: wake_pending OR wake_at already past.
  const wakeAtPast =
    wakeAt != null && new Date(wakeAt).getTime() <= now;
  if (wakePending || wakeAtPast) {
    return {
      state: "waking",
      label: wakeReasonLabel(wakeReason),
      subLabel: "within 30s",
    };
  }
  if (wakeAt) {
    return {
      state: "scheduled",
      label: wakeReasonLabel(wakeReason),
      subLabel: `in ${formatCountdown(wakeAt, now)}`,
    };
  }
  return { state: "idle", label: "Idle" };
}

const DOT_CLASS: Record<IndicatorState, string> = {
  running: "bg-attention animate-pulse",
  waking: "bg-attention",
  scheduled: "bg-ink-faint",
  idle: "bg-ink-faint/50",
};

const LABEL_CLASS: Record<IndicatorState, string> = {
  running: "text-attention",
  waking: "text-attention",
  scheduled: "text-ink-muted",
  idle: "text-ink-faint",
};

export function AgentActivityIndicator({ dossierId, showIdle }: Props) {
  const agentStatus = useAgentStatus(dossierId);
  const resumeState = useResumeState(dossierId);

  // Re-render once a second so the elapsed / countdown text ticks even when
  // the underlying queries haven't refetched. useEffect with setInterval is
  // standard; the component unmounts clean up the timer.
  const [tickNow, setTickNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setTickNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);

  const running = !!agentStatus.data?.running;
  const startedAt = agentStatus.data?.started_at ?? null;
  const wakeAt = resumeState.data?.wake_at ?? null;
  const wakePending = resumeState.data?.wake_pending ?? false;
  const wakeReason = resumeState.data?.wake_reason ?? null;

  const d = derive(running, startedAt, wakeAt, wakePending, wakeReason, tickNow);

  if (d.state === "idle" && !showIdle) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className="inline-flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.08em]"
    >
      <span
        aria-hidden="true"
        className={`inline-block w-2 h-2 rounded-full ${DOT_CLASS[d.state]}`}
      />
      <span className={LABEL_CLASS[d.state]}>{d.label}</span>
      {d.subLabel ? (
        <span className="text-ink-faint normal-case tracking-normal">
          {d.subLabel}
        </span>
      ) : null}
    </div>
  );
}

export default AgentActivityIndicator;
