from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DossierType(str, Enum):
    decision_memo = "decision_memo"
    investigation = "investigation"
    position_paper = "position_paper"
    comparison = "comparison"
    plan = "plan"
    script = "script"


class DossierStatus(str, Enum):
    active = "active"
    paused = "paused"
    delivered = "delivered"


class SectionType(str, Enum):
    summary = "summary"
    finding = "finding"
    recommendation = "recommendation"
    evidence = "evidence"
    open_question = "open_question"
    decision_needed = "decision_needed"
    ruled_out = "ruled_out"


class SectionState(str, Enum):
    confident = "confident"
    provisional = "provisional"
    blocked = "blocked"


class SourceKind(str, Enum):
    web = "web"
    user_paste = "user_paste"
    reasoning = "reasoning"


class Source(BaseModel):
    kind: SourceKind
    url: Optional[str] = None
    title: Optional[str] = None
    snippet: Optional[str] = None


class CheckInCadence(str, Enum):
    on_demand = "on_demand"
    daily = "daily"
    weekly = "weekly"
    material_changes_only = "material_changes_only"


class CheckInPolicy(BaseModel):
    cadence: CheckInCadence = CheckInCadence.on_demand
    notes: str = ""


class InvestigationPlanItem(BaseModel):
    id: str = Field(default_factory=lambda: new_id("pli"))  # prefix: "pli"
    question: str
    rationale: str = ""
    expected_sources: list[str] = Field(default_factory=list)
    as_sub_investigation: bool = False
    status: Literal["planned", "in_progress", "completed", "abandoned"] = "planned"


class InvestigationPlan(BaseModel):
    items: list[InvestigationPlanItem] = Field(default_factory=list)
    rationale: str = ""              # why this plan shape
    drafted_at: datetime
    approved_at: Optional[datetime] = None
    revised_at: Optional[datetime] = None
    revision_count: int = 0


class Debrief(BaseModel):
    what_i_did: str = ""
    what_i_found: str = ""
    what_you_should_do_next: str = ""
    what_i_couldnt_figure_out: str = ""
    last_updated: datetime


class NextAction(BaseModel):
    id: str                               # prefix: "act"
    dossier_id: str
    action: str                           # short imperative
    rationale: str = ""
    priority: int = 0                     # lower = higher priority; use spaced ints
    completed: bool = False
    completed_at: Optional[datetime] = None
    created_at: datetime


