import React from "react";

/**
 * Button — the one button primitive.
 *
 * Variants:
 *   primary   — filled accent, paper text. Default action.
 *   secondary — outline ink, paper background. "Cancel"-grade action.
 *   ghost     — text-only, no border. Quiet inline action.
 *
 * Sizes:
 *   sm — compact (h≈28px), for toolbars and inline rows.
 *   md — default (h≈36px), for forms and page CTAs.
 *
 * Keyboard + focus are handled by the native <button>; globals.css installs
 * a visible focus-ring on `:focus-visible`. Disabled dims to 50% and blocks
 * the pointer.
 */

export type ButtonVariant = "primary" | "secondary" | "ghost";
export type ButtonSize = "sm" | "md";

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
}

const base =
  "inline-flex items-center justify-center font-sans rounded transition-colors " +
  "disabled:opacity-50 disabled:cursor-not-allowed";

const variantClasses: Record<ButtonVariant, string> = {
  primary: "bg-accent text-paper hover:bg-accent-hover",
  secondary:
    "bg-paper text-ink border border-rule-strong hover:bg-paper-dark",
  ghost: "text-accent hover:text-accent-hover bg-transparent",
};

const sizeClasses: Record<ButtonSize, string> = {
  sm: "text-xs px-3 py-1.5",
  md: "text-sm px-4 py-2",
};

function cx(...parts: Array<string | false | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

export function Button({
  variant = "primary",
  size = "md",
  className,
  type,
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type ?? "button"}
      className={cx(base, variantClasses[variant], sizeClasses[size], className)}
      {...rest}
    >
      {children}
    </button>
  );
}

export default Button;
