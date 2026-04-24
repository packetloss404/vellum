import React, { useMemo } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import DossierPage from "./DossierPage";
import {
  stressCaseFile,
  STRESS_CHANGE_LOG,
  STRESS_DOSSIER_ID,
  STRESS_INVESTIGATION_LOG_COUNTS,
} from "../mocks/stressCaseFile";
import { qk } from "../api/hooks";

/**
 * StressPage — /stress. Mounts DossierPage against a local, pre-populated
 * QueryClient seeded with the worst-case fixture from
 * ../mocks/stressCaseFile. No network: all queries DossierPage fires
 * resolve synchronously out of the cache.
 *
 * Why a local QueryClient rather than wiring the fixture through the
 * app-level client: we want /stress to feel exactly like /dossiers/<id>
 * at render time but without any risk of polluting the real app cache,
 * and without needing to add a special fixture case to the api layer.
 * DossierPage is mounted directly with `fixtureId` (no nested router —
 * the outer BrowserRouter already owns routing). Pre-seed what
 * DossierPage reads:
 *
 *   - ["dossier", id]                           → DossierFull
 *   - ["dossier", id, "change-log"]             → ChangeLogEntry[]
 *   - ["dossier", id, "investigation-log", …]   → InvestigationLogEntry[]
 *   - ["dossier", id, "investigation-log", "counts"] → Record<string, number>
  *   - ["dossier", id, "resume-state"]           → { active_work_session_id: null }
  *   - ["dossier", id, "agent-status"]           → { running: false }
 *
  * DossierPage is mounted in readOnlyFixture mode so visit/resume mutations
  * do not hit the backend. If a query somehow misfires, retries are disabled
  * so it errors loudly rather than spinning.
 */
export default function StressPage() {
  const queryClient = useMemo(() => {
    const qc = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
          // Keep the seeded data from being considered stale and refetched.
          staleTime: Infinity,
          // No network at all on this page — if a query somehow fires, it
          // should fail fast rather than hang.
          refetchOnMount: false,
          refetchOnWindowFocus: false,
          refetchOnReconnect: false,
        },
        mutations: {
          // Mutations are no-ops against our fixture — swallow errors.
          retry: false,
        },
      },
    });

    const id = STRESS_DOSSIER_ID;
    qc.setQueryData(qk.dossier(id), stressCaseFile);
    qc.setQueryData(qk.changeLog(id), STRESS_CHANGE_LOG);
    // useInvestigationLog composes the query key as
    //   [...qk.investigationLog(id, entryType), limit]
    // DossierPage's sidebar calls it with { limit: 500 } and no entry
    // type, so the key is [...qk.investigationLog(id, undefined), 500].
    qc.setQueryData(
      [...qk.investigationLog(id, undefined), 500],
      stressCaseFile.investigation_log ?? [],
    );
    qc.setQueryData(
      qk.investigationLogCounts(id),
      STRESS_INVESTIGATION_LOG_COUNTS,
    );
    qc.setQueryData(qk.resumeState(id), {
      active_work_session_id: null,
      wake_pending: false,
    });
    qc.setQueryData(qk.agentStatus(id), {
      running: false,
      started_at: null,
    });

    return qc;
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <DossierPage readOnlyFixture fixtureId={STRESS_DOSSIER_ID} />
    </QueryClientProvider>
  );
}
