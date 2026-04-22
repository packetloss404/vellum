import React, { useEffect, useLayoutEffect, useRef, useState } from "react";

/**
 * IntakeInput — the sticky composer at the bottom of the intake thread.
 *
 * Keyboard:
 *   - Enter submits.
 *   - Shift+Enter inserts a newline.
 *   - Cmd/Ctrl+Enter also submits (matches the muscle memory of people who
 *     reach for a modifier-key submit out of habit).
 *   - While an IME composition is active (e.g. Japanese, Chinese), Enter is
 *     passed through so the user can finalize the composition without
 *     accidentally submitting the turn.
 *
 * Textarea auto-grows between 3 and 12 rows. We measure via a hidden
 * mirror sized from the computed line-height so growth tracks font-size
 * changes — keeping this document-like rather than chat-like.
 */

export interface IntakeInputProps {
  onSend: (text: string) => Promise<void>;
  disabled?: boolean;
  placeholder?: string;
}

const MIN_ROWS = 3;
const MAX_ROWS = 12;

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

  // Resize the textarea to fit content, clamped to MIN_ROWS..MAX_ROWS. We
  // reset height to `auto` first so scrollHeight reflects the *current*
  // content rather than the previously-applied height.
  useLayoutEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    const style = window.getComputedStyle(el);
    const lineHeight = parseFloat(style.lineHeight);
    const paddingY =
      parseFloat(style.paddingTop) + parseFloat(style.paddingBottom);
    const borderY =
      parseFloat(style.borderTopWidth) + parseFloat(style.borderBottomWidth);
    const minH = lineHeight * MIN_ROWS + paddingY + borderY;
    const maxH = lineHeight * MAX_ROWS + paddingY + borderY;

    el.style.height = "auto";
    const next = Math.min(Math.max(el.scrollHeight, minH), maxH);
    el.style.height = `${next}px`;
    el.style.overflowY = el.scrollHeight > maxH ? "auto" : "hidden";
  }, [value]);

  // Keep focus on the composer when the parent flips disabled back off —
  // otherwise the user has to click back in after each assistant turn.
  useEffect(() => {
    if (!disabled) {
      textareaRef.current?.focus();
    }
  }, [disabled]);

  async function handleSubmit(e?: React.FormEvent) {
    if (e) e.preventDefault();
    if (!canSend) return;
    const text = trimmed;
    // Clear optimistically so the textarea feels responsive. If the caller
    // throws, restore so the user can retry without retyping.
    setValue("");
    try {
      await onSend(text);
    } catch {
      setValue(text);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key !== "Enter") return;
    if (isComposing) return; // IME in progress
    // Shift+Enter always means newline.
    if (e.shiftKey) return;
    // Cmd/Ctrl+Enter always submits (even if Shift would normally newline).
    // Plain Enter submits too; Shift+Enter newlines.
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
          rows={MIN_ROWS}
          placeholder={placeholder ?? "Reply…"}
          disabled={disabled}
          aria-label="Reply"
          className="w-full resize-none font-serif text-base bg-surface border border-rule focus:border-accent focus:outline-none rounded px-3 py-2 text-ink placeholder:text-ink-faint disabled:opacity-50"
        />
        <div className="flex items-center justify-between">
          <div className="text-xs font-mono text-ink-faint">
            Enter to send · Shift+Enter for newline
          </div>
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
