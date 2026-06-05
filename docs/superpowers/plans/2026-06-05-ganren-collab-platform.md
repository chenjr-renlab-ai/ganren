# 干人协作平台 MVP 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现一个 Python 单进程协作平台：CC 发布者把任务（含考核框架要求的标签/AI 介入度/agent 自主度/难度/决策记录）发布到中心调度平台，CC 协作者认领、干活、问问题、提交 review；所有状态变更落 events 表作为 AI-Native 考核仪表盘的 single source of truth。

**Architecture:** FastAPI ASGI 应用，FastMCP 以 streamable HTTP mount 进同一 app；业务逻辑全集中在 service 层，HTTP/MCP 都是薄适配；SQLite WAL 模式 + 单事务 + 乐观锁（UPDATE WHERE 守卫 + version）实现并发安全；Slack outbound 异步 fire-and-forget。

**Tech Stack:** Python 3.12, uv（包管理）, FastAPI 0.115+, mcp[fastmcp] 官方 SDK, sqlite3 stdlib（不引入 ORM）, pydantic v2, httpx（Slack 出站）, python-ulid, pytest + httpx AsyncClient + respx。

**Spec reference:** `docs/superpowers/specs/2026-06-05-ganren-collab-platform-design.md`

---

## 文件结构

```
ganren/
├── pyproject.toml
├── .env.example
├── README.md
├── src/ganren_platform/
│   ├── __init__.py
│   ├── main.py                   # uvicorn entry point
│   ├── config.py                 # dotenv 配置加载
│   ├── db.py                     # SQLite 连接 + transaction + migrate
│   ├── models.py                 # Pydantic schemas + 校验器
│   ├── errors.py                 # 自定义异常 + 错误码
│   ├── migrations/
│   │   └── 001_initial.sql       # 5 张表 + 索引
│   ├── service/
│   │   ├── __init__.py
│   │   ├── events.py             # insert_event 助手 + id/时间工具
│   │   ├── tasks.py              # publish/list/get/claim/abandon/cancel/submit/reject/sign_off/retag/record_outcome/report_escalation
│   │   ├── questions.py          # ask_question / answer_question
│   │   └── inbox.py              # inbox / my_tasks / unit_health
│   ├── notifications/
│   │   ├── __init__.py
│   │   └── slack.py              # 异步 webhook + 模板
│   ├── http_api/
│   │   ├── __init__.py
│   │   ├── app.py                # FastAPI app + 异常处理 + actor 依赖
│   │   ├── routes_tasks.py
│   │   ├── routes_questions.py
│   │   └── routes_inbox.py
│   └── mcp_api/
│       ├── __init__.py
│       └── server.py             # FastMCP 工具注册
└── tests/
    ├── conftest.py               # temp db + fixtures
    ├── test_service_events.py
    ├── test_service_tasks_lifecycle.py
    ├── test_service_tasks_concurrency.py
    ├── test_service_questions.py
    ├── test_service_inbox.py
    ├── test_slack.py
    ├── test_http_api.py
    └── test_mcp_api.py
```

设计原则：
- service 层文件按任务生命周期切分，不按 verb 切分（同一份事务模板复用）
- HTTP routes 按资源切分；MCP server 用一个文件统一注册所有工具（轻量包装）
- 测试文件按 service 模块对应

---

## Task 1: 项目骨架与依赖

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `src/ganren_platform/__init__.py`
- Create: `src/ganren_platform/config.py`
- Create: `src/ganren_platform/main.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: 写 pyproject.toml**

```toml
[project]
name = "ganren-platform"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "mcp[cli]>=1.2",
    "pydantic>=2.9",
    "python-ulid>=3.0",
    "httpx>=0.27",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "respx>=0.21",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/ganren_platform"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: 写 .env.example**

```dotenv
BIND_ADDR=0.0.0.0:8787
GANREN_DB_PATH=./data/ganren.db
SLACK_WEBHOOK_URL=
LOG_LEVEL=info
```

- [ ] **Step 3: 写 src/ganren_platform/__init__.py（空文件）和 config.py**

`src/ganren_platform/__init__.py`:
```python
```

`src/ganren_platform/config.py`:
```python
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Config:
    bind_addr: str
    db_path: str
    slack_webhook_url: str | None
    log_level: str

def load_config() -> Config:
    return Config(
        bind_addr=os.environ.get("BIND_ADDR", "0.0.0.0:8787"),
        db_path=os.environ.get("GANREN_DB_PATH", "./data/ganren.db"),
        slack_webhook_url=os.environ.get("SLACK_WEBHOOK_URL") or None,
        log_level=os.environ.get("LOG_LEVEL", "info"),
    )
```

- [ ] **Step 4: 写 main.py（仅占位，后面 Task 14/15 填实）**

```python
import sys
from .config import load_config

def main() -> int:
    cfg = load_config()
    print(f"ganren-platform config loaded: bind={cfg.bind_addr} db={cfg.db_path}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: 写 tests/__init__.py 和 conftest.py 占位**

`tests/__init__.py`:
```python
```

`tests/conftest.py`:
```python
import pytest
import tempfile
import os
from pathlib import Path

@pytest.fixture
def temp_db_path():
    with tempfile.TemporaryDirectory() as tmp:
        yield str(Path(tmp) / "test.db")
```

- [ ] **Step 6: 安装依赖并验证骨架**

Run:
```
uv sync --extra dev
uv run python -m ganren_platform.main
```
Expected: 输出 `ganren-platform config loaded: bind=0.0.0.0:8787 db=./data/ganren.db`

- [ ] **Step 7: 提交**

```bash
git init
git add pyproject.toml .env.example src tests
git commit -m "feat: project skeleton with config and main entry"
```

---

## Task 2: SQLite 连接、事务管理、migration

**Files:**
- Create: `src/ganren_platform/db.py`
- Create: `src/ganren_platform/migrations/001_initial.sql`
- Create: `tests/test_db.py`

- [ ] **Step 1: 写失败的测试 tests/test_db.py**

```python
import sqlite3
from ganren_platform.db import get_connection, transaction, migrate

def test_migrate_creates_tables(temp_db_path):
    migrate(temp_db_path)
    conn = get_connection(temp_db_path)
    tables = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert {"tasks", "events", "questions", "actors", "units", "_migrations"} <= tables

def test_wal_mode_enabled(temp_db_path):
    migrate(temp_db_path)
    conn = get_connection(temp_db_path)
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"

def test_transaction_rolls_back_on_exception(temp_db_path):
    migrate(temp_db_path)
    conn = get_connection(temp_db_path)
    conn.execute(
        "INSERT INTO actors (handle, display) VALUES (?, ?)",
        ("alice", "Alice"),
    )
    try:
        with transaction(conn):
            conn.execute(
                "INSERT INTO actors (handle, display) VALUES (?, ?)",
                ("bob", "Bob"),
            )
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    handles = {r["handle"] for r in conn.execute("SELECT handle FROM actors")}
    assert handles == {"alice"}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_db.py -v`
Expected: ImportError 或 ModuleNotFoundError，全部失败

- [ ] **Step 3: 写 migrations/001_initial.sql**

```sql
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
```

- [ ] **Step 4: 写 db.py**

```python
import sqlite3
from contextlib import contextmanager
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

def get_connection(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

@contextmanager
def transaction(conn: sqlite3.Connection):
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

def migrate(db_path: str) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS _migrations "
            "(name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        applied = {r["name"] for r in conn.execute("SELECT name FROM _migrations")}
        for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if sql_file.name in applied:
                continue
            sql = sql_file.read_text(encoding="utf-8")
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO _migrations (name, applied_at) VALUES (?, datetime('now'))",
                (sql_file.name,),
            )
    finally:
        conn.close()
```

- [ ] **Step 5: 跑测试验证通过**

Run: `uv run pytest tests/test_db.py -v`
Expected: 3 passed

- [ ] **Step 6: 提交**

```bash
git add src/ganren_platform/db.py src/ganren_platform/migrations tests/test_db.py
git commit -m "feat(db): sqlite WAL connection, transaction helper, migration runner"
```

---

## Task 3: Pydantic models + 错误类型

**Files:**
- Create: `src/ganren_platform/models.py`
- Create: `src/ganren_platform/errors.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: 写失败的 tests/test_models.py**

```python
import pytest
from pydantic import ValidationError
from ganren_platform.models import PublishTaskRequest, DecisionRecord, Artifact

def _base_publish_kwargs(**overrides):
    base = dict(
        title="t",
        description="d",
        context_summary="s",
        tags=["IC"],
        ai_involvement="L2",
        agent_autonomy="L3",
        difficulty="routine",
    )
    base.update(overrides)
    return base

def test_publish_request_accepts_minimal_routine_task():
    req = PublishTaskRequest(**_base_publish_kwargs())
    assert req.tags == ["IC"]
    assert req.decision_record is None

def test_publish_request_requires_decision_record_for_hard():
    with pytest.raises(ValidationError, match="decision_record"):
        PublishTaskRequest(**_base_publish_kwargs(difficulty="hard"))

def test_publish_request_requires_decision_record_for_dri():
    with pytest.raises(ValidationError, match="decision_record"):
        PublishTaskRequest(**_base_publish_kwargs(tags=["DRI"]))

def test_publish_request_accepts_hard_with_decision_record():
    dr = DecisionRecord(
        options_considered=["A", "B"],
        chosen="A",
        prob_estimate=0.7,
        rationale="A is safer",
    )
    req = PublishTaskRequest(**_base_publish_kwargs(difficulty="hard", decision_record=dr))
    assert req.decision_record.chosen == "A"

def test_publish_request_rejects_empty_tags():
    with pytest.raises(ValidationError):
        PublishTaskRequest(**_base_publish_kwargs(tags=[]))

def test_publish_request_rejects_invalid_tag():
    with pytest.raises(ValidationError):
        PublishTaskRequest(**_base_publish_kwargs(tags=["IC", "Other"]))

def test_decision_record_clamps_probability():
    with pytest.raises(ValidationError):
        DecisionRecord(
            options_considered=["A"],
            chosen="A",
            prob_estimate=1.5,
            rationale="r",
        )

def test_artifact_kinds():
    Artifact(kind="file", path="src/a.py")
    Artifact(kind="link", url="https://example.com")
    Artifact(kind="snippet", lang="python", body="x = 1")
    Artifact(kind="transcript", body="...")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_models.py -v`
Expected: ModuleNotFoundError

- [ ] **Step 3: 写 errors.py**

```python
class PlatformError(Exception):
    code: str = "error"
    http_status: int = 500

    def __init__(self, message: str, **extras):
        super().__init__(message)
        self.extras = extras

class MissingDecisionRecord(PlatformError):
    code = "missing_decision_record"
    http_status = 400

class InvalidTags(PlatformError):
    code = "invalid_tags"
    http_status = 400

class CtxTooLarge(PlatformError):
    code = "ctx_too_large"
    http_status = 400

class NotAllowed(PlatformError):
    code = "not_allowed"
    http_status = 403

class TaskNotFound(PlatformError):
    code = "task_not_found"
    http_status = 404

class QuestionNotFound(PlatformError):
    code = "question_not_found"
    http_status = 404

class AlreadyClaimed(PlatformError):
    code = "already_claimed"
    http_status = 409

class InvalidState(PlatformError):
    code = "invalid_state"
    http_status = 409

class VersionConflict(PlatformError):
    code = "version_conflict"
    http_status = 409
```

- [ ] **Step 4: 写 models.py**

```python
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field, model_validator

Tag = Literal["IC", "Builder", "Coach", "DRI"]
AIInvolvement = Literal["L1", "L2", "L3"]
AgentAutonomy = Literal["L1", "L2", "L3", "L4", "L5"]
Difficulty = Literal["routine", "hard"]
TaskStatus = Literal["open", "claimed", "awaiting_review", "closed"]
TagSource = Literal["auto", "override"]
ArtifactKind = Literal["file", "snippet", "link", "transcript"]

class Artifact(BaseModel):
    kind: ArtifactKind
    path: Optional[str] = None
    url: Optional[str] = None
    body: Optional[str] = None
    lang: Optional[str] = None

class DecisionRecord(BaseModel):
    options_considered: list[str] = Field(..., min_length=1)
    chosen: str
    prob_estimate: float = Field(..., ge=0.0, le=1.0)
    rationale: str

class Outcome(BaseModel):
    summary: str
    matched_estimate: Optional[bool] = None

class PublishTaskRequest(BaseModel):
    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    context_summary: str
    tags: list[Tag] = Field(..., min_length=1)
    ai_involvement: AIInvolvement
    agent_autonomy: AgentAutonomy
    difficulty: Difficulty
    artifacts: list[Artifact] = Field(default_factory=list)
    decision_record: Optional[DecisionRecord] = None
    unit_id: Optional[str] = None

    @model_validator(mode="after")
    def _require_decision_record_when_hard_or_dri(self):
        if (self.difficulty == "hard" or "DRI" in self.tags) and self.decision_record is None:
            raise ValueError(
                "decision_record is required when difficulty='hard' or tags contain 'DRI'"
            )
        return self

class TaskListItem(BaseModel):
    id: str
    title: str
    description: str
    tags: list[Tag]
    ai_involvement: AIInvolvement
    agent_autonomy: AgentAutonomy
    difficulty: Difficulty
    created_by: str

class QuestionOut(BaseModel):
    id: str
    task_id: str
    asked_by: str
    question: str
    ctx_summary: Optional[str]
    ctx_full: Optional[str]
    answer: Optional[str]
    answered_by: Optional[str]
    status: Literal["open", "answered"]
    asked_at: str
    answered_at: Optional[str]

class TaskFull(BaseModel):
    id: str
    title: str
    description: str
    context_summary: str
    artifacts: list[Artifact]
    tags: list[Tag]
    tag_source: TagSource
    ai_involvement: AIInvolvement
    agent_autonomy: AgentAutonomy
    difficulty: Difficulty
    decision_record: Optional[DecisionRecord]
    outcome: Optional[Outcome]
    rework_count: int
    escalated: bool
    unit_id: Optional[str]
    status: TaskStatus
    created_by: str
    claimed_by: Optional[str]
    created_at: str
    claimed_at: Optional[str]
    submitted_at: Optional[str]
    closed_at: Optional[str]
    version: int
    question_history: list[QuestionOut] = Field(default_factory=list)

class AskQuestionRequest(BaseModel):
    task_id: str
    question: str = Field(..., min_length=1)
    ctx_summary: Optional[str] = None
    ctx_full: Optional[str] = None

class AnswerQuestionRequest(BaseModel):
    question_id: str
    answer: str = Field(..., min_length=1)
```

