import React from "react";
import type { DecisionPoint } from "../../api/types";
import { DecisionPointItem } from "./DecisionPointItem";

/**
 * DecisionPointBlock — the "DECIDE" surface at the top of a dossier.
 *
 * Renders one block per open decision_point. Renders nothing when
 * there are no open items.
 */

export interface DecisionPointBlockProps {
  items: DecisionPoint[];
  dossierId: string;
}

export function DecisionPointBlock({
  items,
  dossierId,
}: DecisionPointBlockProps) {
  const open = items.filter((i) => i.resolved_at == null);
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
