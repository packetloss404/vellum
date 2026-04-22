import React, { useEffect, useRef } from "react";
import { Link, useParams } from "react-router-dom";
import { Header } from "../components/layout/Header";
import { NeedsInputBlock } from "../components/needs-input/NeedsInputBlock";
import { DecisionPointBlock } from "../components/decision-points/DecisionPointBlock";
import { Pill } from "../components/common/Pill";
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
  useResumeAgent,
  useResumeState,
  useVisitDossier,
} from "../api/hooks";
import { relativeTime } from "../utils/time";
import { useDocumentTitle } from "../utils/useDocumentTitle";
import type { DossierStatus } from "../api/types";

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

function statusPillVariant(
  status: string,
): "default" | "accent" | "attention" {
  return (status as DossierStatus) === "active" ? "accent" : "default";
}

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

  // Filter out plan_approval decision points — those are owned by the
  // plan-approval component (mounted inside PlanBlock via data-slot).
  // We match on title prefix defensively since `kind` isn't a field on
  // DecisionPoint; the intake/agent conventionally prefixes these.
  const visibleDecisionPoints = (decision_points ?? []).filter((dp) => {
    const t = (dp.title ?? "").toLowerCase();
    return !t.startsWith("approve plan") && !t.includes("plan approval");
  });

  const typeLabel = dossier.dossier_type.replace(/_/g, " ");
  const cadenceLabel = dossier.check_in_policy?.cadence?.replace(/_/g, " ");

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
          {/* TITLE + meta + Resume CTA. Flex row so the CTA anchors top-right. */}
          <div className="flex items-start justify-between gap-6">
            <div className="min-w-0 flex-1">
              <DossierHero
                title={dossier.title}
                subtitle={dossier.problem_statement ?? undefined}
                meta={
                  <>
                    <span className="lowercase tracking-wide">{typeLabel}</span>
                    <span aria-hidden="true">·</span>
                    <Pill variant={statusPillVariant(dossier.status)}>
                      {dossier.status}
                    </Pill>
                    <span aria-hidden="true">·</span>
                    <span>created {relativeTime(dossier.created_at)}</span>
                    {cadenceLabel ? (
                      <>
                        <span aria-hidden="true">·</span>
                        <span>check-in: {cadenceLabel}</span>
                      </>
                    ) : null}
                  </>
                }
              />
            </div>
            {showResume ? (
              <button
                type="button"
                onClick={() => resumeAgent.mutate(dossierId)}
                disabled={resumeAgent.isPending}
                className="shrink-0 bg-accent text-paper px-4 py-2 font-sans text-sm rounded hover:bg-accent-hover transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {resumeAgent.isPending ? "Resuming…" : "Resume"}
              </button>
            ) : null}
          </div>

          {/* Debrief — only renders if populated. */}
          <DebriefBlock debrief={dossier.debrief} />

          {/* Plan — renders placeholder slot for plan-approval when unapproved. */}
          <PlanBlock plan={dossier.investigation_plan} />

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
