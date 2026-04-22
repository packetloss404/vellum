import React from "react";
import { Link, useLocation } from "react-router-dom";
import { Pill } from "../common/Pill";
import type { DossierStatus } from "../../api/types";

/**
 * Header — the single piece of chrome above every page.
 *
 * Styled as a quiet printed masthead: "Vellum" wordmark on the left in
 * serif, a small "All dossiers" link on the right on any page other than
 * "/". No user menu, no notifications, no toolbar — the dossier IS the
 * page, so chrome stays out of the way.
 *
 * In dossier mode (when a `dossier` prop is passed), the current dossier's
 * title and type/status line appear beside the wordmark, with the "all
 * dossiers" link still visible to the right. This mirrors a printed case
 * file's cover marking and keeps navigation within reach on detail pages.
 */

export interface HeaderProps {
  title?: string;
  dossier?: {
    title: string;
    dossier_type: string;
    status: string;
  };
}

function statusVariant(
  status: string,
): { variant: "default" | "state" | "accent" | "attention"; state?: "confident" | "provisional" | "blocked" } {
  switch (status as DossierStatus) {
    case "active":
      return { variant: "accent" };
    case "paused":
      return { variant: "default" };
    case "delivered":
      // Confident green — the case file is finished, and the status
      // pill should read positive, not incidental.
      return { variant: "state", state: "confident" };
    default:
      return { variant: "default" };
  }
}

export function Header({ title, dossier }: HeaderProps) {
  const dossierMode = !!dossier;
  const { pathname } = useLocation();
  const onHome = pathname === "/";

  return (
    <header className="border-b border-rule bg-paper">
      <div className="mx-auto max-w-page px-6 py-4 flex items-center justify-between gap-6">
        <Link
          to="/"
          className="font-serif text-xl text-ink tracking-tight hover:text-accent transition-colors shrink-0"
          aria-label="Vellum — home"
        >
          Vellum
        </Link>

        {dossierMode ? (
          <div className="text-center min-w-0 flex-1">
            <div className="text-sm font-serif text-ink truncate">
              {dossier!.title}
            </div>
            <div className="mt-0.5 flex items-center gap-2 justify-center text-xs font-mono text-ink-faint">
              <span className="lowercase tracking-wide">
                {dossier!.dossier_type.replace(/_/g, " ")}
              </span>
              <span aria-hidden="true">·</span>
              {(() => {
                const v = statusVariant(dossier!.status);
                return (
                  <Pill variant={v.variant} state={v.state}>
                    {dossier!.status}
                  </Pill>
                );
              })()}
            </div>
          </div>
        ) : title ? (
          <span className="text-sm font-mono text-ink-faint truncate">
            {title}
          </span>
        ) : (
          <span className="flex-1" aria-hidden="true" />
        )}

        {!onHome ? (
          <Link
            to="/"
            className="shrink-0 font-sans text-xs text-ink-faint hover:text-accent transition-colors uppercase tracking-wide"
          >
            All dossiers
          </Link>
        ) : (
          <span className="shrink-0 w-[92px]" aria-hidden="true" />
        )}
      </div>
    </header>
  );
}

export default Header;
