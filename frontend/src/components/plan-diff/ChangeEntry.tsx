import type { ChangeLogEntry, ChangeKind } from "../../api/types";
import { relativeTime } from "../../utils/time";

/**
 * ChangeEntry — a single row in the plan-diff sidebar.
 *
 * Each ChangeKind has a finalized presentation (glyph + category + accent).
 * Accent buckets:
 *   - amber   → state changes, flagged work (needs_input_added etc.)
 *   - neutral → added / routine edits
 *   - rusty   → removals, abandonments, rejections
 *   - green   → resolutions, completions ("confident" green)
 */

// --------------------------------------------------------------------------
// Shared presentation tables.
// The entire sidebar (grouping + rendering) reads from these two maps, so
// callers importing `categoryOfKind` stay in sync with this file.

export type PlanDiffCategory =
  | "plan_and_debrief"
  | "sections"
  | "sub_investigations"
  | "artifacts"
  | "flagged"
  | "considered_and_rejected"
  | "housekeeping";

export const PLAN_DIFF_CATEGORY_ORDER: PlanDiffCategory[] = [
  "plan_and_debrief",
  "sections",
  "sub_investigations",
  "artifacts",
  "flagged",
  "considered_and_rejected",
  "housekeeping",
];

export const PLAN_DIFF_CATEGORY_LABEL: Record<PlanDiffCategory, string> = {
  plan_and_debrief: "Plan & debrief",
  sections: "Sections",
  sub_investigations: "Sub-investigations",
  artifacts: "Artifacts",
  flagged: "Flagged for you",
  considered_and_rejected: "Considered & rejected",
  housekeeping: "Housekeeping",
};

export const CATEGORY_OF_KIND: Record<ChangeKind, PlanDiffCategory> = {
  // Plan & debrief
  debrief_updated: "plan_and_debrief",
  plan_updated: "plan_and_debrief",
  working_theory_updated: "plan_and_debrief",
  // Sections
  section_created: "sections",
  section_updated: "sections",
  section_deleted: "sections",
  state_changed: "sections",
  sections_reordered: "sections",
  // Sub-investigations
  sub_investigation_spawned: "sub_investigations",
  sub_investigation_completed: "sub_investigations",
  sub_investigation_abandoned: "sub_investigations",
  // Artifacts
  artifact_added: "artifacts",
  artifact_updated: "artifacts",
  // Flagged for you
  needs_input_added: "flagged",
  needs_input_resolved: "flagged",
  decision_point_added: "flagged",
  decision_point_resolved: "flagged",
  // Considered & rejected
  ruled_out_added: "considered_and_rejected",
  considered_and_rejected_added: "considered_and_rejected",
  // Housekeeping
  investigation_log_appended: "housekeeping",
  next_action_added: "housekeeping",
  next_action_completed: "housekeeping",
  next_action_removed: "housekeeping",
};

export function categoryOfKind(kind: ChangeKind): PlanDiffCategory {
  return CATEGORY_OF_KIND[kind];
}

// --------------------------------------------------------------------------

type Accent = "amber" | "neutral" | "rusty" | "green";

interface KindPresentation {
  label: string;
  glyph: string;
  accent: Accent;
  strikethrough?: boolean;
  mutedBody?: boolean;
}

