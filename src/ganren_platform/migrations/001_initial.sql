CREATE TABLE IF NOT EXISTS actors (
    handle TEXT PRIMARY KEY,
    display TEXT NOT NULL,
    onboarding_date TEXT,
    primary_unit_id TEXT
);

CREATE TABLE IF NOT EXISTS units (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('squad','builder_fleet','engine')),
    coach_handle TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    context_summary TEXT NOT NULL,
    artifacts TEXT NOT NULL DEFAULT '[]',
    tags TEXT NOT NULL,
    tag_source TEXT NOT NULL DEFAULT 'auto' CHECK (tag_source IN ('auto','override')),
    ai_involvement TEXT NOT NULL CHECK (ai_involvement IN ('L1','L2','L3')),
    agent_autonomy TEXT NOT NULL CHECK (agent_autonomy IN ('L1','L2','L3','L4','L5')),
    difficulty TEXT NOT NULL CHECK (difficulty IN ('routine','hard')),
    decision_record TEXT,
    outcome TEXT,
    rework_count INTEGER NOT NULL DEFAULT 0,
    escalated INTEGER NOT NULL DEFAULT 0,
    unit_id TEXT,
    status TEXT NOT NULL CHECK (status IN ('open','claimed','awaiting_review','closed')),
    created_by TEXT NOT NULL,
    claimed_by TEXT,
    created_at TEXT NOT NULL,
    claimed_at TEXT,
    submitted_at TEXT,
    closed_at TEXT,
    version INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_created_by ON tasks(created_by);
CREATE INDEX IF NOT EXISTS idx_tasks_claimed_by ON tasks(claimed_by);

CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    type TEXT NOT NULL,
    actor TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    delivery_failed INTEGER NOT NULL DEFAULT 0,
    tags_snapshot TEXT NOT NULL,
    ai_involvement_snap TEXT,
    agent_autonomy_snap TEXT,
    unit_id_snap TEXT,
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

CREATE INDEX IF NOT EXISTS idx_events_task_id ON events(task_id);
CREATE INDEX IF NOT EXISTS idx_events_type_created_at ON events(type, created_at);
CREATE INDEX IF NOT EXISTS idx_events_actor ON events(actor);

CREATE TABLE IF NOT EXISTS questions (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    asked_by TEXT NOT NULL,
    question TEXT NOT NULL,
    ctx_summary TEXT,
    ctx_full TEXT,
    answer TEXT,
    answered_by TEXT,
    status TEXT NOT NULL CHECK (status IN ('open','answered')),
    asked_at TEXT NOT NULL,
    answered_at TEXT,
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

CREATE INDEX IF NOT EXISTS idx_questions_task_id ON questions(task_id);
CREATE INDEX IF NOT EXISTS idx_questions_asked_by ON questions(asked_by);
CREATE INDEX IF NOT EXISTS idx_questions_status ON questions(status);
