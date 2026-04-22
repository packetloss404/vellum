import React, { useMemo, useState } from "react";
import type { Artifact, ArtifactKind, ArtifactState } from "../../api/types";
import { ArtifactCard } from "./ArtifactCard";

/**
 * ArtifactList — the "Artifacts" pane of a dossier. Shows every drafted
 * letter / script / comparison / timeline / checklist / offer / other
 * as its own card (see ArtifactCard). For dossiers with a lot of
 * output, filter chips let the user narrow by kind or state, and a
 * sort toggle flips chronological order.
 *
 * By default we hide `superseded` artifacts — the newer revision
 * subsumes the older one and the card-level "Revises X" link keeps
 * provenance legible.
 */

export interface ArtifactListProps {
  artifacts: Artifact[];
}

type KindFilter = ArtifactKind | "all";
type StateFilter = "active" | "all" | ArtifactState;
type SortOrder = "asc" | "desc";

const KIND_ORDER: ArtifactKind[] = [
  "letter",
  "script",
  "comparison",
  "timeline",
  "checklist",
  "offer",
  "other",
];

const KIND_LABELS: Record<ArtifactKind, string> = {
  letter: "letters",
  script: "scripts",
  comparison: "comparisons",
  timeline: "timelines",
  checklist: "checklists",
  offer: "offers",
  other: "other",
};

function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        "px-2 py-0.5 text-xs font-mono rounded border transition-colors " +
        (active
          ? "bg-accent-bg text-accent border-accent"
          : "bg-transparent text-ink-muted border-rule hover:border-rule-strong")
      }
    >
      {children}
    </button>
  );
}

export function ArtifactList({ artifacts }: ArtifactListProps) {
  const total = artifacts?.length ?? 0;

  // Present in the artifacts list — used to decide which kind chips to show.
  const presentKinds = useMemo(() => {
    const set = new Set<ArtifactKind>();
    for (const a of artifacts ?? []) set.add(a.kind);
    return KIND_ORDER.filter((k) => set.has(k));
  }, [artifacts]);

  const showKindChips = total > 3 && presentKinds.length > 1;
  const hasSuperseded = useMemo(
    () => (artifacts ?? []).some((a) => a.state === "superseded"),
    [artifacts],
  );

  const [kindFilter, setKindFilter] = useState<KindFilter>("all");
  const [stateFilter, setStateFilter] = useState<StateFilter>("active");
  const [sortOrder, setSortOrder] = useState<SortOrder>("asc");

  const filtered = useMemo(() => {
    const list = (artifacts ?? []).filter((a) => {
      if (kindFilter !== "all" && a.kind !== kindFilter) return false;
      if (stateFilter === "active") {
        if (a.state === "superseded") return false;
      } else if (stateFilter !== "all") {
        if (a.state !== stateFilter) return false;
      }
      return true;
    });
    list.sort((a, b) => {
      const aT = new Date(a.created_at).getTime();
      const bT = new Date(b.created_at).getTime();
      return sortOrder === "asc" ? aT - bT : bT - aT;
    });
    return list;
  }, [artifacts, kindFilter, stateFilter, sortOrder]);

  // Map of id → title so "Revises X" anchors render a human label.
  const priorTitles = useMemo(() => {
    const map: Record<string, string> = {};
    for (const a of artifacts ?? []) map[a.id] = a.title;
    return map;
  }, [artifacts]);

  // Empty state: no artifacts at all (vs. filtered to zero).
  if (total === 0) {
    return (
      <section className="space-y-4">
        <h2 className="font-mono text-xs uppercase tracking-wide text-ink-faint">
          Artifacts
        </h2>
        <p className="font-serif italic text-ink-faint">
          No artifacts drafted yet.
        </p>
      </section>
    );
  }

  const countLabel = `${total} drafted`;

  return (
    <section className="space-y-4">
      <div className="flex items-baseline justify-between gap-4 flex-wrap">
        <h2 className="font-mono text-xs uppercase tracking-wide text-ink-faint">
          Artifacts
          <span className="ml-2 text-ink-faint normal-case tracking-normal">
            ({countLabel})
          </span>
        </h2>
        <button
          type="button"
          onClick={() =>
            setSortOrder((s) => (s === "asc" ? "desc" : "asc"))
          }
          className="text-xs font-mono text-ink-muted hover:text-accent underline"
        >
          {sortOrder === "asc" ? "Oldest first" : "Newest first"}
        </button>
      </div>

      {showKindChips ? (
        <div className="flex flex-wrap gap-2" role="toolbar" aria-label="Filter by kind">
          <Chip
            active={kindFilter === "all"}
            onClick={() => setKindFilter("all")}
          >
            all
          </Chip>
          {presentKinds.map((k) => (
            <Chip
              key={k}
              active={kindFilter === k}
              onClick={() => setKindFilter(k)}
            >
              {KIND_LABELS[k]}
            </Chip>
          ))}
        </div>
      ) : null}

      {hasSuperseded ? (
        <div className="flex flex-wrap gap-2" role="toolbar" aria-label="Filter by state">
          <Chip
            active={stateFilter === "active"}
            onClick={() => setStateFilter("active")}
          >
            hide superseded
          </Chip>
          <Chip
            active={stateFilter === "all"}
            onClick={() => setStateFilter("all")}
          >
            show all
          </Chip>
          <Chip
            active={stateFilter === "superseded"}
            onClick={() => setStateFilter("superseded")}
          >
            superseded only
          </Chip>
        </div>
      ) : null}

      {filtered.length === 0 ? (
        <p className="font-serif italic text-ink-faint">
          No artifacts match the current filter.
        </p>
      ) : (
        <div className="space-y-4">
          {filtered.map((a) => (
            <ArtifactCard
              key={a.id}
              artifact={a}
              priorTitles={priorTitles}
            />
          ))}
        </div>
      )}
    </section>
  );
}

export default ArtifactList;
