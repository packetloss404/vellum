// Thin fetch wrapper around the Vellum backend.
// In dev, Vite proxies /api/* so BASE stays "". In other envs set VITE_API_URL.

import type {
  AgentStatus,
  BudgetDay,
  BudgetToday,
  ChangeLogEntry,
  DecisionPoint,
  Dossier,
  DossierFull,
  IntakeSession,
  IntakeStartResult,
  IntakeTurnResult,
  NeedsInput,
  SettingEntry,
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

  seedDossier: () =>
    request<Dossier>("POST", "/api/dossiers/seed"),

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

  // Fleet-wide snapshot of which dossiers currently have an agent task
  // in flight. One request powers the "Researching" pill on every
  // dossier card in the list view — avoids an N+1 fanout.
  listRunningAgents: () =>
    request<Array<{ dossier_id: string; started_at?: string | null }>>(
      "GET",
      "/api/agents/running",
    ),

  // ---------- v2: Resume ----------
  // Resume kicks the agent back on for an existing dossier. The backend
  // route is being added by another agent in parallel; the detail page
  // gracefully degrades (shows "Resume" unconditionally) if getResumeState
  // 404s, so this call is tolerant of that transition.
  resumeAgent: (dossierId: string) =>
    request<unknown>("POST", `/api/dossiers/${dossierId}/resume`),

  // Returns the full resume-state payload. Legacy shape carried only
  // active_work_session_id; day-3 sleep-mode added wake_at / wake_pending /
  // wake_reason so the activity indicator can read the scheduler's view
  // of the dossier without a second round-trip.
  getResumeState: (dossierId: string) =>
    request<{
      dossier_id: string;
      has_plan: boolean;
      plan_approved: boolean;
      active_work_session_id: string | null;
      last_session_ended_at: string | null;
      last_visited_at: string | null;
      open_needs_input_count: number;
      open_decision_point_count: number;
      delivered: boolean;
      wake_at: string | null;
      wake_pending: boolean;
      wake_reason: string | null;
    }>("GET", `/api/dossiers/${dossierId}/resume-state`),

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

  // ---------- Sleep-mode: settings + budget ----------
  listSettings: () => request<SettingEntry[]>("GET", "/api/settings"),

  getSetting: (key: string) =>
    request<SettingEntry>("GET", `/api/settings/${encodeURIComponent(key)}`),

  updateSetting: (key: string, value: unknown) =>
    request<SettingEntry>("PUT", `/api/settings/${encodeURIComponent(key)}`, {
      value,
    }),

  budgetToday: () => request<BudgetToday>("GET", "/api/budget/today"),

  budgetRange: (days = 7) =>
    request<BudgetDay[]>("GET", `/api/budget/range${qs({ days })}`),
};
