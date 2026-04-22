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

  resolveDecisionPoint: (dossierId: string, dpId: string, chosen: string) =>
    request<DecisionPoint>(
      "POST",
      `/api/dossiers/${dossierId}/decision-points/${dpId}/resolve`,
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
};
