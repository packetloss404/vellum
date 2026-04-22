import React, { useState } from "react";
import type { Artifact } from "../../api/types";
import { Pill } from "../common/Pill";
import { truncate } from "../../utils/format";
import { relativeTime } from "../../utils/time";

/**
 * ArtifactList — read-only list of artifacts produced during the
 * investigation (letters, scripts, comparisons, etc.). Each row shows
 * kind + title; clicking expands to reveal the content.
 *
 * Day-3 scaffold; day 4 may render each kind with its own layout.
 */

export interface ArtifactListProps {
  artifacts: Artifact[];
}

const PREVIEW_LEN = 200;

function ArtifactRow({ artifact }: { artifact: Artifact }) {
  const [expanded, setExpanded] = useState(false);
  const hasContent = (artifact.content ?? "").trim().length > 0;
  const preview = hasContent ? truncate(artifact.content, PREVIEW_LEN) : "";
  const chevron = expanded ? "▾" : "▸";

  return (
    <li
      id={`artifact-${artifact.id}`}
      className="scroll-mt-24 border-t border-rule pt-4 first:border-t-0 first:pt-0"
    >
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        aria-expanded={expanded}
        className="w-full text-left group"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span
                aria-hidden="true"
                className="font-mono text-xs w-3 inline-block text-ink-faint"
              >
                {chevron}
              </span>
              <span className="font-mono text-xs uppercase tracking-wide text-ink-faint">
                {artifact.kind}
              </span>
              <h3 className="font-serif text-base text-ink leading-snug group-hover:text-accent transition-colors">
                {artifact.title}
              </h3>
            </div>
            <div className="mt-1 pl-5 text-xs font-mono text-ink-faint flex flex-wrap gap-x-2">
              <span>updated {relativeTime(artifact.last_updated)}</span>
            </div>
          </div>
          <Pill>{artifact.state}</Pill>
        </div>
      </button>

      {!expanded && hasContent ? (
        <p className="mt-2 pl-5 text-sm font-serif text-ink-muted leading-relaxed">
          {preview}
        </p>
      ) : null}

      {expanded ? (
        <div className="mt-3 pl-5">
          {artifact.intended_use &&
          artifact.intended_use.trim().length > 0 ? (
            <div className="mb-3 text-xs font-mono text-ink-faint italic">
              Intended use: {artifact.intended_use}
            </div>
          ) : null}
          {hasContent ? (
            <pre className="font-serif text-base text-ink leading-relaxed whitespace-pre-wrap m-0">
              {artifact.content}
            </pre>
          ) : (
            <p className="italic text-ink-faint font-serif">(no content yet)</p>
          )}
        </div>
      ) : null}
    </li>
  );
}

export function ArtifactList({ artifacts }: ArtifactListProps) {
  if (!artifacts || artifacts.length === 0) return null;

  return (
    <section className="space-y-4">
      <h2 className="font-mono text-xs uppercase tracking-wide text-ink-faint">
        Artifacts ({artifacts.length})
      </h2>
      <ul className="space-y-4 list-none p-0 m-0">
        {artifacts.map((a) => (
          <ArtifactRow key={a.id} artifact={a} />
        ))}
      </ul>
    </section>
  );
}

export default ArtifactList;