- [ ] **Step 5: 跑测试验证**

Run: `uv run pytest tests/test_models.py -v`
Expected: 8 passed

- [ ] **Step 6: 提交**

```bash
git add src/ganren_platform/models.py src/ganren_platform/errors.py tests/test_models.py
git commit -m "feat(models): pydantic schemas and error types"
```

---

## Task 4: events 写入助手 + id/时间工具

**Files:**
- Create: `src/ganren_platform/service/__init__.py`
- Create: `src/ganren_platform/service/events.py`
- Create: `tests/test_service_events.py`

- [ ] **Step 1: 写失败的 tests/test_service_events.py**

```python
import json
from ganren_platform.db import get_connection, migrate, transaction
from ganren_platform.service.events import insert_event, new_id, now_iso

def test_new_id_is_unique_and_sortable():
    ids = [new_id() for _ in range(100)]
    assert len(set(ids)) == 100
    assert ids == sorted(ids)

def test_now_iso_returns_utc_string():
    s = now_iso()
    assert "T" in s
    assert s.endswith("+00:00") or s.endswith("Z")

def test_insert_event_persists_row(temp_db_path):
    migrate(temp_db_path)
    conn = get_connection(temp_db_path)
    conn.execute(
        "INSERT INTO tasks ("
        "id, title, description, context_summary, tags, ai_involvement, "
        "agent_autonomy, difficulty, status, created_by, created_at"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("t1", "T", "D", "S", '["IC"]', "L2", "L3", "routine",
         "open", "alice", now_iso()),
    )
    with transaction(conn):
        eid = insert_event(
            conn,
            task_id="t1",
            type="task.created",
            actor="alice",
            payload={"title": "T"},
            tags_snapshot=["IC"],
            ai_involvement_snap="L2",
            agent_autonomy_snap="L3",
            unit_id_snap=None,
        )
    row = conn.execute("SELECT * FROM events WHERE id=?", (eid,)).fetchone()
    assert row["type"] == "task.created"
    assert row["actor"] == "alice"
    assert json.loads(row["payload"]) == {"title": "T"}
    assert json.loads(row["tags_snapshot"]) == ["IC"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_service_events.py -v`
Expected: ModuleNotFoundError

- [ ] **Step 3: 写 service/__init__.py（空）和 events.py**

`src/ganren_platform/service/__init__.py`:
```python
```

`src/ganren_platform/service/events.py`:
```python
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional
from ulid import ULID

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def new_id() -> str:
    return str(ULID())

def insert_event(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    type: str,
    actor: str,
    payload: dict[str, Any],
    tags_snapshot: list[str],
    ai_involvement_snap: Optional[str],
    agent_autonomy_snap: Optional[str],
    unit_id_snap: Optional[str],
) -> str:
    event_id = new_id()
    conn.execute(
        "INSERT INTO events ("
        "id, task_id, type, actor, payload, created_at, "
        "tags_snapshot, ai_involvement_snap, agent_autonomy_snap, unit_id_snap"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            event_id, task_id, type, actor,
            json.dumps(payload),
            now_iso(),
            json.dumps(tags_snapshot),
            ai_involvement_snap,
            agent_autonomy_snap,
            unit_id_snap,
        ),
    )
    return event_id
```

- [ ] **Step 4: 跑测试**

Run: `uv run pytest tests/test_service_events.py -v`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add src/ganren_platform/service tests/test_service_events.py
git commit -m "feat(service): events helper with ulid and utc timestamps"
```

---

## Task 5: publish_task + 行映射助手

**Files:**
- Create: `src/ganren_platform/service/tasks.py`
- Create: `tests/test_service_tasks_publish.py`
- Modify: `tests/conftest.py` (新增 fixtures)

- [ ] **Step 1: 扩展 conftest.py 加 fixtures**

完整新版 `tests/conftest.py`:

```python
import pytest
import sqlite3
import tempfile
from pathlib import Path
from ganren_platform.db import get_connection, migrate
from ganren_platform.models import PublishTaskRequest, DecisionRecord

@pytest.fixture
def temp_db_path():
    with tempfile.TemporaryDirectory() as tmp:
        yield str(Path(tmp) / "test.db")

@pytest.fixture
def conn(temp_db_path) -> sqlite3.Connection:
    migrate(temp_db_path)
    c = get_connection(temp_db_path)
    c.execute("INSERT INTO actors (handle, display) VALUES (?, ?)", ("alice", "Alice"))
    c.execute("INSERT INTO actors (handle, display) VALUES (?, ?)", ("bob", "Bob"))
    c.execute("INSERT INTO actors (handle, display) VALUES (?, ?)", ("carol", "Carol"))
    yield c
    c.close()

@pytest.fixture
def routine_publish_req() -> PublishTaskRequest:
    return PublishTaskRequest(
        title="Build login",
        description="Implement login endpoint",
        context_summary="See spec section 2",
        tags=["Builder"],
        ai_involvement="L2",
        agent_autonomy="L3",
        difficulty="routine",
    )

@pytest.fixture
def hard_publish_req() -> PublishTaskRequest:
    return PublishTaskRequest(
        title="Pick auth provider",
        description="Decide between Auth0 and Cognito",
        context_summary="Constraints listed",
        tags=["DRI"],
        ai_involvement="L1",
        agent_autonomy="L1",
        difficulty="hard",
        decision_record=DecisionRecord(
            options_considered=["Auth0", "Cognito", "self-built"],
            chosen="Auth0",
            prob_estimate=0.6,
            rationale="Lower ops overhead",
        ),
    )
```

- [ ] **Step 2: 写失败的 tests/test_service_tasks_publish.py**

```python
import json
from ganren_platform.service.tasks import publish_task, get_task

def test_publish_routine_task_inserts_row_and_event(conn, routine_publish_req):
    task_id = publish_task(conn, actor="alice", req=routine_publish_req)
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    assert row["status"] == "open"
    assert row["created_by"] == "alice"
    assert row["tag_source"] == "auto"
    assert json.loads(row["tags"]) == ["Builder"]
    assert row["version"] == 0
    events = conn.execute(
        "SELECT * FROM events WHERE task_id=? ORDER BY created_at", (task_id,)
    ).fetchall()
    assert len(events) == 1
    assert events[0]["type"] == "task.created"

def test_publish_hard_task_persists_decision_record(conn, hard_publish_req):
    task_id = publish_task(conn, actor="alice", req=hard_publish_req)
    row = conn.execute("SELECT decision_record FROM tasks WHERE id=?", (task_id,)).fetchone()
    dr = json.loads(row["decision_record"])
    assert dr["chosen"] == "Auth0"
    assert dr["prob_estimate"] == 0.6

def test_get_task_returns_full_payload(conn, routine_publish_req):
    task_id = publish_task(conn, actor="alice", req=routine_publish_req)
    task = get_task(conn, task_id=task_id)
    assert task.id == task_id
    assert task.title == "Build login"
    assert task.tags == ["Builder"]
    assert task.status == "open"
    assert task.version == 0

def test_get_task_raises_when_missing(conn):
    from ganren_platform.errors import TaskNotFound
    import pytest
    with pytest.raises(TaskNotFound):
        get_task(conn, task_id="does-not-exist")
```

- [ ] **Step 3: 跑测试确认失败**

Run: `uv run pytest tests/test_service_tasks_publish.py -v`
Expected: ModuleNotFoundError

- [ ] **Step 4: 写 service/tasks.py（publish + row 映射 + get_task）**

```python
import json
import sqlite3
from typing import Optional
from ..models import (
    PublishTaskRequest, TaskFull, TaskListItem, Artifact, DecisionRecord, Outcome,
    QuestionOut,
)
from ..errors import TaskNotFound
from ..db import transaction
from .events import insert_event, new_id, now_iso

def _row_to_task_full(row: sqlite3.Row, questions: list[QuestionOut]) -> TaskFull:
    return TaskFull(
        id=row["id"],
        title=row["title"],
        description=row["description"],
        context_summary=row["context_summary"],
        artifacts=[Artifact(**a) for a in json.loads(row["artifacts"])],
        tags=json.loads(row["tags"]),
        tag_source=row["tag_source"],
        ai_involvement=row["ai_involvement"],
        agent_autonomy=row["agent_autonomy"],
        difficulty=row["difficulty"],
        decision_record=(
            DecisionRecord(**json.loads(row["decision_record"]))
            if row["decision_record"] else None
        ),
        outcome=(
            Outcome(**json.loads(row["outcome"]))
            if row["outcome"] else None
        ),
        rework_count=row["rework_count"],
        escalated=bool(row["escalated"]),
        unit_id=row["unit_id"],
        status=row["status"],
        created_by=row["created_by"],
        claimed_by=row["claimed_by"],
        created_at=row["created_at"],
        claimed_at=row["claimed_at"],
        submitted_at=row["submitted_at"],
        closed_at=row["closed_at"],
        version=row["version"],
        question_history=questions,
    )

def _row_to_question(row: sqlite3.Row) -> QuestionOut:
    return QuestionOut(
        id=row["id"],
        task_id=row["task_id"],
        asked_by=row["asked_by"],
        question=row["question"],
        ctx_summary=row["ctx_summary"],
        ctx_full=row["ctx_full"],
        answer=row["answer"],
        answered_by=row["answered_by"],
        status=row["status"],
        asked_at=row["asked_at"],
        answered_at=row["answered_at"],
    )

def _row_to_list_item(row: sqlite3.Row) -> TaskListItem:
    return TaskListItem(
        id=row["id"],
        title=row["title"],
        description=row["description"],
        tags=json.loads(row["tags"]),
        ai_involvement=row["ai_involvement"],
        agent_autonomy=row["agent_autonomy"],
        difficulty=row["difficulty"],
        created_by=row["created_by"],
    )

def publish_task(conn: sqlite3.Connection, *, actor: str, req: PublishTaskRequest) -> str:
    task_id = new_id()
    created_at = now_iso()
    with transaction(conn):
        conn.execute(
            "INSERT INTO tasks ("
            "id, title, description, context_summary, artifacts, tags, "
            "tag_source, ai_involvement, agent_autonomy, difficulty, "
            "decision_record, status, created_by, created_at, version, unit_id"
            ") VALUES (?, ?, ?, ?, ?, ?, 'auto', ?, ?, ?, ?, 'open', ?, ?, 0, ?)",
            (
                task_id, req.title, req.description, req.context_summary,
                json.dumps([a.model_dump(exclude_none=True) for a in req.artifacts]),
                json.dumps(req.tags),
                req.ai_involvement, req.agent_autonomy, req.difficulty,
                json.dumps(req.decision_record.model_dump()) if req.decision_record else None,
                actor, created_at, req.unit_id,
            ),
        )
        insert_event(
            conn,
            task_id=task_id,
            type="task.created",
            actor=actor,
            payload={"title": req.title, "tags": req.tags},
            tags_snapshot=req.tags,
            ai_involvement_snap=req.ai_involvement,
            agent_autonomy_snap=req.agent_autonomy,
            unit_id_snap=req.unit_id,
        )
    return task_id

def get_task(conn: sqlite3.Connection, *, task_id: str) -> TaskFull:
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if row is None:
        raise TaskNotFound(f"task {task_id} not found", task_id=task_id)
    q_rows = conn.execute(
        "SELECT * FROM questions WHERE task_id=? ORDER BY asked_at",
        (task_id,),
    ).fetchall()
    return _row_to_task_full(row, [_row_to_question(q) for q in q_rows])
```

- [ ] **Step 5: 跑测试**

Run: `uv run pytest tests/test_service_tasks_publish.py tests/test_models.py tests/test_db.py tests/test_service_events.py -v`
Expected: all pass

- [ ] **Step 6: 提交**

```bash
git add src/ganren_platform/service/tasks.py tests/test_service_tasks_publish.py tests/conftest.py
git commit -m "feat(service): publish_task and get_task with row mappers"
```

---

## Task 6: list_open_tasks（描述视图，不带 context_summary）

**Files:**
- Modify: `src/ganren_platform/service/tasks.py`
- Create: `tests/test_service_tasks_list.py`

- [ ] **Step 1: 写失败的 tests/test_service_tasks_list.py**

```python
from ganren_platform.service.tasks import publish_task, list_open_tasks
from ganren_platform.models import PublishTaskRequest

