import React from "react";
import { Link } from "react-router-dom";
import type { IntakeState, IntakeStatus } from "../../api/types";
import { Pill } from "../common/Pill";

/**
 * IntakeStateSummary — the right-rail "Gathered so far" panel.
 *
 * Mirrors the state block the intake agent sees internally. Muted support
 * for the thread; the thread is the focus.
 */

export interface IntakeStateSummaryProps {
  state: IntakeState;
  status: IntakeStatus;
  dossierId?: string | null;
}

type FieldRow = { key: string; label: string; value: string | null };

function buildRows(state: IntakeState): FieldRow[] {
  const outOfScope =
    state.out_of_scope && state.out_of_scope.length > 0
      ? state.out_of_scope.join(", ")
      : null;

  const checkIn = state.check_in_policy
    ? `${state.check_in_policy.cadence.replace(/_/g, " ")}${
        state.check_in_policy.notes
          ? ` — ${state.check_in_policy.notes}`
          : ""
      }`
    : null;

  const dossierType = state.dossier_type
    ? state.dossier_type.replace(/_/g, " ")
    : null;

  return [
    { key: "title", label: "Title", value: state.title ?? null },
    {
      key: "problem_statement",
      label: "Problem",
      value: state.problem_statement ?? null,
    },
    { key: "dossier_type", label: "Type", value: dossierType },
    { key: "out_of_scope", label: "Out of scope", value: outOfScope },
    { key: "check_in_policy", label: "Check-in", value: checkIn },
  ];
}

function missingKeys(rows: FieldRow[]): string[] {
  return rows.filter((r) => r.value === null).map((r) => r.key);
}

export function IntakeStateSummary({
  state,
  status,
  dossierId,
}: IntakeStateSummaryProps) {
  const rows = buildRows(state);
  const missing = missingKeys(rows);

  if (status === "abandoned") {
    return (
      <aside className="sticky top-6 w-full md:w-[260px] text-ink-faint font-serif italic text-sm">
        Abandoned.
      </aside>
    );
  }

  return (
    <aside className="sticky top-6 w-full md:w-[260px]">
      <div className="text-xs font-mono uppercase tracking-wide text-ink-faint">
        Gathered so far
      </div>

      <div className="mt-4 space-y-4">
        {rows.map((r) => (
          <div key={r.key}>
            <div className="text-xs font-mono uppercase text-ink-muted">
              {r.label}
            </div>
            <div
              className={
                r.value
                  ? "text-sm font-serif text-ink mt-1"
                  : "text-sm font-serif text-ink-faint italic mt-1"
              }
            >
              {r.value ?? "not set"}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-6">
        {status === "committed" && dossierId ? (
          <Link to={`/dossiers/${dossierId}`} className="inline-block">
            <Pill variant="state" state="confident">
              Dossier open
            </Pill>
          </Link>
        ) : missing.length === 0 ? (
          <div className="text-xs font-mono text-attention">
            All gathered — ready to commit.
          </div>
        ) : (
          <div className="text-xs font-mono text-attention">
            Missing: {missing.join(", ")}
          </div>
        )}
      </div>
    </aside>
  );
}

export default IntakeStateSummary;
