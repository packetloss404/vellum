import React from "react";
import type { Source } from "../../api/types";

/**
 * SourceList — renders a section's citations in a tight, notebook-footnote
 * style list. Web sources become links; pastes and reasoning entries are
 * rendered as italic provenance labels.
 */

export interface SourceListProps {
  sources: Source[];
}

function safeHostname(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function WebSourceItem({ source }: { source: Source }) {
  const label =
    source.title && source.title.trim().length > 0
      ? source.title
      : source.url
      ? safeHostname(source.url)
      : "(untitled source)";

  if (!source.url) {
    return (
      <span className="font-mono text-xs text-ink-muted">{label}</span>
    );
  }

  return (
    <a
      href={source.url}
      target="_blank"
      rel="noopener noreferrer"
      className="font-mono text-xs text-accent hover:text-accent-hover underline break-words"
    >
      {label}
    </a>
  );
}

export function SourceList({ sources }: SourceListProps) {
  if (!sources || sources.length === 0) {
    return null;
  }

  return (
    <div className="pt-2">
      <div className="text-xs uppercase tracking-wide text-ink-faint font-sans mb-1.5">
        Sources
      </div>
      <ul className="space-y-1 list-none">
        {sources.map((source, idx) => {
          const key = `${source.kind}-${source.url ?? source.title ?? idx}-${idx}`;
          if (source.kind === "web") {
            return (
              <li key={key}>
                <WebSourceItem source={source} />
              </li>
            );
          }
          if (source.kind === "user_paste") {
            return (
              <li
                key={key}
                className="italic text-ink-muted text-xs font-serif"
              >
                Pasted by you: {source.title ?? "(untitled)"}
              </li>
            );
          }
          return (
            <li
              key={key}
              className="italic text-ink-muted text-xs font-serif"
            >
              Reasoning: {source.title ?? "(untitled)"}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export default SourceList;
