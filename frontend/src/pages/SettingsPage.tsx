import { useEffect, useMemo, useState } from "react";
import { useBudgetToday, useSettings, useUpdateSetting } from "../api/hooks";
import { Header } from "../components/layout/Header";
import { Button } from "../components/common/Button";
import type { SettingEntry } from "../api/types";

/**
 * SettingsPage — flat editor over the DB-backed `settings` table.
 *
 * Ian's call (day-3): scoped to the NEW budget / guard / sleep-mode knobs
 * only. The existing env-driven stuck thresholds in config.py stay put;
 * this page does not surface them.
 *
 * Design stance: untyped at the API layer, lightly typed here for nicer
 * controls. The type hint dictionary knows about the default seeded keys;
 * any other key falls back to a JSON textarea so forward-compat settings
 * added server-side don't need a frontend bump to be editable.
 */

type FieldKind = "boolean" | "number" | "percentage" | "json";

interface FieldMeta {
  kind: FieldKind;
  label: string;
  description: string;
  suffix?: string;
}

const FIELDS: Record<string, FieldMeta> = {
  sleep_mode_enabled: {
    kind: "boolean",
    label: "Sleep mode",
    description:
      "Master switch. When off, the scheduler skips its tick work, schedule_wake becomes a no-op, and the user drives every resume manually.",
  },
  schedule_wake_max_hours: {
    kind: "number",
    label: "Max schedule-wake interval",
    description:
      "Cap on the hours the agent can schedule itself forward in a single schedule_wake call. Guardrail against 'wake me in 90 days' drift.",
    suffix: "hours",
  },
  budget_daily_soft_cap_usd: {
    kind: "number",
    label: "Daily soft cap",
    description:
      "When today's global spend crosses this, the agent surfaces a decision_point. Soft signal — the loop is never terminated mid-thought. Set to 0 to disable.",
    suffix: "USD",
  },
  budget_daily_warn_fraction: {
    kind: "percentage",
    label: "Daily warn fraction",
    description:
      "Warn at this share of the daily cap, before the cap itself is crossed. 0.8 = warn at 80%.",
  },
  budget_per_session_soft_cap_usd: {
    kind: "number",
    label: "Per-session soft cap",
    description:
      "When a single work_session's spend crosses this, surface a decision_point even if the daily cap is fine. Set to 0 to disable.",
    suffix: "USD",
  },
};

function metaFor(key: string): FieldMeta {
  return (
    FIELDS[key] ?? {
      kind: "json",
      label: key,
      description: "Custom setting (JSON-encoded value).",
    }
  );
}

function formatDollars(cost: number): string {
  if (cost <= 0) return "$0.00";
  if (cost < 0.01) return "<$0.01";
  return `$${cost.toFixed(2)}`;
}

interface FieldProps {
  entry: SettingEntry;
  draft: unknown;
  setDraft: (v: unknown) => void;
}

function BooleanField({ draft, setDraft }: FieldProps) {
  const on = !!draft;
  return (
    <label className="inline-flex items-center gap-3 cursor-pointer">
      <input
        type="checkbox"
        checked={on}
        onChange={(e) => setDraft(e.target.checked)}
        className="h-4 w-4 accent-accent cursor-pointer"
      />
      <span className="font-mono text-xs text-ink-muted">
        {on ? "enabled" : "disabled"}
      </span>
    </label>
  );
}

function NumberField({ entry, draft, setDraft }: FieldProps) {
  const raw = draft as number | string;
  const suffix = metaFor(entry.key).suffix;
  return (
    <div className="flex items-center gap-2">
      <input
        type="number"
        step="0.01"
        value={typeof raw === "number" ? raw : (raw ?? "")}
        onChange={(e) => {
          const v = e.target.value;
          setDraft(v === "" ? 0 : Number(v));
        }}
        className="w-32 bg-paper border border-rule rounded px-2 py-1 font-mono text-sm text-ink focus:outline-none focus:border-accent"
      />
      {suffix ? (
        <span className="font-mono text-[11px] text-ink-faint">{suffix}</span>
      ) : null}
    </div>
  );
}

function PercentageField({ draft, setDraft }: FieldProps) {
  const raw = draft as number;
  const pct = typeof raw === "number" ? Math.round(raw * 100) : 0;
  return (
    <div className="flex items-center gap-2">
      <input
        type="number"
        min={0}
        max={100}
        step="1"
        value={pct}
        onChange={(e) => {
          const v = e.target.value;
          const num = v === "" ? 0 : Math.max(0, Math.min(100, Number(v)));
          setDraft(num / 100);
        }}
        className="w-24 bg-paper border border-rule rounded px-2 py-1 font-mono text-sm text-ink focus:outline-none focus:border-accent"
      />
      <span className="font-mono text-[11px] text-ink-faint">%</span>
    </div>
  );
}

