import React from "react";
import type { NeedsInput } from "../../api/types";
import { NeedsInputItem } from "./NeedsInputItem";

/**
 * NeedsInputBlock — the "NEEDS YOU" surface at the top of a dossier.
 *
 * Renders one block per open needs_input. If nothing is open, renders
 * nothing at all — this surface should never show an empty state.
 */

export interface NeedsInputBlockProps {
  items: NeedsInput[];
  dossierId: string;
}

export function NeedsInputBlock({ items, dossierId }: NeedsInputBlockProps) {
  const open = items.filter((i) => i.answered_at == null);
  if (open.length === 0) return null;

  return (
    <div className="space-y-4">
      {open.map((item) => (
        <NeedsInputItem key={item.id} item={item} dossierId={dossierId} />
      ))}
    </div>
  );
}

export default NeedsInputBlock;
