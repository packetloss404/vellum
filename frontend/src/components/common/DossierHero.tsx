import React from "react";

/**
 * DossierHero — the shared top-of-dossier block.
 *
 * Unifies the hero markup between DossierPage and DemoPage. The core shape
 * is: an optional eyebrow (mono, uppercase), an optional serif title, a
 * serif subtitle paragraph, and an optional meta line (pills, timestamps,
 * out-of-scope list — whatever the caller wants). Meta is a ReactNode
 * because the two pages show genuinely different things on that line.
 *
 * This component does not impose column framing — callers wrap it in
 * whatever max-w-prose / border / padding their layout already uses.
 */

interface DossierHeroProps {
  title?: string;
  eyebrow?: string;
  subtitle?: string;
  meta?: React.ReactNode;
  className?: string;
}

export function DossierHero({
  title,
  eyebrow,
  subtitle,
  meta,
  className,
}: DossierHeroProps) {
  return (
    <section className={className}>
      {eyebrow ? (
        <div className="text-xs font-mono uppercase tracking-wide text-ink-faint mb-2">
          {eyebrow}
        </div>
      ) : null}
      {title ? (
        <h1 className="text-3xl font-serif text-ink tracking-tight">
          {title}
        </h1>
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