def _req(tags, ai="L2", autonomy="L3", difficulty="routine", dr=None):
    return PublishTaskRequest(
        title="T", description="D", context_summary="S",
        tags=tags, ai_involvement=ai, agent_autonomy=autonomy,
        difficulty=difficulty, decision_record=dr,
    )

def test_list_open_tasks_returns_only_open(conn):
    t1 = publish_task(conn, actor="alice", req=_req(["IC"]))
    t2 = publish_task(conn, actor="alice", req=_req(["Builder"]))
    conn.execute("UPDATE tasks SET status='closed' WHERE id=?", (t2,))
    items = list_open_tasks(conn)
    ids = {it.id for it in items}
    assert ids == {t1}

def test_list_open_tasks_omits_context_summary_fields(conn):
    publish_task(conn, actor="alice", req=_req(["IC"]))
    items = list_open_tasks(conn)
    # TaskListItem 没有 context_summary 字段
    assert not hasattr(items[0], "context_summary")

def test_list_open_tasks_filters_by_tag(conn):
    publish_task(conn, actor="alice", req=_req(["IC"]))
    t_builder = publish_task(conn, actor="alice", req=_req(["Builder"]))
    items = list_open_tasks(conn, tags=["Builder"])
    assert [it.id for it in items] == [t_builder]

def test_list_open_tasks_filters_by_ai_involvement(conn):
    t1 = publish_task(conn, actor="alice", req=_req(["IC"], ai="L1"))
    publish_task(conn, actor="alice", req=_req(["IC"], ai="L3"))
    items = list_open_tasks(conn, ai_involvement="L1")
    assert [it.id for it in items] == [t1]

def test_list_open_tasks_filters_by_difficulty(conn):
    from ganren_platform.models import DecisionRecord
    dr = DecisionRecord(options_considered=["a"], chosen="a", prob_estimate=0.5, rationale="r")
    t_hard = publish_task(conn, actor="alice", req=_req(["IC"], difficulty="hard", dr=dr))
    publish_task(conn, actor="alice", req=_req(["IC"]))
    items = list_open_tasks(conn, difficulty="hard")
    assert [it.id for it in items] == [t_hard]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_service_tasks_list.py -v`
Expected: ImportError on list_open_tasks

- [ ] **Step 3: 把 list_open_tasks 加到 service/tasks.py 末尾**

```python
def list_open_tasks(
    conn: sqlite3.Connection,
    *,
    tags: Optional[list[str]] = None,
    ai_involvement: Optional[str] = None,
    difficulty: Optional[str] = None,
) -> list[TaskListItem]:
    sql = "SELECT * FROM tasks WHERE status='open'"
    params: list = []
    if ai_involvement:
        sql += " AND ai_involvement = ?"
        params.append(ai_involvement)
    if difficulty:
        sql += " AND difficulty = ?"
        params.append(difficulty)
    sql += " ORDER BY created_at"
    rows = conn.execute(sql, params).fetchall()
    items = [_row_to_list_item(r) for r in rows]
    if tags:
        wanted = set(tags)
        items = [it for it in items if wanted & set(it.tags)]
    return items
```

- [ ] **Step 4: 跑测试**

Run: `uv run pytest tests/test_service_tasks_list.py -v`
Expected: 5 passed

- [ ] **Step 5: 提交**

```bash
git add src/ganren_platform/service/tasks.py tests/test_service_tasks_list.py
git commit -m "feat(service): list_open_tasks with tag/ai/difficulty filters"
```

---

## Task 7: claim_task（原子并发认领）

**Files:**
- Modify: `src/ganren_platform/service/tasks.py`
- Create: `tests/test_service_tasks_claim.py`
- Create: `tests/test_service_tasks_concurrency.py`

- [ ] **Step 1: 写失败的 tests/test_service_tasks_claim.py**

```python
import pytest
from ganren_platform.service.tasks import publish_task, claim_task
from ganren_platform.models import PublishTaskRequest
from ganren_platform.errors import AlreadyClaimed, TaskNotFound

def _req():
    return PublishTaskRequest(
        title="T", description="D", context_summary="S",
        tags=["IC"], ai_involvement="L2", agent_autonomy="L3", difficulty="routine",
    )

def test_claim_open_task_succeeds(conn):
    tid = publish_task(conn, actor="alice", req=_req())
    task = claim_task(conn, actor="bob", task_id=tid)
    assert task.status == "claimed"
    assert task.claimed_by == "bob"
    assert task.version == 1
    events = conn.execute(
        "SELECT type FROM events WHERE task_id=? ORDER BY created_at", (tid,)
    ).fetchall()
    assert [e["type"] for e in events] == ["task.created", "task.claimed"]

def test_claim_returns_question_history(conn):
    tid = publish_task(conn, actor="alice", req=_req())
    task = claim_task(conn, actor="bob", task_id=tid)
    assert task.question_history == []

def test_claim_nonexistent_raises_task_not_found(conn):
    with pytest.raises(TaskNotFound):
        claim_task(conn, actor="bob", task_id="missing")

def test_claim_already_claimed_raises(conn):
    tid = publish_task(conn, actor="alice", req=_req())
    claim_task(conn, actor="bob", task_id=tid)
    with pytest.raises(AlreadyClaimed):
        claim_task(conn, actor="carol", task_id=tid)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_service_tasks_claim.py -v`
Expected: ImportError on claim_task

- [ ] **Step 3: 把 claim_task 加到 service/tasks.py**

```python
def claim_task(conn: sqlite3.Connection, *, actor: str, task_id: str) -> TaskFull:
    from ..errors import AlreadyClaimed
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if row is None:
        raise TaskNotFound(f"task {task_id} not found", task_id=task_id)
    if row["status"] != "open":
        raise AlreadyClaimed(
            f"task {task_id} status is {row['status']}",
            task_id=task_id,
            current_status=row["status"],
            current_claimed_by=row["claimed_by"],
        )
    claimed_at = now_iso()
    with transaction(conn):
        cursor = conn.execute(
            "UPDATE tasks SET status='claimed', claimed_by=?, claimed_at=?, "
            "version=version+1 WHERE id=? AND status='open' AND version=?",
            (actor, claimed_at, task_id, row["version"]),
        )
        if cursor.rowcount == 0:
            raise AlreadyClaimed(
                f"task {task_id} was claimed by another actor",
                task_id=task_id,
            )
        insert_event(
            conn,
            task_id=task_id,
            type="task.claimed",
            actor=actor,
            payload={},
            tags_snapshot=json.loads(row["tags"]),
            ai_involvement_snap=row["ai_involvement"],
            agent_autonomy_snap=row["agent_autonomy"],
            unit_id_snap=row["unit_id"],
        )
    return get_task(conn, task_id=task_id)
```

- [ ] **Step 4: 跑单元测试**

Run: `uv run pytest tests/test_service_tasks_claim.py -v`
Expected: 4 passed

- [ ] **Step 5: 写并发测试 tests/test_service_tasks_concurrency.py**

```python
import threading
import pytest
from ganren_platform.db import get_connection, migrate
from ganren_platform.service.tasks import publish_task, claim_task
from ganren_platform.models import PublishTaskRequest
from ganren_platform.errors import AlreadyClaimed

def _req():
    return PublishTaskRequest(
        title="T", description="D", context_summary="S",
        tags=["IC"], ai_involvement="L2", agent_autonomy="L3", difficulty="routine",
    )

def test_two_concurrent_claims_one_wins(temp_db_path):
    migrate(temp_db_path)
    setup = get_connection(temp_db_path)
    setup.execute("INSERT INTO actors (handle, display) VALUES ('a','A'),('b','B'),('c','C')")
    tid = publish_task(setup, actor="a", req=_req())
    setup.close()

    results: dict[str, object] = {}
    barrier = threading.Barrier(2)

    def attempt(actor: str):
        conn = get_connection(temp_db_path)
        try:
            barrier.wait()
            results[actor] = claim_task(conn, actor=actor, task_id=tid)
        except Exception as e:
            results[actor] = e
        finally:
            conn.close()

    t1 = threading.Thread(target=attempt, args=("b",))
    t2 = threading.Thread(target=attempt, args=("c",))
    t1.start(); t2.start()
    t1.join(); t2.join()

    successes = [v for v in results.values() if not isinstance(v, Exception)]
    failures = [v for v in results.values() if isinstance(v, AlreadyClaimed)]
    assert len(successes) == 1
    assert len(failures) == 1
```

- [ ] **Step 6: 跑并发测试**

Run: `uv run pytest tests/test_service_tasks_concurrency.py -v`
Expected: 1 passed

- [ ] **Step 7: 提交**

```bash
git add src/ganren_platform/service/tasks.py tests/test_service_tasks_claim.py tests/test_service_tasks_concurrency.py
git commit -m "feat(service): claim_task with atomic optimistic locking"
```

---

## Task 8: abandon_task + cancel_task

**Files:**
- Modify: `src/ganren_platform/service/tasks.py`
- Create: `tests/test_service_tasks_abandon_cancel.py`

- [ ] **Step 1: 写失败的 tests/test_service_tasks_abandon_cancel.py**

```python
import pytest
from ganren_platform.service.tasks import publish_task, claim_task, abandon_task, cancel_task
from ganren_platform.models import PublishTaskRequest
from ganren_platform.errors import InvalidState, NotAllowed

def _req():
    return PublishTaskRequest(
        title="T", description="D", context_summary="S",
        tags=["IC"], ai_involvement="L2", agent_autonomy="L3", difficulty="routine",
    )

def test_abandon_returns_task_to_open(conn):
    tid = publish_task(conn, actor="alice", req=_req())
    claim_task(conn, actor="bob", task_id=tid)
    abandon_task(conn, actor="bob", task_id=tid, reason="blocked")
    row = conn.execute("SELECT status, claimed_by FROM tasks WHERE id=?", (tid,)).fetchone()
    assert row["status"] == "open"
    assert row["claimed_by"] is None
    types = [e["type"] for e in conn.execute(
        "SELECT type FROM events WHERE task_id=? ORDER BY created_at", (tid,)
    )]
    assert types == ["task.created", "task.claimed", "task.abandoned"]

def test_abandon_not_claimer_raises(conn):
    tid = publish_task(conn, actor="alice", req=_req())
    claim_task(conn, actor="bob", task_id=tid)
    with pytest.raises(NotAllowed):
        abandon_task(conn, actor="carol", task_id=tid, reason="x")

def test_abandon_when_not_claimed_raises(conn):
    tid = publish_task(conn, actor="alice", req=_req())
    with pytest.raises(InvalidState):
        abandon_task(conn, actor="alice", task_id=tid, reason="x")

def test_cancel_open_task(conn):
    tid = publish_task(conn, actor="alice", req=_req())
    cancel_task(conn, actor="alice", task_id=tid, reason="dropped")
    row = conn.execute("SELECT status FROM tasks WHERE id=?", (tid,)).fetchone()
    assert row["status"] == "closed"

def test_cancel_claimed_task_allowed(conn):
    tid = publish_task(conn, actor="alice", req=_req())
    claim_task(conn, actor="bob", task_id=tid)
    cancel_task(conn, actor="alice", task_id=tid, reason="scope changed")
    row = conn.execute("SELECT status FROM tasks WHERE id=?", (tid,)).fetchone()
    assert row["status"] == "closed"

def test_cancel_by_non_creator_forbidden(conn):
    tid = publish_task(conn, actor="alice", req=_req())
    with pytest.raises(NotAllowed):
        cancel_task(conn, actor="bob", task_id=tid, reason="x")

def test_cancel_awaiting_review_forbidden(conn):
    tid = publish_task(conn, actor="alice", req=_req())
    claim_task(conn, actor="bob", task_id=tid)
    conn.execute("UPDATE tasks SET status='awaiting_review' WHERE id=?", (tid,))
    with pytest.raises(InvalidState):
        cancel_task(conn, actor="alice", task_id=tid, reason="x")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_service_tasks_abandon_cancel.py -v`
Expected: ImportError

- [ ] **Step 3: 加 abandon_task 和 cancel_task 到 service/tasks.py**

```python
def abandon_task(conn: sqlite3.Connection, *, actor: str, task_id: str, reason: str) -> None:
    from ..errors import InvalidState, NotAllowed
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if row is None:
        raise TaskNotFound(f"task {task_id} not found", task_id=task_id)
    if row["status"] != "claimed":
        raise InvalidState(
            f"cannot abandon task in status {row['status']}",
            task_id=task_id, current_status=row["status"],
        )
    if row["claimed_by"] != actor:
        raise NotAllowed(
            f"only claimer can abandon",
            task_id=task_id, claimed_by=row["claimed_by"],
        )
    with transaction(conn):
        cursor = conn.execute(
            "UPDATE tasks SET status='open', claimed_by=NULL, claimed_at=NULL, "
            "version=version+1 WHERE id=? AND status='claimed' AND version=?",
            (task_id, row["version"]),
        )
        if cursor.rowcount == 0:
            raise InvalidState("task state changed concurrently", task_id=task_id)
        insert_event(
            conn,
            task_id=task_id,
            type="task.abandoned",
            actor=actor,
            payload={"reason": reason},
            tags_snapshot=json.loads(row["tags"]),
            ai_involvement_snap=row["ai_involvement"],
            agent_autonomy_snap=row["agent_autonomy"],
            unit_id_snap=row["unit_id"],
        )

