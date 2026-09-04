import { useEffect, useMemo, useState } from "react";
import type { ResearchPolicy } from "../../api/types";
import {
  usePauseAutonomousResearch,
  useResearchEvidence,
  useResearchProgress,
  useResearchRuns,
  useRestartAutonomousResearch,
  useResumeAutonomousResearch,
  useSaveResearchPolicy,
  useStartAutonomousResearch,
} from "../../api/hooks";
import { Button } from "../common/Button";
import { EvidenceLedger } from "./EvidenceLedger";
import { ResearchTimeline } from "./ResearchTimeline";

const STANDARD: ResearchPolicy = {
  depth: "standard",
  autonomy_enabled: false,
  max_sessions: 4,
  max_turns_per_session: 20,
  max_cost_usd: 12,
  target_source_count: 20,
  min_primary_sources: 3,
  continuation_delay_minutes: 1,
};

const DEEP: ResearchPolicy = {
  depth: "deep",
  autonomy_enabled: false,
  max_sessions: 10,
  max_turns_per_session: 30,
  max_cost_usd: 30,
  target_source_count: 50,
  min_primary_sources: 8,
  continuation_delay_minutes: 1,
};

const STATUS_LABELS: Record<string, string> = {
  manual: "Manual",
  queued: "Queued",
  running: "Researching",
  waiting_for_user: "Waiting for you",
  pause_requested: "Finishing current call",
  blocked_sleep: "Sleep mode off",
  paused: "Paused",
  completed: "Coverage complete",
  failed: "Failed",
  quarantined: "Needs attention",
  cancelled: "Cancelled",
  superseded: "Replaced",
  cap_reached: "Limit reached",
  delivered: "Delivered",
};

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="font-mono text-[10px] uppercase tracking-wider text-ink-faint">
        {label}
      </div>
      <div className="mt-0.5 font-serif text-sm text-ink">{value}</div>
    </div>
  );
}

function NumberInput({
  label,
  value,
  min,
  step = 1,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  step?: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="block">
      <span className="font-mono text-[10px] uppercase tracking-wider text-ink-faint">
        {label}
      </span>
      <input
        type="number"
        value={value}
        min={min}
        step={step}
        onChange={(event) => onChange(Number(event.target.value))}
        className="mt-1 w-full rounded border border-rule bg-paper px-2 py-1.5 font-mono text-xs text-ink focus:border-accent focus:outline-none"
      />
    </label>
  );
}

