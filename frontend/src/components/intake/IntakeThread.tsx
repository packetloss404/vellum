import React from "react";
import type { IntakeMessage } from "../../api/types";
import { EmptyState } from "../common/EmptyState";

/**
 * IntakeThread — document-like rendering of the intake conversation.
 *
 * This is explicitly NOT a chatbot bubble UI. Both sides are left-aligned;
 * the only differentiation is the small-caps mono author label and a subtle
 * left border on assistant messages.
 *
 * When `pending` is true, a "VELLUM" author label with an animated ellipsis
 * appears below the last message so the user sees that a reply is being
 * drafted. This is a CSS-animated inline indicator, not a spinner — it
 * should feel like someone is writing, not like the system is loading.
 */

export interface IntakeThreadProps {
  messages: IntakeMessage[];
  pending?: boolean;
}

export function IntakeThread({ messages, pending }: IntakeThreadProps) {
  if (messages.length === 0 && !pending) {
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

      {pending ? <ThinkingIndicator /> : null}
    </div>
  );
}

/**
 * ThinkingIndicator — three dots that animate in sequence via CSS. The
 * spans share one keyframe and stagger via animation-delay so the browser
 * does all the work.
 */
function ThinkingIndicator() {
  return (
    <div aria-live="polite" aria-label="Vellum is thinking">
      <div className="text-xs font-mono uppercase tracking-wide text-ink-faint mb-1">
        VELLUM
      </div>
      <div className="font-serif text-base text-ink-muted leading-relaxed border-l-2 border-rule pl-4 italic">
        <span className="inline-flex items-end gap-[2px] align-baseline">
          <Dot delay="0s" />
          <Dot delay="0.2s" />
          <Dot delay="0.4s" />
        </span>
        <style>{`
          @keyframes vellum-thinking-dot {
            0%, 80%, 100% { opacity: 0.15; transform: translateY(0); }
            40% { opacity: 1; transform: translateY(-2px); }
          }
        `}</style>
      </div>
    </div>
  );
}

function Dot({ delay }: { delay: string }) {
  return (
    <span
      aria-hidden="true"
      style={{
        display: "inline-block",
        width: "4px",
        height: "4px",
        borderRadius: "50%",
        background: "currentColor",
        animation: "vellum-thinking-dot 1.2s ease-in-out infinite",
        animationDelay: delay,
      }}
    />
  );
}

export default IntakeThread;
