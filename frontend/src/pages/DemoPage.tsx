import React, { useState } from "react";
import type { NeedsInput } from "../api/types";
import { Header } from "../components/layout/Header";
import { SectionsList } from "../components/sections/SectionsList";
import { RuledOutList } from "../components/sections/RuledOutList";
import { ReasoningTrail } from "../components/sections/ReasoningTrail";
import { DecisionPointBlock } from "../components/decision-points/DecisionPointBlock";
import { PlanDiffSidebarView } from "../components/plan-diff/PlanDiffSidebarView";
import { Card } from "../components/common/Card";
import { DossierHero } from "../components/common/DossierHero";
import { Pill } from "../components/common/Pill";
import { relativeTime } from "../utils/time";
import { useDocumentTitle } from "../utils/useDocumentTitle";
import { MOCK_CHANGE_LOG, MOCK_DOSSIER_FULL } from "../mocks/dossier";

/**
 * DemoPage — a live preview of the hero dossier UI using fixture data.
 *
 * Renders the same component tree as DossierPage, but skips all network
 * calls: sections, needs_input, ruled-out, and the plan-diff sidebar all
 * read from ../mocks/dossier. "Send to dossier" is stubbed to console.log
 * so the visual affordances still respond; the sidebar's "Mark as read"
 * button is omitted entirely on this page (no mutation to run).
 *
 * NeedsInputItem reaches for React Query hooks internally, which we don't
 * want to exercise on this page — so we re-implement its outer shell here
 * against the fixtures, while still sharing the real presentational bits
 * (Card, Pill, PlanDiffSidebarView, etc.).
 */

interface DemoNeedsInputProps {
  item: NeedsInput;
}

function DemoNeedsInputItem({ item }: DemoNeedsInputProps) {
  const [answer, setAnswer] = useState("");
  const trimmed = answer.trim();
  const canSubmit = trimmed.length > 0;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    // eslint-disable-next-line no-console
    console.log("[demo] Send to dossier (no-op):", {
      needsInputId: item.id,
      answer: trimmed,
    });
    setAnswer("");
  }

  return (
    <Card className="border-l-4 border-l-attention">
      <div className="flex items-center justify-between gap-3 mb-3">
        <Pill variant="attention" className="uppercase tracking-wide">
          NEEDS YOU
        </Pill>
        <span className="text-xs text-ink-faint font-mono">
          {relativeTime(item.created_at)}
        </span>
      </div>

      <p className="text-lg font-serif text-ink leading-relaxed">
        {item.question}
      </p>

      <form onSubmit={handleSubmit} className="mt-4">
        <textarea
          value={answer}
          onChange={(e) => setAnswer(e.target.value)}
          rows={3}
          placeholder="Answer in a sentence or two…"
          className="w-full font-serif text-base bg-surface border border-rule rounded px-3 py-2 text-ink placeholder:text-ink-faint focus:outline-none focus:border-accent resize-y"
        />

        <div className="mt-3 flex items-center justify-end gap-3">
          <button
            type="submit"
            disabled={!canSubmit}
            className="bg-accent text-paper font-sans text-sm rounded px-4 py-2 hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Send to dossier
          </button>
        </div>
      </form>
    </Card>
  );
}

export default function DemoPage() {
  useDocumentTitle("Demo · Vellum");

  const {
    dossier,
    sections,
    needs_input,
    decision_points,
    ruled_out,
    reasoning_trail,
  } = MOCK_DOSSIER_FULL;

  const openNeeds = needs_input.filter((n) => n.answered_at == null);

  const sortedChangeLog = [...MOCK_CHANGE_LOG].sort(
    (a, b) =>
      new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );

  return (
    <div className="min-h-screen bg-paper">
      <Header
        dossier={{
          title: dossier.title,
          dossier_type: dossier.dossier_type,
          status: dossier.status,
        }}
      />

      <div className="mx-auto max-w-page px-6 py-10 flex gap-10">
        <main className="flex-1 min-w-0 space-y-10">
          {dossier.problem_statement ? (
            <div className="border-l-2 border-rule pl-5">
              <DossierHero
                eyebrow="Problem"
                subtitle={dossier.problem_statement}
              />
              {dossier.out_of_scope.length > 0 ? (
                <div className="mt-3 text-xs font-mono text-ink-faint">
                  Out of scope:{" "}
                  {dossier.out_of_scope.map((item, i) => (
                    <span key={item}>
                      {i > 0 ? ", " : ""}
                      <span className="text-ink-muted">{item}</span>
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}

          {openNeeds.length > 0 ? (
            <div className="space-y-4">
              {openNeeds.map((item) => (
                <DemoNeedsInputItem key={item.id} item={item} />
              ))}
            </div>
          ) : null}

          <DecisionPointBlock items={decision_points} dossierId={dossier.id} />

          <SectionsList sections={sections} />

          <RuledOutList ruledOut={ruled_out} />

          <ReasoningTrail entries={reasoning_trail} />
        </main>

        <PlanDiffSidebarView entries={sortedChangeLog} />
      </div>
    </div>
  );
}
