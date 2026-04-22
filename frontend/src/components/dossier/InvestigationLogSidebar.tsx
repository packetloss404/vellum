import React, { useMemo, useState } from "react";
import {
  useInvestigationLog,
  useInvestigationLogCounts,
} from "../../api/hooks";
import type {
  InvestigationLogEntry,
  InvestigationLogEntryType,
} from "../../api/types";
import { relativeTime } from "../../utils/time";

/**
 * InvestigationLogSidebar — evidence-of-work surface on the dossier detail
 * page. Three bands:
 *
 *   1. Counts hero (sticky at top of the sidebar): big mono numbers —
 *      "47 sources, 4 sub-investigations, 3 artifacts, 2 rejected".
 *   2. Filter chips: toggle entry_types in/out of view. Each chip shows
 *      its own count.
 *   3. Timeline: reverse-chronological, grouped by day. Each row has a
 *      glyph, a serif summary, and a mono relative timestamp. Click to
 *      expand payload; clicking an entry tied to a sub-investigation or
 *      section scrolls the main body to that anchor.
 *
 * The component owns its filter + expanded state; no external wiring.
 */

const LOG_LIMIT = 500;
// Render cap per window — kept below total fetched so at 200+ entries
// we don't inflate the DOM beyond what the sidebar can comfortably
// scroll. "Show more" pages additional entries in at VISIBLE_PAGE.
const VISIBLE_INITIAL = 100;
const VISIBLE_PAGE = 100;

// All entry types we know about. Drives filter chips and glyphs. The
// `label` is what appears on the filter chip; `glyph` is the timeline
// marker (plain Unicode so it renders in serif without substitution).
const ENTRY_TYPES: {
  type: InvestigationLogEntryType;
  glyph: string;
  label: string;
}[] = [
  { type: "source_consulted", glyph: "§", label: "source" }, // §
  { type: "sub_investigation_spawned", glyph: "↳", label: "sub spawned" }, // ↳
  { type: "sub_investigation_returned", glyph: "↱", label: "sub returned" }, // ↱
  { type: "section_upserted", glyph: "¶", label: "section" }, // ¶
  { type: "section_revised", glyph: "¶′", label: "section revised" }, // ¶′
  { type: "artifact_added", glyph: "✎", label: "artifact" }, // ✎
  { type: "artifact_revised", glyph: "✎′", label: "artifact revised" }, // ✎′
  { type: "path_rejected", glyph: "✕", label: "rejected" }, // ✕
  { type: "decision_flagged", glyph: "?", label: "decision" },
  { type: "input_requested", glyph: "!", label: "input" },
  { type: "plan_revised", glyph: "◆", label: "plan" }, // ◆
  { type: "stuck_declared", glyph: "⊘", label: "stuck" }, // ⊘
];

const GLYPH_BY_TYPE: Record<InvestigationLogEntryType, string> = Object.fromEntries(
  ENTRY_TYPES.map((e) => [e.type, e.glyph]),
) as Record<InvestigationLogEntryType, string>;

const LABEL_BY_TYPE: Record<InvestigationLogEntryType, string> = Object.fromEntries(
  ENTRY_TYPES.map((e) => [e.type, e.label]),
) as Record<InvestigationLogEntryType, string>;

interface InvestigationLogSidebarProps {
  dossierId: string;
  /**
   * Live counts from the dossier snapshot. Used as the source of truth for
   * the hero numbers when the investigation_log is missing `*_spawned` /
   * `*_added` entry types (the backend only logs some event types, so the
   * log-counts endpoint under-reports sub-investigations and artifacts).
   * When provided, these trump the log-derived counts for subs/artifacts/
   * rejected. `sources` still comes from the log (that's the only place
   * they're counted).
   */
  subsCount?: number;
  artifactsCount?: number;
  rejectedCount?: number;
}

// ---------- helpers ----------

/**
 * Total count across the few "hero" metrics shown in the sticky header.
 *
 * Sources come from the log (the only place they're counted). For subs /
 * artifacts / rejected we prefer the live dossier snapshot counts when the
 * caller supplies them — the log endpoint only reports entry types that
 * have actually been written, so a dossier whose agent didn't emit
 * `sub_investigation_spawned` / `artifact_added` entries would show `0`
 * in the sidebar even when subs/artifacts clearly exist. The dossier
 * snapshot is authoritative.
 */
function heroMetrics(
  counts: Record<string, number> | undefined,
  liveCounts: {
    subs?: number;
    artifacts?: number;
    rejected?: number;
  },
) {
  const c = counts ?? {};
  const logSubs = c.sub_investigation_spawned ?? 0;
  const logArtifacts = (c.artifact_added ?? 0) + (c.artifact_revised ?? 0);
  const logRejected = c.path_rejected ?? 0;
  return {
    sources: c.source_consulted ?? 0,
    subs: liveCounts.subs ?? logSubs,
    artifacts: liveCounts.artifacts ?? logArtifacts,
    rejected: liveCounts.rejected ?? logRejected,
  };
}

