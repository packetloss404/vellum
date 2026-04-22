// Types mirrored from backend/vellum/models.py and backend/vellum/intake/models.py.
// ISO datetime strings come through as `string`. Pydantic `Optional` fields use
// `field?: T | null` so we don't conflate JSON `null` with JS `undefined`.

// ---------- Enums as string unions ----------

export type DossierType =
  | "decision_memo"
  | "investigation"
  | "position_paper"
  | "comparison"
  | "plan"
  | "script";

export type DossierStatus = "active" | "paused" | "delivered";

export type SectionType =
  | "summary"
  | "finding"
  | "recommendation"
  | "evidence"
  | "open_question"
  | "decision_needed"
  | "ruled_out";

export type SectionState = "confident" | "provisional" | "blocked";

export type SourceKind = "web" | "user_paste" | "reasoning";

export type CheckInCadence =
  | "on_demand"
  | "daily"
  | "weekly"
  | "material_changes_only";

export type IntakeStatus = "gathering" | "committed" | "abandoned";

export type WorkSessionTrigger =
  | "user_open"
  | "scheduled"
  | "resume"
  | "intake"
  | "manual";

export type ChangeKind =
  | "section_created"
  | "section_updated"
  | "section_deleted"
  | "state_changed"
  | "needs_input_added"
  | "needs_input_resolved"
  | "decision_point_added"
  | "decision_point_resolved"
  | "ruled_out_added"
  | "sections_reordered"
  // v2 additions
  | "artifact_added"
  | "artifact_updated"
  | "sub_investigation_spawned"
  | "sub_investigation_completed"
  | "sub_investigation_abandoned"
  | "debrief_updated"
  | "plan_updated"
  | "next_action_added"
  | "next_action_completed"
  | "next_action_removed"
  | "investigation_log_appended"
  | "considered_and_rejected_added";

export type IntakeMessageRole = "user" | "assistant";

// ---------- Shared value objects ----------

export interface Source {
  kind: SourceKind;
  url?: string | null;
  title?: string | null;
  snippet?: string | null;
}

export interface CheckInPolicy {
  cadence: CheckInCadence;
  notes: string;
}

// ---------- Core domain objects ----------

export interface Dossier {
  id: string;
  title: string;
  problem_statement: string;
  out_of_scope: string[];
  dossier_type: DossierType;
  status: DossierStatus;
  check_in_policy: CheckInPolicy;
  last_visited_at?: string | null;
  created_at: string;
  updated_at: string;
  // v2 additions (nullable — older dossiers may not have these populated)
  debrief?: Debrief | null;
  investigation_plan?: InvestigationPlan | null;
}

export interface Section {
  id: string;
  dossier_id: string;
  type: SectionType;
  title: string;
  content: string;
  state: SectionState;
  // Pydantic stores this as `float`, not `int` — fractional values are used
  // for mid-list inserts during reorder.
  order: number;
  change_note: string;
  sources: Source[];
  depends_on: string[];
  last_updated: string;
  created_at: string;
}

export interface NeedsInput {
  id: string;
  dossier_id: string;
  question: string;
  blocks_section_ids: string[];
  created_at: string;
  answered_at?: string | null;
  answer?: string | null;
}

export interface DecisionOption {
  label: string;
  implications: string;
  recommended: boolean;
}

/**
 * `kind` distinguishes the purpose of a decision_point. The plan-approval
 * gate agent is adding this field server-side (default "generic"). Optional
 * here so older persisted points that lack the field parse cleanly.
 */
export type DecisionPointKind =
  | "plan_approval"
  | "stuck_resolution"
  | "generic";

export interface DecisionPoint {
  id: string;
  dossier_id: string;
  title: string;
  options: DecisionOption[];
  recommendation?: string | null;
  blocks_section_ids: string[];
  created_at: string;
  resolved_at?: string | null;
  chosen?: string | null;
  kind?: DecisionPointKind;
}

export interface ReasoningTrailEntry {
  id: string;
  dossier_id: string;
  work_session_id?: string | null;
  note: string;
  tags: string[];
  created_at: string;
}