function JsonField({ draft, setDraft }: FieldProps) {
  const [text, setText] = useState(() => JSON.stringify(draft, null, 2));
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    setText(JSON.stringify(draft, null, 2));
  }, [draft]);
  return (
    <div className="flex flex-col gap-1">
      <textarea
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          try {
            const parsed = JSON.parse(e.target.value);
            setErr(null);
            setDraft(parsed);
          } catch (ex) {
            setErr((ex as Error).message);
          }
        }}
        rows={4}
        className="w-full bg-paper border border-rule rounded px-2 py-1 font-mono text-xs text-ink focus:outline-none focus:border-accent"
      />
      {err ? (
        <span className="font-mono text-[11px] text-state-blocked">{err}</span>
      ) : null}
    </div>
  );
}

function renderControl(props: FieldProps) {
  const kind = metaFor(props.entry.key).kind;
  switch (kind) {
    case "boolean":
      return <BooleanField {...props} />;
    case "number":
      return <NumberField {...props} />;
    case "percentage":
      return <PercentageField {...props} />;
    default:
      return <JsonField {...props} />;
  }
}

function SettingRow({ entry }: { entry: SettingEntry }) {
  const meta = metaFor(entry.key);
  const [draft, setDraft] = useState<unknown>(entry.value);
  const update = useUpdateSetting();

  // When the server value changes (another tab saved), reset the local
  // draft so we don't hold a stale value.
  useEffect(() => {
    setDraft(entry.value);
  }, [entry.value]);

  const dirty = useMemo(
    () => JSON.stringify(draft) !== JSON.stringify(entry.value),
    [draft, entry.value],
  );

  const onSave = () => {
    update.mutate({ key: entry.key, value: draft });
  };
  const onReset = () => setDraft(entry.value);

  return (
    <div className="py-5 border-t border-rule first:border-t-0">
      <div className="flex items-baseline justify-between gap-4">
        <div className="min-w-0">
          <div className="font-serif text-base text-ink">{meta.label}</div>
          <code className="font-mono text-[10px] text-ink-faint">
            {entry.key}
          </code>
        </div>
        <div className="shrink-0">{renderControl({ entry, draft, setDraft })}</div>
      </div>
      <p className="mt-2 font-serif text-sm text-ink-muted leading-relaxed max-w-prose">
        {meta.description}
      </p>
      {dirty ? (
        <div className="mt-3 flex items-center gap-2">
          <Button
            onClick={onSave}
            disabled={update.isPending}
            variant="primary"
          >
            {update.isPending ? "Saving…" : "Save"}
          </Button>
          <Button onClick={onReset} variant="ghost" disabled={update.isPending}>
            Reset
          </Button>
          {update.error ? (
            <span className="font-mono text-[11px] text-state-blocked">
              failed to save
            </span>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function BudgetBanner() {
  const { data } = useBudgetToday();
  if (!data) return null;
  const tone =
    data.state === "soft_cap_crossed"
      ? "border-state-blocked text-state-blocked"
      : data.state === "warn"
        ? "border-attention text-attention"
        : "border-rule text-ink-muted";
  return (
    <div
      className={`mb-6 border rounded px-4 py-3 font-mono text-xs ${tone}`}
    >
      <div className="flex items-baseline justify-between gap-3">
        <span>
          Today ({data.day}) — {formatDollars(data.spent_usd)} spent
          {data.daily_cap_usd > 0 ? (
            <>
              {" of "}
              <span className="text-ink">
                {formatDollars(data.daily_cap_usd)}
              </span>
              {" cap"}
            </>
          ) : (
            " · no cap set"
          )}
        </span>
        <span className="uppercase tracking-wide">
          {data.state.replace(/_/g, " ")}
        </span>
      </div>
      <div className="mt-1 text-ink-faint">
        {data.input_tokens.toLocaleString()} in ·{" "}
        {data.output_tokens.toLocaleString()} out
      </div>
    </div>
  );
}

export default function SettingsPage() {
  const { data, isLoading, error } = useSettings();

  // Sort settings so the meta-ordered keys appear first in FIELDS order.
  const ordered = useMemo(() => {
    if (!data) return [];
    const known = Object.keys(FIELDS);
    const knownSet = new Set(known);
    const byKey = new Map(data.map((s) => [s.key, s] as const));
    const head = known
      .map((k) => byKey.get(k))
      .filter((v): v is SettingEntry => !!v);
    const tail = data
      .filter((s) => !knownSet.has(s.key))
      .sort((a, b) => a.key.localeCompare(b.key));
    return [...head, ...tail];
  }, [data]);

  return (
    <div className="min-h-screen bg-paper">
      <Header title="Settings" />
      <main className="mx-auto max-w-page px-6 py-10">
        <header className="mb-8">
          <h1 className="font-serif text-3xl text-ink">Settings</h1>
          <p className="mt-2 font-serif text-sm text-ink-muted max-w-prose leading-relaxed">
            Knobs for sleep mode and spend guardrails. Budgets are soft
            signals — the agent surfaces a decision point when a cap
            crosses, it never terminates mid-thought.
          </p>
        </header>

        <BudgetBanner />

        {isLoading ? (
          <p className="font-mono text-sm text-ink-faint">Loading…</p>
        ) : error ? (
          <p className="font-mono text-sm text-state-blocked">
            Couldn&rsquo;t load settings.
          </p>
        ) : (
          <section>
            {ordered.map((entry) => (
              <SettingRow key={entry.key} entry={entry} />
            ))}
          </section>
        )}
      </main>
    </div>
  );
}
