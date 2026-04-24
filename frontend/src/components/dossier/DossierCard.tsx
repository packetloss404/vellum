import React from "react";
import { Link } from "react-router-dom";
import type { Dossier, DossierStatus } from "../../api/types";
import { Card } from "../common/Card";
import { Pill } from "../common/Pill";
import { relativeTime } from "../../utils/time";
import { truncate } from "../../utils/format";

/**
 * DossierCard — a single row on the DossierListPage.
 *
 * Shows title + truncated problem_statement + a mono metadata line
 * (status, counts, last_visited_at). Click routes into the detail page.
 * Day-3 scaffold; day-4 polishes the visual hierarchy.
 *
 * `running` is a runtime overlay on the persistent status — when true,
 * we show a live "researching" pill instead of the persistent status.
 * The persistent status (active / paused / delivered) still matters for
 * sorting, completion counts, etc. — we just surface the live state
 * first on the card when it's in flight.
 */

const TRUNCATE_LIMIT = 180;

function statusPill(status: string): {
  variant: "default" | "accent" | "state";
  state?: "confident" | "provisional" | "blocked";
} {
  switch (status as DossierStatus) {
    case "active":
      return { variant: "accent" };
    case "delivered":
      // Confident green for the delivered state, matching the Header.
      return { variant: "state", state: "confident" };
    default:
      return { variant: "default" };
  }
}

interface ResearchingPillProps {}

/**
 * ResearchingPill — live amber pulse, distinct from both the persistent
 * "active" (accent/brown) and the delivered green. Matches the language
 * AgentActivityIndicator uses on the dossier detail page so the same
 * word means the same thing in both places.
 */
function ResearchingPill(_: ResearchingPillProps) {
  return (
    <span className="inline-flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.08em] text-attention">
      <span
        aria-hidden="true"
        className="inline-block h-2 w-2 rounded-full bg-attention animate-pulse"
      />
      researching
    </span>
  );
}

export interface DossierCardProps {
  dossier: Dossier;
  // Counts come from the backend list payload if/when present; we accept
  // them as a separate prop so the list page can wire them up cheaply
  // even before the backend serializes them onto the Dossier row.
  counts?: {
    sections?: number;
    sub_investigations?: number;
    artifacts?: number;
  };
  // True when an agent task is currently in flight for this dossier
  // (GET /api/agents/running reports it). List page fetches once and
  // passes through — no per-card polling.
  running?: boolean;
}

export function DossierCard({ dossier, counts, running }: DossierCardProps) {
  const preview = truncate(dossier.problem_statement ?? "", TRUNCATE_LIMIT);
  const typeLabel = dossier.dossier_type.replace(/_/g, " ");
  const visited = dossier.last_visited_at
    ? relativeTime(dossier.last_visited_at)
    : null;

  const sectionCount = counts?.sections ?? 0;
  const subCount = counts?.sub_investigations ?? 0;
  const artifactCount = counts?.artifacts ?? 0;
  const hasCounts = sectionCount + subCount + artifactCount > 0;

  return (
    <Link
      to={`/dossiers/${dossier.id}`}
      className="block group focus:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded"
    >
      <Card className="transition-colors group-hover:border-rule-strong">
        <div className="text-xl font-serif text-ink group-hover:text-accent transition-colors">
          {dossier.title}
        </div>
        {preview ? (
          <p className="text-sm font-serif text-ink-muted mt-2 leading-relaxed">
            {preview}
          </p>
        ) : null}
        <div className="flex flex-wrap items-center gap-2 text-xs font-mono text-ink-faint mt-4">
          <span className="lowercase tracking-wide">{typeLabel}</span>
          <span aria-hidden="true">·</span>
          {running ? (
            <ResearchingPill />
          ) : (
            (() => {
              const sp = statusPill(dossier.status);
              return (
                <Pill variant={sp.variant} state={sp.state}>
                  {dossier.status}
                </Pill>
              );
            })()
          )}
          {hasCounts ? (
            <>
              <span aria-hidden="true">·</span>
              <span>
                {sectionCount} sections · {subCount} subs · {artifactCount}{" "}
                artifacts
              </span>
            </>
          ) : null}
          <span aria-hidden="true">·</span>
          <span>
            {visited ? `visited ${visited}` : `updated ${relativeTime(dossier.updated_at)}`}
          </span>
        </div>
      </Card>
    </Link>
  );
}

export default DossierCard;
