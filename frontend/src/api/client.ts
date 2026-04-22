// Thin fetch wrapper around the Vellum backend.
// In dev, Vite proxies /api/* so BASE stays "". In other envs set VITE_API_URL.

import type {
  AgentStatus,
  ChangeLogEntry,
  DecisionPoint,
  Dossier,
  DossierFull,
  IntakeSession,
  IntakeStartResult,
  IntakeTurnResult,
  NeedsInput,
  // v2
  Artifact,
  ArtifactCreate,
  ArtifactUpdate,
  ConsideredAndRejected,
  ConsideredAndRejectedCreate,
  DebriefUpdate,
  InvestigationLogAppend,
  InvestigationLogEntry,
  InvestigationLogEntryType,
  InvestigationPlanUpdate,
  NextAction,
  NextActionCreate,
  SubInvestigation,
  SubInvestigationComplete,
  SubInvestigationSpawn,
  SubInvestigationState,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    public body: unknown,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const BASE = import.meta.env.VITE_API_URL || "";

/** Build `?a=1&b=2` from a record, skipping null/undefined. Returns "" when empty. */
function qs(params: Record<string, string | number | undefined | null>): string {
  const parts: string[] = [];
  for (const [key, val] of Object.entries(params)) {
    if (val === undefined || val === null) continue;
    parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(String(val))}`);
  }
  return parts.length ? `?${parts.join("&")}` : "";
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const res = await fetch(BASE + path, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    let parsed: unknown = null;
    try {
      parsed = await res.json();
    } catch {
      // response had no JSON body; fine.
    }
    throw new ApiError(res.status, parsed, `${method} ${path} -> ${res.status}`);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  // ---------- Dossiers ----------
  listDossiers: () => request<Dossier[]>("GET", "/api/dossiers"),

  getDossier: (id: string) =>
    request<DossierFull>("GET", `/api/dossiers/${id}`),

  visitDossier: (id: string) =>
    request<Dossier>("POST", `/api/dossiers/${id}/visit`),

  getChangeLog: (id: string) =>
    request<ChangeLogEntry[]>("GET", `/api/dossiers/${id}/change-log`),

  resolveNeedsInput: (dossierId: string, niId: string, answer: string) =>
    request<NeedsInput>(
      "POST",
      `/api/dossiers/${dossierId}/needs-input/${niId}/resolve`,
      { answer },
    ),

  resolveDecisionPoint: (
    dossierId: string,
    dpId: string,
    chosen: string,
    workSessionId?: string,
  ) =>
    request<DecisionPoint>(
      "POST",
      `/api/dossiers/${dossierId}/decision-points/${dpId}/resolve${qs({ work_session_id: workSessionId })}`,
      { chosen },
    ),

  // ---------- Intake ----------
  startIntake: (openingMessage?: string) =>
    request<IntakeStartResult>(
      "POST",
      "/api/intake",
      openingMessage ? { opening_message: openingMessage } : {},
    ),

  sendIntakeMessage: (id: string, content: string) =>
    request<IntakeTurnResult>("POST", `/api/intake/${id}/message`, { content }),

  getIntake: (id: string) =>
    request<IntakeSession>("GET", `/api/intake/${id}`),

  commitIntake: (id: string) =>
    request<{ dossier_id: string }>("POST", `/api/intake/${id}/commit`),

  abandonIntake: (id: string) =>
    request<{ ok: true }>("DELETE", `/api/intake/${id}`),

  // ---------- Agent ----------
  startAgent: (dossierId: string, maxTurns?: number) =>
    request<unknown>("POST", `/api/dossiers/${dossierId}/agent/start`, {
      max_turns: maxTurns ?? 200,
    }),

  stopAgent: (dossierId: string) =>
    request<unknown>("POST", `/api/dossiers/${dossierId}/agent/stop`),

  agentStatus: (dossierId: string) =>
    request<AgentStatus>("GET", `/api/dossiers/${dossierId}/agent/status`),

  // ---------- v2: Artifacts ----------
  createArtifact: (
    dossierId: string,
    body: ArtifactCreate,
    workSessionId?: string,
  ) =>
    request<Artifact>(
      "POST",
      `/api/dossiers/${dossierId}/artifacts${qs({ work_session_id: workSessionId })}`,
      body,
    ),

  listArtifacts: (dossierId: string) =>
    request<Artifact[]>("GET", `/api/dossiers/${dossierId}/artifacts`),

  updateArtifact: (
    dossierId: string,
    artifactId: string,
    body: ArtifactUpdate,
    workSessionId?: string,
  ) =>
    request<Artifact>(
      "PATCH",
      `/api/dossiers/${dossierId}/artifacts/${artifactId}${qs({ work_session_id: workSessionId })}`,
      body,
    ),

  deleteArtifact: (
    dossierId: string,
    artifactId: string,
    workSessionId?: string,
  ) =>
    request<{ ok: true }>(
      "DELETE",
      `/api/dossiers/${dossierId}/artifacts/${artifactId}${qs({ work_session_id: workSessionId })}`,
    ),

  // ---------- v2: Sub-investigations ----------
  spawnSubInvestigation: (
    dossierId: string,
    body: SubInvestigationSpawn,
    workSessionId?: string,
  ) =>
    request<SubInvestigation>(
      "POST",
      `/api/dossiers/${dossierId}/sub-investigations${qs({ work_session_id: workSessionId })}`,
      body,
    ),

  listSubInvestigations: (dossierId: string, state?: SubInvestigationState) =>
    request<SubInvestigation[]>(
      "GET",
      `/api/dossiers/${dossierId}/sub-investigations${qs({ state })}`,
    ),

  completeSubInvestigation: (
    dossierId: string,
    subId: string,
    body: SubInvestigationComplete,
    workSessionId?: string,
  ) =>
    request<SubInvestigation>(
      "POST",
      `/api/dossiers/${dossierId}/sub-investigations/${subId}/complete${qs({ work_session_id: workSessionId })}`,
      body,
    ),

  abandonSubInvestigation: (
    dossierId: string,
    subId: string,
    reason: string,
    workSessionId?: string,
  ) =>
    request<SubInvestigation>(
      "POST",
      `/api/dossiers/${dossierId}/sub-investigations/${subId}/abandon${qs({ work_session_id: workSessionId })}`,
      { reason },
    ),

  // ---------- v2: Debrief / Investigation plan ----------
  updateDebrief: (
    dossierId: string,
    body: DebriefUpdate,
    workSessionId?: string,
  ) =>
    request<Dossier>(
      "PATCH",
      `/api/dossiers/${dossierId}/debrief${qs({ work_session_id: workSessionId })}`,
      body,
    ),

  updateInvestigationPlan: (
    dossierId: string,
    body: InvestigationPlanUpdate,
    workSessionId?: string,
  ) =>
    request<Dossier>(
      "PATCH",
      `/api/dossiers/${dossierId}/investigation-plan${qs({ work_session_id: workSessionId })}`,
      body,
    ),

  // ---------- v2: Next actions ----------
  addNextAction: (
    dossierId: string,
    body: NextActionCreate,
    workSessionId?: string,
  ) =>
    request<NextAction>(
      "POST",
      `/api/dossiers/${dossierId}/next-actions${qs({ work_session_id: workSessionId })}`,
      body,
    ),

  listNextActions: (dossierId: string) =>
    request<NextAction[]>("GET", `/api/dossiers/${dossierId}/next-actions`),

  completeNextAction: (
    dossierId: string,
    actionId: string,
    workSessionId?: string,
  ) =>
    request<NextAction>(
      "POST",
      `/api/dossiers/${dossierId}/next-actions/${actionId}/complete${qs({ work_session_id: workSessionId })}`,
    ),

  removeNextAction: (
    dossierId: string,
    actionId: string,
    workSessionId?: string,
  ) =>
    request<{ ok: true }>(
      "DELETE",
      `/api/dossiers/${dossierId}/next-actions/${actionId}${qs({ work_session_id: workSessionId })}`,
    ),

  reorderNextActions: (
    dossierId: string,
    actionIds: string[],
    workSessionId?: string,
  ) =>
    request<NextAction[]>(
      "POST",
      `/api/dossiers/${dossierId}/next-actions/reorder${qs({ work_session_id: workSessionId })}`,
      { action_ids: actionIds },
    ),

  // ---------- v2: Investigation log ----------
  appendInvestigationLog: (
    dossierId: string,
    body: InvestigationLogAppend,
    workSessionId?: string,
  ) =>
    request<InvestigationLogEntry>(
      "POST",
      `/api/dossiers/${dossierId}/investigation-log${qs({ work_session_id: workSessionId })}`,
      body,
    ),

  listInvestigationLog: (
    dossierId: string,
    entryType?: InvestigationLogEntryType,
    limit?: number,
  ) =>
    request<InvestigationLogEntry[]>(
      "GET",
      `/api/dossiers/${dossierId}/investigation-log${qs({ entry_type: entryType, limit })}`,
    ),

  investigationLogCounts: (dossierId: string) =>
    request<Record<string, number>>(
      "GET",
      `/api/dossiers/${dossierId}/investigation-log/counts`,
    ),

  // ---------- v2: Considered and rejected ----------
  addConsideredAndRejected: (
    dossierId: string,
    body: ConsideredAndRejectedCreate,
    workSessionId?: string,
  ) =>
    request<ConsideredAndRejected>(
      "POST",
      `/api/dossiers/${dossierId}/considered-and-rejected${qs({ work_session_id: workSessionId })}`,
      body,
    ),

  listConsideredAndRejected: (dossierId: string) =>
    request<ConsideredAndRejected[]>(
      "GET",
      `/api/dossiers/${dossierId}/considered-and-rejected`,
    ),
};
