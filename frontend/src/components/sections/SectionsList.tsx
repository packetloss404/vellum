import React from "react";
import type { Section } from "../../api/types";
import { SectionCard } from "./SectionCard";
import { EmptyState } from "../common/EmptyState";

/**
 * SectionsList — the body of a dossier. Renders each Section as a
 * SectionCard with generous vertical rhythm so the document breathes.
 */

export interface SectionsListProps {
  sections: Section[];
}

export function SectionsList({ sections }: SectionsListProps) {
  if (!sections || sections.length === 0) {
    return (
      <EmptyState
        title="The dossier is empty."
        hint="The agent will populate it as it works."
      />
    );
  }

  return (
    <div className="space-y-10">
      {sections.map((section) => (
        <SectionCard key={section.id} section={section} />
      ))}
    </div>
  );
}

export default SectionsList;
