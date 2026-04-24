import type {
  ChangeLogEntry,
  SessionSummary,
  WorkSession,
  WorkSessionTrigger,
} from "../../api/types";
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
 *
 * When a matching SessionSummary row exists for a session (keyed by
 * session_id === work_session.id) and has a non-empty `summary`, we expand
 * the session block with a short serif-prose summary plus bulleted lists
 * for confirmed / ruled_out / blocked_on and an optional "Next" line.
 * Sessions without a summary (or with an empty one — the runtime fallback
 * row) fall back to the compact line-only view.
 */

interface SessionsSummaryProps {
  workSessions: WorkSession[];
  entries: ChangeLogEntry[];
  lastVisitedAt?: string | null;
  /** Optional — if omitted or empty, every session renders compact-only. */
  summaries?: SessionSummary[];
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

interface BulletListProps {
  label: string;
  items: string[];
}

function BulletList({ label, items }: BulletListProps) {
  if (items.length === 0) return null;
  return (
    <div className="mt-1.5">
      <div className="font-mono text-[10px] uppercase tracking-[0.1em] text-ink-faint">
        {label}
      </div>
      <ul className="list-none p-0 m-0 mt-0.5 space-y-0.5">
        {items.map((item, i) => (
          <li
            key={i}
            className="font-serif text-[12.5px] text-ink-muted leading-snug pl-3 relative before:content-['·'] before:absolute before:left-0 before:text-ink-faint"
          >
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function SessionsSummary({
  workSessions,
  entries,
  lastVisitedAt,
  summaries,
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

  // Index summaries by session_id for O(1) lookup.
  const summaryBySession = new Map<string, SessionSummary>();
  if (summaries) {
    for (const s of summaries) {
      summaryBySession.set(s.session_id, s);
    }
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
      <ol className="list-none p-0 m-0 space-y-3">
        {relevant.map((ws) => {
          const count = entryCountsBySession.get(ws.id) ?? 0;
          const trigger = TRIGGER_LABEL[ws.trigger] ?? ws.trigger;
          const duration = formatDuration(ws.started_at, ws.ended_at);
          const isActive = !ws.ended_at;
          const summary = summaryBySession.get(ws.id);
          const hasExpansion =
            summary !== undefined &&
            (summary.summary.trim().length > 0 ||
              summary.confirmed.length > 0 ||
              summary.ruled_out.length > 0 ||
              summary.blocked_on.length > 0 ||
              (summary.questions_advanced?.length ?? 0) > 0 ||
              !!summary.recommended_next_action);
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
              {hasExpansion && summary ? (
                <div className="mt-1.5 pl-0">
                  {summary.summary.trim().length > 0 ? (
                    <p className="font-serif text-[13px] text-ink leading-snug">
                      {summary.summary}
                    </p>
                  ) : null}
                  <BulletList label="Confirmed" items={summary.confirmed} />
                  <BulletList label="Ruled out" items={summary.ruled_out} />
                  <BulletList label="Blocked on" items={summary.blocked_on} />
                  {summary.questions_advanced && summary.questions_advanced.length > 0 ? (
                    <div className="mt-1.5">
                      <div className="font-mono text-[10px] uppercase tracking-[0.1em] text-ink-faint">
                        Questions advanced
                      </div>
                      <div className="mt-0.5 flex flex-wrap gap-1">
                        {summary.questions_advanced.map((id) => (
                          <code
                            key={id}
                            className="font-mono text-[10px] text-ink-muted bg-paper-dark px-1.5 py-0.5 rounded"
                          >
                            {id}
                          </code>
                        ))}
                      </div>
                    </div>
                  ) : null}
                  {summary.recommended_next_action ? (
                    <div className="mt-1.5">
                      <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-ink-faint mr-1.5">
                        Next
                      </span>
                      <span className="font-serif text-[12.5px] text-ink-muted leading-snug">
                        {summary.recommended_next_action}
                      </span>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </li>
          );
        })}
      </ol>
    </section>
  );
}

export default SessionsSummary;
