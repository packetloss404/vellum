// React Query hooks over ./client. Mutations invalidate the query keys they
// affect so dependent views refetch automatically.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";
import type {
  InvestigationLogEntryType,
  SubInvestigationState,
} from "./types";

// ---------- query key helpers ----------

export const qk = {
  dossiers: () => ["dossiers"] as const,
  dossier: (id: string) => ["dossier", id] as const,
  changeLog: (id: string) => ["dossier", id, "change-log"] as const,
  intake: (id: string) => ["intake", id] as const,
  // v2
  artifacts: (id: string) => ["dossier", id, "artifacts"] as const,
  subInvestigations: (id: string, state?: SubInvestigationState) =>
    ["dossier", id, "sub-investigations", state ?? null] as const,
  nextActions: (id: string) => ["dossier", id, "next-actions"] as const,
  investigationLog: (id: string, entryType?: InvestigationLogEntryType) =>
    ["dossier", id, "investigation-log", entryType ?? null] as const,
  investigationLogCounts: (id: string) =>
    ["dossier", id, "investigation-log", "counts"] as const,
  consideredAndRejected: (id: string) =>
    ["dossier", id, "considered-and-rejected"] as const,
};

// ---------- queries ----------

export const useDossierList = () =>
  useQuery({ queryKey: qk.dossiers(), queryFn: api.listDossiers });

export const useDossier = (id: string) =>
  useQuery({
    queryKey: qk.dossier(id),
    queryFn: () => api.getDossier(id),
    enabled: !!id,
  });

export const useChangeLog = (id: string) =>
  useQuery({
    queryKey: qk.changeLog(id),
    queryFn: () => api.getChangeLog(id),
    enabled: !!id,
  });

export const useIntake = (id: string) =>
  useQuery({
    queryKey: qk.intake(id),
    queryFn: () => api.getIntake(id),
    enabled: !!id,
  });

export const useAgentStatus = (dossierId: string) =>
  useQuery({
    queryKey: ["dossier", dossierId, "agent-status"] as const,
    queryFn: () => api.agentStatus(dossierId),
    enabled: !!dossierId,
  });

// ---------- dossier mutations ----------

export function useVisitDossier() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (dossierId: string) => api.visitDossier(dossierId),
    onSuccess: (_data, dossierId) => {
      // Visiting resets the "since last visit" window used by the change log.
      qc.invalidateQueries({ queryKey: qk.changeLog(dossierId) });
      qc.invalidateQueries({ queryKey: qk.dossier(dossierId) });
      qc.invalidateQueries({ queryKey: qk.dossiers() });
    },
  });
}

export function useResolveNeedsInput() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: {
      dossierId: string;
      needsInputId: string;
      answer: string;
    }) =>
      api.resolveNeedsInput(vars.dossierId, vars.needsInputId, vars.answer),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: qk.dossier(vars.dossierId) });
      qc.invalidateQueries({ queryKey: qk.changeLog(vars.dossierId) });
    },
  });
}

export function useResolveDecisionPoint() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: {
      dossierId: string;
      decisionPointId: string;
      chosen: string;
      workSessionId?: string;
    }) =>
      api.resolveDecisionPoint(
        vars.dossierId,
        vars.decisionPointId,
        vars.chosen,
        vars.workSessionId,
      ),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: qk.dossier(vars.dossierId) });
      qc.invalidateQueries({ queryKey: qk.changeLog(vars.dossierId) });
    },
  });
}

// ---------- intake mutations ----------

export function useStartIntake() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (openingMessage?: string) => api.startIntake(openingMessage),
    onSuccess: (data) => {
      // Seed the intake cache with what the server just returned so the next
      // useIntake(id) render doesn't need to refetch.
      qc.setQueryData(qk.intake(data.intake.id), data.intake);
    },
  });
}

export function useSendIntakeMessage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { intakeId: string; content: string }) =>
      api.sendIntakeMessage(vars.intakeId, vars.content),
    onSuccess: (data, vars) => {
      qc.invalidateQueries({ queryKey: qk.intake(vars.intakeId) });
      // If this turn committed the intake, a new dossier now exists.
      if (data.dossier_id) {
        qc.invalidateQueries({ queryKey: qk.dossiers() });
        qc.invalidateQueries({ queryKey: qk.dossier(data.dossier_id) });
      }
    },
  });
}

