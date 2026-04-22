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
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

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
