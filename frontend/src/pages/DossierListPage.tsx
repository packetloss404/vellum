import React from "react";
import { Link } from "react-router-dom";
import { Header } from "../components/layout/Header";
import { EmptyState } from "../components/common/EmptyState";
import { DossierCard } from "../components/dossier/DossierCard";
import { useDossierList } from "../api/hooks";
import { useDocumentTitle } from "../utils/useDocumentTitle";
import type { Dossier } from "../api/types";

/**
 * DossierListPage — the landing view at "/".
 *
 * Visually a "shelf of notebooks" rather than a SaaS table: each dossier
 * is a card in a responsive grid (1 col on narrow, 2 on lg, 3 on xl),
 * anchored by a serif title, its problem statement excerpt, and a quiet
 * mono metadata strip.
 *
 * Counts (sections / sub-investigations / artifacts) are read from the
 * list row if the backend serializes them there; the list page does NOT
 * fan out per-dossier count fetches — that would be N network calls for
 * a landing view, which is never worth it.
 */

function NewDossierButton({ className = "" }: { className?: string }) {
  return (
    <Link
      to="/intake"
      className={
        "inline-flex items-center bg-accent text-paper px-4 py-2 font-sans text-sm rounded hover:bg-accent-hover transition-colors " +
        className
      }
    >
      Open a new dossier
    </Link>
  );
}

// The backend Dossier row may carry counts on extra fields in the future.
// Until then, we pick them off defensively so we don't add a `Dossier &
// { counts?: ... }` type to the shared types file for a maybe-field.
function extractCounts(
  row: unknown,
): { sections?: number; sub_investigations?: number; artifacts?: number } | undefined {
  if (!row || typeof row !== "object") return undefined;
  const r = row as Record<string, unknown>;
  const maybeCounts =
    (r.counts as Record<string, unknown> | undefined) ?? undefined;
  const source = maybeCounts ?? r;
  const sections =
    typeof source.sections === "number"
      ? source.sections
      : typeof source.section_count === "number"
      ? source.section_count
      : undefined;
  const subs =
    typeof source.sub_investigations === "number"
      ? source.sub_investigations
      : typeof source.sub_investigation_count === "number"
      ? source.sub_investigation_count
      : undefined;
  const artifacts =
    typeof source.artifacts === "number"
      ? source.artifacts
      : typeof source.artifact_count === "number"
      ? source.artifact_count
      : undefined;

  if (sections === undefined && subs === undefined && artifacts === undefined) {
    return undefined;
  }
  return {
    sections,
    sub_investigations: subs,
    artifacts,
  };
}

function sortByUpdated(list: readonly Dossier[]): Dossier[] {
  return [...list].sort(
    (a, b) =>
      new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
  );
}

function formatSubhead(list: readonly Dossier[]): string {
  const total = list.length;
  const delivered = list.filter((d) => d.status === "delivered").length;
  const noun = total === 1 ? "investigation" : "investigations";
  const verb = delivered === 1 ? "delivered" : "delivered";
  return `${total} ${noun} · ${delivered} ${verb}`;
}

export default function DossierListPage() {
  useDocumentTitle("Vellum");
  const { data, isLoading, error } = useDossierList();

  const sorted = React.useMemo(
    () => (data ? sortByUpdated(data) : []),
    [data],
  );

  return (
    <div className="min-h-screen bg-paper">
      <Header />

      <main className="mx-auto max-w-page py-16 px-6">
        <div className="flex flex-wrap items-end justify-between gap-6 mb-12">
          <div className="min-w-0">
            <h1 className="text-4xl font-serif text-ink tracking-tight">
              Your dossiers.
            </h1>
            {data && data.length > 0 ? (
              <p className="mt-2 text-sm font-mono text-ink-faint">
                {formatSubhead(data)}
              </p>
            ) : (
              <p className="mt-2 font-serif text-ink-muted">
                Durable thinking on problems that deserve it.
              </p>
            )}
          </div>
          {data && data.length > 0 ? (
            <NewDossierButton className="shrink-0" />
          ) : null}
        </div>

        {isLoading ? (
          <p className="text-ink-faint font-mono text-sm">Loading…</p>
        ) : error ? (
          <p className="text-sm font-serif text-state-blocked">
            Couldn't load dossiers. Try again in a moment.
          </p>
        ) : !data || data.length === 0 ? (
          <EmptyState
            title="No dossiers yet."
            hint="Open a new one to begin."
          >
            <NewDossierButton />
          </EmptyState>
        ) : (
          <ul className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6 list-none p-0 m-0">
            {sorted.map((d) => (
              <li key={d.id} className="h-full">
                <DossierCard dossier={d} counts={extractCounts(d)} />
              </li>
            ))}
          </ul>
        )}
      </main>
    </div>
  );
}
