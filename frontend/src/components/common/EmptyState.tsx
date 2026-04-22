import React from "react";

export interface EmptyStateProps {
  title: string;
  hint?: string;
  children?: React.ReactNode;
}

export function EmptyState({ title, hint, children }: EmptyStateProps) {
  return (
    <div className="text-center text-ink-muted font-serif italic py-12 px-6">
      <div className="text-lg">{title}</div>
      {hint ? (
        <div className="mt-2 text-sm text-ink-faint not-italic font-serif">
          {hint}
        </div>
      ) : null}
      {children ? <div className="mt-4 not-italic">{children}</div> : null}
    </div>
  );
}

export default EmptyState;