// Unicode glyphs chosen for legibility in Lora / JetBrains Mono at 12px.
// Arrows + asterisks + daggers read as "thing happened" marks without the
// weight of a full icon font.
const KIND_MAP: Record<ChangeKind, KindPresentation> = {
  // ---- Sections
  section_created: { label: "Added section", glyph: "+", accent: "neutral" },
  section_updated: { label: "Revised section", glyph: "~", accent: "neutral" },
  section_deleted: {
    label: "Removed section",
    glyph: "−",
    accent: "rusty",
    strikethrough: true,
    mutedBody: true,
  },
  state_changed: { label: "State changed", glyph: "↦", accent: "amber" },
  sections_reordered: {
    label: "Reordered sections",
    glyph: "⇅",
    accent: "neutral",
  },

  // ---- Flagged for you
  needs_input_added: {
    label: "Needs you",
    glyph: "?",
    accent: "amber",
  },
  needs_input_resolved: {
    label: "Answered",
    glyph: "✓",
    accent: "green",
    mutedBody: true,
  },
  decision_point_added: {
    label: "Decision point",
    glyph: "◆",
    accent: "amber",
  },
  decision_point_resolved: {
    label: "Decided",
    glyph: "✓",
    accent: "green",
    mutedBody: true,
  },

  // ---- Considered & rejected
  ruled_out_added: {
    label: "Ruled out",
    glyph: "×",
    accent: "rusty",
    strikethrough: true,
    mutedBody: true,
  },
  considered_and_rejected_added: {
    label: "Considered & rejected",
    glyph: "×",
    accent: "rusty",
    mutedBody: true,
  },

  // ---- Artifacts
  artifact_added: { label: "Artifact", glyph: "+", accent: "neutral" },
  artifact_updated: { label: "Artifact revised", glyph: "~", accent: "neutral" },

  // ---- Sub-investigations
  sub_investigation_spawned: {
    label: "Sub-investigation",
    glyph: "↳",
    accent: "neutral",
  },
  sub_investigation_completed: {
    label: "Sub returned",
    glyph: "✓",
    accent: "green",
  },
  sub_investigation_abandoned: {
    label: "Sub abandoned",
    glyph: "×",
    accent: "rusty",
    mutedBody: true,
  },

  // ---- Plan & debrief
  debrief_updated: { label: "Debrief", glyph: "§", accent: "neutral" },
  plan_updated: { label: "Plan", glyph: "§", accent: "neutral" },
  working_theory_updated: { label: "Working theory", glyph: "◎", accent: "amber" },

  // ---- Housekeeping
  next_action_added: {
    label: "Next action",
    glyph: "+",
    accent: "amber",
  },
  next_action_completed: {
    label: "Next action done",
    glyph: "✓",
    accent: "green",
    mutedBody: true,
  },
  next_action_removed: {
    label: "Next action removed",
    glyph: "−",
    accent: "rusty",
    strikethrough: true,
    mutedBody: true,
  },
  investigation_log_appended: {
    label: "Log entry",
    glyph: "·",
    accent: "neutral",
  },
};

// accent → tailwind class for the glyph
const GLYPH_COLOR: Record<Accent, string> = {
  amber: "text-attention",
  neutral: "text-ink-faint",
  rusty: "text-state-blocked",
  green: "text-state-confident",
};

// --------------------------------------------------------------------------
// State-change body parsing.

const MAX_NOTE_LENGTH = 120;

function truncate(text: string, max = MAX_NOTE_LENGTH): string {
  if (text.length <= max) return text;
  return text.slice(0, max - 1).trimEnd() + "…";
}

/**
 * Parse a state-change note into its constituent parts.
 *
 * Accepts:
 *   "from → to"                                 → { label: null, from, to }
 *   "label: from → to"                          → { label, from, to }
 *
 * The label form was added for working-theory confidence drift
 * ("working_theory: medium → high") and also matches the sub-investigation
 * flavour ("sub-investigation 'X': running → blocked (reason)"), so the
 * tone regexes below get a clean `from`/`to` to classify.
 */
function parseStateTransition(note: string): {
  label: string | null;
  from: string;
  to: string;
} | null {
  const match = note.match(/^\s*(.+?)\s*(?:→|->)\s*(.+?)\s*$/);
  if (!match) return null;
  let from = match[1];
  let label: string | null = null;
  // Split off a leading "<label>: " prefix, but only if it looks like a
  // real label — a single colon-separated tag rather than a sentence that
  // happens to include a colon. We require the label side not to contain
  // a space-before-colon and the remainder to be non-empty.
  const labelMatch = from.match(/^(.+?):\s+(.+)$/);
  if (labelMatch) {
    label = labelMatch[1].trim();
    from = labelMatch[2].trim();
  }
  return { label, from, to: match[2] };
}

