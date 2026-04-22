import React from "react";
import { Link } from "react-router-dom";
import { Header } from "../components/layout/Header";
import { EmptyState } from "../components/common/EmptyState";
import { DossierCard } from "../components/dossier/DossierCard";
import { useDossierList } from "../api/hooks";
import { useDocumentTitle } from "../utils/useDocumentTitle";

/**
 * DossierListPage — the landing view at "/".
 *
 * A quiet index of the user's dossiers: one line of encouragement, one
 * CTA to start a new one, and below it a stack of DossierCards. Day 3
 * is scaffold; day 4 polishes the presentation.
 *
 * Dossier counts (sections / sub-investigations / artifacts) are read
 * from whatever the list endpoint returns. If the backend doesn't yet
 * serialize them onto the row (reasonable — DossierFull is the richer
 * payload), the card simply omits the counts chip.
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

export default function DossierListPage() {
  useDocumentTitle("Vellum");
  const { data, isLoading, error } = useDossierList();

  return (
    <div className="min-h-screen bg-paper">
      <Header />

      <main className="max-w-prose mx-auto py-16 px-6">
        <h1 className="text-3xl font-serif text-ink mb-2 tracking-tight">
          Your dossiers.
        </h1>
        <p className="text-ink-muted font-serif mb-10">
          Durable thinking on problems that deserve it.
        </p>

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
          <>
            <div className="mb-10">
              <NewDossierButton />
            </div>
            <ul className="space-y-6 list-none p-0 m-0">
              {data.map((d) => (
                <li key={d.id}>
                  <DossierCard dossier={d} counts={extractCounts(d)} />
                </li>
              ))}
            </ul>
          </>
        )}
      </main>
    </div>
  );
}
