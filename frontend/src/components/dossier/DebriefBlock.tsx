import React from "react";
import type { Debrief } from "../../api/types";
import { Card } from "../common/Card";

/**
 * DebriefBlock — the "here's what I did, here's what I found" summary at
 * the top of a reopened dossier. Four labeled fields, each rendered as
 * flowing serif prose. Empty fields show as "—" so the shape of the
 * debrief is always legible. Renders nothing if no debrief is populated.
 */

export interface DebriefBlockProps {
  debrief?: Debrief | null;
}

const EMPTY = "—";

const FIELDS: Array<{ key: keyof Debrief; label: string }> = [
  { key: "what_i_did", label: "What I did" },
  { key: "what_i_found", label: "What I found" },
  { key: "what_you_should_do_next", label: "What you should do next" },
  { key: "what_i_couldnt_figure_out", label: "What I couldn't figure out" },
];

function valueFor(debrief: Debrief, key: keyof Debrief): string {
  const raw = debrief[key];
  if (typeof raw !== "string") return EMPTY;
  const trimmed = raw.trim();
  return trimmed.length > 0 ? trimmed : EMPTY;
}

export function DebriefBlock({ debrief }: DebriefBlockProps) {
  if (!debrief) return null;

  // If every field is empty, still skip — we don't render four dashes
  // with no context.
  const anyPopulated = FIELDS.some(
    ({ key }) =>
      typeof debrief[key] === "string" &&
      (debrief[key] as string).trim().length > 0,
  );
  if (!anyPopulated) return null;

  return (
    <Card className="space-y-5">
      <h2 className="font-mono text-xs uppercase tracking-wide text-ink-faint">
        Debrief
      </h2>
      <dl className="space-y-5">
        {FIELDS.map(({ key, label }) => {
          const value = valueFor(debrief, key);
          const isEmpty = value === EMPTY;
          return (
            <div key={key}>
              <dt className="font-mono text-xs uppercase tracking-wide text-ink-faint mb-1">
                {label}
              </dt>
              <dd
                className={
                  isEmpty
                    ? "font-serif text-base text-ink-faint italic"
                    : "font-serif text-base text-ink leading-relaxed whitespace-pre-wrap"
                }
              >
                {value}
              </dd>
            </div>
          );
        })}
      </dl>
    </Card>
  );
}

export default DebriefBlock;
