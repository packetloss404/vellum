import React from "react";
import type { Dossier } from "../../api/types";
import { relativeTime } from "../../utils/time";

/**
 * QuarantineBanner — loud strip shown when self-heal has paused automatic
 * retries after repeated failed sessions. Resume (top-right of the page)
 * clears the quarantine server-side and starts a fresh session.
 */

export interface QuarantineBannerProps {
  dossier: Dossier;
}

export function QuarantineBanner({ dossier }: QuarantineBannerProps) {
  if (!dossier.quarantined_at) return null;

  const count = dossier.consecutive_error_count;

  return (
    <div
      role="alert"
      className="border border-state-blocked/40 border-l-4 border-l-state-blocked bg-state-blocked/5 rounded px-4 py-3"
    >
      <div className="text-xs font-mono uppercase tracking-wide text-state-blocked">
        Automatic retries paused
      </div>
      <p className="mt-1 font-serif text-sm text-ink leading-relaxed">
        {count
          ? `The last ${count} working sessions on this dossier failed, so `
          : "Repeated working sessions on this dossier failed, so "}
        the agent stopped retrying on its own
        {dossier.quarantined_at
          ? ` ${relativeTime(dossier.quarantined_at)}`
          : ""}
        . Nothing was lost — press <strong>Resume</strong> to try again.
      </p>
    </div>
  );
}
