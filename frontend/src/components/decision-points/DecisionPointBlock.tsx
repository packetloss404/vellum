import React from "react";
import type { DecisionPoint } from "../../api/types";
import { DecisionPointItem } from "./DecisionPointItem";

/**
 * DecisionPointBlock — the "DECIDE" surface at the top of a dossier.
 *
 * Renders one block per open decision_point. Renders nothing when
 * there are no open items.
 *
 * Plan-approval decisions (`kind === "plan_approval"`) are rendered by
 * `PlanApprovalBlock` instead, so we filter them out here to avoid a
 * duplicate card. The heuristic fallback (title contains "approve"/"plan"
 * when `kind` is absent) matches PlanApprovalBlock's fallback so the two
 * surfaces stay in sync for pre-`kind`-field dossiers.
 */

function isPlanApproval(p: DecisionPoint): boolean {
  if (p.kind === "plan_approval") return true;
  if (p.kind === undefined) {
    const t = p.title.toLowerCase();
    return t.includes("approve") || t.includes("plan");
  }
  return false;
}

export interface DecisionPointBlockProps {
  items: DecisionPoint[];
  dossierId: string;
}

export function DecisionPointBlock({
  items,
  dossierId,
}: DecisionPointBlockProps) {
  const open = items.filter(
    (i) => i.resolved_at == null && !isPlanApproval(i),
  );
  if (open.length === 0) return null;

  return (
    <div className="space-y-4">
      {open.map((item) => (
        <DecisionPointItem key={item.id} item={item} dossierId={dossierId} />
      ))}
    </div>
  );
}

export default DecisionPointBlock;