/** YYYY-MM-DD in local time; used as the grouping key. */
function dayKey(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "unknown";
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** "Today" / "Yesterday" / "Mar 4" for a day-key. */
function dayLabel(key: string): string {
  if (key === "unknown") return "Unknown";
  const [y, m, d] = key.split("-").map(Number);
  const then = new Date(y, (m ?? 1) - 1, d ?? 1);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const diffDays = Math.round((today.getTime() - then.getTime()) / 86_400_000);
  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  const MONTHS = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
  ];
  return `${MONTHS[then.getMonth()]} ${then.getDate()}`;
}

/**
 * Best-effort scroll into the main body when an entry is clicked. We try
 * the most specific anchor first (sub-investigation, then section). No
 * router navigation — this is in-page only.
 */
function scrollToEntryTarget(entry: InvestigationLogEntry): void {
  const payload = entry.payload ?? {};
  const tryScroll = (id: string | null | undefined): boolean => {
    if (!id) return false;
    const el = document.getElementById(id);
    if (!el) return false;
    el.scrollIntoView({ behavior: "smooth", block: "start" });
    return true;
  };

  if (entry.sub_investigation_id) {
    if (tryScroll(`sub-${entry.sub_investigation_id}`)) return;
  }

  const sectionId =
    (typeof payload.section_id === "string" ? payload.section_id : null) ??
    (Array.isArray(payload.supports_section_ids) &&
    typeof payload.supports_section_ids[0] === "string"
      ? (payload.supports_section_ids[0] as string)
      : null);
  if (sectionId) {
    if (tryScroll(`section-${sectionId}`)) return;
  }

  const artifactId =
    typeof payload.artifact_id === "string" ? payload.artifact_id : null;
  if (artifactId) tryScroll(`artifact-${artifactId}`);
}

// ---------- subcomponents ----------

function CountsHero({
  counts,
  loading,
  liveCounts,
}: {
  counts: Record<string, number> | undefined;
  loading: boolean;
  liveCounts: { subs?: number; artifacts?: number; rejected?: number };
}) {
  if (loading && !counts) {
    return (
      <div className="font-mono text-xs text-ink-faint">Loading counts…</div>
    );
  }
  const m = heroMetrics(counts, liveCounts);
  return (
    <dl className="font-mono text-ink grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 leading-tight">
      <dt className="text-2xl font-semibold tabular-nums">{m.sources}</dt>
      <dd className="self-end text-xs text-ink-muted uppercase tracking-wide pb-1">
        sources
      </dd>
      <dt className="text-2xl font-semibold tabular-nums">{m.subs}</dt>
      <dd className="self-end text-xs text-ink-muted uppercase tracking-wide pb-1">
        sub-investigations
      </dd>
      <dt className="text-2xl font-semibold tabular-nums">{m.artifacts}</dt>
      <dd className="self-end text-xs text-ink-muted uppercase tracking-wide pb-1">
        artifacts
      </dd>
      <dt className="text-2xl font-semibold tabular-nums">{m.rejected}</dt>
      <dd className="self-end text-xs text-ink-muted uppercase tracking-wide pb-1">
        considered &amp; rejected
      </dd>
    </dl>
  );
}

function FilterChips({
  counts,
  selected,
  onToggle,
  onReset,
}: {
  counts: Record<string, number> | undefined;
  selected: Set<InvestigationLogEntryType>;
  onToggle: (t: InvestigationLogEntryType) => void;
  onReset: () => void;
}) {
  const anySelected = selected.size > 0;
  const visible = ENTRY_TYPES.filter((e) => (counts?.[e.type] ?? 0) > 0);
  // If we have zero counts for any type, fall through to show the full set
  // so users can still see the control exists.
  const chips = visible.length ? visible : ENTRY_TYPES;

  return (
    <div className="flex flex-wrap gap-1.5">
      <button
        type="button"
        onClick={onReset}
        className={[
          "font-mono text-[11px] px-2 py-0.5 border rounded-sm transition-colors",
          anySelected
            ? "border-rule text-ink-muted hover:border-rule-strong"
            : "border-ink text-ink bg-surface-sunk",
        ].join(" ")}
        aria-pressed={!anySelected}
      >
        all
      </button>
      {chips.map((e) => {
        const n = counts?.[e.type] ?? 0;
        const active = selected.has(e.type);
        return (
          <button
            key={e.type}
            type="button"
            onClick={() => onToggle(e.type)}
            className={[
              "font-mono text-[11px] px-2 py-0.5 border rounded-sm transition-colors",
              "inline-flex items-center gap-1.5",
              active
                ? "border-ink text-ink bg-surface-sunk"
                : "border-rule text-ink-muted hover:border-rule-strong",
            ].join(" ")}
            aria-pressed={active}
            title={e.type}
          >
            <span aria-hidden="true" className="font-serif">
              {e.glyph}
            </span>
            <span>{e.label}</span>
            <span className="tabular-nums text-ink-faint">{n}</span>
          </button>
        );
      })}
    </div>
  );
}

