import React, { useEffect, useRef } from "react";
import { Link, useParams } from "react-router-dom";
import { Header } from "../components/layout/Header";
import { NeedsInputBlock } from "../components/needs-input/NeedsInputBlock";
import { DecisionPointBlock } from "../components/decision-points/DecisionPointBlock";
import { PlanApprovalBlock } from "../components/plan-approval/PlanApprovalBlock";
import { DossierHero } from "../components/common/DossierHero";
import { DebriefBlock } from "../components/dossier/DebriefBlock";
import { PlanBlock } from "../components/dossier/PlanBlock";
import { SectionList } from "../components/dossier/SectionList";
import { SubInvestigationList } from "../components/dossier/SubInvestigationList";
import { ArtifactList } from "../components/dossier/ArtifactList";
import { ConsideredRejectedList } from "../components/dossier/ConsideredRejectedList";
import { NextActionsList } from "../components/dossier/NextActionsList";
import { InvestigationLogSidebar } from "../components/dossier/InvestigationLogSidebar";
import { PlanDiffSidebar } from "../components/plan-diff/PlanDiffSidebar";
import {
  useChangeLog,
  useDossier,
  useInvestigationLogCounts,
  useResumeAgent,
  useResumeState,
  useVisitDossier,
} from "../api/hooks";
import { useDocumentTitle } from "../utils/useDocumentTitle";

/**
 * DossierPage — the case-file cover at /dossiers/:id.
 *
 * Layout (wide ≥1280px):
 *   ┌─────────────────────────────────────────────────┐
 *   │ Hero (title, meta, Resume CTA) · full width     │
 *   │ Debrief · full width                            │
 *   ├─────────────────────────────┬───────────────────┤
 *   │ Plan + PlanApproval         │ Plan-diff sidebar │
 *   │ Needs input                 │ Investigation log │
 *   │ Decision points             │                   │
 *   │ Sections                    │ (sticky,          │
 *   │ Sub-investigations          │  scrolls          │
 *   │ Artifacts                   │  independently)   │
 *   │ Considered & rejected       │                   │
 *   │ Next actions                │                   │
 *   └─────────────────────────────┴───────────────────┘
 *
 * Below `lg` the two columns collapse — sidebars stack after the main
 * content.
 *
 * VISIT-BEFORE-DIFF TIMING. The "since your last visit" sidebar must
 * render entries captured BEFORE we POST /visit (which resets
 * last_visited_at server-side). We achieve this by:
 *   1. Firing both GET /dossier and GET /change-log immediately (they
 *      both read from pre-visit state).
 *   2. Holding off on POST /visit until useChangeLog has completed.
 *      The change-log entries are now cached under the query key.
 *   3. POST /visit invalidates the change-log query; the refetch after
 *      visit returns the empty post-visit window, but the user has
 *      already seen the diff for this session. The sidebar gracefully
 *      transitions to "nothing new since you were last here" — which
 *      matches the user's mental model (they just saw it).
 */

function CenteredMessage({ children }: { children: React.ReactNode }) {
  return (
    <main className="mx-auto max-w-page px-6 py-24">
      <div className="min-h-[40vh] flex items-center justify-center text-center">
        <div className="text-ink-muted font-serif text-lg">{children}</div>
      </div>
    </main>
  );
}

