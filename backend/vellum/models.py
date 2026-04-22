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


class Dossier(BaseModel):
    id: str
    title: str
    problem_statement: str
    out_of_scope: list[str] = Field(default_factory=list)
    dossier_type: DossierType
    status: DossierStatus = DossierStatus.active
    check_in_policy: CheckInPolicy = Field(default_factory=CheckInPolicy)
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
    resume = "resume"
    intake = "intake"
    manual = "manual"


class WorkSession(BaseModel):
    id: str
    dossier_id: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    trigger: WorkSessionTrigger
    token_budget_used: int = 0


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
    "artifact_added",
    "artifact_updated",
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
    artifacts: list["Artifact"] = Field(default_factory=list)


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


DossierFull.model_rebuild()