export function ResearchControl({
  dossierId,
  delivered = false,
}: {
  dossierId: string;
  delivered?: boolean;
}) {
  const progress = useResearchProgress(dossierId);
  const save = useSaveResearchPolicy();
  const start = useStartAutonomousResearch();
  const pause = usePauseAutonomousResearch();
  const resume = useResumeAutonomousResearch();
  const restart = useRestartAutonomousResearch();
  const runs = useResearchRuns(dossierId);
  const [selectedRunId, setSelectedRunId] = useState<string>();
  const evidenceRunId =
    selectedRunId ?? progress.data?.active_run_id ?? runs.data?.[0]?.id;
  const evidence = useResearchEvidence(dossierId, evidenceRunId);
  const [draft, setDraft] = useState<ResearchPolicy>(STANDARD);

  useEffect(() => {
    if (progress.data?.policy) setDraft(progress.data.policy);
  }, [progress.data?.policy]);

  const dirty = useMemo(() => {
    if (!progress.data) return false;
    const comparableDraft = {
      ...draft,
      autonomy_enabled: progress.data.policy.autonomy_enabled,
    };
    return JSON.stringify(comparableDraft) !== JSON.stringify(progress.data.policy);
  }, [draft, progress.data]);

  if (!progress.data) return null;
  const data = progress.data;
  const enabled = data.policy.autonomy_enabled;
  const busy = save.isPending || start.isPending || pause.isPending || resume.isPending || restart.isPending;
  const error = save.error || start.error || pause.error || resume.error || restart.error;
  const allowed = new Set(
    data.allowed_actions ?? (enabled ? ["pause"] : ["start"]),
  );

  const choosePreset = (policy: ResearchPolicy) =>
    setDraft({ ...policy, autonomy_enabled: enabled });

  return (
    <section className="rounded border border-rule bg-surface px-5 py-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-accent">
            Long research
          </div>
          <h2 className="mt-1 font-serif text-xl text-ink">
            Autonomous evidence gathering
          </h2>
          <p className="mt-1 max-w-2xl font-serif text-sm leading-relaxed text-ink-muted">
            Runs bounded research sessions in the background, preserving the
            dossier between each pass. It pauses for decisions, user facts,
            spend limits, or session limits.
          </p>
        </div>
        <span className="rounded-full border border-rule-strong px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-ink-muted">
          {STATUS_LABELS[data.status] ?? data.status}
        </span>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-4 border-y border-rule py-4 sm:grid-cols-4 lg:grid-cols-6">
        <Metric
          label="Sources"
          value={`${data.unique_source_count} / ${data.policy.target_source_count}`}
        />
        <Metric
          label="Primary"
          value={`${data.primary_source_count} / ${data.policy.min_primary_sources}`}
        />
        <Metric label="Domains" value={String(data.unique_domains)} />
        <Metric
          label="Plan"
          value={`${data.completed_plan_items} / ${data.total_plan_items}`}
        />
        <Metric
          label="Sessions"
          value={`${data.sessions_used} / ${data.policy.max_sessions}`}
        />
        <Metric
          label="Spend"
          value={`$${data.cost_usd.toFixed(2)} / $${data.policy.max_cost_usd.toFixed(2)}`}
        />
      </div>

      <details className="mt-4">
        <summary className="cursor-pointer font-mono text-xs text-ink-muted hover:text-ink">
          Research depth and limits
        </summary>
        <div className="mt-4">
          <div className="grid gap-2 sm:grid-cols-2">
            <Button
              size="sm"
              variant={draft.depth === "standard" ? "primary" : "secondary"}
              onClick={() => choosePreset(STANDARD)}
              disabled={busy || enabled}
            >
              Standard
            </Button>
            <Button
              size="sm"
              variant={draft.depth === "deep" ? "primary" : "secondary"}
              onClick={() => choosePreset(DEEP)}
              disabled={busy || enabled}
            >
              Deep
            </Button>
            <p className="font-serif text-xs leading-relaxed text-ink-faint sm:col-span-1">
              Standard favors a decisive answer with primary-source preference,
              counterexample search, and a final citation audit.
            </p>
            <p className="font-serif text-xs leading-relaxed text-ink-faint sm:col-span-1">
              Deep decomposes material claims, triangulates independent sources,
              and requires contradiction and final coverage passes.
            </p>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-5">
            <NumberInput
              label="Max sessions"
              value={draft.max_sessions}
              min={1}
              onChange={(value) => setDraft({ ...draft, max_sessions: value })}
            />
            <NumberInput
              label="Turns / session"
              value={draft.max_turns_per_session}
              min={5}
              onChange={(value) =>
                setDraft({ ...draft, max_turns_per_session: value })
              }
            />
            <NumberInput
              label="Max spend (USD)"
              value={draft.max_cost_usd}
              min={0.1}
              step={0.5}
              onChange={(value) => setDraft({ ...draft, max_cost_usd: value })}
            />
            <NumberInput
              label="Source target"
              value={draft.target_source_count}
              min={1}
              onChange={(value) => setDraft({ ...draft, target_source_count: value })}
            />
            <NumberInput
              label="Primary minimum"
              value={draft.min_primary_sources}
              min={0}
              onChange={(value) => setDraft({ ...draft, min_primary_sources: value })}
            />
          </div>
          {dirty && !enabled ? (
            <div className="mt-3">
              <Button
                size="sm"
                variant="secondary"
                disabled={busy}
                onClick={() => save.mutate({ dossierId, policy: draft })}
              >
                Save limits
              </Button>
            </div>
          ) : null}
        </div>
      </details>

      {data.completion_report?.checks?.length ? (
        <div className="mt-4 rounded border border-rule bg-paper p-3">
          <div className="font-mono text-[10px] uppercase tracking-wider text-ink-faint">
            Coverage gate — linked evidence, not truth verification
          </div>
          <ul className="mt-2 grid gap-2 sm:grid-cols-2">
            {data.completion_report.checks.map((check) => (
              <li key={check.key} className="flex items-start gap-2 font-serif text-xs text-ink-muted">
                <span aria-hidden="true" className={check.passed ? "text-state-confident" : "text-attention"}>
                  {check.passed ? "✓" : "○"}
                </span>
                <span>
                  {check.label} ({check.current}/{check.target})
                  {check.detail ? <span className="block text-ink-faint">{check.detail}</span> : null}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {data.stop_reason ? (
        <p className="mt-4 font-mono text-xs text-attention">
          {data.stop_reason.replace(/_/g, " ")}
        </p>
      ) : null}
      {error ? (
        <p className="mt-4 font-mono text-xs text-state-blocked">
          Couldn&rsquo;t update autonomous research.
        </p>
      ) : null}

      {!delivered ? (
        <div className="mt-4 flex flex-wrap items-center gap-3">
          {allowed.has("pause") ? (
            <Button
              variant="secondary"
              disabled={busy}
              onClick={() => pause.mutate(dossierId)}
            >
              {pause.isPending ? "Pausing…" : "Pause after current call"}
            </Button>
          ) : null}
          {allowed.has("resume") && data.active_run_id ? (
            <Button
              disabled={busy}
              onClick={() => resume.mutate({ dossierId, runId: data.active_run_id! })}
            >
              {resume.isPending ? "Queuing…" : "Resume this run"}
            </Button>
          ) : null}
          {allowed.has("start") ? (
            <Button
              disabled={busy}
              onClick={() => start.mutate({ dossierId, policy: draft })}
            >
              {start.isPending ? "Queuing…" : "Start autonomous research"}
            </Button>
          ) : null}
          {allowed.has("restart") ? (
            <Button
              variant="secondary"
              disabled={busy}
              onClick={() => {
                if (window.confirm("Start a new research run with fresh session and spend limits? The existing run stays in history.")) {
                  restart.mutate({ dossierId, policy: draft });
                }
              }}
            >
              {restart.isPending ? "Starting…" : "New research run"}
            </Button>
          ) : null}
          <span className="font-mono text-[10px] text-ink-faint">
            Limits stop future calls; a call already in flight may finish and add spend.
          </span>
        </div>
      ) : null}

      <div className="mt-5 grid gap-4 border-t border-rule pt-4 lg:grid-cols-2">
        <details>
          <summary className="cursor-pointer font-mono text-xs text-ink-muted hover:text-ink">
            Run history ({runs.data?.length ?? 0})
          </summary>
          <div className="mt-3">
            <ResearchTimeline
              runs={runs.data ?? []}
              selectedRunId={evidenceRunId}
              onSelect={setSelectedRunId}
            />
          </div>
        </details>
        <details>
          <summary className="cursor-pointer font-mono text-xs text-ink-muted hover:text-ink">
            Evidence ledger ({evidence.data?.sources.length ?? 0})
          </summary>
          <div className="mt-3"><EvidenceLedger evidence={evidence.data} /></div>
        </details>
      </div>
    </section>
  );
}