function LogRow({ entry }: { entry: InvestigationLogEntry }) {
  const [open, setOpen] = useState(false);
  const glyph = GLYPH_BY_TYPE[entry.entry_type] ?? "·"; // · fallback
  const label = LABEL_BY_TYPE[entry.entry_type] ?? entry.entry_type;

  const payload = entry.payload ?? {};
  const hasPayload = Object.keys(payload).length > 0;
  const isClickable =
    !!entry.sub_investigation_id ||
    typeof payload.section_id === "string" ||
    (Array.isArray(payload.supports_section_ids) &&
      payload.supports_section_ids.length > 0) ||
    typeof payload.artifact_id === "string";

  const onRowClick = () => {
    setOpen((v) => !v);
    if (isClickable) scrollToEntryTarget(entry);
  };

  return (
    <li className="border-t border-rule first:border-t-0">
      <button
        type="button"
        onClick={onRowClick}
        className="w-full text-left py-2.5 flex items-start gap-3 group"
        aria-expanded={open}
      >
        <span
          aria-hidden="true"
          className="font-serif text-ink-muted w-4 shrink-0 text-center leading-snug pt-0.5"
          title={label}
        >
          {glyph}
        </span>
        <p className="flex-1 font-serif text-sm text-ink leading-snug group-hover:text-accent">
          {entry.summary}
        </p>
        <span className="font-mono text-[11px] text-ink-faint shrink-0 tabular-nums pt-0.5">
          {relativeTime(entry.created_at)}
        </span>
      </button>
      {open && hasPayload && (
        <div className="pl-7 pr-1 pb-3">
          <PayloadDetails entry={entry} />
        </div>
      )}
    </li>
  );
}

/**
 * Render the payload for an expanded entry. For known entry_types we pull
 * out the well-known fields; otherwise we dump the JSON so the user can
 * still see what was recorded.
 */
function PayloadDetails({ entry }: { entry: InvestigationLogEntry }) {
  const p = entry.payload ?? {};
  const str = (k: string) =>
    typeof p[k] === "string" ? (p[k] as string) : null;
  const arr = (k: string) =>
    Array.isArray(p[k]) ? (p[k] as unknown[]) : null;

  const rows: { label: string; value: React.ReactNode }[] = [];

  if (entry.entry_type === "source_consulted") {
    const citation = str("citation") ?? str("url") ?? str("title");
    const why = str("why") ?? str("reason");
    const learned = str("what_learned") ?? str("learned");
    if (citation) rows.push({ label: "citation", value: citation });
    if (why) rows.push({ label: "why", value: why });
    if (learned) rows.push({ label: "learned", value: learned });
  } else if (
    entry.entry_type === "sub_investigation_spawned" ||
    entry.entry_type === "sub_investigation_returned"
  ) {
    const scope = str("scope");
    const qs = arr("questions") ?? arr("findings");
    if (scope) rows.push({ label: "scope", value: scope });
    if (qs && qs.length)
      rows.push({
        label: entry.entry_type === "sub_investigation_returned"
          ? "findings"
          : "questions",
        value: (
          <ul className="list-disc pl-5 m-0">
            {qs.map((q, i) => (
              <li key={i}>{String(q)}</li>
            ))}
          </ul>
        ),
      });
  } else if (entry.entry_type === "path_rejected") {
    const path = str("path");
    const why = str("why_rejected") ?? str("reason");
    if (path) rows.push({ label: "path", value: path });
    if (why) rows.push({ label: "why", value: why });
  }

  // Fallback: if we didn't pull any known fields, show raw JSON.
  if (rows.length === 0) {
    return (
      <pre className="font-mono text-[11px] text-ink-muted whitespace-pre-wrap break-words bg-surface-sunk px-2 py-1.5 rounded-sm m-0">
        {JSON.stringify(entry.payload, null, 2)}
      </pre>
    );
  }

  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 font-serif text-[13px] text-ink-muted leading-snug">
      {rows.map((r, i) => (
        <React.Fragment key={i}>
          <dt className="font-mono text-[11px] uppercase tracking-wide text-ink-faint pt-0.5">
            {r.label}
          </dt>
          <dd className="m-0">{r.value}</dd>
        </React.Fragment>
      ))}
    </dl>
  );
}

// ---------- main component ----------

