import type { ChangeLogEntry, ChangeKind } from "../../api/types";
import { relativeTime } from "../../utils/time";

interface ChangeEntryProps {
  entry: ChangeLogEntry;
}

const MAX_NOTE_LENGTH = 120;

function truncate(text: string, max = MAX_NOTE_LENGTH): string {
  if (text.length <= max) return text;
  return text.slice(0, max - 1).trimEnd() + "…";
}

interface KindPresentation {
  label: string;
  dotClass?: string;
  strikethrough?: boolean;
  mutedBody?: boolean;
  accentBody?: "attention" | "accent";
}

const KIND_MAP: Record<ChangeKind, KindPresentation> = {
  section_created: {
    label: "Added section",
    dotClass: "bg-state-confident",
  },
  section_updated: {
    label: "Revised",
    dotClass: "bg-ink-faint",
  },
  section_deleted: {
    label: "Removed section",
    dotClass: "bg-ink-faint",
    strikethrough: true,
    mutedBody: true,
  },
  state_changed: {
    label: "State",
  },
  needs_input_added: {
    label: "Needs you",
    dotClass: "bg-attention",
    accentBody: "attention",
  },
  needs_input_resolved: {
    label: "Answered",
    mutedBody: true,
  },
  decision_point_added: {
    label: "Decision point",
    dotClass: "bg-accent",
    accentBody: "accent",
  },
  decision_point_resolved: {
    label: "Decided",
    mutedBody: true,
  },
  ruled_out_added: {
    label: "Ruled out",
    dotClass: "bg-ink-faint",
    strikethrough: true,
    mutedBody: true,
  },
  sections_reordered: {
    label: "Reordered sections",
    dotClass: "bg-ink-faint",
  },
};

function Dot({ className }: { className: string }) {
  return (
    <span
      className={`w-1.5 h-1.5 rounded-full inline-block align-middle mr-2 ${className}`}
      aria-hidden="true"
    />
  );
}

// Parses a "X -> Y" or "X → Y" pattern. Returns null if absent.
function parseStateTransition(
  note: string
): { from: string; to: string } | null {
  const match = note.match(/^\s*(.+?)\s*(?:→|->)\s*(.+?)\s*$/);
  if (!match) return null;
  return { from: match[1], to: match[2] };
}

function stateToneClass(state: string): string {
  const s = state.toLowerCase();
  if (/(confident|done|complete|ready|resolved)/.test(s))
    return "text-state-confident";
  if (/(blocked|stuck|failed)/.test(s)) return "text-state-blocked";
  if (/(provisional|draft|pending|wip)/.test(s))
    return "text-state-provisional";
  return "text-ink-muted";
}

function StateChangeBody({ note }: { note: string }) {
  const transition = parseStateTransition(note);
  if (!transition) {
    return (
      <span className="font-serif text-sm text-ink">{truncate(note)}</span>
    );
  }
  return (
    <span className="font-serif text-sm text-ink inline-flex items-baseline gap-1.5">
      <span className={`font-mono text-xs ${stateToneClass(transition.from)}`}>
        {truncate(transition.from, 40)}
      </span>
      <span className="text-ink-faint font-mono text-xs" aria-hidden="true">
        →
      </span>
      <span
        className={`font-mono text-xs ${stateToneClass(transition.to)}`}
      >
        {truncate(transition.to, 40)}
      </span>
    </span>
  );
}

export function ChangeEntry({ entry }: ChangeEntryProps) {
  const presentation = KIND_MAP[entry.kind];
  const label = presentation.label;

  const bodyClasses = [
    "font-serif",
    "text-sm",
    "block",
    "mt-1",
    "pl-[14px]", // aligns under the label, past the 6px dot + 8px gap
  ];

  if (presentation.strikethrough) bodyClasses.push("line-through");
  if (presentation.accentBody === "attention") {
    bodyClasses.push("text-attention");
  } else if (presentation.accentBody === "accent") {
    bodyClasses.push("text-accent");
  } else if (presentation.mutedBody) {
    bodyClasses.push("text-ink-muted");
  } else {
    bodyClasses.push("text-ink");
  }

  const isStateChange = entry.kind === "state_changed";

  return (
    <li className="group">
      <div className="flex items-baseline justify-between gap-3">
        <div className="flex items-baseline min-w-0">
          {presentation.dotClass ? (
            <Dot className={presentation.dotClass} />
          ) : isStateChange ? (
            <span
              className="font-mono text-xs text-ink-faint mr-2 align-middle"
              aria-hidden="true"
            >
              ↦
            </span>
          ) : null}
          <span className="font-mono text-xs uppercase tracking-wide text-ink-muted truncate">
            {label}
          </span>
        </div>
        <time
          dateTime={entry.created_at}
          className="font-mono text-xs text-ink-faint shrink-0"
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
    </li>
  );
}

export default ChangeEntry;
