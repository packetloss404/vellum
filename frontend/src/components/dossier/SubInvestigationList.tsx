import React, { useState } from "react";
import type {
  Artifact,
  Section,
  SubInvestigation,
  SubInvestigationState,
} from "../../api/types";
import { relativeTime } from "../../utils/time";

/**
 * SubInvestigationList — the visible tree of investigation. Sub-investigations
 * are first-class: each card shows scope, questions, state, return summary,
 * and findings that scroll-link to the sections/artifacts they produced.
 *
 * Day-4: polished renderer. Delivered subs collapse to header + return
 * summary; running subs stay open. Each card carries an `id={`sub-${id}`}`
 * anchor so the investigation-log sidebar can scroll to it.
 */

export interface SubInvestigationListProps {
  subs: SubInvestigation[];
  sections: Section[];
  artifacts: Artifact[];
}

// ---------- State pip ----------

/**
 * Pip + label color per state. We use the design tokens where they map
 * cleanly (state-confident for delivered, state-blocked for blocked) and
 * approximate the rest with neutral/muted Tailwind classes so running
 * reads as in-progress and abandoned reads as inert/struck-through.
 */
interface PipStyle {
  pipClass: string;
  labelClass: string;
  striken?: boolean;
}

const PIP_BY_STATE: Record<SubInvestigationState, PipStyle> = {
  running: {
    // Muted accent — "in-progress," not alarming.
    pipClass: "bg-accent animate-pulse",
    labelClass: "text-accent",
  },
  delivered: {
    // Confident green — the branch returned with findings.
    pipClass: "bg-state-confident",
    labelClass: "text-state-confident",
  },
  blocked: {
    // Rusty red — still open, but stuck.
    pipClass: "bg-state-blocked",
    labelClass: "text-state-blocked",
  },
  abandoned: {
    // Grey + struck-through — the agent walked away.
    pipClass: "bg-ink-faint",
    labelClass: "text-ink-faint line-through",
    striken: true,
  },
};

function StatePip({ state }: { state: SubInvestigationState }) {
  const style = PIP_BY_STATE[state];
  return (
    <span className="inline-flex items-center gap-1.5 font-mono text-xs uppercase tracking-wide">
      <span
        aria-hidden="true"
        className={`inline-block h-2 w-2 rounded-full ${style.pipClass}`}
      />
      <span className={style.labelClass}>{state}</span>
    </span>
  );
}

// ---------- Finding chips ----------

/**
 * Inline chip linking into the main document. We resolve titles from the
 * parent dossier's sections/artifacts props; if the id can't be resolved
 * (stale finding) we fall back to a truncated id so the link still renders.
 */
function FindingChip({
  href,
  kindLabel,
  title,
}: {
  href: string;
  kindLabel: string;
  title: string;
}) {
  return (
    <a
      href={href}
      className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded border border-rule bg-surface-sunk text-xs font-mono text-ink-muted hover:border-accent hover:text-accent transition-colors no-underline"
    >
      <span className="uppercase tracking-wide text-ink-faint">
        {kindLabel}
      </span>
      <span className="font-serif normal-case tracking-normal text-ink">
        {title}
      </span>
    </a>
  );
}

function shortId(id: string): string {
  return id.length > 8 ? `${id.slice(0, 8)}…` : id;
}

// ---------- Card ----------