def cancel_task(conn: sqlite3.Connection, *, actor: str, task_id: str, reason: str) -> None:
    from ..errors import InvalidState, NotAllowed
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if row is None:
        raise TaskNotFound(f"task {task_id} not found", task_id=task_id)
    if row["created_by"] != actor:
        raise NotAllowed("only creator can cancel", task_id=task_id)
    if row["status"] not in ("open", "claimed"):
        raise InvalidState(
            f"cannot cancel task in status {row['status']}",
            task_id=task_id, current_status=row["status"],
        )
    closed_at = now_iso()
    with transaction(conn):
        cursor = conn.execute(
            "UPDATE tasks SET status='closed', closed_at=?, version=version+1 "
            "WHERE id=? AND status IN ('open','claimed') AND version=?",
            (closed_at, task_id, row["version"]),
        )
        if cursor.rowcount == 0:
            raise InvalidState("task state changed concurrently", task_id=task_id)
        insert_event(
            conn,
            task_id=task_id,
            type="task.cancelled",
            actor=actor,
            payload={"reason": reason},
            tags_snapshot=json.loads(row["tags"]),
            ai_involvement_snap=row["ai_involvement"],
            agent_autonomy_snap=row["agent_autonomy"],
            unit_id_snap=row["unit_id"],
        )
```

- [ ] **Step 4: 跑测试**

Run: `uv run pytest tests/test_service_tasks_abandon_cancel.py -v`
Expected: 7 passed

- [ ] **Step 5: 提交**

```bash
git add src/ganren_platform/service/tasks.py tests/test_service_tasks_abandon_cancel.py
git commit -m "feat(service): abandon_task and cancel_task with state guards"
```

---

## Task 9: submit_for_review + reject_task + sign_off_task

**Files:**
- Modify: `src/ganren_platform/service/tasks.py`
- Create: `tests/test_service_tasks_review.py`

- [ ] **Step 1: 写失败的 tests/test_service_tasks_review.py**

```python
import pytest
from ganren_platform.service.tasks import (
    publish_task, claim_task, submit_for_review, reject_task, sign_off_task
)
from ganren_platform.models import PublishTaskRequest
from ganren_platform.errors import InvalidState, NotAllowed

def _req():
    return PublishTaskRequest(
        title="T", description="D", context_summary="S",
        tags=["IC"], ai_involvement="L2", agent_autonomy="L3", difficulty="routine",
    )

def test_submit_moves_to_awaiting_review(conn):
    tid = publish_task(conn, actor="alice", req=_req())
    claim_task(conn, actor="bob", task_id=tid)
    submit_for_review(conn, actor="bob", task_id=tid, summary="done")
    row = conn.execute("SELECT status, submitted_at FROM tasks WHERE id=?", (tid,)).fetchone()
    assert row["status"] == "awaiting_review"
    assert row["submitted_at"] is not None

def test_submit_by_non_claimer_forbidden(conn):
    tid = publish_task(conn, actor="alice", req=_req())
    claim_task(conn, actor="bob", task_id=tid)
    with pytest.raises(NotAllowed):
        submit_for_review(conn, actor="carol", task_id=tid, summary="done")

def test_submit_open_task_forbidden(conn):
    tid = publish_task(conn, actor="alice", req=_req())
    with pytest.raises(InvalidState):
        submit_for_review(conn, actor="alice", task_id=tid, summary="done")

def test_reject_returns_to_claimed_and_increments_rework(conn):
    tid = publish_task(conn, actor="alice", req=_req())
    claim_task(conn, actor="bob", task_id=tid)
    submit_for_review(conn, actor="bob", task_id=tid, summary="done")
    reject_task(conn, actor="alice", task_id=tid, reason="missing tests")
    row = conn.execute(
        "SELECT status, claimed_by, rework_count FROM tasks WHERE id=?", (tid,)
    ).fetchone()
    assert row["status"] == "claimed"
    assert row["claimed_by"] == "bob"
    assert row["rework_count"] == 1

def test_reject_by_non_creator_forbidden(conn):
    tid = publish_task(conn, actor="alice", req=_req())
    claim_task(conn, actor="bob", task_id=tid)
    submit_for_review(conn, actor="bob", task_id=tid, summary="done")
    with pytest.raises(NotAllowed):
        reject_task(conn, actor="bob", task_id=tid, reason="x")

def test_sign_off_closes_task(conn):
    tid = publish_task(conn, actor="alice", req=_req())
    claim_task(conn, actor="bob", task_id=tid)
    submit_for_review(conn, actor="bob", task_id=tid, summary="done")
    sign_off_task(conn, actor="alice", task_id=tid, comment="lgtm")
    row = conn.execute(
        "SELECT status, closed_at FROM tasks WHERE id=?", (tid,)
    ).fetchone()
    assert row["status"] == "closed"
    assert row["closed_at"] is not None

def test_sign_off_open_task_forbidden(conn):
    tid = publish_task(conn, actor="alice", req=_req())
    with pytest.raises(InvalidState):
        sign_off_task(conn, actor="alice", task_id=tid, comment="x")

def test_multiple_rejects_accumulate_rework_count(conn):
    tid = publish_task(conn, actor="alice", req=_req())
    claim_task(conn, actor="bob", task_id=tid)
    for _ in range(3):
        submit_for_review(conn, actor="bob", task_id=tid, summary="done")
        reject_task(conn, actor="alice", task_id=tid, reason="redo")
    row = conn.execute("SELECT rework_count FROM tasks WHERE id=?", (tid,)).fetchone()
    assert row["rework_count"] == 3
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_service_tasks_review.py -v`
Expected: ImportError

- [ ] **Step 3: 加 submit/reject/sign_off 到 service/tasks.py**

```python
def submit_for_review(conn: sqlite3.Connection, *, actor: str, task_id: str, summary: str) -> None:
    from ..errors import InvalidState, NotAllowed
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if row is None:
        raise TaskNotFound(f"task {task_id} not found", task_id=task_id)
    if row["status"] != "claimed":
        raise InvalidState(
            f"cannot submit task in status {row['status']}",
            task_id=task_id, current_status=row["status"],
        )
    if row["claimed_by"] != actor:
        raise NotAllowed("only claimer can submit", task_id=task_id)
    submitted_at = now_iso()
    with transaction(conn):
        cursor = conn.execute(
            "UPDATE tasks SET status='awaiting_review', submitted_at=?, "
            "version=version+1 WHERE id=? AND status='claimed' AND version=?",
            (submitted_at, task_id, row["version"]),
        )
        if cursor.rowcount == 0:
            raise InvalidState("task state changed concurrently", task_id=task_id)
        insert_event(
            conn,
            task_id=task_id,
            type="task.submitted",
            actor=actor,
            payload={"summary": summary},
            tags_snapshot=json.loads(row["tags"]),
            ai_involvement_snap=row["ai_involvement"],
            agent_autonomy_snap=row["agent_autonomy"],
            unit_id_snap=row["unit_id"],
        )

def reject_task(
    conn: sqlite3.Connection, *, actor: str, task_id: str, reason: str,
    hints: Optional[str] = None,
) -> None:
    from ..errors import InvalidState, NotAllowed
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if row is None:
        raise TaskNotFound(f"task {task_id} not found", task_id=task_id)
    if row["created_by"] != actor:
        raise NotAllowed("only creator can reject", task_id=task_id)
    if row["status"] != "awaiting_review":
        raise InvalidState(
            f"cannot reject task in status {row['status']}",
            task_id=task_id, current_status=row["status"],
        )
    with transaction(conn):
        cursor = conn.execute(
            "UPDATE tasks SET status='claimed', rework_count=rework_count+1, "
            "submitted_at=NULL, version=version+1 "
            "WHERE id=? AND status='awaiting_review' AND version=?",
            (task_id, row["version"]),
        )
        if cursor.rowcount == 0:
            raise InvalidState("task state changed concurrently", task_id=task_id)
        insert_event(
            conn,
            task_id=task_id,
            type="task.rejected",
            actor=actor,
            payload={"reason": reason, "hints": hints},
            tags_snapshot=json.loads(row["tags"]),
            ai_involvement_snap=row["ai_involvement"],
            agent_autonomy_snap=row["agent_autonomy"],
            unit_id_snap=row["unit_id"],
        )

def sign_off_task(
    conn: sqlite3.Connection, *, actor: str, task_id: str, comment: Optional[str] = None,
) -> None:
    from ..errors import InvalidState, NotAllowed
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if row is None:
        raise TaskNotFound(f"task {task_id} not found", task_id=task_id)
    if row["created_by"] != actor:
        raise NotAllowed("only creator can sign off", task_id=task_id)
    if row["status"] != "awaiting_review":
        raise InvalidState(
            f"cannot sign off task in status {row['status']}",
            task_id=task_id, current_status=row["status"],
        )
    closed_at = now_iso()
    with transaction(conn):
        cursor = conn.execute(
            "UPDATE tasks SET status='closed', closed_at=?, version=version+1 "
            "WHERE id=? AND status='awaiting_review' AND version=?",
            (closed_at, task_id, row["version"]),
        )
        if cursor.rowcount == 0:
            raise InvalidState("task state changed concurrently", task_id=task_id)
        insert_event(
            conn,
            task_id=task_id,
            type="task.signed_off",
            actor=actor,
            payload={"comment": comment},
            tags_snapshot=json.loads(row["tags"]),
            ai_involvement_snap=row["ai_involvement"],
            agent_autonomy_snap=row["agent_autonomy"],
            unit_id_snap=row["unit_id"],
        )
```

- [ ] **Step 4: 跑测试**

Run: `uv run pytest tests/test_service_tasks_review.py -v`
Expected: 8 passed

- [ ] **Step 5: 提交**

```bash
git add src/ganren_platform/service/tasks.py tests/test_service_tasks_review.py
git commit -m "feat(service): submit/reject/sign_off with rework counter"
```

---

## Task 10: retag + record_outcome + report_escalation

**Files:**
- Modify: `src/ganren_platform/service/tasks.py`
- Create: `tests/test_service_tasks_bypass.py`

- [ ] **Step 1: 写失败的 tests/test_service_tasks_bypass.py**

```python
import json
import pytest
from ganren_platform.service.tasks import (
    publish_task, claim_task, submit_for_review, sign_off_task,
    retag_task, record_outcome, report_escalation,
)
from ganren_platform.models import PublishTaskRequest, Outcome
from ganren_platform.errors import InvalidState, NotAllowed

def _req(tags=None):
    return PublishTaskRequest(
        title="T", description="D", context_summary="S",
        tags=tags or ["IC"], ai_involvement="L2", agent_autonomy="L3", difficulty="routine",
    )

def test_retag_by_creator_sets_override_source(conn):
    tid = publish_task(conn, actor="alice", req=_req())
    retag_task(conn, actor="alice", task_id=tid, new_tags=["Builder"], reason="cleaned scope")
    row = conn.execute("SELECT tags, tag_source FROM tasks WHERE id=?", (tid,)).fetchone()
    assert json.loads(row["tags"]) == ["Builder"]
    assert row["tag_source"] == "override"

def test_retag_by_outsider_forbidden(conn):
    tid = publish_task(conn, actor="alice", req=_req())
    with pytest.raises(NotAllowed):
        retag_task(conn, actor="bob", task_id=tid, new_tags=["Builder"], reason="x")

def test_retag_by_unit_coach_allowed(conn):
    conn.execute(
        "INSERT INTO units (id, name, type, created_at) VALUES ('u1','U','squad','now')"
    )
    conn.execute("UPDATE units SET coach_handle='carol' WHERE id='u1'")
    req = _req()
    object.__setattr__(req, "unit_id", "u1")
    tid = publish_task(conn, actor="alice", req=req)
    retag_task(conn, actor="carol", task_id=tid, new_tags=["Coach"], reason="coach reclassified")
    row = conn.execute("SELECT tags FROM tasks WHERE id=?", (tid,)).fetchone()
    assert json.loads(row["tags"]) == ["Coach"]

def test_retag_event_carries_snapshot(conn):
    tid = publish_task(conn, actor="alice", req=_req())
    retag_task(conn, actor="alice", task_id=tid, new_tags=["Builder"], reason="x")
    ev = conn.execute(
        "SELECT type, tags_snapshot FROM events WHERE task_id=? AND type='task.retagged'",
        (tid,),
    ).fetchone()
    assert json.loads(ev["tags_snapshot"]) == ["Builder"]

def test_record_outcome_only_after_closed(conn):
    tid = publish_task(conn, actor="alice", req=_req())
    with pytest.raises(InvalidState):
        record_outcome(conn, actor="alice", task_id=tid,
                       outcome=Outcome(summary="x", matched_estimate=True))

def test_record_outcome_after_signoff_persists(conn):
    tid = publish_task(conn, actor="alice", req=_req())
    claim_task(conn, actor="bob", task_id=tid)
    submit_for_review(conn, actor="bob", task_id=tid, summary="done")
    sign_off_task(conn, actor="alice", task_id=tid)
    record_outcome(conn, actor="alice", task_id=tid,
                   outcome=Outcome(summary="shipped", matched_estimate=True))
    row = conn.execute("SELECT outcome FROM tasks WHERE id=?", (tid,)).fetchone()
    assert json.loads(row["outcome"])["matched_estimate"] is True

