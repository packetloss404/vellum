import React, { useEffect, useRef } from "react";
import { Link, useParams } from "react-router-dom";
import { Header } from "../components/layout/Header";
import { SectionsList } from "../components/sections/SectionsList";
import { RuledOutList } from "../components/sections/RuledOutList";
import { ReasoningTrail } from "../components/sections/ReasoningTrail";
import { NeedsInputBlock } from "../components/needs-input/NeedsInputBlock";
import { DecisionPointBlock } from "../components/decision-points/DecisionPointBlock";
import { PlanApprovalBlock } from "../components/plan-approval/PlanApprovalBlock";
import { PlanDiffSidebar } from "../components/plan-diff/PlanDiffSidebar";
import { Pill } from "../components/common/Pill";
import { DossierHero } from "../components/common/DossierHero";
import { EmptyState } from "../components/common/EmptyState";
import {
  useAgentStatus,
  useDossier,
  useStartAgent,
} from "../api/hooks";
import { relativeTime } from "../utils/time";
import { useDocumentTitle } from "../utils/useDocumentTitle";
import type { DossierStatus } from "../api/types";

/**
 * DossierPage — the hero view at /dossiers/:id.
 *
 * The dossier IS the page. A wide left column for the document (title,
 * needs_input, decision_points, sections, ruled out) and a narrow right
 * column for the "since yesterday" plan-diff sidebar. No nav chrome.
 *
 * Loading and error states render in the main content area, below the
 * Header — we keep the Header default-mode in those states since we
 * don't yet know the dossier title.
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
  const { data, isLoading, error } = useDossier(id ?? "");
  const agentStatus = useAgentStatus(id ?? "");
  const startAgent = useStartAgent();
  useDocumentTitle(data?.dossier ? `${data.dossier.title} · Vellum` : "Vellum");

  // Auto-resume the agent when the user opens an active dossier that has
  // no in-flight session. Matches the product story: the dossier is a
  // destination, and arriving at it should trigger fresh thinking. Fires
  // at most once per mount (the ref guard prevents a retry loop even if
  // agentStatus reports not-running again after the mutation error-recovers).
  const autoStartedRef = useRef(false);
  const dossierStatus = data?.dossier?.status;
  const agentRunning = agentStatus.data?.running;
  useEffect(() => {
    if (autoStartedRef.current) return;
    if (!id) return;
    if (dossierStatus !== "active") return;
    if (agentStatus.data === undefined) return; // wait for first status
    if (agentRunning) return;
    if (startAgent.isPending) return;
    autoStartedRef.current = true;
    startAgent.mutate({ dossierId: id });
  }, [
    id,
    dossierStatus,
    agentRunning,
    agentStatus.data,
    startAgent,
  ]);

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
    ruled_out,
    reasoning_trail,
  } = data;

  const hasSections = sections && sections.length > 0;
  const openNeeds = (needs_input ?? []).filter((n) => n.answered_at == null);
  const openDecisions = (decision_points ?? []).filter(
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

  const typeLabel = dossier.dossier_type.replace(/_/g, " ");
  const cadenceLabel = dossier.check_in_policy?.cadence?.replace(/_/g, " ");

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
          {/* TITLE — page-lead block, distinct from the header's compact title. */}
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

          {/* NEEDS YOU — at the top, a single crisp amber block per open item. */}
          <NeedsInputBlock items={needs_input ?? []} dossierId={id} />

          {/* APPROVE THE PLAN — Day-3 gate. Renders when the intake-seeded
              investigation_plan is awaiting user approval. Null otherwise. */}
          <PlanApprovalBlock dossier={data} />

          {/* DECIDE — decision points that the agent wants the user to resolve.
              The plan-approval decision is routed to PlanApprovalBlock above
              and filtered out here. */}
          <DecisionPointBlock items={decision_points ?? []} dossierId={id} />

          {isEmpty ? (
            <EmptyState
              title="Nothing written yet."
              hint="The agent is still thinking."
            />
          ) : (
            <>
              {/* Main document body. */}
              {hasSections ? <SectionsList sections={sections} /> : null}

              {/* Ruled-out ledger, collapsible; renders nothing if empty. */}
              <RuledOutList ruledOut={ruled_out ?? []} />

              {/* Reasoning trail — "show your work." Collapsed by default. */}
              <ReasoningTrail entries={reasoning_trail ?? []} />
            </>
          )}
        </div>

        {/* Sidebar: PlanDiffSidebar renders its own <aside> with sticky. */}
        <div className="min-w-0">
          <PlanDiffSidebar dossierId={id} />
        </div>
      </main>
    </div>
  );
}
