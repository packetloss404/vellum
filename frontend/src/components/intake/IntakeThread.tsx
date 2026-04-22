import React from "react";
import type { IntakeMessage } from "../../api/types";
import { EmptyState } from "../common/EmptyState";

/**
 * IntakeThread — document-like rendering of the intake conversation.
 *
 * This is explicitly NOT a chatbot bubble UI. Both sides are left-aligned;
 * the only differentiation is the small-caps mono author label and a subtle
 * left border on assistant messages.
 */

export interface IntakeThreadProps {
  messages: IntakeMessage[];
}

export function IntakeThread({ messages }: IntakeThreadProps) {
  if (messages.length === 0) {
    return (
      <EmptyState
        title="Describe the problem."
        hint="Two or three sentences will do."
      />
    );
  }

  return (
    <div className="space-y-6">
      {messages.map((m) => {
        const isAssistant = m.role === "assistant";
        return (
          <div key={m.id}>
            <div className="text-xs font-mono uppercase tracking-wide text-ink-faint mb-1">
              {isAssistant ? "VELLUM" : "YOU"}
            </div>
            <div
              className={
                isAssistant
                  ? "font-serif text-base text-ink leading-relaxed whitespace-pre-wrap border-l-2 border-rule pl-4"
                  : "font-serif text-base text-ink leading-relaxed whitespace-pre-wrap"
              }
            >
              {m.content}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default IntakeThread;
