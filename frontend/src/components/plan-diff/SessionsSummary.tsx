import type { ChangeLogEntry, WorkSession, WorkSessionTrigger } from "../../api/types";
import { relativeTime } from "../../utils/time";

/**
 * SessionsSummary — a compact "what did each work session do since you were
 * here" block that sits ABOVE the category-grouped change list in the
 * plan-diff sidebar. The category view stays the primary scan surface; this
 * gives the user the durable-thinking framing ("three sessions overnight,
 * one woke at 2am and one when I resolved the needs_input, total $0.42").
 *
 * Sessions shown: every WorkSession whose started_at falls after
 * lastVisitedAt, in ascending time order. If the user has never visited
 * before, all sessions appear.
 */

interface SessionsSummaryProps {
  workSessions: WorkSession[];
  entries: ChangeLogEntry[];
  lastVisitedAt?: string | null;
}

const TRIGGER_LABEL: Record<WorkSessionTrigger, string> = {
  user_open: "User opened",
  scheduled: "Scheduled wake",
  reactive: "Reactive wake",
  resume: "Resumed",
  intake: "Intake",
  manual: "Manual",
};

function formatDollars(cost: number | undefined): string {
  if (!cost || cost <= 0) return "—";
  if (cost < 0.01) return "<$0.01";
  return `$${cost.toFixed(2)}`;
}

function formatDuration(startIso: string, endIso?: string | null): string {
  const start = new Date(startIso).getTime();
  const end = endIso ? new Date(endIso).getTime() : Date.now();
  const mins = Math.max(0, Math.round((end - start) / 60000));
  if (mins < 1) return "<1m";
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  const rem = mins % 60;
  return rem > 0 ? `${hours}h${rem}m` : `${hours}h`;
}

export function SessionsSummary({
  workSessions,
  entries,
  lastVisitedAt,
}: SessionsSummaryProps) {
  // Sessions to show: everything that started at or after lastVisitedAt.
  // A first-visit (lastVisitedAt === null) still collects the sessions,
  // since the user wants to see what the agent did even on first arrival.
  const threshold = lastVisitedAt ? new Date(lastVisitedAt).getTime() : 0;
  const relevant = workSessions
    .filter(
      (ws) =>
        !ws.started_at || new Date(ws.started_at).getTime() >= threshold,
    )
    .sort(
      (a, b) =>
        new Date(a.started_at).getTime() - new Date(b.started_at).getTime(),
    );

  if (relevant.length === 0) return null;

  const entryCountsBySession = new Map<string, number>();
  for (const e of entries) {
    entryCountsBySession.set(
      e.work_session_id,
      (entryCountsBySession.get(e.work_session_id) ?? 0) + 1,
    );
  }

  const totalCost = relevant.reduce(
    (sum, ws) => sum + (ws.cost_usd ?? 0),
    0,
  );

  return (
    <section aria-label="Sessions since your last visit" className="mb-6">
      <h3 className="font-mono text-[10px] uppercase tracking-[0.12em] text-ink-faint mb-2">
        Sessions {relevant.length > 1 ? `(${relevant.length})` : ""}
        {totalCost > 0 ? (
          <span className="text-ink-muted normal-case tracking-normal ml-2">
            total {formatDollars(totalCost)}
          </span>
        ) : null}
      </h3>
      <ol className="list-none p-0 m-0 space-y-2">
        {relevant.map((ws) => {
          const count = entryCountsBySession.get(ws.id) ?? 0;
          const trigger = TRIGGER_LABEL[ws.trigger] ?? ws.trigger;
          const duration = formatDuration(ws.started_at, ws.ended_at);
          const isActive = !ws.ended_at;
          return (
            <li
              key={ws.id}
              className="font-mono text-[11px] text-ink-muted leading-snug"
            >
              <div className="flex items-baseline justify-between gap-2">
                <span className="truncate">
                  <span className="text-ink">{trigger}</span>
                  <span className="text-ink-faint"> · </span>
                  {duration}
                  {isActive ? (
                    <span className="text-attention ml-1">· running</span>
                  ) : null}
                </span>
                <time
                  dateTime={ws.started_at}
                  className="text-ink-faint shrink-0"
                  title={new Date(ws.started_at).toLocaleString()}
                >
                  {relativeTime(ws.started_at)}
                </time>
              </div>
              <div className="flex items-baseline justify-between gap-2 mt-0.5">
                <span className="text-ink-faint">
                  {count} change{count === 1 ? "" : "s"}
                  {ws.end_reason && ws.end_reason !== "ended_turn" ? (
                    <>
                      <span> · </span>
                      <span className="text-ink-muted">
                        {ws.end_reason.replace(/_/g, " ")}
                      </span>
                    </>
                  ) : null}
                </span>
                <span className="text-ink-faint shrink-0">
                  {formatDollars(ws.cost_usd)}
                </span>
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

export default SessionsSummary;
