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
  | "sections_reordered";

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
