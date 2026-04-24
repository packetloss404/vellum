PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS dossiers (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    problem_statement TEXT NOT NULL,
    out_of_scope TEXT NOT NULL DEFAULT '[]',
    dossier_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    check_in_policy TEXT NOT NULL DEFAULT '{"cadence":"on_demand","notes":""}',
    debrief TEXT,
    investigation_plan TEXT,
    last_visited_at TEXT,
    wake_at TEXT,
    wake_pending INTEGER NOT NULL DEFAULT 0,
    wake_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
-- Index on wake columns is created by db._ensure_indices AFTER
-- _ensure_columns has ALTERed the columns onto existing DBs. Keeping it
-- out of schema.sql avoids "no such column" failures on pre-sleep-mode
-- databases during the executescript pass.

CREATE TABLE IF NOT EXISTS sections (
    id TEXT PRIMARY KEY,
    dossier_id TEXT NOT NULL,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL,
    "order" REAL NOT NULL,
    change_note TEXT NOT NULL DEFAULT '',
    sources TEXT NOT NULL DEFAULT '[]',
    depends_on TEXT NOT NULL DEFAULT '[]',
    last_updated TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (dossier_id) REFERENCES dossiers(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_sections_dossier ON sections(dossier_id, "order");

CREATE TABLE IF NOT EXISTS needs_input (
    id TEXT PRIMARY KEY,
    dossier_id TEXT NOT NULL,
    question TEXT NOT NULL,
    blocks_section_ids TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    answered_at TEXT,
    answer TEXT,
    FOREIGN KEY (dossier_id) REFERENCES dossiers(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_needs_input_dossier ON needs_input(dossier_id, answered_at);

CREATE TABLE IF NOT EXISTS decision_points (
    id TEXT PRIMARY KEY,
    dossier_id TEXT NOT NULL,
    title TEXT NOT NULL,
    options TEXT NOT NULL,
    recommendation TEXT,
    blocks_section_ids TEXT NOT NULL DEFAULT '[]',
    kind TEXT NOT NULL DEFAULT 'generic',
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    chosen TEXT,
    FOREIGN KEY (dossier_id) REFERENCES dossiers(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_decision_points_dossier ON decision_points(dossier_id, resolved_at);

CREATE TABLE IF NOT EXISTS reasoning_trail (
    id TEXT PRIMARY KEY,
    dossier_id TEXT NOT NULL,
    work_session_id TEXT,
    note TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    FOREIGN KEY (dossier_id) REFERENCES dossiers(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_reasoning_dossier ON reasoning_trail(dossier_id, created_at);

CREATE TABLE IF NOT EXISTS ruled_out (
    id TEXT PRIMARY KEY,
    dossier_id TEXT NOT NULL,
    subject TEXT NOT NULL,
    reason TEXT NOT NULL,
    sources TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    FOREIGN KEY (dossier_id) REFERENCES dossiers(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_ruled_out_dossier ON ruled_out(dossier_id, created_at);

CREATE TABLE IF NOT EXISTS work_sessions (
    id TEXT PRIMARY KEY,
    dossier_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    trigger TEXT NOT NULL,
    token_budget_used INTEGER NOT NULL DEFAULT 0,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    end_reason TEXT,
    FOREIGN KEY (dossier_id) REFERENCES dossiers(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_work_sessions_dossier ON work_sessions(dossier_id, started_at);

CREATE TABLE IF NOT EXISTS change_log (
    id TEXT PRIMARY KEY,
    dossier_id TEXT NOT NULL,
    work_session_id TEXT NOT NULL,
    section_id TEXT,
    kind TEXT NOT NULL,
    change_note TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (dossier_id) REFERENCES dossiers(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_change_log_dossier ON change_log(dossier_id, work_session_id, created_at);

CREATE TABLE IF NOT EXISTS next_actions (
    id TEXT PRIMARY KEY,
    dossier_id TEXT NOT NULL,
    action TEXT NOT NULL,
    rationale TEXT NOT NULL DEFAULT '',
    priority REAL NOT NULL,
    completed INTEGER NOT NULL DEFAULT 0,
    completed_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (dossier_id) REFERENCES dossiers(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_next_actions_dossier ON next_actions(dossier_id, priority);

CREATE TABLE IF NOT EXISTS intake_sessions (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'gathering',
    state TEXT NOT NULL DEFAULT '{}',
    dossier_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_intake_sessions_status ON intake_sessions(status, updated_at);

CREATE TABLE IF NOT EXISTS intake_messages (
    id TEXT PRIMARY KEY,
    intake_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (intake_id) REFERENCES intake_sessions(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_intake_messages_intake ON intake_messages(intake_id, created_at);

CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    dossier_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    intended_use TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT 'draft',
    kind_note TEXT,
    supersedes TEXT,
    last_updated TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (dossier_id) REFERENCES dossiers(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_artifacts_dossier ON artifacts(dossier_id, created_at);

CREATE TABLE IF NOT EXISTS sub_investigations (
    id TEXT PRIMARY KEY,
    dossier_id TEXT NOT NULL,
    parent_section_id TEXT,
    scope TEXT NOT NULL,
    questions TEXT NOT NULL DEFAULT '[]',
    state TEXT NOT NULL DEFAULT 'running',
    return_summary TEXT,
    findings_section_ids TEXT NOT NULL DEFAULT '[]',
    findings_artifact_ids TEXT NOT NULL DEFAULT '[]',
    started_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY (dossier_id) REFERENCES dossiers(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_sub_investigations_dossier ON sub_investigations(dossier_id, started_at);
CREATE INDEX IF NOT EXISTS idx_sub_investigations_state ON sub_investigations(dossier_id, state);

-- v2: typed, append-only log of everything the agent did (the "47 sources consulted"
-- evidence-of-work counter). Separate from reasoning_trail (freeform narrative notes)
-- and change_log (user-visit-diff surface). This is the count-of-work surface.
CREATE TABLE IF NOT EXISTS investigation_log (
    id TEXT PRIMARY KEY,
    dossier_id TEXT NOT NULL,
    work_session_id TEXT,
    sub_investigation_id TEXT,
    entry_type TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    summary TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (dossier_id) REFERENCES dossiers(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_investigation_log_dossier ON investigation_log(dossier_id, created_at);
CREATE INDEX IF NOT EXISTS idx_investigation_log_type ON investigation_log(dossier_id, entry_type);

-- v2: enriched "considered and rejected" — paths the agent seriously explored and
-- dismissed, with visible reasoning. Richer than ruled_out (which is just subject+reason).
CREATE TABLE IF NOT EXISTS considered_and_rejected (
    id TEXT PRIMARY KEY,
    dossier_id TEXT NOT NULL,
    sub_investigation_id TEXT,
    path TEXT NOT NULL,
    why_compelling TEXT NOT NULL,
    why_rejected TEXT NOT NULL,
    cost_of_error TEXT NOT NULL DEFAULT '',
    sources TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    FOREIGN KEY (dossier_id) REFERENCES dossiers(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_crj_dossier ON considered_and_rejected(dossier_id, created_at);

-- Sleep mode: tool-call idempotency spine. One row per model-emitted tool_use
-- block. dispatch_tool_call checks here first; if the tool_use_id is seen,
-- it short-circuits to the recorded result instead of re-running the handler.
-- Stable only within one successful response from Anthropic (SDK retries
-- regenerate IDs) — primary value is migration-proofness for Path B/C and
-- defense against in-process replay.
CREATE TABLE IF NOT EXISTS tool_invocations (
    tool_use_id TEXT PRIMARY KEY,
    dossier_id TEXT NOT NULL,
    work_session_id TEXT,
    tool_name TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    result_json TEXT NOT NULL,
    is_error INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (dossier_id) REFERENCES dossiers(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_tool_invocations_dossier ON tool_invocations(dossier_id, created_at);
CREATE INDEX IF NOT EXISTS idx_tool_invocations_session ON tool_invocations(work_session_id, created_at);

-- Sleep mode: daily global cost rollup. Primary key is the UTC date string.
-- UPSERT on every post-turn usage capture. Soft-signal budgets in `settings`
-- are compared against today's row.
CREATE TABLE IF NOT EXISTS budget_accounting (
    day TEXT PRIMARY KEY,
    spent_usd REAL NOT NULL DEFAULT 0,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

-- Sleep mode: DB-backed settings surface. Editable from UI. Scoped to the
-- NEW budget/guard/sleep-mode knobs — existing env-driven stuck thresholds
-- remain in config.py. Value is JSON so we can store bools, numbers, or
-- structured options without per-type columns.
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Phase 3: per-session executive summary. One row per work_session at most.
-- The agent authors summaries via the summarize_session tool (tool lives in
-- tools/handlers.py — not your scope). Runtime fallback writes a minimal
-- row on session end if the agent didn't call it (also not your scope).
CREATE TABLE IF NOT EXISTS session_summaries (
    session_id TEXT PRIMARY KEY,
    dossier_id TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    confirmed TEXT NOT NULL DEFAULT '[]',
    ruled_out TEXT NOT NULL DEFAULT '[]',
    blocked_on TEXT NOT NULL DEFAULT '[]',
    recommended_next_action TEXT,
    cost_usd REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES work_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (dossier_id) REFERENCES dossiers(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_session_summaries_dossier ON session_summaries(dossier_id, created_at);
