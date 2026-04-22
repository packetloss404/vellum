import React, { useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import type { Section, SectionType, SectionState } from "../../api/types";
import { SourceList } from "../sections/SourceList";
import { relativeTime } from "../../utils/time";

/**
 * SectionCard — one dossier section rendered as a well-set page.
 *
 * The overline row carries the type label (uppercase, small caps feel),
 * a colored state pip, and—if present—the agent's `change_note` in
 * serif italic so the reader sees "why this moved" without leaving the
 * section. The body is markdown-rendered under a scoped `.prose`
 * wrapper so embedded headings stay subordinate to the section title.
 *
 * Long sections collapse to a ~250-char preview; blocked sections
 * always expand so the reader can see why.
 */

export interface SectionCardProps {
  section: Section;
}

const COLLAPSE_THRESHOLD = 600;
const PREVIEW_CHARS = 250;

// ---------- State pip ----------

const statePipClass: Record<SectionState, string> = {
  // solid deep green — the "this is settled" accent
  confident: "bg-state-confident",
  // amber/warm yellow — caution, work-in-progress
  provisional: "bg-attention",
  // rusty red — this is stuck
  blocked: "bg-state-blocked",
};

const stateLabelClass: Record<SectionState, string> = {
  confident: "text-state-confident",
  provisional: "text-attention",
  blocked: "text-state-blocked",
};

function StatePip({ state }: { state: SectionState }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        aria-hidden="true"
        className={`inline-block h-2 w-2 rounded-full ${statePipClass[state]}`}
      />
      <span
        className={`font-mono text-[11px] uppercase tracking-wide ${stateLabelClass[state]}`}
      >
        {state}
      </span>
    </span>
  );
}

// ---------- Type treatment ----------

type TypeTreatment = {
  wrapper: string;
  title: string;
  content: string;
  label: string;
};

const defaultTreatment: TypeTreatment = {
  wrapper: "pl-5 border-l border-rule",
  title: "font-serif text-2xl text-ink leading-snug",
  content: "",
  label: "",
};

const typeTreatments: Record<SectionType, TypeTreatment> = {
  // Lighter rule, slightly larger body — reads like the opening paragraph
  summary: {
    wrapper: "pl-5 border-l border-rule/60",
    title: "font-serif text-2xl text-ink leading-snug",
    content: "text-[1.0625rem]",
    label: "",
  },
  finding: defaultTreatment,
  // Recommendations stand out — the accent rule signals "do this"
  recommendation: {
    wrapper: "pl-5 border-l-2 border-accent",
    title: "font-serif text-2xl text-ink leading-snug",
    content: "",
    label: "text-accent",
  },
  // Evidence is quieter, supportive; citations read as mono references
  evidence: {
    wrapper: "pl-5 border-l border-rule",
    title: "font-serif text-xl text-ink leading-snug",
    content: "text-[0.95rem]",
    label: "",
  },
  // Open questions: reflective, unresolved, serif italic
  open_question: {
    wrapper: "pl-5 border-l border-rule",
    title: "font-serif italic text-2xl text-ink-muted leading-snug",
    content: "italic text-ink-muted",
    label: "italic text-ink-muted",
  },
  // Decision-needed: amber left rule draws the eye
  decision_needed: {
    wrapper: "pl-5 border-l-2 border-attention",
    title: "font-serif text-2xl text-ink leading-snug",
    content: "",
    label: "text-attention",
  },
  // Ruled out: dismissed—user sees it without being distracted
  ruled_out: {
    wrapper: "pl-5 border-l border-rule opacity-70",
    title: "font-serif text-xl text-ink-muted line-through leading-snug",
    content: "text-ink-muted",
    label: "text-ink-faint",
  },
};

function typeLabel(t: SectionType): string {
  return t.replace(/_/g, " ");
}

// ---------- Markdown rendering (scoped .prose) ----------

// Scoped prose: section titles are h2 in the card, so markdown h1/h2
// render visually at h3/h4 weight to keep the hierarchy clean.
const mdComponents = {
  p: (props: any) => (
    <p className="mb-4 last:mb-0 leading-relaxed" {...props} />
  ),
  h1: (props: any) => (
    <h3
      className="font-serif text-lg text-ink mt-5 mb-2 first:mt-0"
      {...props}
    />
  ),
  h2: (props: any) => (
    <h4
      className="font-serif text-base text-ink mt-4 mb-2 first:mt-0"
      {...props}
    />
  ),
  h3: (props: any) => (
    <h5
      className="font-serif text-base text-ink mt-3 mb-1.5 first:mt-0 font-semibold"
      {...props}
    />
  ),
  h4: (props: any) => (
    <h6
      className="font-serif text-sm text-ink-muted mt-3 mb-1.5 first:mt-0 font-semibold uppercase tracking-wide"
      {...props}
    />
  ),
  ul: (props: any) => (
    <ul className="list-disc pl-6 mb-4 space-y-1" {...props} />
  ),
  ol: (props: any) => (
    <ol className="list-decimal pl-6 mb-4 space-y-1" {...props} />
  ),
  li: (props: any) => <li className="leading-relaxed" {...props} />,
  blockquote: (props: any) => (
    <blockquote
      className="border-l-2 border-rule pl-4 italic text-ink-muted my-4"
      {...props}
    />
  ),
  table: (props: any) => (
    <div className="my-4 overflow-x-auto">
      <table className="w-full border-collapse font-sans text-sm" {...props} />
    </div>
  ),
  thead: (props: any) => <thead className="border-b border-rule-strong" {...props} />,
  th: (props: any) => (
    <th
      className="text-left py-1.5 pr-4 font-semibold text-ink"
      {...props}
    />
  ),
  td: (props: any) => (
    <td className="py-1.5 pr-4 border-b border-rule align-top" {...props} />
  ),
  code: ({ className, children, ...props }: any) => {
    const isBlock = /^language-/.test(className || "");
    if (isBlock) {
      return (
        <code
          className="font-mono text-sm bg-surface-sunk p-3 rounded overflow-x-auto block my-4"
          {...props}
        >
          {children}
        </code>
      );
    }
    return (
      <code
        className="font-mono text-sm bg-surface-sunk px-1 rounded"
        {...props}
      >
        {children}
      </code>
    );
  },
  pre: (props: any) => <pre className="m-0" {...props} />,
  a: (props: any) => (
    <a
      target="_blank"
      rel="noopener noreferrer"
      className="text-accent underline hover:text-accent-hover"
      {...props}
    />
  ),
  hr: (props: any) => <hr className="border-rule my-6" {...props} />,
  strong: (props: any) => (
    <strong className="font-semibold text-ink" {...props} />
  ),
  em: (props: any) => <em className="italic" {...props} />,
};