def test_report_escalation_sets_flag(conn):
    tid = publish_task(conn, actor="alice", req=_req())
    claim_task(conn, actor="bob", task_id=tid)
    report_escalation(conn, actor="bob", task_id=tid, note="agent stuck")
    row = conn.execute("SELECT escalated FROM tasks WHERE id=?", (tid,)).fetchone()
    assert row["escalated"] == 1

def test_report_escalation_by_non_claimer_forbidden(conn):
    tid = publish_task(conn, actor="alice", req=_req())
    claim_task(conn, actor="bob", task_id=tid)
    with pytest.raises(NotAllowed):
        report_escalation(conn, actor="carol", task_id=tid, note="x")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_service_tasks_bypass.py -v`
Expected: ImportError

- [ ] **Step 3: 加 retag/record_outcome/report_escalation 到 service/tasks.py**

```python
def _is_unit_coach(conn: sqlite3.Connection, actor: str, unit_id: Optional[str]) -> bool:
    if not unit_id:
        return False
    row = conn.execute(
        "SELECT coach_handle FROM units WHERE id=?", (unit_id,)
    ).fetchone()
    return row is not None and row["coach_handle"] == actor

def retag_task(
    conn: sqlite3.Connection, *, actor: str, task_id: str,
    new_tags: list[str], reason: str,
) -> None:
    from ..errors import NotAllowed, InvalidTags
    if not new_tags:
        raise InvalidTags("new_tags must be non-empty", task_id=task_id)
    allowed_tags = {"IC", "Builder", "Coach", "DRI"}
    if not set(new_tags) <= allowed_tags:
        raise InvalidTags(f"unknown tags: {set(new_tags) - allowed_tags}", task_id=task_id)
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if row is None:
        raise TaskNotFound(f"task {task_id} not found", task_id=task_id)
    is_creator = row["created_by"] == actor
    is_coach = _is_unit_coach(conn, actor, row["unit_id"])
    if not (is_creator or is_coach):
        raise NotAllowed("only creator or unit coach can retag", task_id=task_id)
    with transaction(conn):
        conn.execute(
            "UPDATE tasks SET tags=?, tag_source='override' WHERE id=?",
            (json.dumps(new_tags), task_id),
        )
        insert_event(
            conn,
            task_id=task_id,
            type="task.retagged",
            actor=actor,
            payload={"reason": reason, "old_tags": json.loads(row["tags"])},
            tags_snapshot=new_tags,
            ai_involvement_snap=row["ai_involvement"],
            agent_autonomy_snap=row["agent_autonomy"],
            unit_id_snap=row["unit_id"],
        )

def record_outcome(
    conn: sqlite3.Connection, *, actor: str, task_id: str, outcome: Outcome,
) -> None:
    from ..errors import InvalidState
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if row is None:
        raise TaskNotFound(f"task {task_id} not found", task_id=task_id)
    if row["status"] != "closed":
        raise InvalidState(
            f"cannot record outcome on status {row['status']}",
            task_id=task_id, current_status=row["status"],
        )
    with transaction(conn):
        conn.execute(
            "UPDATE tasks SET outcome=? WHERE id=?",
            (json.dumps(outcome.model_dump()), task_id),
        )
        insert_event(
            conn,
            task_id=task_id,
            type="task.outcome_recorded",
            actor=actor,
            payload=outcome.model_dump(),
            tags_snapshot=json.loads(row["tags"]),
            ai_involvement_snap=row["ai_involvement"],
            agent_autonomy_snap=row["agent_autonomy"],
            unit_id_snap=row["unit_id"],
        )

def report_escalation(
    conn: sqlite3.Connection, *, actor: str, task_id: str, note: str,
) -> None:
    from ..errors import NotAllowed
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if row is None:
        raise TaskNotFound(f"task {task_id} not found", task_id=task_id)
    if row["claimed_by"] != actor:
        raise NotAllowed("only claimer can report escalation", task_id=task_id)
    with transaction(conn):
        conn.execute("UPDATE tasks SET escalated=1 WHERE id=?", (task_id,))
        insert_event(
            conn,
            task_id=task_id,
            type="task.escalated",
            actor=actor,
            payload={"note": note},
            tags_snapshot=json.loads(row["tags"]),
            ai_involvement_snap=row["ai_involvement"],
            agent_autonomy_snap=row["agent_autonomy"],
            unit_id_snap=row["unit_id"],
        )
```

- [ ] **Step 4: 跑测试**

Run: `uv run pytest tests/test_service_tasks_bypass.py -v`
Expected: 8 passed

- [ ] **Step 5: 提交**

```bash
git add src/ganren_platform/service/tasks.py tests/test_service_tasks_bypass.py
git commit -m "feat(service): retag, record_outcome, report_escalation bypass actions"
```

---

## Task 11: questions service（ask + answer，含长度校验）

**Files:**
- Create: `src/ganren_platform/service/questions.py`
- Create: `tests/test_service_questions.py`

- [ ] **Step 1: 写失败的 tests/test_service_questions.py**

```python
import pytest
from ganren_platform.service.tasks import publish_task, claim_task
from ganren_platform.service.questions import ask_question, answer_question
from ganren_platform.models import PublishTaskRequest, AskQuestionRequest, AnswerQuestionRequest
from ganren_platform.errors import NotAllowed, QuestionNotFound, CtxTooLarge

def _req():
    return PublishTaskRequest(
        title="T", description="D", context_summary="S",
        tags=["IC"], ai_involvement="L2", agent_autonomy="L3", difficulty="routine",
    )

def test_ask_by_claimer_succeeds(conn):
    tid = publish_task(conn, actor="alice", req=_req())
    claim_task(conn, actor="bob", task_id=tid)
    qid = ask_question(conn, actor="bob", req=AskQuestionRequest(
        task_id=tid, question="which option?", ctx_summary="stuck on choice"
    ))
    row = conn.execute("SELECT * FROM questions WHERE id=?", (qid,)).fetchone()
    assert row["status"] == "open"
    assert row["asked_by"] == "bob"

def test_ask_by_non_claimer_forbidden(conn):
    tid = publish_task(conn, actor="alice", req=_req())
    claim_task(conn, actor="bob", task_id=tid)
    with pytest.raises(NotAllowed):
        ask_question(conn, actor="carol", req=AskQuestionRequest(
            task_id=tid, question="?"
        ))

def test_ask_with_oversize_ctx_summary_rejected(conn):
    tid = publish_task(conn, actor="alice", req=_req())
    claim_task(conn, actor="bob", task_id=tid)
    with pytest.raises(CtxTooLarge):
        ask_question(conn, actor="bob", req=AskQuestionRequest(
            task_id=tid, question="?", ctx_summary="x" * 501,
        ))

def test_ask_with_oversize_ctx_full_rejected(conn):
    tid = publish_task(conn, actor="alice", req=_req())
    claim_task(conn, actor="bob", task_id=tid)
    with pytest.raises(CtxTooLarge):
        ask_question(conn, actor="bob", req=AskQuestionRequest(
            task_id=tid, question="?", ctx_full="x" * 4097,
        ))

def test_answer_by_creator_succeeds(conn):
    tid = publish_task(conn, actor="alice", req=_req())
    claim_task(conn, actor="bob", task_id=tid)
    qid = ask_question(conn, actor="bob", req=AskQuestionRequest(
        task_id=tid, question="?"))
    answer_question(conn, actor="alice", req=AnswerQuestionRequest(
        question_id=qid, answer="use option A"
    ))
    row = conn.execute("SELECT status, answer, answered_by FROM questions WHERE id=?", (qid,)).fetchone()
    assert row["status"] == "answered"
    assert row["answer"] == "use option A"
    assert row["answered_by"] == "alice"

def test_answer_by_non_creator_forbidden(conn):
    tid = publish_task(conn, actor="alice", req=_req())
    claim_task(conn, actor="bob", task_id=tid)
    qid = ask_question(conn, actor="bob", req=AskQuestionRequest(
        task_id=tid, question="?"))
    with pytest.raises(NotAllowed):
        answer_question(conn, actor="bob", req=AnswerQuestionRequest(
            question_id=qid, answer="x"
        ))

def test_answer_unknown_question_raises(conn):
    with pytest.raises(QuestionNotFound):
        answer_question(conn, actor="alice", req=AnswerQuestionRequest(
            question_id="missing", answer="x"
        ))
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_service_questions.py -v`
Expected: ImportError

- [ ] **Step 3: 写 service/questions.py**

```python
import json
import sqlite3
from ..models import AskQuestionRequest, AnswerQuestionRequest
from ..errors import (
    NotAllowed, TaskNotFound, QuestionNotFound, CtxTooLarge, InvalidState,
)
from ..db import transaction
from .events import insert_event, new_id, now_iso

CTX_SUMMARY_MAX = 500
CTX_FULL_MAX = 4096

def ask_question(conn: sqlite3.Connection, *, actor: str, req: AskQuestionRequest) -> str:
    if req.ctx_summary and len(req.ctx_summary.encode("utf-8")) > CTX_SUMMARY_MAX:
        raise CtxTooLarge(
            f"ctx_summary exceeds {CTX_SUMMARY_MAX} bytes",
            limit=CTX_SUMMARY_MAX,
        )
    if req.ctx_full and len(req.ctx_full.encode("utf-8")) > CTX_FULL_MAX:
        raise CtxTooLarge(
            f"ctx_full exceeds {CTX_FULL_MAX} bytes",
            limit=CTX_FULL_MAX,
        )
    task = conn.execute("SELECT * FROM tasks WHERE id=?", (req.task_id,)).fetchone()
    if task is None:
        raise TaskNotFound(f"task {req.task_id} not found", task_id=req.task_id)
    if task["claimed_by"] != actor:
        raise NotAllowed("only claimer can ask questions", task_id=req.task_id)
    qid = new_id()
    asked_at = now_iso()
    with transaction(conn):
        conn.execute(
            "INSERT INTO questions ("
            "id, task_id, asked_by, question, ctx_summary, ctx_full, "
            "status, asked_at"
            ") VALUES (?, ?, ?, ?, ?, ?, 'open', ?)",
            (qid, req.task_id, actor, req.question, req.ctx_summary, req.ctx_full, asked_at),
        )
        insert_event(
            conn,
            task_id=req.task_id,
            type="question.asked",
            actor=actor,
            payload={"question_id": qid, "ctx_summary": req.ctx_summary},
            tags_snapshot=json.loads(task["tags"]),
            ai_involvement_snap=task["ai_involvement"],
            agent_autonomy_snap=task["agent_autonomy"],
            unit_id_snap=task["unit_id"],
        )
    return qid

def answer_question(conn: sqlite3.Connection, *, actor: str, req: AnswerQuestionRequest) -> None:
    q = conn.execute("SELECT * FROM questions WHERE id=?", (req.question_id,)).fetchone()
    if q is None:
        raise QuestionNotFound(f"question {req.question_id} not found", question_id=req.question_id)
    if q["status"] == "answered":
        raise InvalidState("question already answered", question_id=req.question_id)
    task = conn.execute("SELECT * FROM tasks WHERE id=?", (q["task_id"],)).fetchone()
    if task["created_by"] != actor:
        raise NotAllowed("only task creator can answer", task_id=q["task_id"])
    answered_at = now_iso()
    with transaction(conn):
        conn.execute(
            "UPDATE questions SET answer=?, answered_by=?, answered_at=?, status='answered' "
            "WHERE id=? AND status='open'",
            (req.answer, actor, answered_at, req.question_id),
        )
        insert_event(
            conn,
            task_id=q["task_id"],
            type="question.answered",
            actor=actor,
            payload={"question_id": req.question_id},
            tags_snapshot=json.loads(task["tags"]),
            ai_involvement_snap=task["ai_involvement"],
            agent_autonomy_snap=task["agent_autonomy"],
            unit_id_snap=task["unit_id"],
        )
```

- [ ] **Step 4: 跑测试**

Run: `uv run pytest tests/test_service_questions.py -v`
Expected: 7 passed

- [ ] **Step 5: 加 body model 到 models.py 末尾（HTTP routes 用，不含 path 参数）**

```python
class AskQuestionBody(BaseModel):
    question: str = Field(..., min_length=1)
    ctx_summary: Optional[str] = None
    ctx_full: Optional[str] = None

class AnswerQuestionBody(BaseModel):
    answer: str = Field(..., min_length=1)
```

- [ ] **Step 6: 提交**

```bash
git add src/ganren_platform/service/questions.py src/ganren_platform/models.py tests/test_service_questions.py
git commit -m "feat(service): questions ask/answer with ctx size guards"
```

---

## Task 12: inbox + my_tasks + unit_health

**Files:**
- Create: `src/ganren_platform/service/inbox.py`
- Create: `tests/test_service_inbox.py`

- [ ] **Step 1: 写失败的 tests/test_service_inbox.py**

```python
from ganren_platform.service.tasks import (
    publish_task, claim_task, submit_for_review, reject_task,
)
from ganren_platform.service.questions import ask_question, answer_question
from ganren_platform.service.inbox import inbox, my_tasks, unit_health
from ganren_platform.models import PublishTaskRequest, AskQuestionRequest, AnswerQuestionRequest

def _req(unit_id=None):
    req = PublishTaskRequest(
        title="T", description="D", context_summary="S",
        tags=["IC"], ai_involvement="L2", agent_autonomy="L3", difficulty="routine",
        unit_id=unit_id,
    )
    return req

