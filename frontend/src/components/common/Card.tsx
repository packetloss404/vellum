import React from "react";

/**
 * Card — the fundamental content container.
 *
 * The default tone is "surface" (crisp white-ish), which reads as a sheet
 * laid on the paper background — matches how Card is used today across
 * PlanBlock, NeedsInputItem, DossierCard, etc.
 *
 * The "sunk" tone uses paper-dark: a warmer, slightly-darker surface for
 * cards that should read as INSET into the page (e.g. sidebars, secondary
 * containers). Use sparingly.
 */

export type CardTone = "surface" | "sunk";

export interface CardProps {
  children: React.ReactNode;
  className?: string;
  as?: keyof JSX.IntrinsicElements;
  tone?: CardTone;
}

const toneClasses: Record<CardTone, string> = {
  surface: "bg-surface",
  sunk: "bg-paper-dark",
};

function cx(...parts: Array<string | false | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

export function Card({
  children,
  className,
  as,
  tone = "surface",
}: CardProps) {
  const Tag = (as ?? "div") as any;
  return (
    <Tag
      className={cx(
        toneClasses[tone],
        "border border-rule rounded p-6",
        className,
      )}
    >
      {children}
    </Tag>
  );
}

export default Card;
