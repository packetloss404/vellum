import React from "react";
import { Link } from "react-router-dom";
import { Pill } from "../common/Pill";
import type { DossierStatus } from "../../api/types";

/**
 * Header — the single piece of chrome above every page.
 *
 * Two modes:
 *   - Default (no dossier): just the Vellum wordmark, centered in a
 *     restrained top bar. This is all the chrome the landing page gets.
 *   - Dossier mode: wordmark left, dossier title + metadata row right.
 *     One-row layout on wide viewports; stacks on narrow.
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
): "default" | "state" | "accent" | "attention" {
  // Map dossier status onto a Pill variant. "active" reads as accent,
  // everything else stays muted/default.
  switch (status as DossierStatus) {
    case "active":
      return "accent";
    case "paused":
      return "default";
    case "delivered":
      return "default";
    default:
      return "default";
  }
}

export function Header({ title, dossier }: HeaderProps) {
  const dossierMode = !!dossier;

  return (
    <header className="border-b border-rule bg-paper">
      <div
        className={
          dossierMode
            ? "mx-auto max-w-page px-6 py-4 flex items-center justify-between gap-6"
            : "mx-auto max-w-page px-6 py-5"
        }
      >
        <Link
          to="/"
          className={
            dossierMode
              ? "font-serif text-xl text-ink tracking-tight hover:text-accent transition-colors"
              : "font-serif text-2xl text-ink tracking-tight hover:text-accent transition-colors"
          }
        >
          Vellum
        </Link>

        {dossierMode ? (
          <div className="text-right min-w-0 flex-1">
            <div className="text-lg font-serif text-ink truncate">
              {dossier!.title}
            </div>
            <div className="mt-0.5 flex items-center gap-2 justify-end text-xs font-mono text-ink-faint">
              <span className="lowercase tracking-wide">
                {dossier!.dossier_type.replace(/_/g, " ")}
              </span>
              <span aria-hidden="true">·</span>
              <Pill variant={statusVariant(dossier!.status)}>
                {dossier!.status}
              </Pill>
            </div>
          </div>
        ) : title ? (
          <span className="ml-4 text-sm font-mono text-ink-faint">{title}</span>
        ) : null}
      </div>
    </header>
  );
}

export default Header;