function stateToneClass(state: string): string {
  const s = state.toLowerCase();
  if (/(confident|done|complete|ready|resolved|high)/.test(s))
    return "text-state-confident";
  if (/(blocked|stuck|failed|low)/.test(s)) return "text-state-blocked";
  if (/(provisional|draft|pending|wip|medium)/.test(s))
    return "text-state-provisional";
  return "text-ink-muted";
}

function StateChangeBody({ note }: { note: string }) {
  const transition = parseStateTransition(note);
  if (!transition) {
    return <span>{truncate(note)}</span>;
  }
  return (
    <span className="inline-flex items-baseline gap-1.5 flex-wrap">
      {transition.label ? (
        <span className="font-mono text-[11px] text-ink-faint">
          {truncate(transition.label, 40)}
        </span>
      ) : null}
      <span className={`font-mono text-xs ${stateToneClass(transition.from)}`}>
        {truncate(transition.from, 40)}
      </span>
      <span className="text-ink-faint font-mono text-xs" aria-hidden="true">
        →
      </span>
      <span className={`font-mono text-xs ${stateToneClass(transition.to)}`}>
        {truncate(transition.to, 40)}
      </span>
    </span>
  );
}

// --------------------------------------------------------------------------

/** The in-DOM id a click on this entry should scroll to, or null. */
function targetAnchorId(entry: ChangeLogEntry): string | null {
  if (entry.section_id) return `section-${entry.section_id}`;
  // We don't currently carry the sub-investigation id on ChangeLogEntry, so
  // we only scroll to sections. If/when the backend threads a
  // sub_investigation_id onto entries, extend here.
  return null;
}

function scrollToAnchor(anchorId: string) {
  if (typeof document === "undefined") return;
  const el = document.getElementById(anchorId);
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "start" });
}

interface ChangeEntryProps {
  entry: ChangeLogEntry;
}

export function ChangeEntry({ entry }: ChangeEntryProps) {
  const presentation = KIND_MAP[entry.kind];
  const anchor = targetAnchorId(entry);
  const isStateChange = entry.kind === "state_changed";

  const bodyClasses = [
    "font-serif",
    "text-sm",
    "block",
    "mt-1",
    "leading-snug",
    "pl-[14px]", // aligns under the label, past glyph + gap
  ];
  if (presentation.strikethrough) bodyClasses.push("line-through");
  if (presentation.mutedBody) {
    bodyClasses.push("text-ink-muted");
  } else {
    bodyClasses.push("text-ink");
  }

  const content = (
    <>
      <div className="flex items-baseline justify-between gap-3">
        <div className="flex items-baseline min-w-0">
          <span
            className={`font-mono text-xs mr-2 align-middle w-[8px] inline-block ${GLYPH_COLOR[presentation.accent]}`}
            aria-hidden="true"
          >
            {presentation.glyph}
          </span>
          <span className="font-mono text-[11px] uppercase tracking-wide text-ink-muted truncate">
            {presentation.label}
          </span>
        </div>
        <time
          dateTime={entry.created_at}
          className="font-mono text-[11px] text-ink-faint shrink-0"
          title={new Date(entry.created_at).toLocaleString()}
        >
          {relativeTime(entry.created_at)}
        </time>
      </div>

      {isStateChange ? (
        <span className={bodyClasses.join(" ")}>
          <StateChangeBody note={entry.change_note} />
        </span>
      ) : (
        <span className={bodyClasses.join(" ")}>
          {truncate(entry.change_note)}
        </span>
      )}
    </>
  );

  if (anchor) {
    return (
      <li className="group">
        <button
          type="button"
          onClick={() => scrollToAnchor(anchor)}
          className="w-full text-left rounded -mx-1 px-1 py-0.5 hover:bg-surface-sunk/60 focus:outline-none focus:bg-surface-sunk/60 transition-colors"
        >
          {content}
        </button>
      </li>
    );
  }

  return <li className="group">{content}</li>;
}

export default ChangeEntry;
