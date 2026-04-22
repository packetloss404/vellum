import React from "react";
import { Link } from "react-router-dom";
import { Header } from "../components/layout/Header";
import { Card } from "../components/common/Card";
import { Pill } from "../components/common/Pill";
import { EmptyState } from "../components/common/EmptyState";
import { useDossierList } from "../api/hooks";
import { relativeTime } from "../utils/time";
import { useDocumentTitle } from "../utils/useDocumentTitle";
import type { Dossier, DossierStatus } from "../api/types";

/**
 * DossierListPage — the landing view at "/".
 *
 * A quiet index of the user's dossiers: one line of encouragement, one
 * CTA to start a new one, and below it a stack of cards with the title,
 * a truncated problem_statement, and a terse metadata row. No nav chrome
 * beyond the Header. No spinners, no skeletons.
 */

const TRUNCATE_LIMIT = 180;

function truncate(s: string, n: number): string {
  if (!s) return "";
  if (s.length <= n) return s;
  // Trim to last word boundary under the limit so we don't break mid-word.
  const sliced = s.slice(0, n);
  const lastSpace = sliced.lastIndexOf(" ");
  const clean = (lastSpace > 40 ? sliced.slice(0, lastSpace) : sliced).trimEnd();
  return clean + "…";
}

function statusPillVariant(
  status: string,
): "default" | "accent" | "attention" {
  return (status as DossierStatus) === "active" ? "accent" : "default";
}

function NewDossierButton({ className = "" }: { className?: string }) {
  return (
    <Link
      to="/intake"
      className={
        "inline-flex items-center bg-accent text-paper px-4 py-2 font-sans text-sm rounded hover:bg-accent-hover transition-colors " +
        className
      }
    >
      New dossier
    </Link>
  );
}

function DossierRow({ dossier }: { dossier: Dossier }) {
  const preview = truncate(dossier.problem_statement ?? "", TRUNCATE_LIMIT);
  const updated = relativeTime(dossier.updated_at);
  const typeLabel = dossier.dossier_type.replace(/_/g, " ");

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
        <div className="flex items-center gap-2 text-xs font-mono text-ink-faint mt-4">
          <span className="lowercase tracking-wide">{typeLabel}</span>
          <span aria-hidden="true">·</span>
          <span>updated {updated}</span>
          <span aria-hidden="true">·</span>
          <Pill variant={statusPillVariant(dossier.status)}>
            {dossier.status}
          </Pill>
        </div>
      </Card>
    </Link>
  );
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
            hint="Start one to see it here."
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
                  <DossierRow dossier={d} />
                </li>
              ))}
            </ul>
          </>
        )}
      </main>
    </div>
  );
}
