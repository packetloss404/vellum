import { useMemo } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import DossierPage from "./DossierPage";
import { qk } from "../api/hooks";
import type { ChangeLogEntry, DossierFull } from "../api/types";

/**
 * FixtureHost — shared render path for the /stress* routes.
 *
 * Mounts DossierPage against a local, pre-populated QueryClient seeded
 * with a caller-supplied fixture. No network: all queries DossierPage
 * fires resolve synchronously out of the cache.
 *
 * Why a local QueryClient rather than wiring the fixture through the
 * app-level client: we want the fixture routes to feel exactly like
 * /dossiers/<id> at render time but without any risk of polluting the
 * real app cache, and without needing to add a special fixture case to
 * the api layer. DossierPage is mounted directly with `fixtureId` — no
 * nested router, the outer BrowserRouter already owns routing.
 *
 * Pre-seeded query keys:
 *   - ["dossier", id]                               → DossierFull
 *   - ["dossier", id, "change-log"]                 → ChangeLogEntry[]
 *   - ["dossier", id, "investigation-log", …, 500]  → InvestigationLogEntry[]
 *   - ["dossier", id, "investigation-log", "counts"] → Record<string, number>
 *   - ["dossier", id, "resume-state"]               → { … null }
 *   - ["dossier", id, "agent-status"]               → { running: false, … }
 *
 * DossierPage is mounted in readOnlyFixture mode so visit/resume
 * mutations do not hit the backend. Retries are disabled so a misfired
 * query errors loudly rather than spinning.
 */
export interface FixtureHostProps {
  dossier: DossierFull;
  changeLog: ChangeLogEntry[];
  investigationLogCounts: Record<string, number>;
}

export function FixtureHost({
  dossier,
  changeLog,
  investigationLogCounts,
}: FixtureHostProps) {
  const dossierId = dossier.dossier.id;

  const queryClient = useMemo(() => {
    const qc = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
          staleTime: Infinity,
          refetchOnMount: false,
          refetchOnWindowFocus: false,
          refetchOnReconnect: false,
        },
        mutations: { retry: false },
      },
    });

    qc.setQueryData(qk.dossier(dossierId), dossier);
    qc.setQueryData(qk.changeLog(dossierId), changeLog);
    qc.setQueryData(
      [...qk.investigationLog(dossierId, undefined), 500],
      dossier.investigation_log ?? [],
    );
    qc.setQueryData(
      qk.investigationLogCounts(dossierId),
      investigationLogCounts,
    );
    qc.setQueryData(qk.resumeState(dossierId), {
      active_work_session_id: null,
      wake_pending: false,
    });
    qc.setQueryData(qk.agentStatus(dossierId), {
      running: false,
      started_at: null,
    });

    return qc;
  }, [dossierId, dossier, changeLog, investigationLogCounts]);

  return (
    <QueryClientProvider client={queryClient}>
      <DossierPage readOnlyFixture fixtureId={dossierId} />
    </QueryClientProvider>
  );
}

export default FixtureHost;
