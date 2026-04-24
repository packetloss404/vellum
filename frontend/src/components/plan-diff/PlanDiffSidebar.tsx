import {
  useChangeLogSinceVisit,
  useDossier,
  useVisitDossier,
} from "../../api/hooks";
import { PlanDiffSidebarView } from "./PlanDiffSidebarView";
import type { SessionSummary, WorkSession } from "../../api/types";

/**
 * PlanDiffSidebar — sidebar shell.
 *
 * Data-flow detail worth calling out: DossierPage POSTs /visit on mount,
 * which resets `last_visited_at` and empties the "since last visit"
 * window. To render a useful diff anyway, `useChangeLogSinceVisit`
 * snapshots the FIRST non-empty response and ignores later refetches —
 * so even if /visit completes and the change-log query is invalidated
 * mid-render, the sidebar still shows what the user came back to.
 *
 * The `lastVisitedAt` we pass to the view is ALSO pre-visit: we read it
 * from the dossier cache's first value. If the dossier cache refreshes
 * after /visit lands, we still show the original timestamp.
 */

interface PlanDiffSidebarProps {
  dossierId: string;
}

export function PlanDiffSidebar({ dossierId }: PlanDiffSidebarProps) {
  const dossier = useDossier(dossierId);
  const diff = useChangeLogSinceVisit(dossierId);
  const visit = useVisitDossier();

  // First-seen value of last_visited_at, captured by the hook. `undefined`
  // while we're still waiting for the dossier; `null` for a first visit.
  const lastVisitedAt = diff.lastVisitedAtSnapshot;

  // Loading: either no dossier yet, or change-log snapshot hasn't settled.
  const isLoading =
    (dossier.isLoading && !dossier.data) ||
    (diff.isLoading && !diff.snapshotReady);

  const workSessions: WorkSession[] = dossier.data?.work_sessions ?? [];
  const summaries: SessionSummary[] = dossier.data?.session_summaries ?? [];

  return (
    <PlanDiffSidebarView
      entries={diff.entries}
      workSessions={workSessions}
      summaries={summaries}
      lastVisitedAt={lastVisitedAt}
      isLoading={isLoading}
      error={diff.error}
      onMarkRead={() => visit.mutate(dossierId)}
      isMarking={visit.isPending}
    />
  );
}

export default PlanDiffSidebar;