// ---------- Dependencies link ----------

function DependencyLinks({
  ids,
  titleById,
}: {
  ids: string[];
  titleById: Map<string, string>;
}) {
  if (ids.length === 0) return null;
  return (
    <div className="pt-3 text-xs font-serif italic text-ink-faint">
      Builds on:{" "}
      {ids.map((id, idx) => {
        const t = titleById.get(id);
        const label = t ?? id.slice(0, 8);
        return (
          <React.Fragment key={id}>
            {idx > 0 ? <span>, </span> : null}
            <a
              href={`#section-${id}`}
              className="not-italic text-accent hover:text-accent-hover underline"
            >
              {label}
            </a>
          </React.Fragment>
        );
      })}
    </div>
  );
}

// ---------- Card ----------

export interface SectionCardFullProps extends SectionCardProps {
  titleById?: Map<string, string>;
}

export function SectionCard({ section, titleById }: SectionCardFullProps) {
  const treatment = typeTreatments[section.type] ?? defaultTreatment;
  const content = section.content ?? "";
  const hasContent = content.trim().length > 0;
  const hasChangeNote =
    section.change_note && section.change_note.trim().length > 0;

  const isLong = content.length > COLLAPSE_THRESHOLD;
  // Blocked sections must stay expanded — user needs to see why.
  const mustExpand = section.state === "blocked";
  const [expanded, setExpanded] = useState<boolean>(!isLong || mustExpand);

  const showFull = expanded || mustExpand || !isLong;
  const previewText = useMemo(() => {
    if (!isLong) return content;
    // Cut on a whitespace boundary near PREVIEW_CHARS for cleaner breaks.
    const slice = content.slice(0, PREVIEW_CHARS);
    const lastSpace = slice.lastIndexOf(" ");
    const cut = lastSpace > PREVIEW_CHARS - 60 ? lastSpace : PREVIEW_CHARS;
    return content.slice(0, cut).trimEnd() + "…";
  }, [content, isLong]);

  const depTitles = titleById ?? new Map<string, string>();
  const depIds = section.depends_on ?? [];

  return (
    <article
      id={`section-${section.id}`}
      className={`scroll-mt-24 ${treatment.wrapper}`}
    >
      {/* Overline: type · state · change_note */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px]">
        <span
          className={`font-mono uppercase tracking-wider text-ink-faint ${treatment.label}`}
        >
          {typeLabel(section.type)}
        </span>
        <span aria-hidden="true" className="text-ink-faint">
          ·
        </span>
        <StatePip state={section.state} />
        {hasChangeNote ? (
          <span className="font-serif italic text-ink-muted text-xs basis-full sm:basis-auto sm:before:content-['·_'] sm:before:text-ink-faint">
            {section.change_note}
          </span>
        ) : null}
      </div>

      {/* Title */}
      <h2 className={`mt-2 break-words ${treatment.title}`}>
        {section.title}
      </h2>

      {/* Body */}
      <div
        className={`prose mt-4 max-w-[70ch] font-serif text-base text-ink leading-relaxed ${treatment.content}`}
      >
        {hasContent ? (
          showFull ? (
            <ReactMarkdown components={mdComponents as any}>
              {content}
            </ReactMarkdown>
          ) : (
            <>
              <p className="mb-3 leading-relaxed">{previewText}</p>
              <button
                type="button"
                onClick={() => setExpanded(true)}
                className="font-mono text-xs text-accent hover:text-accent-hover underline"
                aria-expanded={false}
              >
                Show full
              </button>
            </>
          )
        ) : (
          <p className="italic text-ink-faint">(no content yet)</p>
        )}
      </div>

      {/* Collapse back up, only when user expanded a long section */}
      {hasContent && isLong && showFull && !mustExpand ? (
        <div className="mt-2 max-w-[70ch]">
          <button
            type="button"
            onClick={() => setExpanded(false)}
            className="font-mono text-xs text-ink-faint hover:text-ink-muted underline"
            aria-expanded={true}
          >
            Show less
          </button>
        </div>
      ) : null}

      {/* Sources */}
      {section.sources && section.sources.length > 0 ? (
        <div className="mt-4 max-w-[70ch]">
          <SourceList sources={section.sources} />
        </div>
      ) : null}

      {/* Depends-on */}
      <DependencyLinks ids={depIds} titleById={depTitles} />

      {/* Last updated */}
      <div className="pt-3 font-mono text-[11px] text-ink-faint">
        updated {relativeTime(section.last_updated)}
      </div>
    </article>
  );
}

export default SectionCard;