function SubCard({
  sub,
  sections,
  artifacts,
}: {
  sub: SubInvestigation;
  sections: Section[];
  artifacts: Artifact[];
}) {
  const isRunning = sub.state === "running";
  // Delivered subs collapse to header + summary; running stays open.
  const [expanded, setExpanded] = useState<boolean>(isRunning);

  const hasSummary =
    !!sub.return_summary && sub.return_summary.trim().length > 0;
  const hasQuestions = sub.questions && sub.questions.length > 0;
  const findingsCount =
    sub.findings_section_ids.length + sub.findings_artifact_ids.length;

  const sectionById = new Map(sections.map((s) => [s.id, s]));
  const artifactById = new Map(artifacts.map((a) => [a.id, a]));

  const abandoned = sub.state === "abandoned";
  const scopeClass = abandoned
    ? "font-serif text-lg text-ink-muted leading-snug line-through"
    : "font-serif text-lg text-ink leading-snug";

  const chevron = expanded ? "▾" : "▸";

  return (
    <li
      id={`sub-${sub.id}`}
      className="scroll-mt-24 border border-rule rounded bg-surface p-5 first:mt-0"
    >
      {/* Header row: pip+state | scope | count+chevron */}
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        aria-expanded={expanded}
        className="w-full text-left group"
      >
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-3 mb-1">
              <StatePip state={sub.state} />
            </div>
            <div className={scopeClass}>{sub.scope}</div>
          </div>
          <div className="shrink-0 flex items-center gap-3">
            <div className="text-right font-mono text-xs text-ink-faint leading-tight">
              <div>
                {sub.questions.length}{" "}
                {sub.questions.length === 1 ? "question" : "questions"}
              </div>
              <div>
                {findingsCount}{" "}
                {findingsCount === 1 ? "finding" : "findings"}
              </div>
            </div>
            <span
              aria-hidden="true"
              className="font-mono text-xs text-ink-faint group-hover:text-accent transition-colors"
            >
              {chevron}
            </span>
          </div>
        </div>
      </button>

      {/* Return summary — rendered at all zoom levels when present. Gives
          a delivered sub a confident, readable one-liner while collapsed. */}
      {hasSummary ? (
        <div className="mt-4 border-l-2 border-accent pl-4">
          <p className="font-serif text-base text-ink leading-relaxed whitespace-pre-wrap m-0">
            {sub.return_summary}
          </p>
        </div>
      ) : null}

      {/* Expanded body — questions + findings + timestamps. */}
      {expanded ? (
        <div className="mt-4 space-y-4">
          {hasQuestions ? (
            <div>
              <div className="font-mono text-xs uppercase tracking-wide text-ink-faint mb-1.5">
                Questions
              </div>
              <ul className="list-disc pl-5 space-y-1 m-0">
                {sub.questions.map((q, idx) => (
                  <li
                    key={idx}
                    className="font-serif italic text-sm text-ink-muted leading-relaxed"
                  >
                    {q}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {findingsCount > 0 ? (
            <div>
              <div className="font-mono text-xs uppercase tracking-wide text-ink-faint mb-1.5">
                Findings
              </div>
              <div className="flex flex-wrap gap-2">
                {sub.findings_section_ids.map((sid) => {
                  const sec = sectionById.get(sid);
                  const title = sec ? sec.title : `section ${shortId(sid)}`;
                  return (
                    <FindingChip
                      key={`s-${sid}`}
                      href={`#section-${sid}`}
                      kindLabel="section"
                      title={title}
                    />
                  );
                })}
                {sub.findings_artifact_ids.map((aid) => {
                  const art = artifactById.get(aid);
                  const title = art ? art.title : `artifact ${shortId(aid)}`;
                  return (
                    <FindingChip
                      key={`a-${aid}`}
                      href={`#artifact-${aid}`}
                      kindLabel="artifact"
                      title={title}
                    />
                  );
                })}
              </div>
            </div>
          ) : null}

          <div className="font-mono text-xs text-ink-faint flex flex-wrap gap-x-3 gap-y-1">
            <span>started {relativeTime(sub.started_at)}</span>
            {sub.completed_at ? (
              <>
                <span aria-hidden="true">·</span>
                <span>completed {relativeTime(sub.completed_at)}</span>
              </>
            ) : null}
          </div>
        </div>
      ) : null}
    </li>
  );
}

// ---------- Empty state ----------

function EmptyState() {
  return (
    <div className="font-serif italic text-ink-muted leading-relaxed">
      <p className="m-0">No sub-investigations opened yet.</p>
      <p className="mt-2 text-sm text-ink-faint not-italic font-mono">
        The agent investigates by opening scoped sub-investigations. If none
        appear on a consequential problem, something&rsquo;s off.
      </p>
    </div>
  );
}

// ---------- Root ----------

export function SubInvestigationList({
  subs,
  sections,
  artifacts,
}: SubInvestigationListProps) {
  // Newest-spawned first, for a stable reverse-chron read.
  const ordered = [...(subs ?? [])].sort(
    (a, b) =>
      new Date(b.started_at).getTime() - new Date(a.started_at).getTime(),
  );

  return (
    <section className="space-y-4">
      <h2 className="font-mono text-xs uppercase tracking-wide text-ink-faint">
        Sub-investigations{ordered.length > 0 ? ` (${ordered.length})` : ""}
      </h2>
      {ordered.length === 0 ? (
        <EmptyState />
      ) : (
        <ul className="space-y-4 list-none p-0 m-0">
          {ordered.map((sub) => (
            <SubCard
              key={sub.id}
              sub={sub}
              sections={sections}
              artifacts={artifacts}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

export default SubInvestigationList;
