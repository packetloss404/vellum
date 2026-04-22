import React from "react";

export interface CardProps {
  children: React.ReactNode;
  className?: string;
  as?: keyof JSX.IntrinsicElements;
}

function cx(...parts: Array<string | false | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

export function Card({ children, className, as }: CardProps) {
  const Tag = (as ?? "div") as any;
  return (
    <Tag
      className={cx(
        "bg-surface border border-rule rounded p-6",
        className
      )}
    >
      {children}
    </Tag>
  );
}

export default Card;
