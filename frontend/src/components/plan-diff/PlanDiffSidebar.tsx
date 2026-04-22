import { useMemo } from "react";
import { useChangeLog, useVisitDossier } from "../../api/hooks";
import type { ChangeLogEntry } from "../../api/types";
import { PlanDiffSidebarView } from "./PlanDiffSidebarView";

interface PlanDiffSidebarProps {
  dossierId: string;
}

export function PlanDiffSidebar({ dossierId }: PlanDiffSidebarProps) {
  const { data, isLoading, error } = useChangeLog(dossierId);
  const visit = useVisitDossier();

  const sorted = useMemo<ChangeLogEntry[]>(() => {
    if (!data) return [];
    // Most recent first. Do not dedupe — each entry is its own moment.
    return [...data].sort(
      (a, b) =>
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    );
  }, [data]);

  return (
    <PlanDiffSidebarView
      entries={sorted}
      isLoading={isLoading}
      error={error}
      onMarkRead={() => visit.mutate(dossierId)}
      isMarking={visit.isPending}
    />
  );
}

export default PlanDiffSidebar;
