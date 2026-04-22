import React from "react";
import type { DossierFull } from "../../api/types";
import { relativeTime } from "../../utils/time";

/**
 * DossierHero — the top-of-page "case-file cover" for a dossier.
 *
 * Two render modes, picked by which props the caller supplies:
 *
 *   1. Rich mode (`dossier` + optional `counts`): the full Day-4 hero.
 *      Type overline in small caps, commanding serif title, problem
 *      statement rendered as a serif-italic pull-quote with a left rule,
 *      a mono counts strip ("47 sources · 4 sub-investigations · 3
 *      artifacts"), and a fine-print last-visited line. This is what
 *      DossierPage uses.
 *
 *   2. Legacy mode (`title` / `eyebrow` / `subtitle` / `meta`): the
 *      minimal variant kept for DemoPage, which composes the hero with
 *      fixture data and doesn't have a full DossierFull in hand. The
 *      original API is preserved so DemoPage keeps compiling.
 */

export interface DossierHeroProps {
  // Rich mode
  dossier?: DossierFull;
  counts?: Record<string, number>;

  // Legacy mode (DemoPage)
  title?: string;
  eyebrow?: string;
  subtitle?: string;
  meta?: React.ReactNode;

  className?: string;
}

function formatTypeLabel(dossierType: string): string {
  return dossierType.replace(/_/g, " ");
}

interface CountStripItem {
  /** Plural form used when count !== 1. */
  plural: string;
  /** Singular form used when count === 1. */
  singular: string;
  count: number;
}

function buildCountStrip(
  dossier: DossierFull,
  counts: Record<string, number> | undefined,
): CountStripItem[] {
  const sources = counts?.source_consulted ?? 0;
  const subs =
    (dossier.sub_investigations?.length ?? 0) ||
    counts?.sub_investigation_spawned ||
    0;
  const artifacts =
    (dossier.artifacts?.length ?? 0) || counts?.artifact_added || 0;
  const rejected = dossier.considered_and_rejected?.length ?? 0;

  const items: CountStripItem[] = [
    { plural: "sources", singular: "source", count: sources },
    {
      plural: "sub-investigations",
      singular: "sub-investigation",
      count: subs,
    },
    { plural: "artifacts", singular: "artifact", count: artifacts },
    {
      plural: "considered & rejected",
      singular: "considered & rejected",
      count: rejected,
    },
  ];
  // Keep only items with > 0 so the strip stays tight. If all are zero the
  // caller renders the "No sources yet" fallback.
  return items.filter((item) => item.count > 0);
}

function wordFor(item: CountStripItem): string {
  return item.count === 1 ? item.singular : item.plural;
}

/**
 * Rich hero — the Day-4 case-file cover. Private helper composed by the
 * public DossierHero component when a `dossier` prop is supplied.
 */
function RichHero({
  dossier: full,
  counts,
}: {
  dossier: DossierFull;
  counts?: Record<string, number>;
}) {
  const { dossier } = full;
  const typeLabel = formatTypeLabel(dossier.dossier_type);
  const problem = dossier.problem_statement?.trim();
  const stripItems = buildCountStrip(full, counts);
  const lastVisited = dossier.last_visited_at
    ? relativeTime(dossier.last_visited_at)
    : null;

  return (
    <section className="space-y-6">
      <div>
        <div className="text-[11px] font-mono uppercase tracking-[0.18em] text-ink-faint mb-3">
          {typeLabel}
        </div>
        <h1 className="font-serif text-ink tracking-tight leading-[1.1] text-4xl md:text-5xl break-words">
          {dossier.title}
        </h1>
      </div>

      {problem ? (
        <blockquote className="border-l-2 border-rule-strong pl-5 max-w-[70ch]">
          <p className="font-serif italic text-ink-muted text-lg leading-relaxed">
            {problem}
          </p>
        </blockquote>
      ) : null}

      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 font-mono text-xs text-ink-muted">
        {stripItems.length === 0 ? (
          <span className="text-ink-faint">No sources yet</span>
        ) : (
          stripItems.map((item, i) => (
            <React.Fragment key={item.plural}>
              {i > 0 ? (
                <span aria-hidden="true" className="text-ink-faint">
                  ·
                </span>
              ) : null}
              <span>
                <span className="text-ink tabular-nums">{item.count}</span>{" "}
                {wordFor(item)}
              </span>
            </React.Fragment>
          ))
        )}
        {lastVisited ? (
          <>
            <span aria-hidden="true" className="text-ink-faint">
              ·
            </span>
            <span className="text-ink-faint">Last visited {lastVisited}</span>
          </>
        ) : null}
      </div>
    </section>
  );
}

/**
 * Legacy hero — DemoPage composes this with fixture data. The original
 * eyebrow/title/subtitle/meta shape, unchanged, so the demo surface keeps
 * rendering while DossierPage moves to the richer variant above.
 */
function LegacyHero({
  title,
  eyebrow,
  subtitle,
  meta,
  className,
}: Pick<
  DossierHeroProps,
  "title" | "eyebrow" | "subtitle" | "meta" | "className"
>) {
  return (
    <section className={className}>
      {eyebrow ? (
        <div className="text-xs font-mono uppercase tracking-wide text-ink-faint mb-2">
          {eyebrow}
        </div>
      ) : null}
      {title ? (
        <h1 className="text-3xl font-serif text-ink tracking-tight">{title}</h1>
      ) : null}
      {subtitle ? (
        <p
          className={
            title
              ? "mt-3 text-ink-muted font-serif leading-relaxed"
              : "font-serif text-base text-ink leading-relaxed"
          }
        >
          {subtitle}
        </p>
      ) : null}
      {meta ? (
        <div className="mt-4 flex flex-wrap items-center gap-2 text-xs font-mono text-ink-faint">
          {meta}
        </div>
      ) : null}
    </section>
  );
}

export function DossierHero(props: DossierHeroProps) {
  if (props.dossier) {
    return (
      <div className={props.className}>
        <RichHero dossier={props.dossier} counts={props.counts} />
      </div>
    );
  }
  return (
    <LegacyHero
      title={props.title}
      eyebrow={props.eyebrow}
      subtitle={props.subtitle}
      meta={props.meta}
      className={props.className}
    />
  );
}

export default DossierHero;
