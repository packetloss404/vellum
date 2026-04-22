import React, { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import type { Artifact, ArtifactKind, ArtifactState } from "../../api/types";

/**
 * ArtifactCard — a single usable output from the investigation (a letter,
 * script, comparison, timeline, checklist, offer template, etc.). The card
 * looks like something you can tear off the page: kind chip, title, one-
 * line intended use, markdown body, and a copy-to-clipboard affordance.
 *
 * Long content collapses by default so a dossier with many artifacts
 * still scans cleanly. Anchored by `id="artifact-<id>"` so the
 * investigation-log sidebar can deep-link into a specific card.
 */

export interface ArtifactCardProps {
  artifact: Artifact;
  /**
   * Map of artifact id → artifact title for rendering the "Revises {title}"
   * back-reference when `supersedes` is set. If a prior artifact isn't
   * in the map we fall back to the raw id, still as an in-page link.
   */
  priorTitles?: Record<string, string>;
}

const COLLAPSE_CHAR_THRESHOLD = 400;
const COLLAPSED_PREVIEW_CHARS = 200;
const COPY_FEEDBACK_MS = 2000;

// ---------- Kind badge styling ----------

const KIND_LABELS: Record<ArtifactKind, string> = {
  letter: "LETTER",
  script: "SCRIPT",
  comparison: "COMPARISON",
  timeline: "TIMELINE",
  checklist: "CHECKLIST",
  offer: "OFFER",
  other: "OTHER",
};

const KIND_CLASSES: Record<ArtifactKind, string> = {
  letter: "bg-kind-letter-bg text-kind-letter",
  script: "bg-kind-script-bg text-kind-script",
  comparison: "bg-kind-comparison-bg text-kind-comparison",
  timeline: "bg-kind-timeline-bg text-kind-timeline",
  checklist: "bg-kind-checklist-bg text-kind-checklist",
  offer: "bg-kind-offer-bg text-kind-offer",
  other: "bg-kind-other-bg text-kind-other",
};

function KindBadge({ kind }: { kind: ArtifactKind }) {
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 text-[10px] font-mono tracking-wider rounded ${KIND_CLASSES[kind]}`}
    >
      {KIND_LABELS[kind]}
    </span>
  );
}

// ---------- State badge styling ----------

const STATE_CLASSES: Record<ArtifactState, string> = {
  draft: "text-ink-faint border-rule",
  ready: "text-state-confident border-state-confident/40",
  superseded: "text-ink-faint italic border-rule",
};

function StateBadge({ state }: { state: ArtifactState }) {
  return (
    <span
      className={`inline-flex items-center px-1.5 py-0.5 text-[10px] font-mono tracking-wide rounded border bg-transparent ${STATE_CLASSES[state]}`}
    >
      {state}
    </span>
  );
}

// ---------- Markdown scope ----------
//
// Artifact content is rendered inside a `.artifact-prose` wrapper. Headings
// inside artifact content are intentionally smaller than the card's own
// title (which is text-xl serif) so the artifact title always reads as
// the top of the card. h1 inside prose → text-base; h2 → text-sm; etc.
// See `src/styles` (scoped via arbitrary Tailwind in this component).

const proseHeading1 =
  "font-serif text-base text-ink mt-4 mb-2 first:mt-0 leading-snug";
const proseHeading2 =
  "font-serif text-sm text-ink mt-3 mb-2 first:mt-0 leading-snug uppercase tracking-wide font-semibold";
const proseHeading3 =
  "font-serif text-sm text-ink mt-3 mb-1 first:mt-0 italic";
const proseParagraph = "font-serif text-base text-ink leading-relaxed mb-3 last:mb-0";
const proseList = "list-disc pl-6 mb-3 space-y-1 font-serif text-ink";
const proseOrderedList =
  "list-decimal pl-6 mb-3 space-y-1 font-serif text-ink";
const proseBlockquote =
  "border-l-2 border-rule pl-4 italic text-ink-muted my-3 font-serif";
const proseInlineCode =
  "font-mono text-sm bg-surface-sunk px-1 py-0.5 rounded";
const proseCodeBlock =
  "font-mono text-sm bg-surface-sunk p-3 rounded overflow-x-auto my-3 block whitespace-pre";
const proseLink = "text-accent underline hover:text-accent-hover";
const proseHr = "border-rule my-4";
const proseTableWrap = "overflow-x-auto my-3";
const proseTable =
  "w-full border-collapse text-sm font-serif text-ink";
const proseTh =
  "border border-rule px-2 py-1 text-left font-semibold bg-surface-sunk";
const proseTd = "border border-rule px-2 py-1 align-top";

function ArtifactMarkdown({ content }: { content: string }) {
  return (
    <div className="max-w-[70ch]">
      <ReactMarkdown
        // `disallowedElements` covers raw HTML — react-markdown v9 only
        // emits HTML when `rehype-raw` is active (it's not), so inline
        // HTML is already rendered as text. We still restrict to the
        // element set we style to avoid surprises.
        allowedElements={[
          "p",
          "strong",
          "em",
          "a",
          "ul",
          "ol",
          "li",
          "blockquote",
          "code",
          "pre",
          "h1",
          "h2",
          "h3",
          "h4",
          "h5",
          "h6",
          "table",
          "thead",
          "tbody",
          "tr",
          "th",
          "td",
          "hr",
          "br",
        ]}
        components={{
          p: ({ node, ...props }) => (
            <p className={proseParagraph} {...props} />
          ),
          h1: ({ node, ...props }) => (
            <h1 className={proseHeading1} {...props} />
          ),
          h2: ({ node, ...props }) => (
            <h2 className={proseHeading2} {...props} />
          ),
          h3: ({ node, ...props }) => (
            <h3 className={proseHeading3} {...props} />
          ),
          h4: ({ node, ...props }) => (
            <h4 className={proseHeading3} {...props} />
          ),
          h5: ({ node, ...props }) => (
            <h5 className={proseHeading3} {...props} />
          ),
          h6: ({ node, ...props }) => (
            <h6 className={proseHeading3} {...props} />
          ),
          ul: ({ node, ...props }) => (
            <ul className={proseList} {...props} />
          ),
          ol: ({ node, ...props }) => (
            <ol className={proseOrderedList} {...props} />
          ),
          li: ({ node, ...props }) => <li {...props} />,
          blockquote: ({ node, ...props }) => (
            <blockquote className={proseBlockquote} {...props} />
          ),
          code: ({ node, className, children, ...props }: any) => {
            const isBlock = /^language-/.test(className || "");
            return (
              <code
                className={isBlock ? proseCodeBlock : proseInlineCode}
                {...props}
              >
                {children}
              </code>
            );
          },
          a: ({ node, ...props }) => (
            <a
              target="_blank"
              rel="noopener noreferrer"
              className={proseLink}
              {...props}
            />
          ),
          hr: ({ node, ...props }) => <hr className={proseHr} {...props} />,
          strong: ({ node, ...props }) => (
            <strong className="font-semibold text-ink" {...props} />
          ),
          em: ({ node, ...props }) => <em className="italic" {...props} />,
          table: ({ node, ...props }) => (
            <div className={proseTableWrap}>
              <table className={proseTable} {...props} />
            </div>
          ),
          th: ({ node, ...props }) => <th className={proseTh} {...props} />,
          td: ({ node, ...props }) => <td className={proseTd} {...props} />,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

// ---------- Copy button ----------

function CopyButton({ content }: { content: string }) {
  const [copied, setCopied] = useState(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (timeoutRef.current !== null) clearTimeout(timeoutRef.current);
    },
    [],
  );

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(content);
    } catch {
      // Clipboard blocked (e.g. insecure context). Fail quiet — the
      // button still flashes so the user sees their click was received.
    }
    setCopied(true);
    if (timeoutRef.current !== null) clearTimeout(timeoutRef.current);
    timeoutRef.current = setTimeout(() => {
      setCopied(false);
      timeoutRef.current = null;
    }, COPY_FEEDBACK_MS);
  }

  return (
    <button
      type="button"
      onClick={handleCopy}
      className="inline-flex items-center gap-1 px-2 py-1 text-xs font-mono rounded border border-rule text-ink-muted hover:text-accent hover:border-accent transition-colors"
      aria-live="polite"
    >
      {copied ? "Copied ✓" : "Copy"}
    </button>
  );
}

// ---------- Main card ----------

export function ArtifactCard({ artifact, priorTitles }: ArtifactCardProps) {
  const content = artifact.content ?? "";
  const hasContent = content.trim().length > 0;
  const isLong = content.length > COLLAPSE_CHAR_THRESHOLD;
  const [expanded, setExpanded] = useState(!isLong);

  const priorId = artifact.supersedes;
  const priorLabel =
    priorId && priorTitles && priorTitles[priorId]
      ? priorTitles[priorId]
      : priorId ?? null;

  const previewText = isLong
    ? content.slice(0, COLLAPSED_PREVIEW_CHARS).trimEnd() + "…"
    : content;

  return (
    <article
      id={`artifact-${artifact.id}`}
      className="bg-surface border border-rule rounded p-6 scroll-mt-8"
    >
      {/* Header row: kind badge + title on the left, state + copy on the right. */}
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-2">
            <KindBadge kind={artifact.kind} />
            <StateBadge state={artifact.state} />
          </div>
          <h3 className="font-serif text-xl text-ink leading-snug break-words">
            {artifact.title}
          </h3>
          {artifact.intended_use && artifact.intended_use.trim().length > 0 ? (
            <p className="mt-1 font-sans text-sm text-ink-muted">
              {artifact.intended_use}
            </p>
          ) : null}
          {priorId ? (
            <p className="mt-1 text-xs font-mono text-ink-faint">
              Revises{" "}
              <a
                href={`#artifact-${priorId}`}
                className="underline hover:text-accent"
              >
                {priorLabel}
              </a>
            </p>
          ) : null}
        </div>
        <div className="shrink-0 flex items-center gap-2 pt-1">
          {hasContent ? <CopyButton content={content} /> : null}
        </div>
      </div>

      {/* Body */}
      <div className="mt-4">
        {hasContent ? (
          expanded ? (
            <ArtifactMarkdown content={content} />
          ) : (
            <div>
              <p className="font-serif text-base text-ink leading-relaxed whitespace-pre-wrap">
                {previewText}
              </p>
              <button
                type="button"
                onClick={() => setExpanded(true)}
                className="mt-2 text-xs font-mono text-accent hover:text-accent-hover underline"
              >
                Show full
              </button>
            </div>
          )
        ) : (
          <p className="italic text-ink-faint font-serif">(no content yet)</p>
        )}

        {hasContent && isLong && expanded ? (
          <button
            type="button"
            onClick={() => setExpanded(false)}
            className="mt-3 text-xs font-mono text-ink-faint hover:text-accent underline"
          >
            Collapse
          </button>
        ) : null}
      </div>

      {artifact.kind_note && artifact.kind_note.trim().length > 0 ? (
        <p className="mt-4 text-xs font-mono text-ink-faint italic">
          {artifact.kind_note}
        </p>
      ) : null}
    </article>
  );
}

export default ArtifactCard;
