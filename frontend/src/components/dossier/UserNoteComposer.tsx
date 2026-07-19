import React, { useState } from "react";
import type { UserNote } from "../../api/types";
import { Card } from "../common/Card";
import { useAddUserNote } from "../../api/hooks";
import { relativeTime } from "../../utils/time";

/**
 * UserNoteComposer — "tell the agent something".
 *
 * The one free-form input channel into a running investigation: volunteer a
 * new fact, correct an error, or redirect scope without waiting for the
 * agent to ask. Sending a note wakes the agent on the next scheduler tick.
 * Recent notes render beneath the box with a seen/waiting marker so the
 * user knows whether the agent has picked them up yet.
 */

export interface UserNoteComposerProps {
  dossierId: string;
  notes: UserNote[];
}

const RECENT_NOTES_SHOWN = 3;

export function UserNoteComposer({ dossierId, notes }: UserNoteComposerProps) {
  const [content, setContent] = useState("");
  const mutation = useAddUserNote();

  const trimmed = content.trim();
  const canSubmit = trimmed.length > 0 && !mutation.isPending;
  const recent = notes.slice(-RECENT_NOTES_SHOWN).reverse();

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    mutation.mutate(
      { dossierId, content: trimmed },
      {
        // On failure the textarea keeps its content so the user can retry
        // without retyping.
        onSuccess: () => setContent(""),
      }
    );
  }

  return (
    <Card>
      <div className="text-xs font-mono uppercase tracking-wide text-ink-faint mb-3">
        Tell the agent something
      </div>

      <form onSubmit={handleSubmit}>
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          rows={3}
          placeholder="A new fact, a correction, a change of direction…"
          disabled={mutation.isPending}
          aria-label="Note to the agent"
          className="w-full font-serif text-sm bg-surface border border-rule rounded px-3 py-2 text-ink placeholder:text-ink-faint focus:outline-none focus:border-accent resize-y disabled:opacity-60"
        />
        <div className="mt-2 flex items-center justify-end gap-3">
          {mutation.isError ? (
            <span className="text-xs text-state-blocked font-sans">
              Couldn't send — try again.
            </span>
          ) : null}
          <button
            type="submit"
            disabled={!canSubmit}
            className="border border-rule-strong text-ink-muted hover:text-ink hover:border-accent px-3 py-1.5 font-sans text-xs rounded transition-colors disabled:opacity-60 disabled:cursor-not-allowed bg-surface"
          >
            {mutation.isPending ? "Sending…" : "Send to agent"}
          </button>
        </div>
      </form>

      {recent.length > 0 ? (
        <ul className="mt-4 space-y-3 border-t border-rule pt-3">
          {recent.map((note) => (
            <li key={note.id} className="text-sm">
              <p className="font-serif text-ink whitespace-pre-wrap">
                {note.content}
              </p>
              <div className="mt-1 flex items-center gap-2 text-xs font-mono text-ink-faint">
                <span>{relativeTime(note.created_at)}</span>
                <span aria-hidden="true">·</span>
                <span>
                  {note.seen_at ? "seen by agent" : "waiting for agent"}
                </span>
              </div>
            </li>
          ))}
        </ul>
      ) : null}
    </Card>
  );
}
