import React from "react";
import ReactMarkdown from "react-markdown";
import type { Section } from "../../api/types";
import { Pill } from "../common/Pill";
import { SourceList } from "./SourceList";
import { relativeTime } from "../../utils/time";

/**
 * SectionCard — a single dossier section rendered as a typeset notebook
 * entry. Title, state, metadata, markdown body, sources, and an optional
 * change-note footer. No sidebar, no chrome; just a well-set page.
 */

export interface SectionCardProps {
  section: Section;
}

const markdownClassNames = {
  wrapper: "text-base font-serif leading-relaxed text-ink",
  paragraph: "mb-4 last:mb-0",
  heading1: "font-serif text-2xl text-ink mt-6 mb-3 first:mt-0",
  heading2: "font-serif text-xl text-ink mt-5 mb-2 first:mt-0",
  heading3: "font-serif text-lg text-ink mt-4 mb-2 first:mt-0",
  list: "list-disc pl-6 mb-4 space-y-1",
  orderedList: "list-decimal pl-6 mb-4 space-y-1",
  listItem: "font-serif text-ink",
  blockquote:
    "border-l-2 border-rule pl-4 italic text-ink-muted my-4 font-serif",
  inlineCode: "font-mono text-sm bg-surface-sunk px-1 rounded",
  codeBlock:
    "font-mono text-sm bg-surface-sunk p-3 rounded overflow-x-auto my-4 block",
  link: "text-accent underline hover:text-accent-hover",
  hr: "border-rule my-6",
  strong: "font-semibold text-ink",
  em: "italic",
};

export function SectionCard({ section }: SectionCardProps) {
  const hasContent = section.content && section.content.trim().length > 0;
  const sourceCount = section.sources?.length ?? 0;
  const hasChangeNote =
    section.change_note && section.change_note.trim().length > 0;

  return (
    <section className="space-y-4 border-t border-rule pt-8 pb-2 first:border-t-0 first:pt-0">
      <div className="flex items-start justify-between gap-4">
        <h2 className="text-xl font-serif text-ink leading-snug break-words min-w-0 flex-1">
          {section.title}
        </h2>
        <div className="shrink-0 pt-1">
          <Pill variant="state" state={section.state}>
            {section.state === "confident" ? (
              <span
                aria-hidden="true"
                className="inline-block h-1.5 w-1.5 rounded-full bg-state-confident"
              />
            ) : null}
            <span>{section.state}</span>
          </Pill>
        </div>
      </div>

      <div className="text-xs font-mono text-ink-faint flex flex-wrap items-center gap-x-2">
        <span>{section.type}</span>
        <span aria-hidden="true">·</span>
        <span>{relativeTime(section.last_updated)}</span>
        {sourceCount > 0 ? (
          <>
            <span aria-hidden="true">·</span>
            <span>
              {sourceCount} {sourceCount === 1 ? "source" : "sources"}
            </span>
          </>
        ) : null}
      </div>

      <div className={markdownClassNames.wrapper}>
        {hasContent ? (
          <ReactMarkdown
            components={{
              p: ({ node, ...props }) => (
                <p className={markdownClassNames.paragraph} {...props} />
              ),
              h1: ({ node, ...props }) => (
                <h1 className={markdownClassNames.heading1} {...props} />
              ),
              h2: ({ node, ...props }) => (
                <h2 className={markdownClassNames.heading2} {...props} />
              ),
              h3: ({ node, ...props }) => (
                <h3 className={markdownClassNames.heading3} {...props} />
              ),
              ul: ({ node, ...props }) => (
                <ul className={markdownClassNames.list} {...props} />
              ),
              ol: ({ node, ...props }) => (
                <ol className={markdownClassNames.orderedList} {...props} />
              ),
              li: ({ node, ...props }) => (
                <li className={markdownClassNames.listItem} {...props} />
              ),
              blockquote: ({ node, ...props }) => (
                <blockquote
                  className={markdownClassNames.blockquote}
                  {...props}
                />
              ),
              code: ({ node, className, children, ...props }: any) => {
                // react-markdown v9 removed the `inline` prop; detect by the
                // absence of a language-* className (set only on block code).
                const isBlock = /^language-/.test(className || "");
                return (
                  <code
                    className={
                      isBlock
                        ? markdownClassNames.codeBlock
                        : markdownClassNames.inlineCode
                    }
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
                  className={markdownClassNames.link}
                  {...props}
                />
              ),
              hr: ({ node, ...props }) => (
                <hr className={markdownClassNames.hr} {...props} />
              ),
              strong: ({ node, ...props }) => (
                <strong className={markdownClassNames.strong} {...props} />
              ),
              em: ({ node, ...props }) => (
                <em className={markdownClassNames.em} {...props} />
              ),
            }}
          >
            {section.content}
          </ReactMarkdown>
        ) : (
          <p className="italic text-ink-faint font-serif">(no content yet)</p>
        )}
      </div>

      <SourceList sources={section.sources} />

      {hasChangeNote ? (
        <div className="text-sm text-ink-muted font-serif italic pt-2">
          Change note — {section.change_note}
        </div>
      ) : null}
    </section>
  );
}

export default SectionCard;
