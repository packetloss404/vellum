import { render, screen } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { EvidenceLedger } from "./EvidenceLedger";
import { ResearchTimeline } from "./ResearchTimeline";

describe("research audit surfaces", () => {
  it("labels model classifications separately from objective provenance", () => {
    render(
      <EvidenceLedger
        evidence={{
          run_id: "run_1",
          sources: [{
            id: "src_1", dossier_id: "dos_1", canonical_url: "https://agency.gov/rule",
            original_url: "https://agency.gov/rule", title: "Agency rule", domain: "agency.gov",
            source_kind: "web", model_source_type: "primary", model_authority: "official",
            authority_status: "government_domain", authority_basis: "deterministic_official_domain",
            created_at: "2026-09-04T12:00:00Z", updated_at: "2026-09-04T12:00:00Z",
          }],
          observations: [{
            id: "obs_1", source_id: "src_1", run_id: "run_1", provenance: "cited",
            excerpt: "The rule applies.", created_at: "2026-09-04T12:00:00Z",
          }],
          claims: [], claim_evidence: [],
        }}
      />,
    );
    expect(screen.getByText("Cited")).toBeInTheDocument();
    expect(screen.getByText("Government domain")).toBeInTheDocument();
    expect(screen.getByText(/Agent-classified: primary · official/)).toBeInTheDocument();
    expect(screen.queryByText(/^Verified$/)).not.toBeInTheDocument();
  });

  it("keeps completed and superseded runs visible in history", () => {
    render(
      <BrowserRouter>
        <ResearchTimeline selectedRunId="run_1" runs={[{
          id: "run_1", dossier_id: "dos_1", depth: "deep", strategy_version: "v1",
          status: "completed", initiated_by: "user", state_version: 4,
          started_at: "2026-09-04T12:00:00Z", updated_at: "2026-09-04T13:00:00Z",
          ended_at: "2026-09-04T13:00:00Z", completion_reason: "targets_met",
          sessions_started: 3, cost_usd: 4.25,
          policy_snapshot: {
            depth: "deep", autonomy_enabled: true, max_sessions: 10,
            max_turns_per_session: 30, max_cost_usd: 30, target_source_count: 50,
            min_primary_sources: 8, continuation_delay_minutes: 1,
          },
        }]} />
      </BrowserRouter>,
    );
    expect(screen.getByText(/deep · completed/i)).toBeInTheDocument();
    expect(screen.getByText(/3 sessions · \$4.25/)).toBeInTheDocument();
    expect(screen.getByRole("button", { pressed: true })).toBeInTheDocument();
  });
});