export default function DossierPage() {
  const { id } = useParams<{ id: string }>();
  const dossierId = id ?? "";
  const { data, isLoading, error } = useDossier(dossierId);
  const changeLog = useChangeLog(dossierId);
  const resumeState = useResumeState(dossierId);
  const resumeAgent = useResumeAgent();
  const visit = useVisitDossier();
  const logCounts = useInvestigationLogCounts(dossierId);
  useDocumentTitle(data?.dossier ? `${data.dossier.title} · Vellum` : "Vellum");

  // VISIT TIMING. Fire /visit exactly once per mount, and only AFTER the
  // change-log query has completed — so the diff sidebar captures the
  // pre-visit window before last_visited_at is bumped. If the change-log
  // query errors, we still visit (the diff sidebar shows its own error;
  // we don't want a broken log hook to stall the visit forever).
  const visitedRef = useRef(false);
  const changeLogSettled = changeLog.isSuccess || changeLog.isError;
  useEffect(() => {
    if (!dossierId) return;
    if (visitedRef.current) return;
    if (!changeLogSettled) return;
    visitedRef.current = true;
    visit.mutate(dossierId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dossierId, changeLogSettled]);

  if (!id) {
    return (
      <div className="min-h-screen bg-paper">
        <Header />
        <CenteredMessage>Dossier not found.</CenteredMessage>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="min-h-screen bg-paper">
        <Header />
        <CenteredMessage>Loading dossier…</CenteredMessage>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="min-h-screen bg-paper">
        <Header />
        <CenteredMessage>
          <div>Dossier not found.</div>
          <div className="mt-4 text-sm font-mono text-ink-faint">
            <Link
              to="/"
              className="text-accent hover:text-accent-hover transition-colors"
            >
              Back to dossiers
            </Link>
          </div>
        </CenteredMessage>
      </div>
    );
  }

  const {
    dossier,
    sections,
    needs_input,
    decision_points,
    artifacts,
    sub_investigations,
    considered_and_rejected,
    next_actions,
  } = data;

  // Filter out plan_approval decision points — those are owned by
  // PlanApprovalBlock. Prefer `kind` when present; fall back to title match
  // for legacy rows.
  const visibleDecisionPoints = (decision_points ?? []).filter((dp) => {
    if ((dp as { kind?: string }).kind === "plan_approval") return false;
    const t = (dp.title ?? "").toLowerCase();
    return !t.startsWith("approve plan") && !t.includes("plan approval");
  });

  // Resume CTA — show when:
  //   - dossier is not delivered, AND
  //   - resume-state says there's no active session, OR the endpoint 404s
  //     (another agent is adding it; graceful degrade = show CTA).
  const isDelivered = dossier.status === "delivered";
  const resumeStateKnown = resumeState.data !== undefined;
  const hasActiveSession =
    resumeStateKnown && !!resumeState.data?.active_work_session_id;
  const showResume = !isDelivered && !hasActiveSession;

  return (
    <div className="min-h-screen bg-paper">
      <Header
        dossier={{
          title: dossier.title,
          dossier_type: dossier.dossier_type,
          status: dossier.status,
        }}
      />

      {/* Top band — hero + debrief run the full page width. The Resume
          button sits top-right as a visually subordinate CTA so the title +
          problem statement own the first glance. */}
      <div className="mx-auto max-w-page px-6 pt-10">
        <div className="relative">
          {/* Reserve space to the right of the hero so a long title never
              collides with the Resume CTA at top-right. */}
          <div className={showResume ? "pr-24" : undefined}>
            <DossierHero dossier={data} counts={logCounts.data} />
          </div>
          {showResume ? (
            <button
              type="button"
              onClick={() => resumeAgent.mutate(dossierId)}
              disabled={resumeAgent.isPending}
              className="absolute right-0 top-0 z-10 shrink-0 border border-rule-strong text-ink-muted hover:text-ink hover:border-accent px-3 py-1.5 font-sans text-xs rounded transition-colors disabled:opacity-60 disabled:cursor-not-allowed bg-surface"
            >
              {resumeAgent.isPending ? "Resuming…" : "Resume"}
            </button>
          ) : null}
        </div>

        <div className="mt-10">
          <DebriefBlock debrief={dossier.debrief} />
        </div>
      </div>

      {/* Two-column band. Main column is content-width (max-w-prose via
          the inner wrapper); the right rail is 320-360px, sticky, and
          scrolls independently when its content exceeds the viewport. */}
      <main className="mx-auto max-w-page px-6 py-10 grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_340px] gap-12">
        <div className="space-y-10 max-w-prose min-w-0">
          {/* Plan — the agent's investigation plan. PlanApprovalBlock
              renders inline directly after, only when there's an
              unapproved plan. */}
          <PlanBlock plan={dossier.investigation_plan} />
          <PlanApprovalBlock dossier={data} />

          {/* NEEDS YOU — open needs_input items. */}
          <NeedsInputBlock items={needs_input ?? []} dossierId={dossierId} />

          {/* DECIDE — decision_points, excluding plan_approval (owned elsewhere). */}
          <DecisionPointBlock
            items={visibleDecisionPoints}
            dossierId={dossierId}
          />

          {/* Main document body. */}
          <SectionList sections={sections ?? []} />

          <SubInvestigationList
            subs={sub_investigations ?? []}
            sections={sections ?? []}
            artifacts={artifacts ?? []}
          />

          <ArtifactList artifacts={artifacts ?? []} />

          <ConsideredRejectedList items={considered_and_rejected ?? []} />

          <NextActionsList items={next_actions ?? []} />
        </div>

        {/* Right rail. `sticky top-6` with max-h computed against the
            viewport and overflow-y-auto means it scrolls on its own when
            the log + diff overflow. On narrow it collapses below main. */}
        <aside className="min-w-0 lg:sticky lg:top-6 lg:self-start lg:max-h-[calc(100vh-3rem)] lg:overflow-y-auto">
          <div className="space-y-10">
            <PlanDiffSidebar dossierId={dossierId} />
            <InvestigationLogSidebar dossierId={dossierId} />
          </div>
        </aside>
      </main>
    </div>
  );
}