export function useCommitIntake() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (intakeId: string) => api.commitIntake(intakeId),
    onSuccess: (data, intakeId) => {
      qc.invalidateQueries({ queryKey: qk.intake(intakeId) });
      qc.invalidateQueries({ queryKey: qk.dossiers() });
      if (data.dossier_id) {
        qc.invalidateQueries({ queryKey: qk.dossier(data.dossier_id) });
      }
    },
  });
}

export function useAbandonIntake() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (intakeId: string) => api.abandonIntake(intakeId),
    onSuccess: (_data, intakeId) => {
      qc.invalidateQueries({ queryKey: qk.intake(intakeId) });
    },
  });
}

// ---------- agent mutations ----------

export function useStartAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { dossierId: string; maxTurns?: number }) =>
      api.startAgent(vars.dossierId, vars.maxTurns),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({
        queryKey: ["dossier", vars.dossierId, "agent-status"],
      });
    },
  });
}

export function useStopAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (dossierId: string) => api.stopAgent(dossierId),
    onSuccess: (_data, dossierId) => {
      qc.invalidateQueries({
        queryKey: ["dossier", dossierId, "agent-status"],
      });
      qc.invalidateQueries({ queryKey: qk.dossier(dossierId) });
      qc.invalidateQueries({ queryKey: qk.changeLog(dossierId) });
    },
  });
}

// ---------- v2: Resume ----------

/**
 * useResumeState — lightweight probe used by the dossier detail page to
 * decide whether to show a "Resume" CTA. The underlying endpoint is being
 * added by another agent; until it lands, the query will 404 and the
 * caller should treat that as "unknown" and show the CTA unconditionally.
 * `retry: false` keeps us from hammering the missing route.
 */
export const useResumeState = (dossierId: string) =>
  useQuery({
    queryKey: ["dossier", dossierId, "resume-state"] as const,
    queryFn: () => api.getResumeState(dossierId),
    enabled: !!dossierId,
    retry: false,
  });

export function useResumeAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (dossierId: string) => api.resumeAgent(dossierId),
    onSuccess: (_data, dossierId) => {
      qc.invalidateQueries({
        queryKey: ["dossier", dossierId, "agent-status"],
      });
      qc.invalidateQueries({
        queryKey: ["dossier", dossierId, "resume-state"],
      });
      qc.invalidateQueries({ queryKey: qk.dossier(dossierId) });
    },
  });
}

// ---------- v2 read hooks ----------

export const useArtifacts = (dossierId: string) =>
  useQuery({
    queryKey: qk.artifacts(dossierId),
    queryFn: () => api.listArtifacts(dossierId),
    enabled: !!dossierId,
  });

export const useSubInvestigations = (
  dossierId: string,
  state?: SubInvestigationState,
) =>
  useQuery({
    queryKey: qk.subInvestigations(dossierId, state),
    queryFn: () => api.listSubInvestigations(dossierId, state),
    enabled: !!dossierId,
  });

export const useNextActions = (dossierId: string) =>
  useQuery({
    queryKey: qk.nextActions(dossierId),
    queryFn: () => api.listNextActions(dossierId),
    enabled: !!dossierId,
  });

export const useInvestigationLog = (
  dossierId: string,
  entryType?: InvestigationLogEntryType,
) =>
  useQuery({
    queryKey: qk.investigationLog(dossierId, entryType),
    queryFn: () => api.listInvestigationLog(dossierId, entryType),
    enabled: !!dossierId,
  });

export const useInvestigationLogCounts = (dossierId: string) =>
  useQuery({
    queryKey: qk.investigationLogCounts(dossierId),
    queryFn: () => api.investigationLogCounts(dossierId),
    enabled: !!dossierId,
  });

export const useConsideredAndRejected = (dossierId: string) =>
  useQuery({
    queryKey: qk.consideredAndRejected(dossierId),
    queryFn: () => api.listConsideredAndRejected(dossierId),
    enabled: !!dossierId,
  });
