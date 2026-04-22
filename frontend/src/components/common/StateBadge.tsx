import React from "react";

/**
 * StateBadge — canonical display for section state.
 *
 * Colored circular pip + short label, aligned horizontally. Used throughout
 * the dossier wherever a section/item has a confidence state.
 *
 *   confident   — settled (deep green)
 *   provisional — in-progress (amber)
 *   blocked     — stopped (rusty red)
 *
 * Label defaults to the state name; pass `label` to override.
 */

export type SectionState = "confident" | "provisional" | "blocked";

export interface StateBadgeProps {
  state: SectionState;
  label?: string;
  className?: string;
}

const pipColors: Record<SectionState, string> = {
  confident: "bg-state-confident",
  provisional: "bg-state-provisional",
  blocked: "bg-state-blocked",
};

const textColors: Record<SectionState, string> = {
  confident: "text-state-confident",
  provisional: "text-state-provisional",
  blocked: "text-state-blocked",
};

function cx(...parts: Array<string | false | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

export function StateBadge({ state, label, className }: StateBadgeProps) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 text-xs font-mono",
        textColors[state],
        className,
      )}
      title={`state: ${state}`}
    >
      <span
        aria-hidden="true"
        className={cx(
          "inline-block w-1.5 h-1.5 rounded-full",
          pipColors[state],
        )}
      />
      <span>{label ?? state}</span>
    </span>
  );
}

export default StateBadge;