export interface RuledOut {
  id: string;
  dossier_id: string;
  subject: string;
  reason: string;
  sources: Source[];
  created_at: string;
}

export interface WorkSession {
  id: string;
  dossier_id: string;
  started_at: string;
  ended_at?: string | null;
  trigger: WorkSessionTrigger;
  token_budget_used: number;
}

export interface ChangeLogEntry {
  id: string;
  dossier_id: string;
  work_session_id: string;
  section_id?: string | null;
  kind: ChangeKind;
  change_note: string;
  created_at: string;
}

export interface DossierFull {
  dossier: Dossier;
  sections: Section[];
  needs_input: NeedsInput[];
  decision_points: DecisionPoint[];
  reasoning_trail: ReasoningTrailEntry[];
  ruled_out: RuledOut[];
  work_sessions: WorkSession[];
  // v2 additions — optional because older dossiers may not populate them.
  artifacts?: Artifact[];
  sub_investigations?: SubInvestigation[];
  investigation_log?: InvestigationLogEntry[];
  considered_and_rejected?: ConsideredAndRejected[];
  next_actions?: NextAction[];
}

// ---------- API request shapes (Pydantic *Create / *Update / etc.) ----------

export interface DossierCreate {
  title: string;
  problem_statement: string;
  out_of_scope?: string[];
  dossier_type?: DossierType;
  check_in_policy?: CheckInPolicy;
}

export interface DossierUpdate {
  title?: string | null;
  problem_statement?: string | null;
  out_of_scope?: string[] | null;
  status?: DossierStatus | null;
  check_in_policy?: CheckInPolicy | null;
}

export interface SectionUpsert {
  section_id?: string | null;
  type: SectionType;
  title: string;
  content?: string;
  state: SectionState;
  change_note: string;
  sources?: Source[];
  depends_on?: string[];
  after_section_id?: string | null;
}

export interface SectionStateUpdate {
  new_state: SectionState;
  reason: string;
}

export interface NeedsInputCreate {
  question: string;
  blocks_section_ids?: string[];
}

export interface DecisionPointCreate {
  title: string;
  options: DecisionOption[];
  recommendation?: string | null;
  blocks_section_ids?: string[];
}

export interface ReasoningAppend {
  note: string;
  tags?: string[];
}

export interface RuledOutCreate {
  subject: string;
  reason: string;
  sources?: Source[];
}

export interface WorkSessionStart {
  trigger?: WorkSessionTrigger;
}

// ---------- Intake ----------

export interface IntakeState {
  title?: string | null;
  problem_statement?: string | null;
  dossier_type?: DossierType | null;
  out_of_scope: string[];
  check_in_policy?: CheckInPolicy | null;
}

export interface IntakeMessage {
  id: string;
  role: IntakeMessageRole;
  content: string;
  created_at: string;
}

export interface IntakeSession {
  id: string;
  status: IntakeStatus;
  state: IntakeState;
  messages: IntakeMessage[];
  dossier_id?: string | null;
  created_at: string;
  updated_at: string;
}

/** Shape returned by POST /api/intake (start_intake). */
export interface IntakeStartResult {
  intake: IntakeSession;
  first_reply: string | null;
}

/** Shape returned by POST /api/intake/{id}/message. */
export interface IntakeTurnResult {
  intake_status: IntakeStatus;
  state: IntakeState;
  assistant_message: string;
  dossier_id?: string | null;
  error?: string | null;
}

// ---------- Agent ----------

export interface AgentStatus {
  running: boolean;
  started_at?: string | null;
}

export interface StartAgentRequest {
  max_turns?: number;
  model?: string | null;
}

// ===================================================================
// v2 schema (Day 1). Appended below to avoid disturbing v1 definitions.
// The spec asked for `type` aliases (not `interface`) and snake_case
// fields matching the Pydantic source on the wire.
// ===================================================================

// ---------- Artifacts ----------

export type ArtifactKind =
  | "letter"
  | "script"
  | "comparison"
  | "timeline"
  | "checklist"
  | "offer"
  | "other";

export type ArtifactState = "draft" | "ready" | "superseded";

