import React from "react";

/**
 * Badge — small inline label for kinds and categories.
 *
 * Distinct from Pill: Badge is a quiet typographic tag (used like a noun
 * inline with serif body text — "dossier type", "artifact kind"), while
 * Pill is a mono status chip. Badge uses small-caps-esque tracking.
 *
 * Variants map to token palettes:
 *   neutral   — default, for kinds/categories
 *   accent    — highlights the primary subject
 *   attention — amber, for in-progress / needs-action
 *   blocked   — rusty, for stopped / error kinds
 */

export type BadgeVariant = "neutral" | "accent" | "attention" | "blocked";

export interface BadgeProps {
  children: React.ReactNode;
  variant?: BadgeVariant;
  className?: string;
}

const base =
  "inline-flex items-center px-2 py-0.5 text-[11px] font-sans uppercase " +
  "tracking-wide rounded border";

const variantClasses: Record<BadgeVariant, string> = {
  neutral: "bg-paper-dark text-ink-muted border-rule",
  accent: "bg-accent-bg text-accent border-accent/20",
  attention: "bg-attention-bg text-attention border-attention/20",
  blocked: "bg-state-blocked-bg text-state-blocked border-state-blocked/20",
};

function cx(...parts: Array<string | false | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

export function Badge({ children, variant = "neutral", className }: BadgeProps) {
  return (
    <span className={cx(base, variantClasses[variant], className)}>
      {children}
    </span>
  );
}

export default Badge;