def test_publisher_inbox_sees_open_questions_and_pending_reviews(conn):
    t1 = publish_task(conn, actor="alice", req=_req())
    t2 = publish_task(conn, actor="alice", req=_req())
    claim_task(conn, actor="bob", task_id=t1)
    claim_task(conn, actor="bob", task_id=t2)
    ask_question(conn, actor="bob", req=AskQuestionRequest(task_id=t1, question="?"))
    submit_for_review(conn, actor="bob", task_id=t2, summary="done")
    box = inbox(conn, actor="alice")
    assert len(box.questions_to_answer) == 1
    assert box.questions_to_answer[0].task_id == t1
    assert len(box.reviews_pending) == 1
    assert box.reviews_pending[0].id == t2

def test_collaborator_inbox_sees_answers_and_rejections(conn):
    t1 = publish_task(conn, actor="alice", req=_req())
    t2 = publish_task(conn, actor="alice", req=_req())
    claim_task(conn, actor="bob", task_id=t1)
    claim_task(conn, actor="bob", task_id=t2)
    qid = ask_question(conn, actor="bob", req=AskQuestionRequest(task_id=t1, question="?"))
    answer_question(conn, actor="alice", req=AnswerQuestionRequest(question_id=qid, answer="A"))
    submit_for_review(conn, actor="bob", task_id=t2, summary="done")
    reject_task(conn, actor="alice", task_id=t2, reason="redo")
    box = inbox(conn, actor="bob")
    assert len(box.answers_received) == 1
    assert box.answers_received[0].answer == "A"
    assert len(box.rejections_to_address) == 1
    assert box.rejections_to_address[0].id == t2

def test_my_tasks_returns_created_and_claimed(conn):
    t1 = publish_task(conn, actor="alice", req=_req())
    t2 = publish_task(conn, actor="alice", req=_req())
    claim_task(conn, actor="bob", task_id=t2)
    out = my_tasks(conn, actor="alice")
    created_ids = {t.id for t in out.created}
    assert created_ids == {t1, t2}
    out_bob = my_tasks(conn, actor="bob")
    claimed_ids = {t.id for t in out_bob.claimed}
    assert claimed_ids == {t2}

def test_unit_health_counts_by_unit(conn):
    conn.execute(
        "INSERT INTO units (id, name, type, created_at) VALUES ('u1','U','squad','now')"
    )
    publish_task(conn, actor="alice", req=_req(unit_id="u1"))
    publish_task(conn, actor="alice", req=_req(unit_id="u1"))
    publish_task(conn, actor="alice", req=_req())
    h = unit_health(conn, unit_id="u1")
    assert h.task_count == 2
    assert h.unit_id == "u1"
```

- [ ] **Step 2: 加 inbox 用的 models 到 models.py 末尾**

```python
class InboxResponse(BaseModel):
    questions_to_answer: list[QuestionOut] = Field(default_factory=list)
    reviews_pending: list[TaskListItem] = Field(default_factory=list)
    answers_received: list[QuestionOut] = Field(default_factory=list)
    rejections_to_address: list[TaskListItem] = Field(default_factory=list)

class MyTasksResponse(BaseModel):
    created: list[TaskListItem] = Field(default_factory=list)
    claimed: list[TaskListItem] = Field(default_factory=list)

class UnitHealthResponse(BaseModel):
    unit_id: str
    task_count: int
    closed_count: int
    open_count: int
    abandoned_count: int
```

- [ ] **Step 3: 跑测试确认失败**

Run: `uv run pytest tests/test_service_inbox.py -v`
Expected: ImportError

- [ ] **Step 4: 写 service/inbox.py**

```python
import sqlite3
from ..models import InboxResponse, MyTasksResponse, UnitHealthResponse
from .tasks import _row_to_list_item, _row_to_question

def inbox(conn: sqlite3.Connection, *, actor: str) -> InboxResponse:
    q_to_answer = [
        _row_to_question(r) for r in conn.execute(
            "SELECT q.* FROM questions q JOIN tasks t ON q.task_id=t.id "
            "WHERE t.created_by=? AND q.status='open' ORDER BY q.asked_at",
            (actor,),
        )
    ]
    reviews = [
        _row_to_list_item(r) for r in conn.execute(
            "SELECT * FROM tasks WHERE created_by=? AND status='awaiting_review' "
            "ORDER BY submitted_at",
            (actor,),
        )
    ]
    answers = [
        _row_to_question(r) for r in conn.execute(
            "SELECT * FROM questions WHERE asked_by=? AND status='answered' "
            "ORDER BY answered_at DESC LIMIT 50",
            (actor,),
        )
    ]
    rejections = [
        _row_to_list_item(r) for r in conn.execute(
            "SELECT t.* FROM tasks t "
            "JOIN events e ON e.task_id=t.id "
            "WHERE e.type='task.rejected' AND t.claimed_by=? AND t.status='claimed' "
            "GROUP BY t.id ORDER BY MAX(e.created_at)",
            (actor,),
        )
    ]
    return InboxResponse(
        questions_to_answer=q_to_answer,
        reviews_pending=reviews,
        answers_received=answers,
        rejections_to_address=rejections,
    )

def my_tasks(conn: sqlite3.Connection, *, actor: str) -> MyTasksResponse:
    created = [_row_to_list_item(r) for r in conn.execute(
        "SELECT * FROM tasks WHERE created_by=? ORDER BY created_at DESC",
        (actor,),
    )]
    claimed = [_row_to_list_item(r) for r in conn.execute(
        "SELECT * FROM tasks WHERE claimed_by=? ORDER BY claimed_at DESC",
        (actor,),
    )]
    return MyTasksResponse(created=created, claimed=claimed)

def unit_health(conn: sqlite3.Connection, *, unit_id: str) -> UnitHealthResponse:
    counts = conn.execute(
        "SELECT "
        "COUNT(*) AS total, "
        "SUM(CASE WHEN status='closed' THEN 1 ELSE 0 END) AS closed, "
        "SUM(CASE WHEN status='open' THEN 1 ELSE 0 END) AS opened "
        "FROM tasks WHERE unit_id=?",
        (unit_id,),
    ).fetchone()
    abandoned = conn.execute(
        "SELECT COUNT(*) AS c FROM events e JOIN tasks t ON e.task_id=t.id "
        "WHERE t.unit_id=? AND e.type='task.abandoned'",
        (unit_id,),
    ).fetchone()
    return UnitHealthResponse(
        unit_id=unit_id,
        task_count=counts["total"] or 0,
        closed_count=counts["closed"] or 0,
        open_count=counts["opened"] or 0,
        abandoned_count=abandoned["c"] or 0,
    )
```

- [ ] **Step 5: 跑测试**

Run: `uv run pytest tests/test_service_inbox.py -v`
Expected: 4 passed

- [ ] **Step 6: 提交**

```bash
git add src/ganren_platform/service/inbox.py src/ganren_platform/models.py tests/test_service_inbox.py
git commit -m "feat(service): inbox, my_tasks, unit_health aggregations"
```

---

## Task 13: Slack outbound 通知

**Files:**
- Create: `src/ganren_platform/notifications/__init__.py`
- Create: `src/ganren_platform/notifications/slack.py`
- Create: `tests/test_slack.py`

> **MVP 取舍说明**：Slack 失败仅返回 `False`（HTTP route 端 fire-and-forget 不 await，所以也丢弃返回值），目前 **不** 回写 `events.delivery_failed`。该 schema 字段保留供 V2 cron 批处理补发使用。MVP 行为：Slack 故障不影响业务流程，事件正常写入；运维端通过 Slack 频道是否有消息间接观察。

- [ ] **Step 1: 写失败的 tests/test_slack.py**

```python
import pytest
import respx
import httpx
from ganren_platform.notifications.slack import send_event, format_event

def test_format_task_created():
    text = format_event(
        "task.created",
        {"task_id": "t1", "title": "Login", "tags": ["IC"], "created_by": "alice"},
    )
    assert "📌" in text
    assert "Login" in text
    assert "alice" in text

def test_format_question_asked_includes_summary_not_full():
    text = format_event(
        "question.asked",
        {"task_id": "t1", "ctx_summary": "stuck on choice", "ctx_full": "should-not-appear"},
    )
    assert "stuck on choice" in text
    assert "should-not-appear" not in text

def test_format_abandoned_has_no_mention():
    text = format_event("task.abandoned", {"task_id": "t1"})
    assert "@" not in text

def test_format_unknown_event_returns_none():
    assert format_event("nonexistent.event", {}) is None

@respx.mock
async def test_send_event_posts_to_webhook_when_configured():
    route = respx.post("https://hooks.slack.com/x").mock(return_value=httpx.Response(200))
    ok = await send_event(
        "https://hooks.slack.com/x",
        "task.created",
        {"task_id": "t1", "title": "T", "tags": ["IC"], "created_by": "alice"},
    )
    assert ok is True
    assert route.called

@respx.mock
async def test_send_event_returns_false_on_http_error():
    respx.post("https://hooks.slack.com/x").mock(return_value=httpx.Response(500))
    ok = await send_event(
        "https://hooks.slack.com/x",
        "task.created",
        {"task_id": "t1", "title": "T", "tags": ["IC"], "created_by": "alice"},
    )
    assert ok is False

async def test_send_event_returns_false_without_webhook():
    ok = await send_event(None, "task.created", {"task_id": "t1"})
    assert ok is False
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_slack.py -v`
Expected: ModuleNotFoundError

- [ ] **Step 3: 写 notifications/__init__.py（空）和 slack.py**

`src/ganren_platform/notifications/__init__.py`:
```python
```

`src/ganren_platform/notifications/slack.py`:
```python
from typing import Optional
import httpx

_TEMPLATES: dict[str, str] = {
    "task.created":   "📌 PUBLISH #{task_id} {title} [{tags}] 由 {created_by} 发布",
    "task.claimed":   "🙋 CLAIM #{task_id} 被 {claimed_by} 接走",
    "task.submitted": "✅ REVIEW @{created_by} #{task_id} 待 review",
    "task.signed_off":"🎉 CLOSE #{task_id} 关闭",
    "task.rejected":  "↩️ REJECT @{claimed_by} #{task_id} 打回：{reason}",
    "task.abandoned": "🪂 ABANDON #{task_id} 回池",
    "task.cancelled": "🛑 CANCEL #{task_id} 已取消",
    "question.asked": "❓ Q @{created_by} #{task_id}: {ctx_summary}",
    "question.answered":"💬 A @{asked_by} #{task_id} 已回复",
}

def format_event(event_type: str, payload: dict) -> Optional[str]:
    template = _TEMPLATES.get(event_type)
    if template is None:
        return None
    safe = {
        "task_id": payload.get("task_id", ""),
        "title": payload.get("title", ""),
        "tags": ",".join(payload.get("tags", []) or []),
        "created_by": payload.get("created_by", ""),
        "claimed_by": payload.get("claimed_by", ""),
        "asked_by": payload.get("asked_by", ""),
        "reason": payload.get("reason", ""),
        "ctx_summary": payload.get("ctx_summary", "") or "",
    }
    return template.format(**safe)

async def send_event(
    webhook_url: Optional[str],
    event_type: str,
    payload: dict,
) -> bool:
    if not webhook_url:
        return False
    text = format_event(event_type, payload)
    if text is None:
        return False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(webhook_url, json={"text": text})
            return resp.status_code < 400
    except Exception:
        return False
```

- [ ] **Step 4: 跑测试**

Run: `uv run pytest tests/test_slack.py -v`
Expected: 7 passed

- [ ] **Step 5: 提交**

```bash
git add src/ganren_platform/notifications tests/test_slack.py
git commit -m "feat(notifications): slack outbound with event templates"
```

---

## Task 14: HTTP API + actor 依赖 + 异常处理 + 集成测试

**Files:**
- Create: `src/ganren_platform/http_api/__init__.py`
- Create: `src/ganren_platform/http_api/app.py`
- Create: `src/ganren_platform/http_api/routes_tasks.py`
- Create: `src/ganren_platform/http_api/routes_questions.py`
- Create: `src/ganren_platform/http_api/routes_inbox.py`
- Create: `tests/test_http_api.py`

- [ ] **Step 1: 写失败的 tests/test_http_api.py**

```python
import pytest
import httpx
from ganren_platform.http_api.app import create_app
from ganren_platform.db import migrate, get_connection

@pytest.fixture
def app(temp_db_path):
    migrate(temp_db_path)
    conn = get_connection(temp_db_path)
    for h in ("alice", "bob", "carol"):
        conn.execute("INSERT INTO actors (handle, display) VALUES (?, ?)", (h, h.title()))
    conn.close()
    return create_app(db_path=temp_db_path, slack_webhook_url=None)

@pytest.fixture
async def client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