class WorkingTheoryConfidence(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class WorkingTheory(BaseModel):
    """Point-in-time executive summary of what the agent currently believes.

    Distinct from Debrief (what I did / what I found — process narrative).
    Distinct from sections (evidence and analysis). This is the "if you had
    to decide right now, here's what I think" surface the user reads first
    on return.
    """
    recommendation: str                   # concise belief or recommended next move
    confidence: WorkingTheoryConfidence
    why: str                              # why this is the current theory
    what_would_change_it: str             # what evidence or event would shift it
    updated_at: datetime


class WorkingTheoryUpdate(BaseModel):
    """Partial-merge update. Any field omitted leaves the prior value intact.

    If any field is supplied on a dossier with no existing WorkingTheory,
    all REQUIRED fields must be present — storage enforces this.
    """
    recommendation: Optional[str] = None
    confidence: Optional[WorkingTheoryConfidence] = None
    why: Optional[str] = None
    what_would_change_it: Optional[str] = None


class Dossier(BaseModel):
    id: str
    title: str
    problem_statement: str
    out_of_scope: list[str] = Field(default_factory=list)
    dossier_type: DossierType
    status: DossierStatus = DossierStatus.active
    check_in_policy: CheckInPolicy = Field(default_factory=CheckInPolicy)
    debrief: Optional[Debrief] = None
    investigation_plan: Optional[InvestigationPlan] = None
    working_theory: Optional[WorkingTheory] = None
    last_visited_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class Section(BaseModel):
    id: str
    dossier_id: str
    type: SectionType
    title: str
    content: str = ""
    state: SectionState
    order: float
    change_note: str = ""
    sources: list[Source] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    last_updated: datetime
    created_at: datetime


class NeedsInput(BaseModel):
    id: str
    dossier_id: str
    question: str
    blocks_section_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    answered_at: Optional[datetime] = None
    answer: Optional[str] = None


class DecisionOption(BaseModel):
    label: str
    implications: str = ""
    recommended: bool = False


class DecisionPoint(BaseModel):
    id: str
    dossier_id: str
    title: str
    options: list[DecisionOption]
    recommendation: Optional[str] = None
    blocks_section_ids: list[str] = Field(default_factory=list)
    kind: Literal["plan_approval", "stuck_resolution", "generic"] = "generic"
    created_at: datetime
    resolved_at: Optional[datetime] = None
    chosen: Optional[str] = None


class ReasoningTrailEntry(BaseModel):
    id: str
    dossier_id: str
    work_session_id: Optional[str] = None
    note: str
    tags: list[str] = Field(default_factory=list)
    created_at: datetime


class RuledOut(BaseModel):
    id: str
    dossier_id: str
    subject: str
    reason: str
    sources: list[Source] = Field(default_factory=list)
    created_at: datetime


class WorkSessionTrigger(str, Enum):
    user_open = "user_open"
    scheduled = "scheduled"
    reactive = "reactive"
    resume = "resume"
    intake = "intake"
    manual = "manual"


class WorkSessionEndReason(str, Enum):
    ended_turn = "ended_turn"
    turn_limit = "turn_limit"
    stuck = "stuck"
    delivered = "delivered"
    error = "error"
    crashed = "crashed"
    stopped = "stopped"
    budget_soft_signal = "budget_soft_signal"


class WorkSession(BaseModel):
    id: str
    dossier_id: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    trigger: WorkSessionTrigger
    token_budget_used: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    end_reason: Optional[WorkSessionEndReason] = None


class WakeReason(str, Enum):
    scheduled = "scheduled"
    crash_resume = "crash_resume"
    needs_input_resolved = "needs_input_resolved"
    decision_resolved = "decision_resolved"


class ScheduleWakeArgs(BaseModel):
    # Pydantic cap is only a sanity bound. The real, user-editable cap
    # lives in settings.schedule_wake_max_hours (default 72h) and is
    # checked in the handler.
    hours_from_now: float = Field(..., gt=0)
    reason: str


class Setting(BaseModel):
    key: str
    value: object  # JSON-decoded value
    updated_at: datetime


class SettingUpdate(BaseModel):
    value: object


class BudgetRollup(BaseModel):
    day: str  # YYYY-MM-DD UTC
    spent_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    updated_at: datetime


ChangeKind = Literal[
    "section_created",
    "section_updated",
    "section_deleted",
    "state_changed",
    "needs_input_added",
    "needs_input_resolved",
    "decision_point_added",
    "decision_point_resolved",
    "ruled_out_added",
    "sections_reordered",
    "debrief_updated",
    "plan_updated",
    "next_action_added",
    "next_action_completed",
    "next_action_removed",
    "artifact_added",
    "artifact_updated",
    "sub_investigation_spawned",
    "sub_investigation_completed",
    "sub_investigation_abandoned",
    "investigation_log_appended",
    "considered_and_rejected_added",
    "working_theory_updated",
]


class ChangeLogEntry(BaseModel):
    id: str
    dossier_id: str
    work_session_id: str
    section_id: Optional[str] = None
    kind: ChangeKind
    change_note: str
    created_at: datetime


class DossierFull(BaseModel):
    """Dossier aggregate with all child collections populated."""
    dossier: Dossier
    sections: list[Section] = Field(default_factory=list)
    needs_input: list[NeedsInput] = Field(default_factory=list)
    decision_points: list[DecisionPoint] = Field(default_factory=list)
    reasoning_trail: list[ReasoningTrailEntry] = Field(default_factory=list)
    ruled_out: list[RuledOut] = Field(default_factory=list)
    work_sessions: list[WorkSession] = Field(default_factory=list)
    next_actions: list[NextAction] = Field(default_factory=list)
    artifacts: list["Artifact"] = Field(default_factory=list)
    sub_investigations: list["SubInvestigation"] = Field(default_factory=list)
    investigation_log: list["InvestigationLogEntry"] = Field(default_factory=list)
    considered_and_rejected: list["ConsideredAndRejected"] = Field(default_factory=list)
    session_summaries: list["SessionSummary"] = Field(default_factory=list)


# --- API request shapes ---


class DossierCreate(BaseModel):
    title: str
    problem_statement: str
    out_of_scope: list[str] = Field(default_factory=list)
    dossier_type: DossierType = DossierType.investigation
    check_in_policy: CheckInPolicy = Field(default_factory=CheckInPolicy)


class DossierUpdate(BaseModel):
    title: Optional[str] = None
    problem_statement: Optional[str] = None
    out_of_scope: Optional[list[str]] = None
    status: Optional[DossierStatus] = None
    check_in_policy: Optional[CheckInPolicy] = None


class SectionUpsert(BaseModel):
    section_id: Optional[str] = None
    type: SectionType
    title: str
    content: str = ""
    state: SectionState
    change_note: str
    sources: list[Source] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    after_section_id: Optional[str] = None


class SectionStateUpdate(BaseModel):
    new_state: SectionState
    reason: str


class NeedsInputCreate(BaseModel):
    question: str
    blocks_section_ids: list[str] = Field(default_factory=list)


class NeedsInputResolve(BaseModel):
    answer: str


class DecisionPointCreate(BaseModel):
    title: str
    options: list[DecisionOption]
    recommendation: Optional[str] = None
    blocks_section_ids: list[str] = Field(default_factory=list)
    kind: Literal["plan_approval", "stuck_resolution", "generic"] = "generic"


class DecisionPointResolve(BaseModel):
    chosen: str


class ReasoningAppend(BaseModel):
    note: str
    tags: list[str] = Field(default_factory=list)


class RuledOutCreate(BaseModel):
    subject: str
    reason: str
    sources: list[Source] = Field(default_factory=list)


class WorkSessionStart(BaseModel):
    trigger: WorkSessionTrigger = WorkSessionTrigger.manual


class DebriefUpdate(BaseModel):
    what_i_did: Optional[str] = None
    what_i_found: Optional[str] = None
    what_you_should_do_next: Optional[str] = None
    what_i_couldnt_figure_out: Optional[str] = None


class InvestigationPlanUpdate(BaseModel):
    items: list[InvestigationPlanItem]
    rationale: str = ""
    approve: bool = False                 # when True, set approved_at to now


class NextActionCreate(BaseModel):
    action: str
    rationale: str = ""
    after_action_id: Optional[str] = None # position after this one; None = end


# --- Artifacts ---


class ArtifactKind(str, Enum):
    letter = "letter"
    script = "script"
    comparison = "comparison"
    timeline = "timeline"
    checklist = "checklist"
    offer = "offer"
    other = "other"


class ArtifactState(str, Enum):
    draft = "draft"
    ready = "ready"
    superseded = "superseded"


class Artifact(BaseModel):
    id: str                       # prefix: "art"
    dossier_id: str
    kind: ArtifactKind
    title: str
    content: str = ""              # markdown in v1
    intended_use: str = ""
    state: ArtifactState = ArtifactState.draft
    kind_note: Optional[str] = None
    supersedes: Optional[str] = None  # prior artifact id this replaces
    last_updated: datetime
    created_at: datetime


class ArtifactCreate(BaseModel):
    kind: ArtifactKind
    title: str
    content: str = ""
    intended_use: str = ""
    state: ArtifactState = ArtifactState.draft
    kind_note: Optional[str] = None
    supersedes: Optional[str] = None


class ArtifactUpdate(BaseModel):
    kind: Optional[ArtifactKind] = None
    title: Optional[str] = None
    content: Optional[str] = None
    intended_use: Optional[str] = None
    state: Optional[ArtifactState] = None
    change_note: str   # required — shown in plan-diff sidebar


# --- SubInvestigations ---


class SubInvestigationState(str, Enum):
    running = "running"
    delivered = "delivered"
    blocked = "blocked"
    abandoned = "abandoned"


class SubInvestigation(BaseModel):
    id: str                               # prefix: "sub"
    dossier_id: str
    parent_section_id: Optional[str] = None    # optional link to a parent dossier section
    title: Optional[str] = None           # short identifier ("Verify debt ownership"); scope is fallback
    scope: str                            # short scope statement
    questions: list[str] = Field(default_factory=list)
    state: SubInvestigationState = SubInvestigationState.running
    return_summary: Optional[str] = None  # populated on complete
    findings_section_ids: list[str] = Field(default_factory=list)  # sections produced by sub
    findings_artifact_ids: list[str] = Field(default_factory=list) # artifacts produced by sub
    blocked_reason: Optional[str] = None  # populated when state flips to blocked
    started_at: datetime
    completed_at: Optional[datetime] = None


class SubInvestigationSpawn(BaseModel):
    scope: str
    title: Optional[str] = None           # short identifier for the UI — falls back to scope when absent
    questions: list[str] = Field(default_factory=list)
    parent_section_id: Optional[str] = None


class SubInvestigationComplete(BaseModel):
    return_summary: str
    findings_section_ids: list[str] = Field(default_factory=list)
    findings_artifact_ids: list[str] = Field(default_factory=list)


class SubInvestigationStateUpdate(BaseModel):
    new_state: SubInvestigationState  # typically `blocked`
    reason: str


# --- v2: investigation_log ---


class InvestigationLogEntryType(str, Enum):
    source_consulted = "source_consulted"
    sub_investigation_spawned = "sub_investigation_spawned"
    sub_investigation_returned = "sub_investigation_returned"
    section_upserted = "section_upserted"
    section_revised = "section_revised"
    artifact_added = "artifact_added"
    artifact_revised = "artifact_revised"
    path_rejected = "path_rejected"
    decision_flagged = "decision_flagged"
    input_requested = "input_requested"
    plan_revised = "plan_revised"
    stuck_declared = "stuck_declared"


class InvestigationLogEntry(BaseModel):
    id: str                        # prefix: "ilg"
    dossier_id: str
    work_session_id: Optional[str] = None
    sub_investigation_id: Optional[str] = None  # if produced inside a sub
    entry_type: InvestigationLogEntryType
    payload: dict                  # typed-by-convention; not schema-enforced in v1
    summary: str                   # one-line human-readable
    created_at: datetime


class InvestigationLogAppend(BaseModel):
    entry_type: InvestigationLogEntryType
    payload: dict = Field(default_factory=dict)
    summary: str
    sub_investigation_id: Optional[str] = None


# --- v2: considered_and_rejected ---


class ConsideredAndRejected(BaseModel):
    id: str                        # prefix: "crj"
    dossier_id: str
    sub_investigation_id: Optional[str] = None
    path: str                      # what was considered
    why_compelling: str            # why it was tempting
    why_rejected: str              # why it was dismissed
    cost_of_error: str = ""        # what happens if the rejection was wrong
    sources: list[Source] = Field(default_factory=list)
    created_at: datetime


class ConsideredAndRejectedCreate(BaseModel):
    path: str
    why_compelling: str
    why_rejected: str
    cost_of_error: str = ""
    sources: list[Source] = Field(default_factory=list)
    sub_investigation_id: Optional[str] = None


class MarkDeliveredArgs(BaseModel):
    """Args for the `mark_investigation_delivered` agent tool.

    `why_enough` is the self-justification the agent writes when it decides
    an investigation has met the substance bar: what was covered, what was
    explicitly left open, what the next real action is.
    """
    why_enough: str


# --- Phase 3: session summaries ---


class SessionSummary(BaseModel):
    session_id: str                                           # FK to work_sessions.id
    dossier_id: str
    summary: str = ""                                         # 1–2 sentence narrative
    confirmed: list[str] = Field(default_factory=list)
    ruled_out: list[str] = Field(default_factory=list)
    blocked_on: list[str] = Field(default_factory=list)
    recommended_next_action: Optional[str] = None
    cost_usd: float = 0.0
    created_at: datetime


class SummarizeSessionArgs(BaseModel):
    """Args for the `summarize_session` agent tool."""
    summary: str
    confirmed: list[str] = Field(default_factory=list)
    ruled_out: list[str] = Field(default_factory=list)
    blocked_on: list[str] = Field(default_factory=list)
    recommended_next_action: Optional[str] = None


# Resolve forward references for DossierFull.
DossierFull.model_rebuild()
