import type { ResearchEvidence } from "../../api/types";

const PROVENANCE_LABEL: Record<string, string> = {
  discovered: "Discovered",
  cited: "Cited",
  consulted: "Consulted",
  user_provided: "User provided",
};

export function EvidenceLedger({ evidence }: { evidence?: ResearchEvidence }) {
  if (!evidence || evidence.sources.length === 0) {
    return <p className="font-serif text-sm text-ink-faint">No captured evidence for this run yet.</p>;
  }
  const bySource = new Map<string, typeof evidence.observations>();
  for (const observation of evidence.observations) {
    const current = bySource.get(observation.source_id) ?? [];
    current.push(observation);
    bySource.set(observation.source_id, current);
  }
  return (
    <ul className="space-y-3" aria-label="Evidence ledger">
      {evidence.sources.map((source) => {
        const observations = bySource.get(source.id) ?? [];
        const strongest = observations.some((item) => item.provenance === "consulted")
          ? "consulted"
          : observations.some((item) => item.provenance === "cited")
            ? "cited"
            : observations[0]?.provenance ?? "discovered";
        const excerpt = observations.find((item) => item.excerpt)?.excerpt;
        return (
          <li key={source.id} className="rounded border border-rule bg-paper px-3 py-2">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <a
                href={source.original_url}
                target="_blank"
                rel="noreferrer"
                className="font-serif text-sm text-ink hover:text-accent"
              >
                {source.title || source.domain || source.original_url}
              </a>
              <div className="flex gap-1">
                <span className="rounded border border-rule px-1.5 py-0.5 font-mono text-[9px] uppercase text-ink-muted">
                  {PROVENANCE_LABEL[strongest] ?? strongest}
                </span>
                {["government_domain", "verified_official"].includes(source.authority_status) ? (
                  <span className="rounded border border-rule px-1.5 py-0.5 font-mono text-[9px] uppercase text-ink-muted">
                    Government domain
                  </span>
                ) : null}
              </div>
            </div>
            {source.model_source_type || source.model_authority ? (
              <p className="mt-1 font-mono text-[10px] text-ink-faint">
                Agent-classified: {[source.model_source_type, source.model_authority].filter(Boolean).join(" · ")}
              </p>
            ) : null}
            {excerpt ? <p className="mt-2 font-serif text-xs leading-relaxed text-ink-muted">{excerpt}</p> : null}
          </li>
        );
      })}
    </ul>
  );
}