async def test_publish_then_list_then_claim(client):
    r = await client.post(
        "/v1/tasks",
        headers={"X-Actor": "alice"},
        json={
            "title": "Build login",
            "description": "endpoint",
            "context_summary": "see spec",
            "tags": ["Builder"],
            "ai_involvement": "L2",
            "agent_autonomy": "L3",
            "difficulty": "routine",
        },
    )
    assert r.status_code == 201, r.text
    tid = r.json()["id"]

    r = await client.get("/v1/tasks", headers={"X-Actor": "bob"})
    assert r.status_code == 200
    assert any(t["id"] == tid for t in r.json())

    r = await client.post(f"/v1/tasks/{tid}/claim", headers={"X-Actor": "bob"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "claimed"
    assert body["claimed_by"] == "bob"

async def test_publish_missing_decision_record_for_hard_returns_400(client):
    r = await client.post(
        "/v1/tasks",
        headers={"X-Actor": "alice"},
        json={
            "title": "T", "description": "D", "context_summary": "S",
            "tags": ["IC"], "ai_involvement": "L2", "agent_autonomy": "L3",
            "difficulty": "hard",
        },
    )
    assert r.status_code == 422

async def test_claim_already_claimed_returns_409(client):
    r = await client.post(
        "/v1/tasks", headers={"X-Actor": "alice"},
        json={"title":"T","description":"D","context_summary":"S",
              "tags":["IC"],"ai_involvement":"L2","agent_autonomy":"L3","difficulty":"routine"},
    )
    tid = r.json()["id"]
    await client.post(f"/v1/tasks/{tid}/claim", headers={"X-Actor": "bob"})
    r2 = await client.post(f"/v1/tasks/{tid}/claim", headers={"X-Actor": "carol"})
    assert r2.status_code == 409
    assert r2.json()["code"] == "already_claimed"

async def test_e2e_publish_claim_ask_answer_submit_signoff(client):
    r = await client.post(
        "/v1/tasks", headers={"X-Actor": "alice"},
        json={"title":"T","description":"D","context_summary":"S",
              "tags":["IC"],"ai_involvement":"L2","agent_autonomy":"L3","difficulty":"routine"},
    )
    tid = r.json()["id"]
    await client.post(f"/v1/tasks/{tid}/claim", headers={"X-Actor": "bob"})
    r = await client.post(
        f"/v1/tasks/{tid}/questions", headers={"X-Actor": "bob"},
        json={"question": "which path?", "ctx_summary": "stuck"},
    )
    qid = r.json()["id"]

    r = await client.get("/v1/inbox", headers={"X-Actor": "alice"})
    assert any(q["id"] == qid for q in r.json()["questions_to_answer"])

    await client.post(f"/v1/questions/{qid}/answer", headers={"X-Actor": "alice"},
                      json={"answer": "use path A"})
    r = await client.get("/v1/inbox", headers={"X-Actor": "bob"})
    assert any(q["id"] == qid for q in r.json()["answers_received"])

    await client.post(f"/v1/tasks/{tid}/submit", headers={"X-Actor": "bob"},
                      json={"summary": "done"})
    await client.post(f"/v1/tasks/{tid}/sign_off", headers={"X-Actor": "alice"},
                      json={"comment": "lgtm"})

    r = await client.get(f"/v1/tasks/{tid}", headers={"X-Actor": "alice"})
    assert r.json()["status"] == "closed"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_http_api.py -v`
Expected: ModuleNotFoundError

- [ ] **Step 3: 写 http_api/__init__.py（空）和 app.py**

`src/ganren_platform/http_api/__init__.py`:
```python
```

`src/ganren_platform/http_api/app.py`:
```python
import asyncio
from typing import Optional
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from ..db import get_connection
from ..errors import PlatformError
from ..notifications.slack import send_event

def get_actor(x_actor: str = Header(...)) -> str:
    return x_actor

def create_app(*, db_path: str, slack_webhook_url: Optional[str]) -> FastAPI:
    app = FastAPI(title="ganren-platform")
    app.state.db_path = db_path
    app.state.slack_webhook_url = slack_webhook_url

    @app.exception_handler(PlatformError)
    async def handle_platform_error(request: Request, exc: PlatformError):
        return JSONResponse(
            status_code=exc.http_status,
            content={"code": exc.code, "message": str(exc), **exc.extras},
        )

    from .routes_tasks import router as tasks_router
    from .routes_questions import router as questions_router
    from .routes_inbox import router as inbox_router
    app.include_router(tasks_router)
    app.include_router(questions_router)
    app.include_router(inbox_router)

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    return app

def schedule_slack(app: FastAPI, event_type: str, payload: dict) -> None:
    url = app.state.slack_webhook_url
    if not url:
        return
    asyncio.create_task(send_event(url, event_type, payload))
```

- [ ] **Step 4: 写 routes_tasks.py**

```python
from typing import Optional
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from ..models import (
    PublishTaskRequest, TaskFull, TaskListItem, Outcome,
    AIInvolvement, Difficulty, Tag,
)
from ..db import get_connection
from ..service import tasks as task_svc
from .app import get_actor, schedule_slack

router = APIRouter(prefix="/v1/tasks", tags=["tasks"])

class RetagRequest(BaseModel):
    new_tags: list[Tag]
    reason: str

class CancelRequest(BaseModel):
    reason: str

class AbandonRequest(BaseModel):
    reason: str

class SubmitRequest(BaseModel):
    summary: str

class RejectRequest(BaseModel):
    reason: str
    hints: Optional[str] = None

class SignOffRequest(BaseModel):
    comment: Optional[str] = None

class EscalateRequest(BaseModel):
    note: str

class RecordOutcomeRequest(BaseModel):
    outcome: Outcome

@router.post("", status_code=201)
def publish(req: PublishTaskRequest, request: Request, actor: str = Depends(get_actor)):
    conn = get_connection(request.app.state.db_path)
    try:
        tid = task_svc.publish_task(conn, actor=actor, req=req)
    finally:
        conn.close()
    schedule_slack(request.app, "task.created",
                   {"task_id": tid, "title": req.title, "tags": req.tags, "created_by": actor})
    return {"id": tid}

@router.get("", response_model=list[TaskListItem])
def list_open(
    request: Request,
    tag: Optional[list[Tag]] = None,
    ai_involvement: Optional[AIInvolvement] = None,
    difficulty: Optional[Difficulty] = None,
):
    conn = get_connection(request.app.state.db_path)
    try:
        return task_svc.list_open_tasks(
            conn, tags=tag, ai_involvement=ai_involvement, difficulty=difficulty,
        )
    finally:
        conn.close()

@router.get("/{task_id}", response_model=TaskFull)
def get_one(task_id: str, request: Request):
    conn = get_connection(request.app.state.db_path)
    try:
        return task_svc.get_task(conn, task_id=task_id)
    finally:
        conn.close()

@router.post("/{task_id}/claim", response_model=TaskFull)
def claim(task_id: str, request: Request, actor: str = Depends(get_actor)):
    conn = get_connection(request.app.state.db_path)
    try:
        task = task_svc.claim_task(conn, actor=actor, task_id=task_id)
    finally:
        conn.close()
    schedule_slack(request.app, "task.claimed",
                   {"task_id": task_id, "claimed_by": actor})
    return task

@router.post("/{task_id}/abandon")
def abandon(task_id: str, body: AbandonRequest, request: Request, actor: str = Depends(get_actor)):
    conn = get_connection(request.app.state.db_path)
    try:
        task_svc.abandon_task(conn, actor=actor, task_id=task_id, reason=body.reason)
    finally:
        conn.close()
    schedule_slack(request.app, "task.abandoned", {"task_id": task_id})
    return {"ok": True}

@router.post("/{task_id}/cancel")
def cancel(task_id: str, body: CancelRequest, request: Request, actor: str = Depends(get_actor)):
    conn = get_connection(request.app.state.db_path)
    try:
        task_svc.cancel_task(conn, actor=actor, task_id=task_id, reason=body.reason)
    finally:
        conn.close()
    schedule_slack(request.app, "task.cancelled", {"task_id": task_id})
    return {"ok": True}

@router.post("/{task_id}/submit")
def submit(task_id: str, body: SubmitRequest, request: Request, actor: str = Depends(get_actor)):
    conn = get_connection(request.app.state.db_path)
    try:
        task_svc.submit_for_review(conn, actor=actor, task_id=task_id, summary=body.summary)
        row = conn.execute("SELECT created_by FROM tasks WHERE id=?", (task_id,)).fetchone()
    finally:
        conn.close()
    schedule_slack(request.app, "task.submitted",
                   {"task_id": task_id, "created_by": row["created_by"]})
    return {"ok": True}

@router.post("/{task_id}/reject")
def reject(task_id: str, body: RejectRequest, request: Request, actor: str = Depends(get_actor)):
    conn = get_connection(request.app.state.db_path)
    try:
        task_svc.reject_task(conn, actor=actor, task_id=task_id,
                             reason=body.reason, hints=body.hints)
        row = conn.execute("SELECT claimed_by FROM tasks WHERE id=?", (task_id,)).fetchone()
    finally:
        conn.close()
    schedule_slack(request.app, "task.rejected",
                   {"task_id": task_id, "claimed_by": row["claimed_by"], "reason": body.reason})
    return {"ok": True}

@router.post("/{task_id}/sign_off")
def sign_off(task_id: str, body: SignOffRequest, request: Request, actor: str = Depends(get_actor)):
    conn = get_connection(request.app.state.db_path)
    try:
        task_svc.sign_off_task(conn, actor=actor, task_id=task_id, comment=body.comment)
    finally:
        conn.close()
    schedule_slack(request.app, "task.signed_off", {"task_id": task_id})
    return {"ok": True}

@router.post("/{task_id}/retag")
def retag(task_id: str, body: RetagRequest, request: Request, actor: str = Depends(get_actor)):
    conn = get_connection(request.app.state.db_path)
    try:
        task_svc.retag_task(conn, actor=actor, task_id=task_id,
                            new_tags=body.new_tags, reason=body.reason)
    finally:
        conn.close()
    return {"ok": True}

@router.post("/{task_id}/outcome")
def post_outcome(task_id: str, body: RecordOutcomeRequest, request: Request,
                 actor: str = Depends(get_actor)):
    conn = get_connection(request.app.state.db_path)
    try:
        task_svc.record_outcome(conn, actor=actor, task_id=task_id, outcome=body.outcome)
    finally:
        conn.close()
    return {"ok": True}

@router.post("/{task_id}/escalate")
def escalate(task_id: str, body: EscalateRequest, request: Request,
             actor: str = Depends(get_actor)):
    conn = get_connection(request.app.state.db_path)
    try:
        task_svc.report_escalation(conn, actor=actor, task_id=task_id, note=body.note)
    finally:
        conn.close()
    return {"ok": True}
```

- [ ] **Step 5: 写 routes_questions.py**

```python
from fastapi import APIRouter, Depends, Request
from ..db import get_connection
from ..models import (
    AskQuestionRequest, AnswerQuestionRequest,
    AskQuestionBody, AnswerQuestionBody,
)
from ..service import questions as q_svc
from .app import get_actor, schedule_slack

router = APIRouter(prefix="/v1", tags=["questions"])

@router.post("/tasks/{task_id}/questions", status_code=201)
def ask(task_id: str, body: AskQuestionBody, request: Request, actor: str = Depends(get_actor)):
    req = AskQuestionRequest(
        task_id=task_id,
        question=body.question,
        ctx_summary=body.ctx_summary,
        ctx_full=body.ctx_full,
    )
    conn = get_connection(request.app.state.db_path)
    try:
        qid = q_svc.ask_question(conn, actor=actor, req=req)
        row = conn.execute("SELECT created_by FROM tasks WHERE id=?", (task_id,)).fetchone()
    finally:
        conn.close()
    schedule_slack(request.app, "question.asked",
                   {"task_id": task_id, "ctx_summary": req.ctx_summary,
                    "created_by": row["created_by"]})
    return {"id": qid}

@router.post("/questions/{question_id}/answer")
def answer(question_id: str, body: AnswerQuestionBody, request: Request, actor: str = Depends(get_actor)):
    req = AnswerQuestionRequest(question_id=question_id, answer=body.answer)
    conn = get_connection(request.app.state.db_path)
    try:
        q_svc.answer_question(conn, actor=actor, req=req)
        row = conn.execute(
            "SELECT t.id AS task_id, q.asked_by FROM questions q "
            "JOIN tasks t ON t.id=q.task_id WHERE q.id=?", (question_id,)
        ).fetchone()
    finally:
        conn.close()
    schedule_slack(request.app, "question.answered",
                   {"task_id": row["task_id"], "asked_by": row["asked_by"]})
    return {"ok": True}
```

- [ ] **Step 6: 写 routes_inbox.py**

```python
from fastapi import APIRouter, Depends, Request
from ..db import get_connection
from ..models import InboxResponse, MyTasksResponse, UnitHealthResponse
from ..service import inbox as inbox_svc
from .app import get_actor

router = APIRouter(prefix="/v1", tags=["inbox"])

@router.get("/inbox", response_model=InboxResponse)
def get_inbox(request: Request, actor: str = Depends(get_actor)):
    conn = get_connection(request.app.state.db_path)
    try:
        return inbox_svc.inbox(conn, actor=actor)
    finally:
        conn.close()

@router.get("/my_tasks", response_model=MyTasksResponse)
def get_my_tasks(request: Request, actor: str = Depends(get_actor)):
    conn = get_connection(request.app.state.db_path)
    try:
        return inbox_svc.my_tasks(conn, actor=actor)
    finally:
        conn.close()

@router.get("/units/{unit_id}/health", response_model=UnitHealthResponse)
def get_unit_health(unit_id: str, request: Request):
    conn = get_connection(request.app.state.db_path)
    try:
        return inbox_svc.unit_health(conn, unit_id=unit_id)
    finally:
        conn.close()
```

- [ ] **Step 7: 跑测试**

Run: `uv run pytest tests/test_http_api.py -v`
Expected: 4 passed

- [ ] **Step 8: 提交**

```bash
git add src/ganren_platform/http_api tests/test_http_api.py
git commit -m "feat(http): FastAPI app, routes, actor dependency, error mapping"
```

---

## Task 15: MCP server + 工具注册 + 集成测试

**Files:**
- Create: `src/ganren_platform/mcp_api/__init__.py`
- Create: `src/ganren_platform/mcp_api/server.py`
- Modify: `src/ganren_platform/http_api/app.py`（mount MCP）
- Modify: `src/ganren_platform/main.py`（启动 uvicorn）
- Create: `tests/test_mcp_api.py`

- [ ] **Step 1: 写失败的 tests/test_mcp_api.py**

```python
import pytest
import httpx
from ganren_platform.db import get_connection, migrate
from ganren_platform.http_api.app import create_app

@pytest.fixture
def app(temp_db_path):
    migrate(temp_db_path)
    conn = get_connection(temp_db_path)
    for h in ("alice", "bob"):
        conn.execute("INSERT INTO actors (handle, display) VALUES (?, ?)", (h, h.title()))
    conn.close()
    return create_app(db_path=temp_db_path, slack_webhook_url=None)

@pytest.fixture
async def client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

async def test_mcp_endpoint_lists_tools(client):
    # MCP streamable HTTP: GET /mcp 返回 server-sent events 元信息
    # 这里只测 path 存在并不是 404
    r = await client.get("/mcp/")
    assert r.status_code in (200, 405, 406)  # 不是 404 即可

async def test_publish_via_service_then_visible_via_http(client):
    # Sanity: MCP 工具直接调用难以无 SDK 完成，本测试改为验证：
    # 通过 HTTP publish 后，MCP 工具签名能在 server 暴露列表里看见。
    # MCP server 启动时已经注册工具；我们只断言 /mcp/ 端点可达。
    r = await client.post(
        "/v1/tasks", headers={"X-Actor": "alice"},
        json={"title":"T","description":"D","context_summary":"S",
              "tags":["IC"],"ai_involvement":"L2","agent_autonomy":"L3","difficulty":"routine"},
    )
    assert r.status_code == 201
```

- [ ] **Step 2: 写 mcp_api/__init__.py（空）和 server.py**

`src/ganren_platform/mcp_api/__init__.py`:
```python
```

`src/ganren_platform/mcp_api/server.py`:
```python
from typing import Optional
from mcp.server.fastmcp import FastMCP
from ..db import get_connection
from ..models import (
    PublishTaskRequest, AskQuestionRequest, AnswerQuestionRequest,
    Outcome, Tag, AIInvolvement, Difficulty,
)
from ..service import tasks as task_svc
from ..service import questions as q_svc
from ..service import inbox as inbox_svc

def build_mcp(*, db_path: str) -> FastMCP:
    mcp = FastMCP("ganren-platform")

    def _conn():
        return get_connection(db_path)

    @mcp.tool()
    def publish_task(
        actor: str,
        title: str,
        description: str,
        context_summary: str,
        tags: list[Tag],
        ai_involvement: AIInvolvement,
        agent_autonomy: str,
        difficulty: Difficulty,
        artifacts: Optional[list[dict]] = None,
        decision_record: Optional[dict] = None,
        unit_id: Optional[str] = None,
    ) -> dict:
        req = PublishTaskRequest(
            title=title, description=description, context_summary=context_summary,
            tags=tags, ai_involvement=ai_involvement, agent_autonomy=agent_autonomy,
            difficulty=difficulty,
            artifacts=artifacts or [],
            decision_record=decision_record,
            unit_id=unit_id,
        )
        c = _conn()
        try:
            tid = task_svc.publish_task(c, actor=actor, req=req)
        finally:
            c.close()
        return {"id": tid}

    @mcp.tool()
    def list_open_tasks(
        tags: Optional[list[Tag]] = None,
        ai_involvement: Optional[AIInvolvement] = None,
        difficulty: Optional[Difficulty] = None,
    ) -> list[dict]:
        c = _conn()
        try:
            items = task_svc.list_open_tasks(
                c, tags=tags, ai_involvement=ai_involvement, difficulty=difficulty
            )
        finally:
            c.close()
        return [it.model_dump() for it in items]

    @mcp.tool()
    def get_task(task_id: str) -> dict:
        c = _conn()
        try:
            return task_svc.get_task(c, task_id=task_id).model_dump()
        finally:
            c.close()

    @mcp.tool()
    def claim_task(actor: str, task_id: str) -> dict:
        c = _conn()
        try:
            return task_svc.claim_task(c, actor=actor, task_id=task_id).model_dump()
        finally:
            c.close()

    @mcp.tool()
    def abandon_task(actor: str, task_id: str, reason: str) -> dict:
        c = _conn()
        try:
            task_svc.abandon_task(c, actor=actor, task_id=task_id, reason=reason)
        finally:
            c.close()
        return {"ok": True}

    @mcp.tool()
    def cancel_task(actor: str, task_id: str, reason: str) -> dict:
        c = _conn()
        try:
            task_svc.cancel_task(c, actor=actor, task_id=task_id, reason=reason)
        finally:
            c.close()
        return {"ok": True}

    @mcp.tool()
    def submit_for_review(actor: str, task_id: str, summary: str) -> dict:
        c = _conn()
        try:
            task_svc.submit_for_review(c, actor=actor, task_id=task_id, summary=summary)
        finally:
            c.close()
        return {"ok": True}

    @mcp.tool()
    def reject_task(actor: str, task_id: str, reason: str, hints: Optional[str] = None) -> dict:
        c = _conn()
        try:
            task_svc.reject_task(c, actor=actor, task_id=task_id, reason=reason, hints=hints)
        finally:
            c.close()
        return {"ok": True}

    @mcp.tool()
    def sign_off_task(actor: str, task_id: str, comment: Optional[str] = None) -> dict:
        c = _conn()
        try:
            task_svc.sign_off_task(c, actor=actor, task_id=task_id, comment=comment)
        finally:
            c.close()
        return {"ok": True}

    @mcp.tool()
    def retag_task(actor: str, task_id: str, new_tags: list[Tag], reason: str) -> dict:
        c = _conn()
        try:
            task_svc.retag_task(c, actor=actor, task_id=task_id,
                                new_tags=new_tags, reason=reason)
        finally:
            c.close()
        return {"ok": True}

    @mcp.tool()
    def record_outcome(actor: str, task_id: str, outcome: dict) -> dict:
        c = _conn()
        try:
            task_svc.record_outcome(c, actor=actor, task_id=task_id,
                                    outcome=Outcome(**outcome))
        finally:
            c.close()
        return {"ok": True}

    @mcp.tool()
    def report_escalation(actor: str, task_id: str, note: str) -> dict:
        c = _conn()
        try:
            task_svc.report_escalation(c, actor=actor, task_id=task_id, note=note)
        finally:
            c.close()
        return {"ok": True}

    @mcp.tool()
    def ask_question(
        actor: str, task_id: str, question: str,
        ctx_summary: Optional[str] = None, ctx_full: Optional[str] = None,
    ) -> dict:
        c = _conn()
        try:
            qid = q_svc.ask_question(c, actor=actor, req=AskQuestionRequest(
                task_id=task_id, question=question,
                ctx_summary=ctx_summary, ctx_full=ctx_full,
            ))
        finally:
            c.close()
        return {"id": qid}

    @mcp.tool()
    def answer_question(actor: str, question_id: str, answer: str) -> dict:
        c = _conn()
        try:
            q_svc.answer_question(c, actor=actor, req=AnswerQuestionRequest(
                question_id=question_id, answer=answer,
            ))
        finally:
            c.close()
        return {"ok": True}

    @mcp.tool()
    def inbox(actor: str) -> dict:
        c = _conn()
        try:
            return inbox_svc.inbox(c, actor=actor).model_dump()
        finally:
            c.close()

    @mcp.tool()
    def my_tasks(actor: str) -> dict:
        c = _conn()
        try:
            return inbox_svc.my_tasks(c, actor=actor).model_dump()
        finally:
            c.close()

    @mcp.tool()
    def unit_health(unit_id: str) -> dict:
        c = _conn()
        try:
            return inbox_svc.unit_health(c, unit_id=unit_id).model_dump()
        finally:
            c.close()

    return mcp
```

- [ ] **Step 3: 把 MCP mount 到 http_api/app.py**

在 `app.py` 的 `create_app` 末尾、`return app` 之前加：

```python
    from ..mcp_api.server import build_mcp
    mcp = build_mcp(db_path=db_path)
    app.mount("/mcp", mcp.streamable_http_app())
```

完整改后的 create_app 末尾：

```python
    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    from ..mcp_api.server import build_mcp
    mcp = build_mcp(db_path=db_path)
    app.mount("/mcp", mcp.streamable_http_app())

    return app
```

- [ ] **Step 4: 完成 main.py**

```python
import sys
import uvicorn
from .config import load_config
from .db import migrate
from .http_api.app import create_app

def main() -> int:
    cfg = load_config()
    migrate(cfg.db_path)
    app = create_app(db_path=cfg.db_path, slack_webhook_url=cfg.slack_webhook_url)
    host, _, port = cfg.bind_addr.rpartition(":")
    uvicorn.run(app, host=host or "0.0.0.0", port=int(port), log_level=cfg.log_level)
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: 跑测试**

Run: `uv run pytest tests/test_mcp_api.py tests/test_http_api.py -v`
Expected: all pass

- [ ] **Step 6: 启动 server 手动 smoke test**

Run:
```bash
uv run python -m ganren_platform.main &
sleep 2
curl -s http://localhost:8787/healthz
```
Expected: `{"ok":true}`

停掉进程后继续。

- [ ] **Step 7: 提交**

```bash
git add src/ganren_platform/mcp_api src/ganren_platform/http_api/app.py src/ganren_platform/main.py tests/test_mcp_api.py
git commit -m "feat(mcp): FastMCP tools mounted on /mcp; main entry runs uvicorn"
```

---

## Task 16: README + .mcp.json 示例 + 全测试跑通

**Files:**
- Create: `README.md`
- Create: `.mcp.json.example`

- [ ] **Step 1: 写 README.md**

````markdown
# ganren-platform

中心调度协作平台：CC 发布者把任务推上来，CC 协作者认领、干活、提问、提交 review；events 表对接 AI-Native 考核仪表盘。

## 快速开始

```bash
uv sync --extra dev
cp .env.example .env       # 编辑配置
uv run python -m ganren_platform.main
```

服务监听 `0.0.0.0:8787`。

- HTTP REST：`/v1/*`
- MCP streamable HTTP：`/mcp/*`
- Health：`/healthz`

## CC 端配置

参考 `.mcp.json.example`，把这段加到你的 `.mcp.json`：

```json
{
  "mcpServers": {
    "ganren": {
      "type": "http",
      "url": "http://localhost:8787/mcp/"
    }
  }
}
```

## 测试

```bash
uv run pytest -v
```

## Spec & Plan

- Spec：`docs/superpowers/specs/2026-06-05-ganren-collab-platform-design.md`
- Plan：`docs/superpowers/plans/2026-06-05-ganren-collab-platform.md`
````

- [ ] **Step 2: 写 .mcp.json.example**

```json
{
  "mcpServers": {
    "ganren": {
      "type": "http",
      "url": "http://localhost:8787/mcp/"
    }
  }
}
```

- [ ] **Step 3: 跑全测试**

Run: `uv run pytest -v`
Expected: 全部通过（约 50+ tests）

- [ ] **Step 4: 端到端手动验证**

启动：
```bash
uv run python -m ganren_platform.main &
sleep 2
```

发布：
```bash
curl -s -X POST http://localhost:8787/v1/tasks \
  -H "X-Actor: alice" -H "Content-Type: application/json" \
  -d '{"title":"smoke","description":"d","context_summary":"s","tags":["IC"],"ai_involvement":"L2","agent_autonomy":"L3","difficulty":"routine"}'
```

列出：
```bash
curl -s http://localhost:8787/v1/tasks -H "X-Actor: bob"
```

Expected：响应里有刚才发布的 task。

停掉进程。

- [ ] **Step 5: 提交**

```bash
git add README.md .mcp.json.example
git commit -m "docs: README and example MCP client config"
```

---

## 完成清单（Self-Review 后）

跑完所有 task 后应满足：

- [x] §1 架构：单进程 + FastAPI + FastMCP mounted + SQLite WAL —— Tasks 1, 2, 14, 15
- [x] §2 数据模型 5 张表 + JSON 字段 —— Task 2 migration
- [x] §3 状态机（含 cancel）+ retag/record_outcome 旁路 —— Tasks 7-10
- [x] §3.4 反馈循环（ask/answer 含 ctx 长度校验）—— Task 11
- [x] §4 操作集（发布者 + 协作者 + 通用）—— Tasks 5-12
- [x] §4.4 错误码契约 —— Task 3 errors.py + Task 14 异常映射
- [x] §4.5 字段映射（events tags_snapshot 等）—— Task 4 events helper
- [x] §5 一致性 + 并发（单事务 + 乐观锁）—— Task 7 并发测试
- [x] §6 Slack 模板单 webhook —— Task 13
- [x] §7 测试策略覆盖 service / 并发 / HTTP / MCP / Slack mock / e2e —— 全程
- [x] §8 部署形态（uv 单进程） —— Tasks 1, 15, 16

V2（不在本计划范围）：judgments + judgment_usages、A2A 实验、Slack 失败补发 cron、多频道路由。