export type Artifact = {
  id: string;
  dossier_id: string;
  kind: ArtifactKind;
  title: string;
  content: string;
  intended_use: string;
  state: ArtifactState;
  kind_note: string | null;
  supersedes: string | null;
  last_updated: string;
  created_at: string;
};

export type ArtifactCreate = {
  kind: ArtifactKind;
  title: string;
  content?: string;
  intended_use?: string;
  state?: ArtifactState;
  kind_note?: string | null;
  supersedes?: string | null;
};

export type ArtifactUpdate = {
  kind?: ArtifactKind;
  title?: string;
  content?: string;
  intended_use?: string;
  state?: ArtifactState;
  change_note: string;
};

// ---------- Sub-investigations ----------

export type SubInvestigationState =
  | "running"
  | "delivered"
  | "blocked"
  | "abandoned";

export type SubInvestigation = {
  id: string;
  dossier_id: string;
  parent_section_id: string | null;
  scope: string;
  questions: string[];
  state: SubInvestigationState;
  return_summary: string | null;
  findings_section_ids: string[];
  findings_artifact_ids: string[];
  started_at: string;
  completed_at: string | null;
};

export type SubInvestigationSpawn = {
  scope: string;
  questions?: string[];
  parent_section_id?: string | null;
};

export type SubInvestigationComplete = {
  return_summary: string;
  findings_section_ids?: string[];
  findings_artifact_ids?: string[];
};

// ---------- Debrief / InvestigationPlan / NextAction ----------

export type Debrief = {
  what_i_did: string;
  what_i_found: string;
  what_you_should_do_next: string;
  what_i_couldnt_figure_out: string;
  last_updated: string;
};

export type InvestigationPlanItemStatus =
  | "planned"
  | "in_progress"
  | "completed"
  | "abandoned";

export type InvestigationPlanItem = {
  id: string;
  question: string;
  rationale: string;
  expected_sources: string[];
  as_sub_investigation: boolean;
  status: InvestigationPlanItemStatus;
};

export type InvestigationPlan = {
  items: InvestigationPlanItem[];
  rationale: string;
  drafted_at: string;
  approved_at: string | null;
  revised_at: string | null;
  revision_count: number;
};

export type NextAction = {
  id: string;
  dossier_id: string;
  action: string;
  rationale: string;
  priority: number;
  completed: boolean;
  completed_at: string | null;
  created_at: string;
};

// ---------- Investigation log ----------

export type InvestigationLogEntryType =
  | "source_consulted"
  | "sub_investigation_spawned"
  | "sub_investigation_returned"
  | "section_upserted"
  | "section_revised"
  | "artifact_added"
  | "artifact_revised"
  | "path_rejected"
  | "decision_flagged"
  | "input_requested"
  | "plan_revised"
  | "stuck_declared";

export type InvestigationLogEntry = {
  id: string;
  dossier_id: string;
  work_session_id: string | null;
  sub_investigation_id: string | null;
  entry_type: InvestigationLogEntryType;
  payload: Record<string, unknown>;
  summary: string;
  created_at: string;
};

// ---------- Considered and rejected ----------

export type ConsideredAndRejected = {
  id: string;
  dossier_id: string;
  sub_investigation_id: string | null;
  path: string;
  why_compelling: string;
  why_rejected: string;
  cost_of_error: string;
  sources: Source[];
  created_at: string;
};

// ---------- v2 request payloads used by client fetchers ----------

export type DebriefUpdate = {
  what_i_did?: string;
  what_i_found?: string;
  what_you_should_do_next?: string;
  what_i_couldnt_figure_out?: string;
};

export type InvestigationPlanUpdate = {
  items?: InvestigationPlanItem[];
  rationale?: string;
  approved?: boolean;
};

export type NextActionCreate = {
  action: string;
  rationale?: string;
  priority?: number;
};

export type InvestigationLogAppend = {
  entry_type: InvestigationLogEntryType;
  summary: string;
  payload?: Record<string, unknown>;
  sub_investigation_id?: string | null;
};

export type ConsideredAndRejectedCreate = {
  path: string;
  why_compelling: string;
  why_rejected: string;
  cost_of_error: string;
  sources?: Source[];
  sub_investigation_id?: string | null;
};
