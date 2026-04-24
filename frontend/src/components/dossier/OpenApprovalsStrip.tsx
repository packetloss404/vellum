import type { DecisionPoint, NeedsInput } from "../../api/types";

/**
 * OpenApprovalsStrip — a quiet inline bar that surfaces WHAT NEEDS A
 * CLICK right now. Doesn't reduce the count (that's a product-design
 * problem); just makes "how many items am I staring at" immediately
 * readable so the user can batch-process.
 *
 * Hides entirely when no items are pending — zero visual weight on a
 * quiet dossier.
 */

interface Props {
  needsInput: NeedsInput[];
  decisionPoints: DecisionPoint[];
}

export function OpenApprovalsStrip({ needsInput, decisionPoints }: Props) {
  const openNeedsInput = needsInput.filter((n) => !n.answered_at);
  const openDps = decisionPoints.filter((dp) => !dp.resolved_at);
  const planApproval = openDps.find((dp) => dp.kind === "plan_approval");
  const otherDps = openDps.filter((dp) => dp.kind !== "plan_approval");

  const pieces: Array<{ key: string; label: string; href: string }> = [];
  if (planApproval) {
    pieces.push({
      key: "plan_approval",
      label: "plan approval pending",
      href: "#plan",
    });
  }
  if (otherDps.length > 0) {
    pieces.push({
      key: "other_dps",
      label: `${otherDps.length} decision${otherDps.length === 1 ? "" : "s"} to resolve`,
      href: "#decisions",
    });
  }
  if (openNeedsInput.length > 0) {
    pieces.push({
      key: "needs_input",
      label: `${openNeedsInput.length} question${openNeedsInput.length === 1 ? "" : "s"} to answer`,
      href: "#needs-input",
    });
  }

  if (pieces.length === 0) return null;

  return (
    <section
      aria-label="Items waiting on you"
      className="border border-attention/40 bg-attention-bg/60 rounded px-4 py-2 flex flex-wrap items-center gap-x-4 gap-y-1"
    >
      <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-attention">
        waiting on you
      </span>
      {pieces.map((p, i) => (
        <span key={p.key} className="flex items-center gap-2">
          <a
            href={p.href}
            className="font-serif text-sm text-ink hover:text-accent transition-colors"
          >
            {p.label}
          </a>
          {i < pieces.length - 1 ? (
            <span aria-hidden="true" className="text-ink-faint">
              ·
            </span>
          ) : null}
        </span>
      ))}
    </section>
  );
}

export default OpenApprovalsStrip;