export function InvestigationLogSidebar({
  dossierId,
  subsCount,
  artifactsCount,
  rejectedCount,
}: InvestigationLogSidebarProps) {
  const countsQ = useInvestigationLogCounts(dossierId);
  const logQ = useInvestigationLog(dossierId, { limit: LOG_LIMIT });
  const liveCounts = {
    subs: subsCount,
    artifacts: artifactsCount,
    rejected: rejectedCount,
  };

  const [selected, setSelected] = useState<Set<InvestigationLogEntryType>>(
    new Set(),
  );
  const [visibleCount, setVisibleCount] = useState<number>(VISIBLE_INITIAL);

  const toggle = (t: InvestigationLogEntryType) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(t)) next.delete(t);
      else next.add(t);
      return next;
    });
    // Reset pagination when the filter changes — otherwise the user can
    // land on a filtered set where everything they want is beyond the
    // current visibleCount.
    setVisibleCount(VISIBLE_INITIAL);
  };
  const reset = () => {
    setSelected(new Set());
    setVisibleCount(VISIBLE_INITIAL);
  };

  // Sort newest-first + filter is the expensive part when the log is big;
  // paginate afterward so "Show more" doesn't re-sort.
  const sortedFiltered = useMemo(() => {
    return (logQ.data ?? [])
      .slice()
      .sort(
        (a, b) =>
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
      )
      .filter((e) => selected.size === 0 || selected.has(e.entry_type));
  }, [logQ.data, selected]);

  const visible = useMemo(
    () => sortedFiltered.slice(0, visibleCount),
    [sortedFiltered, visibleCount],
  );

  const grouped = useMemo(() => {
    const groups = new Map<string, InvestigationLogEntry[]>();
    for (const e of visible) {
      const k = dayKey(e.created_at);
      const bucket = groups.get(k);
      if (bucket) bucket.push(e);
      else groups.set(k, [e]);
    }
    return Array.from(groups.entries());
  }, [visible]);

  const totalEntries = logQ.data?.length ?? 0;
  const matchedEntries = sortedFiltered.length;
  const atLimit = totalEntries >= LOG_LIMIT;
  const hasMore = matchedEntries > visible.length;

  return (
    // Outer DossierPage aside already handles sticky + vertical scroll.
    // Keep this section a plain flex column so the hero and timeline
    // coexist without introducing a second scroll container.
    <aside className="flex flex-col">
      {/* Counts hero — sticks to the top of the scroll container (the
          parent aside) so it stays visible while the timeline scrolls. */}
      <div className="shrink-0 sticky top-0 z-[1] bg-paper pb-4 border-b border-rule">
        <div className="font-mono text-xs uppercase tracking-wide text-ink-faint mb-3">
          Investigation log
        </div>
        <CountsHero
          counts={countsQ.data}
          loading={countsQ.isLoading}
          liveCounts={liveCounts}
        />
        <div className="mt-4">
          <FilterChips
            counts={countsQ.data}
            selected={selected}
            onToggle={toggle}
            onReset={reset}
          />
        </div>
      </div>

      {/* Timeline */}
      <div className="flex-1 pt-3">
        {logQ.isLoading ? (
          <div className="font-mono text-xs text-ink-faint">Loading log…</div>
        ) : logQ.error ? (
          <div className="font-mono text-xs text-state-blocked">
            Couldn't load log.
          </div>
        ) : grouped.length === 0 ? (
          <div className="font-serif text-sm italic text-ink-faint">
            {totalEntries === 0
              ? "The agent hasn't done any work yet."
              : "No entries match the current filter."}
          </div>
        ) : (
          <div className="space-y-5">
            {grouped.map(([key, entries]) => (
              <section key={key}>
                <h3 className="font-mono text-[11px] uppercase tracking-wide text-ink-faint mb-1 pb-1">
                  {dayLabel(key)}
                </h3>
                <ul className="list-none p-0 m-0">
                  {entries.map((e) => (
                    <LogRow key={e.id} entry={e} />
                  ))}
                </ul>
              </section>
            ))}
            {hasMore && (
              <div className="pt-3 border-t border-rule text-center">
                <button
                  type="button"
                  onClick={() =>
                    setVisibleCount((v) => v + VISIBLE_PAGE)
                  }
                  className="font-mono text-[11px] text-accent hover:text-accent-hover underline"
                >
                  Show {Math.min(VISIBLE_PAGE, matchedEntries - visible.length)} more
                  <span className="text-ink-faint ml-1 no-underline">
                    ({visible.length} of {matchedEntries})
                  </span>
                </button>
              </div>
            )}
            {atLimit && !hasMore && (
              <p className="font-mono text-[11px] text-ink-faint italic pt-2 border-t border-rule">
                Showing the most recent {LOG_LIMIT} entries.
              </p>
            )}
          </div>
        )}
      </div>
    </aside>
  );
}

export default InvestigationLogSidebar;
