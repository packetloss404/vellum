import React, { useRef, useState } from "react";

/**
 * IntakeInput — the sticky composer at the bottom of the intake thread.
 *
 * Keyboard:
 *   - Enter submits.
 *   - Shift+Enter inserts a newline.
 *   - While an IME composition is active (e.g. Japanese, Chinese), Enter is
 *     passed through so the user can finalize the composition without
 *     accidentally submitting the turn.
 */

export interface IntakeInputProps {
  onSend: (text: string) => Promise<void>;
  disabled?: boolean;
  placeholder?: string;
}

export function IntakeInput({
  onSend,
  disabled,
  placeholder,
}: IntakeInputProps) {
  const [value, setValue] = useState("");
  const [isComposing, setIsComposing] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const trimmed = value.trim();
  const canSend = !disabled && trimmed.length > 0;

  async function handleSubmit(e?: React.FormEvent) {
    if (e) e.preventDefault();
    if (!canSend) return;
    const text = trimmed;
    // Clear optimistically so the textarea feels responsive. If the caller
    // throws, the parent is responsible for surfacing the error; we don't
    // restore the text (keeping the behavior predictable).
    setValue("");
    try {
      await onSend(text);
    } catch {
      // Swallow here — parent renders the error. Restore text so the user
      // can retry without retyping.
      setValue(text);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key !== "Enter") return;
    if (e.shiftKey) return; // newline
    if (isComposing) return; // IME in progress
    e.preventDefault();
    void handleSubmit();
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="sticky bottom-0 bg-paper border-t border-rule py-4"
    >
      <div className="flex flex-col gap-2">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          onCompositionStart={() => setIsComposing(true)}
          onCompositionEnd={() => setIsComposing(false)}
          rows={3}
          placeholder={placeholder ?? "Reply…"}
          disabled={disabled}
          aria-label="Reply"
          className="w-full resize-none font-serif text-base bg-surface border border-rule focus:border-accent focus:outline-none rounded px-3 py-2 text-ink placeholder:text-ink-faint disabled:opacity-50"
        />
        <div className="flex items-center justify-end">
          <button
            type="submit"
            disabled={!canSend}
            className="bg-accent text-paper font-sans text-sm rounded px-4 py-2 hover:bg-accent-hover disabled:opacity-50"
          >
            Send to Vellum
          </button>
        </div>
      </div>
    </form>
  );
}

export default IntakeInput;
