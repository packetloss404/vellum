import type { ResearchRun } from "../../api/types";
import { relativeTime } from "../../utils/time";

function money(value: number) {
  return value > 0 ? `$${value.toFixed(2)}` : "—";
}

export function ResearchTimeline({
  runs,
  selectedRunId,
  onSelect,
}: {
  runs: ResearchRun[];
  selectedRunId?: string;
  onSelect?: (runId: string) => void;
}) {
  if (runs.length === 0) {
    return <p className="font-serif text-sm text-ink-faint">No research runs yet.</p>;
  }
  return (
    <ol className="space-y-2" aria-label="Research run history">
      {runs.map((run) => (
        <li key={run.id}>
          <button
            type="button"
            onClick={() => onSelect?.(run.id)}
            aria-pressed={selectedRunId === run.id}
            className={`w-full rounded border bg-paper px-3 py-2 text-left ${
              selectedRunId === run.id ? "border-accent" : "border-rule"
            }`}
          >
          <div className="flex items-baseline justify-between gap-3">
            <span className="font-mono text-[11px] uppercase tracking-wide text-ink">
              {run.depth} · {run.status.replace(/_/g, " ")}
            </span>
            <time className="font-mono text-[10px] text-ink-faint" dateTime={run.started_at}>
              {relativeTime(run.started_at)}
            </time>
          </div>
          <div className="mt-1 font-serif text-xs text-ink-muted">
            {run.sessions_started} session{run.sessions_started === 1 ? "" : "s"} · {money(run.cost_usd)}
            {run.stop_reason ? ` · ${run.stop_reason.replace(/_/g, " ")}` : ""}
          </div>
          </button>
        </li>
      ))}
    </ol>
  );
}
