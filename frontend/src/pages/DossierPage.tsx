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
import {
  useDossier,
  useInvestigationLogCounts,
  useResumeAgent,
  useResumeState,
  useVisitDossier,
} from "../api/hooks";
import { useDocumentTitle } from "../utils/useDocumentTitle";

/**
 * DossierPage — the read-only hero view at /dossiers/:id. Day 3 scaffold.
 *
 * The dossier IS the page. Blocks render top-to-bottom in the left column
 * (debrief, plan, needs_input, decision_points, sections, sub_investigations,
 * artifacts, considered_and_rejected, next_actions). The right column is
 * the investigation-log sidebar.
 *
 * We POST /visit once per mount (abort-guarded) to reset the "since last
 * visit" window. A prominent "Resume" button appears top-right when the
 * resume-state endpoint says there's no active session; if that endpoint
 * isn't live yet we degrade to showing Resume unconditionally.
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
  const resumeState = useResumeState(dossierId);
  const resumeAgent = useResumeAgent();
  const visit = useVisitDossier();
  const logCounts = useInvestigationLogCounts(dossierId);
  useDocumentTitle(data?.dossier ? `${data.dossier.title} · Vellum` : "Vellum");

  // POST /visit once per mount. A ref guards against StrictMode double-fire
  // and against the visit mutation resolving after the component unmounts.
  const visitedRef = useRef(false);
  useEffect(() => {
    if (!dossierId) return;
    if (visitedRef.current) return;
    visitedRef.current = true;
    visit.mutate(dossierId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dossierId]);

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

  const hasSections = sections && sections.length > 0;
  const openNeeds = (needs_input ?? []).filter((n) => n.answered_at == null);
  const openDecisions = visibleDecisionPoints.filter(
    (d) => d.resolved_at == null,
  );
  // A drafted-but-unapproved investigation_plan also counts as content —
  // PlanApprovalBlock is on-page in that case, so suppress the "nothing
  // written yet" empty state.
  const hasPendingPlan =
    !!dossier.investigation_plan &&
    dossier.investigation_plan.approved_at == null;
  const isEmpty =
    !hasSections &&
    openNeeds.length === 0 &&
    openDecisions.length === 0 &&
    !hasPendingPlan;

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

      <main className="mx-auto max-w-page px-6 py-10 grid grid-cols-1 md:grid-cols-[1fr_320px] gap-12">
        <div className="space-y-10 max-w-prose min-w-0">
          {/* HERO — case-file cover. The Resume button sits top-right as a
              visually subordinate CTA so the title + problem statement own
              the first glance. */}
          <div className="relative">
            <DossierHero dossier={data} counts={logCounts.data} />
            {showResume ? (
              <button
                type="button"
                onClick={() => resumeAgent.mutate(dossierId)}
                disabled={resumeAgent.isPending}
                className="absolute right-0 top-0 shrink-0 border border-rule-strong text-ink-muted hover:text-ink hover:border-accent px-3 py-1.5 font-sans text-xs rounded transition-colors disabled:opacity-60 disabled:cursor-not-allowed bg-surface"
              >
                {resumeAgent.isPending ? "Resuming…" : "Resume"}
              </button>
            ) : null}
          </div>

          {/* Debrief — four-field summary. Always renders a placeholder if
              empty so the page shape is predictable. */}
          <DebriefBlock debrief={dossier.debrief} />

          {/* Plan — lists the items. */}
          <PlanBlock plan={dossier.investigation_plan} />

          {/* APPROVE THE PLAN — Day-3 gate. Renders when the intake-seeded
              investigation_plan is awaiting user approval. Null otherwise. */}
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

          <SubInvestigationList subs={sub_investigations ?? []} />

          <ArtifactList artifacts={artifacts ?? []} />

          <ConsideredRejectedList items={considered_and_rejected ?? []} />

          <NextActionsList items={next_actions ?? []} />
        </div>

        <div className="min-w-0">
          <InvestigationLogSidebar dossierId={dossierId} />
        </div>
      </main>
    </div>
  );
}
