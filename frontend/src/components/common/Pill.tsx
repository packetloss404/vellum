import React from "react";

export type PillVariant = "default" | "state" | "attention" | "accent";
export type PillState = "confident" | "provisional" | "blocked";

export interface PillProps {
  children: React.ReactNode;
  variant?: PillVariant;
  state?: PillState;
  className?: string;
}

const base =
  "inline-flex items-center gap-1 px-2 py-0.5 text-xs font-mono rounded";

const variantClasses: Record<PillVariant, string> = {
  default: "bg-surface-sunk text-ink-muted border border-rule",
  state: "", // resolved via `state` prop below
  attention: "bg-attention-bg text-attention",
  accent: "bg-accent-bg text-accent",
};

const stateClasses: Record<PillState, string> = {
  confident: "bg-state-confident-bg text-state-confident",
  provisional: "bg-state-provisional-bg text-state-provisional",
  blocked: "bg-state-blocked-bg text-state-blocked",
};

function cx(...parts: Array<string | false | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

export function Pill({
  children,
  variant = "default",
  state,
  className,
}: PillProps) {
  const variantClass =
    variant === "state"
      ? stateClasses[state ?? "provisional"]
      : variantClasses[variant];

  return (
    <span className={cx(base, variantClass, className)}>{children}</span>
  );
}

export default Pill;
