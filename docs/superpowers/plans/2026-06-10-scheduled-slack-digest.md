# V2 #4 · 定时 Slack 日报 + 新任务池快照 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 ganren 平台进程内集成 apscheduler，工作日早 10:00 + 晚 18:00 推送等宽表格式日报；publish_task 完成后追加一条任务池快照消息；全程 fail-safe + 内存级 60s 节流。

**Architecture:** 单进程 Python 平台内加 `apscheduler.BackgroundScheduler`，启动时附带启动；新增 `notifications/digest.py` 渲染纯函数 + `notifications/scheduler.py` 调度封装。Slack 推送复用 `slack.py` 重构出的 `post_text` 通用函数。

**Tech Stack:** Python 3.12、apscheduler>=3.10、freezegun（dev only）、现有 httpx 0.27 / pytest 8.3 / respx 0.21。

**Spec reference:** `docs/superpowers/specs/2026-06-10-scheduled-slack-digest-design.md`

---

## 文件结构

```
src/ganren_platform/
├── config.py                       # 改：加 7 个新字段
├── main.py                         # 改：启动时启 scheduler
├── notifications/
│   ├── slack.py                    # 改：重构出通用 post_text(url, text)
│   ├── digest.py                   # 新：渲染日报 + 池快照 + 节流
│   └── scheduler.py                # 新：apscheduler 包装
└── service/tasks.py                # 改：publish_task 末尾调 push_publish_snapshot

tests/
├── test_notifications_digest.py    # 新：digest 单测
├── test_notifications_scheduler.py # 新：scheduler 装配 + cron 校验
└── test_v2_digest_e2e.py           # 新：发布 → 2 条 Slack 端到端
```

设计原则：
- `digest.py` 前 3 个函数是纯函数（无 IO，喂 conn 出 str），后 2 个是 IO（推送 + 节流）
- `scheduler.py` 不知道 digest 内部，只调 `push_morning_digest()` / `push_evening_digest()` 两个入口
- service 层只新增**一行**调用，不引入业务逻辑泄漏

---

## Task 1: 配置升级 + 依赖

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/ganren_platform/config.py`
- Modify: `.env.example`
- Create: `tests/test_v2_config.py`

- [ ] **Step 1: 写失败的 tests/test_v2_config.py**

```python
import os
from ganren_platform.config import load_config

def test_load_config_with_v2_defaults(monkeypatch):
    monkeypatch.delenv("SCHEDULER_ENABLED", raising=False)
    monkeypatch.delenv("MORNING_DIGEST_CRON", raising=False)
    monkeypatch.delenv("EVENING_DIGEST_CRON", raising=False)
    monkeypatch.delenv("SCHEDULER_TZ", raising=False)
    monkeypatch.delenv("PUBLISH_INCLUDES_SNAPSHOT", raising=False)
    monkeypatch.delenv("SNAPSHOT_MAX", raising=False)
    monkeypatch.delenv("SLACK_DIGEST_WEBHOOK", raising=False)
    cfg = load_config()
    assert cfg.scheduler_enabled is True
    assert cfg.scheduler_tz == "Asia/Shanghai"
    assert cfg.morning_digest_cron == "0 10 * * MON-FRI"
    assert cfg.evening_digest_cron == "0 18 * * MON-FRI"
    assert cfg.slack_digest_webhook is None
    assert cfg.publish_includes_snapshot is True
    assert cfg.snapshot_max == 50

def test_load_config_with_v2_overrides(monkeypatch):
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")
    monkeypatch.setenv("SCHEDULER_TZ", "UTC")
    monkeypatch.setenv("SNAPSHOT_MAX", "100")
    monkeypatch.setenv("SLACK_DIGEST_WEBHOOK", "https://hooks.slack.com/A/B/C")
    cfg = load_config()
    assert cfg.scheduler_enabled is False
    assert cfg.scheduler_tz == "UTC"
    assert cfg.snapshot_max == 100
    assert cfg.slack_digest_webhook == "https://hooks.slack.com/A/B/C"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_v2_config.py -v`
Expected: AttributeError on cfg.scheduler_enabled

- [ ] **Step 3: 更新 pyproject.toml 加依赖**

把 dependencies 块的 `dependencies` 列表改成：

```toml
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "mcp[cli]>=1.2",
    "pydantic>=2.9",
    "python-ulid>=3.0",
    "httpx>=0.27",
    "python-dotenv>=1.0",
    "apscheduler>=3.10",
]
```

dev 块改成：

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "respx>=0.21",
    "freezegun>=1.5",
]
```

跑 `uv sync --extra dev` 拉新依赖。

- [ ] **Step 4: 改 config.py 加 7 个字段**

完整新版 `src/ganren_platform/config.py`：

```python
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Config:
    bind_addr: str
    db_path: str
    slack_webhook_url: str | None
    log_level: str
    # V2 #4 新字段
    scheduler_enabled: bool
    scheduler_tz: str
    morning_digest_cron: str
    evening_digest_cron: str
    slack_digest_webhook: str | None
    publish_includes_snapshot: bool
    snapshot_max: int


def load_config() -> Config:
    return Config(
        bind_addr=os.environ.get("BIND_ADDR", "0.0.0.0:8787"),
        db_path=os.environ.get("GANREN_DB_PATH", "./data/ganren.db"),
        slack_webhook_url=os.environ.get("SLACK_WEBHOOK_URL") or None,
        log_level=os.environ.get("LOG_LEVEL", "info"),
        scheduler_enabled=_bool(os.environ.get("SCHEDULER_ENABLED"), True),
        scheduler_tz=os.environ.get("SCHEDULER_TZ", "Asia/Shanghai"),
        morning_digest_cron=os.environ.get("MORNING_DIGEST_CRON", "0 10 * * MON-FRI"),
        evening_digest_cron=os.environ.get("EVENING_DIGEST_CRON", "0 18 * * MON-FRI"),
        slack_digest_webhook=os.environ.get("SLACK_DIGEST_WEBHOOK") or None,
        publish_includes_snapshot=_bool(
            os.environ.get("PUBLISH_INCLUDES_SNAPSHOT"), True
        ),
        snapshot_max=int(os.environ.get("SNAPSHOT_MAX", "50")),
    )
```

- [ ] **Step 5: 更新 .env.example**

完整新版 `.env.example`：

```dotenv
BIND_ADDR=0.0.0.0:8787
GANREN_DB_PATH=./data/ganren.db
SLACK_WEBHOOK_URL=
LOG_LEVEL=info

# V2 #4 · 定时 Slack 日报 + 池快照
SCHEDULER_ENABLED=true
SCHEDULER_TZ=Asia/Shanghai
MORNING_DIGEST_CRON=0 10 * * MON-FRI
EVENING_DIGEST_CRON=0 18 * * MON-FRI
SLACK_DIGEST_WEBHOOK=
PUBLISH_INCLUDES_SNAPSHOT=true
SNAPSHOT_MAX=50
```

- [ ] **Step 6: 跑测试**

Run: `uv run pytest tests/test_v2_config.py -v`
Expected: 2 passed

- [ ] **Step 7: 提交**

```bash
git add pyproject.toml .env.example src/ganren_platform/config.py tests/test_v2_config.py
git commit -m "feat(v2-digest): 配置升级 + apscheduler/freezegun 依赖"
```

---

## Task 2: slack.py 提取 post_text 通用函数

**Files:**
- Modify: `src/ganren_platform/notifications/slack.py`
- Modify: `tests/test_slack.py`

- [ ] **Step 1: 写失败的新测试，追加到 tests/test_slack.py 末尾**

```python
@respx.mock
async def test_post_text_posts_when_url_provided():
    from ganren_platform.notifications.slack import post_text
    route = respx.post("https://hooks.slack.com/x").mock(return_value=httpx.Response(200))
    ok = await post_text("https://hooks.slack.com/x", "hello world")
    assert ok is True
    assert route.called
    assert route.calls[0].request.content == b'{"text": "hello world"}'

async def test_post_text_returns_false_without_url():
    from ganren_platform.notifications.slack import post_text
    ok = await post_text(None, "hello")
    assert ok is False

@respx.mock
async def test_post_text_returns_false_on_http_error():
    from ganren_platform.notifications.slack import post_text
    respx.post("https://hooks.slack.com/x").mock(return_value=httpx.Response(500))
    ok = await post_text("https://hooks.slack.com/x", "hello")
    assert ok is False
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_slack.py::test_post_text_posts_when_url_provided -v`
Expected: ImportError on post_text

- [ ] **Step 3: 重构 slack.py 提取 post_text**

完整新版 `src/ganren_platform/notifications/slack.py`：

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


async def post_text(webhook_url: Optional[str], text: str) -> bool:
    """通用 Slack 推送：直接发任意预格式化文本到 webhook。"""
    if not webhook_url:
        return False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(webhook_url, json={"text": text})
            return resp.status_code < 400
    except Exception:
        return False


async def send_event(
    webhook_url: Optional[str],
    event_type: str,
    payload: dict,
) -> bool:
    text = format_event(event_type, payload)
    if text is None:
        return False
    return await post_text(webhook_url, text)
```

- [ ] **Step 4: 跑所有 slack 测试**

Run: `uv run pytest tests/test_slack.py -v`
Expected: 10 passed（原 7 + 新 3）

- [ ] **Step 5: 提交**

```bash
git add src/ganren_platform/notifications/slack.py tests/test_slack.py
git commit -m "refactor(slack): 提取 post_text 通用函数，send_event 复用之"
```

---

## Task 3: state_dwell 工具函数

**Files:**
- Create: `src/ganren_platform/notifications/__init__.py` 内容不变
- Create: `src/ganren_platform/notifications/digest.py`（先只放 state_dwell）
- Create: `tests/test_notifications_digest.py`

- [ ] **Step 1: 写失败的 tests/test_notifications_digest.py**

```python
from datetime import datetime, timezone, timedelta
import sqlite3
import pytest


def _row(d: dict) -> sqlite3.Row:
    """把 dict 包成模拟的 sqlite3.Row，用于单测"""
    class FakeRow:
        def __init__(self, data): self._data = data
        def __getitem__(self, k): return self._data[k]
    return FakeRow(d)


def test_state_dwell_less_than_1h():
    from ganren_platform.notifications.digest import state_dwell
    now = datetime(2026, 6, 10, 12, 30, tzinfo=timezone.utc)
    anchor = (now - timedelta(minutes=30)).isoformat()
    row = _row({"status": "open", "created_at": anchor, "claimed_at": None, "submitted_at": None})
    assert state_dwell(row, now) == "<1h"


def test_state_dwell_hours():
    from ganren_platform.notifications.digest import state_dwell
    now = datetime(2026, 6, 10, 12, 30, tzinfo=timezone.utc)
    anchor = (now - timedelta(hours=5)).isoformat()
    row = _row({"status": "claimed", "created_at": "x", "claimed_at": anchor, "submitted_at": None})
    assert state_dwell(row, now) == "5h"


def test_state_dwell_days():
    from ganren_platform.notifications.digest import state_dwell
    now = datetime(2026, 6, 10, 12, 30, tzinfo=timezone.utc)
    anchor = (now - timedelta(days=3, hours=2)).isoformat()
    row = _row({"status": "open", "created_at": anchor, "claimed_at": None, "submitted_at": None})
    assert state_dwell(row, now) == "3d"


def test_state_dwell_awaiting_review_uses_submitted_at():
    from ganren_platform.notifications.digest import state_dwell
    now = datetime(2026, 6, 10, 12, 30, tzinfo=timezone.utc)
    anchor = (now - timedelta(hours=2)).isoformat()
    row = _row({
        "status": "awaiting_review",
        "created_at": "x", "claimed_at": "y", "submitted_at": anchor,
    })
    assert state_dwell(row, now) == "2h"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_notifications_digest.py -v`
Expected: ImportError on state_dwell

- [ ] **Step 3: 写 digest.py（只含 state_dwell + 必要 imports）**

`src/ganren_platform/notifications/digest.py`：

```python
"""V2 #4 · 定时 Slack 日报 + 任务池快照 渲染。

5 个函数：
  - state_dwell         · 工具：算单条任务在当前状态停留时长
  - previous_workday    · 工具：算上一个工作日
  - render_pool_snapshot · 纯函数：渲染未关闭任务表格
  - render_morning_digest / render_evening_digest · 纯函数：渲染完整日报
  - push_morning/evening_digest / push_publish_snapshot · IO：推送 + 节流
  - should_push         · 模块级节流
"""
from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timedelta, timezone


def state_dwell(row: sqlite3.Row, now: datetime) -> str:
    """当前状态下任务停留时长。

    open 用 created_at；claimed 用 claimed_at；awaiting_review 用 submitted_at。
    < 1h: '<1h'；< 24h: 'Xh'；>= 24h: 'Xd'。
    """
    if row["status"] == "open":
        anchor = row["created_at"]
    elif row["status"] == "claimed":
        anchor = row["claimed_at"]
    elif row["status"] == "awaiting_review":
        anchor = row["submitted_at"]
    else:
        return "-"
    delta = now - datetime.fromisoformat(anchor)
    if delta.total_seconds() < 3600:
        return "<1h"
    if delta.days >= 1:
        return f"{delta.days}d"
    return f"{int(delta.total_seconds() / 3600)}h"
```

- [ ] **Step 4: 跑测试**

Run: `uv run pytest tests/test_notifications_digest.py -v`
Expected: 4 passed

- [ ] **Step 5: 提交**

```bash
git add src/ganren_platform/notifications/digest.py tests/test_notifications_digest.py
git commit -m "feat(digest): state_dwell 工具函数"
```

---

## Task 4: previous_workday 工具函数

**Files:**
- Modify: `src/ganren_platform/notifications/digest.py`（追加）
- Modify: `tests/test_notifications_digest.py`（追加）

- [ ] **Step 1: 写失败的新测试，追加到 tests/test_notifications_digest.py**

```python
from datetime import date

def test_previous_workday_tuesday_returns_monday():
    from ganren_platform.notifications.digest import previous_workday
    # 2026-06-09 是周二
    assert previous_workday(date(2026, 6, 9)) == date(2026, 6, 8)

def test_previous_workday_friday_returns_thursday():
    from ganren_platform.notifications.digest import previous_workday
    # 2026-06-12 是周五
    assert previous_workday(date(2026, 6, 12)) == date(2026, 6, 11)

def test_previous_workday_monday_returns_previous_friday():
    from ganren_platform.notifications.digest import previous_workday
    # 2026-06-15 是周一
    assert previous_workday(date(2026, 6, 15)) == date(2026, 6, 12)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_notifications_digest.py::test_previous_workday_monday_returns_previous_friday -v`
Expected: ImportError on previous_workday

- [ ] **Step 3: 追加 previous_workday 到 digest.py**

在 `digest.py` 末尾追加：

```python
def previous_workday(today: "date") -> "date":
    """周一 → 上周五；周二-周五 → 昨天。

    cron 限定 MON-FRI 触发，所以 today 总是工作日。
    节假日不特殊处理：如果上一个日历日是节假日（无活动），
    日报里"上一个工作日摘要"会全是 0，这是可接受的。
    """
    if today.weekday() == 0:
        return today - timedelta(days=3)
    return today - timedelta(days=1)
```

同时在 digest.py 顶部 imports 加 `from datetime import date`。

完整修改后顶部 imports：

```python
from __future__ import annotations

import sqlite3
import time
from datetime import date, datetime, timedelta, timezone
```

- [ ] **Step 4: 跑测试**

Run: `uv run pytest tests/test_notifications_digest.py -v`
Expected: 7 passed（前 4 + 新 3）

- [ ] **Step 5: 提交**

```bash
git add src/ganren_platform/notifications/digest.py tests/test_notifications_digest.py
git commit -m "feat(digest): previous_workday 工具"
```

---

## Task 5: 摘要数字 count_events_in_window

**Files:**
- Modify: `src/ganren_platform/notifications/digest.py`
- Modify: `tests/test_notifications_digest.py`

- [ ] **Step 1: 写失败的新测试**

```python
def test_count_events_in_window(tmp_path):
    from ganren_platform.notifications.digest import count_events_in_window
    from ganren_platform.db import get_connection, migrate
    db = str(tmp_path / "t.db")
    migrate(db)
    conn = get_connection(db)
    # 插一个任务（events 表 FK 要求）
    conn.execute(
        "INSERT INTO tasks (id, title, description, context_summary, tags, "
        "ai_involvement, agent_autonomy, difficulty, status, created_by, created_at) "
        "VALUES ('t1','T','D','S','[\"IC\"]','L2','L3','routine','open','alice','2026-06-09T00:00:00+00:00')"
    )
    # 插 4 条事件，2 条在窗口内，2 条在窗口外
    for ts, ev_type in [
        ("2026-06-09T10:00:00+00:00", "task.created"),
        ("2026-06-09T12:00:00+00:00", "task.claimed"),
        ("2026-06-08T23:00:00+00:00", "task.created"),  # 窗口前
        ("2026-06-10T01:00:00+00:00", "task.signed_off"),  # 窗口后
    ]:
        conn.execute(
            "INSERT INTO events (id, task_id, type, actor, payload, created_at, "
            "tags_snapshot) VALUES (?, 't1', ?, 'alice', '{}', ?, '[\"IC\"]')",
            (ts.replace(":", "").replace("-", "").replace("+", "")[:26], ev_type, ts),
        )
    counts = count_events_in_window(
        conn,
        start_iso="2026-06-09T00:00:00+00:00",
        end_iso="2026-06-09T23:59:59+00:00",
    )
    assert counts == {
        "task.created": 1,
        "task.claimed": 1,
        "task.signed_off": 0,
        "task.rejected": 0,
        "question.asked": 0,
        "question.answered": 0,
    }
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_notifications_digest.py::test_count_events_in_window -v`
Expected: ImportError

- [ ] **Step 3: 追加 count_events_in_window 到 digest.py**

```python
TRACKED_EVENT_TYPES = (
    "task.created",
    "task.claimed",
    "task.signed_off",
    "task.rejected",
    "question.asked",
    "question.answered",
)


def count_events_in_window(
    conn: sqlite3.Connection,
    *,
    start_iso: str,
    end_iso: str,
) -> dict[str, int]:
    """聚合窗口内每类事件的发生次数。窗口左闭右闭。"""
    counts = {t: 0 for t in TRACKED_EVENT_TYPES}
    rows = conn.execute(
        "SELECT type, COUNT(*) c FROM events "
        "WHERE created_at >= ? AND created_at <= ? AND type IN "
        "({}) GROUP BY type".format(",".join("?" * len(TRACKED_EVENT_TYPES))),
        (start_iso, end_iso, *TRACKED_EVENT_TYPES),
    ).fetchall()
    for r in rows:
        counts[r["type"]] = r["c"]
    return counts
```

- [ ] **Step 4: 跑测试**

Run: `uv run pytest tests/test_notifications_digest.py -v`
Expected: 8 passed

- [ ] **Step 5: 提交**

```bash
git add src/ganren_platform/notifications/digest.py tests/test_notifications_digest.py
git commit -m "feat(digest): count_events_in_window 摘要聚合"
```

---

## Task 6: render_pool_snapshot 渲染未关闭任务表格

**Files:**
- Modify: `src/ganren_platform/notifications/digest.py`
- Modify: `tests/test_notifications_digest.py`

- [ ] **Step 1: 写失败的新测试**

```python
def test_render_pool_snapshot_empty(tmp_path):
    from ganren_platform.notifications.digest import render_pool_snapshot
    from ganren_platform.db import get_connection, migrate
    db = str(tmp_path / "t.db")
    migrate(db)
    conn = get_connection(db)
    now = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
    out = render_pool_snapshot(conn, now=now, max_rows=50)
    assert "0 条 active" in out

def test_render_pool_snapshot_shows_all_buckets(tmp_path):
    from ganren_platform.notifications.digest import render_pool_snapshot
    from ganren_platform.db import get_connection, migrate
    db = str(tmp_path / "t.db")
    migrate(db)
    conn = get_connection(db)
    base = "2026-06-10T08:00:00+00:00"
    # 1 open，1 claimed，1 awaiting_review
    conn.execute(
        "INSERT INTO tasks (id, title, description, context_summary, tags, "
        "ai_involvement, agent_autonomy, difficulty, status, created_by, created_at) "
        "VALUES ('t_open','open 任务','D','S','[\"IC\"]','L2','L3','routine','open','alice',?)",
        (base,),
    )
    conn.execute(
        "INSERT INTO tasks (id, title, description, context_summary, tags, "
        "ai_involvement, agent_autonomy, difficulty, status, created_by, "
        "claimed_by, claimed_at, created_at) "
        "VALUES ('t_clm','在干任务','D','S','[\"Builder\"]','L2','L3','routine','claimed','alice','bob',?,?)",
        (base, base),
    )
    conn.execute(
        "INSERT INTO tasks (id, title, description, context_summary, tags, "
        "ai_involvement, agent_autonomy, difficulty, status, created_by, "
        "claimed_by, claimed_at, submitted_at, created_at) "
        "VALUES ('t_rev','待 review','D','S','[\"IC\"]','L2','L3','routine','awaiting_review','alice','bob',?,?,?)",
        (base, base, base),
    )
    now = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
    out = render_pool_snapshot(conn, now=now, max_rows=50)
    assert "3 条 active" in out
    assert "open" in out and "在干任务" in out and "待 review" in out
    assert "bob" in out

def test_render_pool_snapshot_caps_at_max_rows(tmp_path):
    from ganren_platform.notifications.digest import render_pool_snapshot
    from ganren_platform.db import get_connection, migrate
    db = str(tmp_path / "t.db")
    migrate(db)
    conn = get_connection(db)
    base = "2026-06-10T08:00:00+00:00"
    for i in range(60):
        conn.execute(
            "INSERT INTO tasks (id, title, description, context_summary, tags, "
            "ai_involvement, agent_autonomy, difficulty, status, created_by, created_at) "
            "VALUES (?, ?, 'D','S','[\"IC\"]','L2','L3','routine','open','alice',?)",
            (f"t_{i:03d}", f"task {i}", base),
        )
    now = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
    out = render_pool_snapshot(conn, now=now, max_rows=50)
    assert "60 条 active" in out  # 真实数
    assert "还有 10 条" in out      # 省略提示
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_notifications_digest.py::test_render_pool_snapshot_empty -v`
Expected: ImportError

- [ ] **Step 3: 追加 render_pool_snapshot 到 digest.py**

```python
STATUS_LABEL = {
    "open": "🟢 open",
    "claimed": "🟡 claimed",
    "awaiting_review": "🔵 review",
}


def _short_id(task_id: str) -> str:
    """ULID 后 6 字符 + 前缀 '#t_'。"""
    return f"#t_{task_id[-6:]}"


def _truncate(s: str, width: int) -> str:
    if len(s) <= width:
        return s
    return s[: width - 3] + "..."


def _format_actor(row: sqlite3.Row) -> str:
    if row["status"] == "open":
        return "-"
    if row["status"] == "claimed":
        return row["claimed_by"] or "-"
    # awaiting_review
    return f"{row['created_by']} 等"


def render_pool_snapshot(
    conn: sqlite3.Connection,
    *,
    now: datetime,
    max_rows: int = 50,
) -> str:
    """渲染未关闭任务等宽表格。

    输出包含一行 "当前任务池（共 N 条 active）："，
    然后 ``` 围栏的等宽表格。
    超过 max_rows 时尾部追加 "... 还有 X 条（open A · claimed B · review C）"。
    """
    total = conn.execute(
        "SELECT COUNT(*) FROM tasks WHERE status IN ('open','claimed','awaiting_review')"
    ).fetchone()[0]
    rows = conn.execute(
        "SELECT * FROM tasks WHERE status IN ('open','claimed','awaiting_review') "
        "ORDER BY CASE status WHEN 'open' THEN 0 WHEN 'claimed' THEN 1 ELSE 2 END, "
        "created_at DESC LIMIT ?",
        (max_rows,),
    ).fetchall()

    header_line = f"当前任务池（共 {total} 条 active）："
    out_lines = [header_line, "```"]
    out_lines.append(
        f"{'状态':<10}{'ID':<11}{'标题':<33}{'负责人':<11}{'停留':<6}"
    )
    out_lines.append("─" * 70)
    for r in rows:
        out_lines.append(
            f"{STATUS_LABEL[r['status']]:<10}"
            f"{_short_id(r['id']):<11}"
            f"{_truncate(r['title'], 32):<33}"
            f"{_truncate(_format_actor(r), 10):<11}"
            f"{state_dwell(r, now):<6}"
        )

    if total > max_rows:
        bucket_counts = conn.execute(
            "SELECT status, COUNT(*) c FROM tasks "
            "WHERE status IN ('open','claimed','awaiting_review') GROUP BY status"
        ).fetchall()
        bucket_map = {r["status"]: r["c"] for r in bucket_counts}
        remain = total - max_rows
        out_lines.append(
            f"... 还有 {remain} 条（open {bucket_map.get('open', 0)} · "
            f"claimed {bucket_map.get('claimed', 0)} · "
            f"review {bucket_map.get('awaiting_review', 0)}）"
        )
    out_lines.append("```")
    return "\n".join(out_lines)
```

- [ ] **Step 4: 跑测试**

Run: `uv run pytest tests/test_notifications_digest.py -v`
Expected: 11 passed

- [ ] **Step 5: 提交**

```bash
git add src/ganren_platform/notifications/digest.py tests/test_notifications_digest.py
git commit -m "feat(digest): render_pool_snapshot 等宽表格 + 上限保护"
```

---

## Task 7: render_morning_digest / render_evening_digest

**Files:**
- Modify: `src/ganren_platform/notifications/digest.py`
- Modify: `tests/test_notifications_digest.py`

- [ ] **Step 1: 写失败的新测试**

```python
def test_render_morning_digest_contains_window_and_pool(tmp_path):
    from ganren_platform.notifications.digest import render_morning_digest
    from ganren_platform.db import get_connection, migrate
    db = str(tmp_path / "t.db")
    migrate(db)
    conn = get_connection(db)
    conn.execute(
        "INSERT INTO tasks (id, title, description, context_summary, tags, "
        "ai_involvement, agent_autonomy, difficulty, status, created_by, created_at) "
        "VALUES ('t1','T','D','S','[\"IC\"]','L2','L3','routine','open','alice','2026-06-09T10:00:00+00:00')"
    )
    out = render_morning_digest(conn, today=date(2026, 6, 10))
    assert "🌅" in out
    assert "ganren 日报" in out
    assert "2026-06-10" in out
    assert "2026-06-09" in out  # 前一个工作日
    assert "1 条 active" in out

def test_render_evening_digest_contains_today_window(tmp_path):
    from ganren_platform.notifications.digest import render_evening_digest
    from ganren_platform.db import get_connection, migrate
    db = str(tmp_path / "t.db")
    migrate(db)
    conn = get_connection(db)
    out = render_evening_digest(conn, today=date(2026, 6, 10))
    assert "🌆" in out
    assert "晚 18:00" in out
    assert "今日（00:00 至 18:00）" in out
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_notifications_digest.py::test_render_morning_digest_contains_window_and_pool -v`
Expected: ImportError

- [ ] **Step 3: 追加 render_morning_digest / render_evening_digest 到 digest.py**

```python
def _format_summary(counts: dict[str, int]) -> str:
    return (
        "```\n"
        f"📌 发布  🙋 认领  🎉 关闭  ↩ 打回  ❓ 提问  💬 回答\n"
        f"  {counts['task.created']:^5}  "
        f"{counts['task.claimed']:^5}  "
        f"{counts['task.signed_off']:^5}  "
        f"{counts['task.rejected']:^5}  "
        f"{counts['question.asked']:^5}  "
        f"{counts['question.answered']:^5}\n"
        "```"
    )


def render_morning_digest(conn: sqlite3.Connection, *, today: date) -> str:
    yday = previous_workday(today)
    start = datetime(yday.year, yday.month, yday.day, 0, 0, 0, tzinfo=timezone.utc).isoformat()
    end = datetime(yday.year, yday.month, yday.day, 23, 59, 59, tzinfo=timezone.utc).isoformat()
    counts = count_events_in_window(conn, start_iso=start, end_iso=end)

    now = datetime.now(timezone.utc)
    pool = render_pool_snapshot(conn, now=now, max_rows=50)

    return (
        f"🌅 ganren 日报 · {today.isoformat()} 早 10:00\n"
        f"上一个工作日（{yday.isoformat()}）摘要：\n"
        f"{_format_summary(counts)}\n"
        f"{pool}"
    )


def render_evening_digest(conn: sqlite3.Connection, *, today: date) -> str:
    start = datetime(today.year, today.month, today.day, 0, 0, 0, tzinfo=timezone.utc).isoformat()
    end = datetime.now(timezone.utc).isoformat()
    counts = count_events_in_window(conn, start_iso=start, end_iso=end)

    now = datetime.now(timezone.utc)
    pool = render_pool_snapshot(conn, now=now, max_rows=50)

    return (
        f"🌆 ganren 日报 · {today.isoformat()} 晚 18:00\n"
        f"今日（00:00 至 18:00）摘要：\n"
        f"{_format_summary(counts)}\n"
        f"{pool}"
    )
```

- [ ] **Step 4: 跑测试**

Run: `uv run pytest tests/test_notifications_digest.py -v`
Expected: 13 passed

- [ ] **Step 5: 提交**

```bash
git add src/ganren_platform/notifications/digest.py tests/test_notifications_digest.py
git commit -m "feat(digest): render_morning_digest / render_evening_digest"
```

---

## Task 8: should_push 节流

**Files:**
- Modify: `src/ganren_platform/notifications/digest.py`
- Modify: `tests/test_notifications_digest.py`

- [ ] **Step 1: 写失败的新测试**

```python
def test_should_push_first_call_returns_true(monkeypatch):
    from ganren_platform.notifications import digest
    # 重置模块状态
    digest._last_push.clear()
    monkeypatch.setattr(digest.time, "time", lambda: 1000.0)
    assert digest.should_push("kind_a") is True

def test_should_push_within_window_returns_false(monkeypatch):
    from ganren_platform.notifications import digest
    digest._last_push.clear()
    monkeypatch.setattr(digest.time, "time", lambda: 1000.0)
    digest.should_push("k")
    # 30s 后再调
    monkeypatch.setattr(digest.time, "time", lambda: 1030.0)
    assert digest.should_push("k") is False

def test_should_push_after_window_returns_true(monkeypatch):
    from ganren_platform.notifications import digest
    digest._last_push.clear()
    monkeypatch.setattr(digest.time, "time", lambda: 1000.0)
    digest.should_push("k")
    # 70s 后再调
    monkeypatch.setattr(digest.time, "time", lambda: 1070.0)
    assert digest.should_push("k") is True

def test_should_push_different_kinds_independent(monkeypatch):
    from ganren_platform.notifications import digest
    digest._last_push.clear()
    monkeypatch.setattr(digest.time, "time", lambda: 1000.0)
    digest.should_push("k1")
    assert digest.should_push("k2") is True
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_notifications_digest.py::test_should_push_first_call_returns_true -v`
Expected: AttributeError on _last_push or should_push

- [ ] **Step 3: 追加 should_push 到 digest.py**

```python
_last_push: dict[str, float] = {}
_THROTTLE_SECONDS = 60


def should_push(kind: str) -> bool:
    """模块级节流：同 kind 在 _THROTTLE_SECONDS 内不重复推。

    kind 取值：'morning_digest' / 'evening_digest' / 'publish_snapshot'。
    实时事件推送（slack.send_event）不走节流。
    """
    now = time.time()
    last = _last_push.get(kind, 0)
    if now - last < _THROTTLE_SECONDS:
        return False
    _last_push[kind] = now
    return True
```

- [ ] **Step 4: 跑测试**

Run: `uv run pytest tests/test_notifications_digest.py -v`
Expected: 17 passed

- [ ] **Step 5: 提交**

```bash
git add src/ganren_platform/notifications/digest.py tests/test_notifications_digest.py
git commit -m "feat(digest): should_push 模块级 60s 节流"
```

---

## Task 9: 推送函数 push_morning/evening_digest + push_publish_snapshot

**Files:**
- Modify: `src/ganren_platform/notifications/digest.py`
- Modify: `tests/test_notifications_digest.py`

- [ ] **Step 1: 写失败的新测试**

```python
import respx
import httpx

@respx.mock
async def test_push_morning_digest_posts_to_webhook(tmp_path):
    from ganren_platform.notifications import digest
    from ganren_platform.db import get_connection, migrate
    digest._last_push.clear()
    db = str(tmp_path / "t.db")
    migrate(db)
    conn = get_connection(db)
    route = respx.post("https://hooks.slack.com/morning").mock(
        return_value=httpx.Response(200)
    )
    ok = await digest.push_morning_digest(
        conn,
        webhook_url="https://hooks.slack.com/morning",
        today=date(2026, 6, 10),
    )
    assert ok is True
    assert route.called
    body = route.calls[0].request.content.decode("utf-8")
    assert "ganren 日报" in body
    assert "2026-06-10" in body

@respx.mock
async def test_push_throttled_within_window(tmp_path):
    from ganren_platform.notifications import digest
    from ganren_platform.db import get_connection, migrate
    digest._last_push.clear()
    db = str(tmp_path / "t.db")
    migrate(db)
    conn = get_connection(db)
    respx.post("https://hooks.slack.com/x").mock(return_value=httpx.Response(200))
    ok1 = await digest.push_morning_digest(
        conn, webhook_url="https://hooks.slack.com/x", today=date(2026, 6, 10)
    )
    ok2 = await digest.push_morning_digest(
        conn, webhook_url="https://hooks.slack.com/x", today=date(2026, 6, 10)
    )
    assert ok1 is True
    assert ok2 is False  # 节流跳过

@respx.mock
async def test_push_publish_snapshot_respects_config_off(tmp_path):
    from ganren_platform.notifications import digest
    from ganren_platform.db import get_connection, migrate
    digest._last_push.clear()
    db = str(tmp_path / "t.db")
    migrate(db)
    conn = get_connection(db)
    route = respx.post("https://hooks.slack.com/x").mock(return_value=httpx.Response(200))
    ok = await digest.push_publish_snapshot(
        conn,
        webhook_url="https://hooks.slack.com/x",
        enabled=False,
    )
    assert ok is False
    assert not route.called
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_notifications_digest.py::test_push_morning_digest_posts_to_webhook -v`
Expected: AttributeError on push_morning_digest

- [ ] **Step 3: 追加推送函数到 digest.py**

```python
from .slack import post_text


async def push_morning_digest(
    conn: sqlite3.Connection,
    *,
    webhook_url: str | None,
    today: date,
) -> bool:
    if not should_push("morning_digest"):
        return False
    try:
        text = render_morning_digest(conn, today=today)
    except Exception:
        return False
    return await post_text(webhook_url, text)


async def push_evening_digest(
    conn: sqlite3.Connection,
    *,
    webhook_url: str | None,
    today: date,
) -> bool:
    if not should_push("evening_digest"):
        return False
    try:
        text = render_evening_digest(conn, today=today)
    except Exception:
        return False
    return await post_text(webhook_url, text)


async def push_publish_snapshot(
    conn: sqlite3.Connection,
    *,
    webhook_url: str | None,
    enabled: bool = True,
) -> bool:
    if not enabled:
        return False
    if not should_push("publish_snapshot"):
        return False
    try:
        now = datetime.now(timezone.utc)
        text = render_pool_snapshot(conn, now=now, max_rows=50)
    except Exception:
        return False
    return await post_text(webhook_url, text)
```

- [ ] **Step 4: 跑测试**

Run: `uv run pytest tests/test_notifications_digest.py -v`
Expected: 20 passed

- [ ] **Step 5: 提交**

```bash
git add src/ganren_platform/notifications/digest.py tests/test_notifications_digest.py
git commit -m "feat(digest): push_*_digest / push_publish_snapshot 推送函数"
```

---

## Task 10: scheduler.py 装配

**Files:**
- Create: `src/ganren_platform/notifications/scheduler.py`
- Create: `tests/test_notifications_scheduler.py`

- [ ] **Step 1: 写失败的 tests/test_notifications_scheduler.py**

```python
import pytest
from datetime import date
from unittest.mock import AsyncMock, patch


def test_build_scheduler_returns_background_scheduler(tmp_path):
    from ganren_platform.notifications.scheduler import build_scheduler
    from ganren_platform.config import Config
    cfg = Config(
        bind_addr="x", db_path=str(tmp_path / "x.db"),
        slack_webhook_url=None, log_level="info",
        scheduler_enabled=True, scheduler_tz="UTC",
        morning_digest_cron="0 10 * * MON-FRI",
        evening_digest_cron="0 18 * * MON-FRI",
        slack_digest_webhook=None,
        publish_includes_snapshot=True, snapshot_max=50,
    )
    sched = build_scheduler(cfg)
    job_ids = {j.id for j in sched.get_jobs()}
    assert "morning_digest" in job_ids
    assert "evening_digest" in job_ids


def test_build_scheduler_invalid_cron_skips_job(tmp_path, caplog):
    from ganren_platform.notifications.scheduler import build_scheduler
    from ganren_platform.config import Config
    cfg = Config(
        bind_addr="x", db_path=str(tmp_path / "x.db"),
        slack_webhook_url=None, log_level="info",
        scheduler_enabled=True, scheduler_tz="UTC",
        morning_digest_cron="invalid cron expr",   # ← 故意坏
        evening_digest_cron="0 18 * * MON-FRI",
        slack_digest_webhook=None,
        publish_includes_snapshot=True, snapshot_max=50,
    )
    sched = build_scheduler(cfg)
    job_ids = {j.id for j in sched.get_jobs()}
    assert "morning_digest" not in job_ids
    assert "evening_digest" in job_ids


def test_start_scheduler_if_enabled_returns_none_when_disabled(tmp_path):
    from ganren_platform.notifications.scheduler import start_scheduler_if_enabled
    from ganren_platform.config import Config
    cfg = Config(
        bind_addr="x", db_path=str(tmp_path / "x.db"),
        slack_webhook_url=None, log_level="info",
        scheduler_enabled=False, scheduler_tz="UTC",
        morning_digest_cron="0 10 * * MON-FRI",
        evening_digest_cron="0 18 * * MON-FRI",
        slack_digest_webhook=None,
        publish_includes_snapshot=True, snapshot_max=50,
    )
    sched = start_scheduler_if_enabled(cfg)
    assert sched is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_notifications_scheduler.py -v`
Expected: ModuleNotFoundError

- [ ] **Step 3: 写 scheduler.py**

```python
"""apscheduler 包装：装载 morning/evening digest 两个 cron job。

fail-safe 原则：任何故障都不应阻塞 web server。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date as _date
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from ..config import Config
from ..db import get_connection
from . import digest

log = logging.getLogger(__name__)


def _parse_cron(expr: str, tz: str) -> Optional[CronTrigger]:
    try:
        return CronTrigger.from_crontab(expr, timezone=tz)
    except Exception as e:
        log.error("invalid cron expression %r: %s", expr, e)
        return None


def _make_morning_callback(db_path: str, webhook_url: Optional[str]):
    def job():
        try:
            conn = get_connection(db_path)
            try:
                asyncio.run(
                    digest.push_morning_digest(
                        conn,
                        webhook_url=webhook_url,
                        today=_date.today(),
                    )
                )
            finally:
                conn.close()
        except Exception as e:
            log.warning("morning_digest job failed: %s", e)
    return job


def _make_evening_callback(db_path: str, webhook_url: Optional[str]):
    def job():
        try:
            conn = get_connection(db_path)
            try:
                asyncio.run(
                    digest.push_evening_digest(
                        conn,
                        webhook_url=webhook_url,
                        today=_date.today(),
                    )
                )
            finally:
                conn.close()
        except Exception as e:
            log.warning("evening_digest job failed: %s", e)
    return job


def build_scheduler(cfg: Config) -> BackgroundScheduler:
    """装载 2 个 cron job。无效 cron 直接 skip 不抛。"""
    sched = BackgroundScheduler(timezone=cfg.scheduler_tz)
    digest_webhook = cfg.slack_digest_webhook or cfg.slack_webhook_url

    morning_trigger = _parse_cron(cfg.morning_digest_cron, cfg.scheduler_tz)
    if morning_trigger is not None:
        sched.add_job(
            _make_morning_callback(cfg.db_path, digest_webhook),
            trigger=morning_trigger,
            id="morning_digest",
        )

    evening_trigger = _parse_cron(cfg.evening_digest_cron, cfg.scheduler_tz)
    if evening_trigger is not None:
        sched.add_job(
            _make_evening_callback(cfg.db_path, digest_webhook),
            trigger=evening_trigger,
            id="evening_digest",
        )

    return sched


def start_scheduler_if_enabled(cfg: Config) -> Optional[BackgroundScheduler]:
    """启动入口，由 main.py 调用。返回 scheduler（用于优雅关闭）或 None。"""
    if not cfg.scheduler_enabled:
        log.info("scheduler disabled by config")
        return None
    try:
        sched = build_scheduler(cfg)
        sched.start()
        log.info("scheduler started with %d job(s)", len(sched.get_jobs()))
        return sched
    except Exception as e:
        log.error("scheduler failed to start: %s", e)
        return None
```

- [ ] **Step 4: 跑测试**

Run: `uv run pytest tests/test_notifications_scheduler.py -v`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add src/ganren_platform/notifications/scheduler.py tests/test_notifications_scheduler.py
git commit -m "feat(scheduler): apscheduler 包装 + 无效 cron 安全跳过 + fail-safe 启动"
```

---

## Task 11: main.py 集成

**Files:**
- Modify: `src/ganren_platform/main.py`

- [ ] **Step 1: 改 main.py，启 uvicorn 前先启 scheduler**

完整新版 `src/ganren_platform/main.py`：

```python
import sys
import uvicorn
from .config import load_config
from .db import migrate
from .http_api.app import create_app
from .notifications.scheduler import start_scheduler_if_enabled


def main() -> int:
    cfg = load_config()
    migrate(cfg.db_path)
    app = create_app(db_path=cfg.db_path, slack_webhook_url=cfg.slack_webhook_url)
    scheduler = start_scheduler_if_enabled(cfg)
    host, _, port = cfg.bind_addr.rpartition(":")
    try:
        uvicorn.run(app, host=host or "0.0.0.0", port=int(port), log_level=cfg.log_level)
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: 跑现有所有测试确认无回归**

Run: `uv run pytest -v`
Expected: 全部通过（V1 79 个 + V2 新增）

- [ ] **Step 3: smoke test：启平台看 scheduler 是否报错**

跑：
```bash
uv run python -m ganren_platform.main &
sleep 3
curl http://localhost:8787/healthz
```
Expected：返回 `{"ok":true}`，stderr 含 `scheduler started with 2 job(s)`

停掉进程后继续。

- [ ] **Step 4: 提交**

```bash
git add src/ganren_platform/main.py
git commit -m "feat(main): 启 uvicorn 前先启 scheduler，关闭时 wait=False 优雅停"
```

---

## Task 12: service/tasks.py publish_task 调 push_publish_snapshot

**Files:**
- Modify: `src/ganren_platform/service/tasks.py`
- Modify: `src/ganren_platform/http_api/routes_tasks.py`（如果需要传 enabled 配置）

- [ ] **Step 1: 写失败的测试，追加到 tests/test_v2_digest_e2e.py（新文件）**

```python
import pytest
import respx
import httpx
import json
from ganren_platform.http_api.app import create_app
from ganren_platform.db import migrate, get_connection


@pytest.fixture
def app(temp_db_path):
    migrate(temp_db_path)
    conn = get_connection(temp_db_path)
    for h in ("alice",):
        conn.execute("INSERT INTO actors (handle, display) VALUES (?, ?)", (h, h.title()))
    conn.close()
    return create_app(db_path=temp_db_path, slack_webhook_url="https://hooks.slack.com/x")


@pytest.fixture
async def client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@respx.mock
async def test_publish_triggers_event_then_snapshot(client):
    from ganren_platform.notifications import digest
    digest._last_push.clear()
    route = respx.post("https://hooks.slack.com/x").mock(return_value=httpx.Response(200))
    r = await client.post(
        "/v1/tasks", headers={"X-Actor": "alice"},
        json={"title":"T","description":"D","context_summary":"S",
              "tags":["IC"],"ai_involvement":"L2","agent_autonomy":"L3","difficulty":"routine"},
    )
    assert r.status_code == 201
    # 等 BackgroundTasks 执行完
    await client.get("/healthz")  # 让 event loop 转一圈
    # 至少有 2 条推送（一条 task.created + 一条 publish_snapshot）
    assert route.call_count >= 2
    bodies = [c.request.content.decode("utf-8") for c in route.calls]
    assert any("📌 PUBLISH" in b for b in bodies)
    assert any("当前任务池" in b for b in bodies)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_v2_digest_e2e.py -v`
Expected: route.call_count is 1（只有 task.created，没有 snapshot）

- [ ] **Step 3: 修改 routes_tasks.py publish 路由，在 schedule_slack 后再加一次 schedule for snapshot**

打开 `src/ganren_platform/http_api/routes_tasks.py`，找到 `publish` 函数。在 `schedule_slack(...)` 调用之后追加一个新的 background_tasks.add_task 调用 push_publish_snapshot：

完整修改：在 `publish` 函数末尾的 `schedule_slack` 调用后追加：

```python
    # V2 #4 · publish 完成后追加一条池快照消息
    from ..notifications.digest import push_publish_snapshot
    from ..config import load_config
    _cfg = load_config()
    if _cfg.publish_includes_snapshot:
        snapshot_webhook = _cfg.slack_digest_webhook or request.app.state.slack_webhook_url
        # 用一个独立 conn 拿快照，因为前面的已经 close 了
        background_tasks.add_task(
            _push_publish_snapshot_bg,
            request.app.state.db_path,
            snapshot_webhook,
        )
```

然后在文件末尾追加 helper 函数：

```python
async def _push_publish_snapshot_bg(db_path: str, webhook_url: Optional[str]):
    from ..notifications.digest import push_publish_snapshot
    conn = get_connection(db_path)
    try:
        await push_publish_snapshot(conn, webhook_url=webhook_url, enabled=True)
    finally:
        conn.close()
```

- [ ] **Step 4: 跑测试**

Run: `uv run pytest tests/test_v2_digest_e2e.py -v`
Expected: 1 passed

也跑全部测试确认无回归：
Run: `uv run pytest -v`
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add src/ganren_platform/http_api/routes_tasks.py tests/test_v2_digest_e2e.py
git commit -m "feat(http): publish_task 完成后追加池快照推送"
```

---

## Task 13: README / USAGE.md 文档同步

**Files:**
- Modify: `README.md`
- Modify: `docs/USAGE.md`

- [ ] **Step 1: 在 USAGE.md §A.6（Slack 配置）下方插入新章节 §A.6.1**

在 USAGE.md `### A.6 配置 Slack（可选但强推）` 之后，在 `### A.7 备份` 之前插入：

```markdown
### A.6.1 V2 · 定时日报与池快照

平台内置 scheduler，工作日早 10:00 + 晚 18:00 自动推送日报；新任务发布时附加任务池快照。

`.env` 新增字段（详见 `.env.example`）：

\`\`\`dotenv
SCHEDULER_ENABLED=true               # 平台启动时是否启 scheduler
SCHEDULER_TZ=Asia/Shanghai
MORNING_DIGEST_CRON=0 10 * * MON-FRI
EVENING_DIGEST_CRON=0 18 * * MON-FRI
SLACK_DIGEST_WEBHOOK=                # 留空则复用 SLACK_WEBHOOK_URL
PUBLISH_INCLUDES_SNAPSHOT=true       # publish 时是否附池快照
SNAPSHOT_MAX=50                      # 池快照单条上限
\`\`\`

特性：
- 日报格式：等宽表格，emoji 状态标签，列含 ID/标题/负责人/停留时长
- 节流：模块级 60s 窗口防止短时间重复推送
- fail-safe：scheduler 故障不阻塞 web server
- 关掉：`SCHEDULER_ENABLED=false`
```

把 `\`` 改成单个反引号 \`。

- [ ] **Step 2: README.md 在测试章节后追加一段**

打开 `README.md`，在最后加：

```markdown

## V2 已落

详见 [`docs/V2_BACKLOG.md`](docs/V2_BACKLOG.md)。第一波已实施：

- **#4 定时 Slack 日报 + 池快照** · [设计](docs/superpowers/specs/2026-06-10-scheduled-slack-digest-design.md) · [实施计划](docs/superpowers/plans/2026-06-10-scheduled-slack-digest.md)
```

- [ ] **Step 3: 提交**

```bash
git add README.md docs/USAGE.md
git commit -m "docs(v2): 同步 USAGE 与 README 关于定时日报的配置说明"
```

---

## 完成清单（self-review 后）

跑完 13 个 task 后应满足：

- [x] §1 架构：3 个新增/修改文件（digest / scheduler / main + service + http）—— Tasks 3-12
- [x] §2 7 个 .env 配置项 —— Task 1
- [x] §3.1 时间窗口（前一个工作日 + 今日）—— Tasks 4, 7
- [x] §3.2-3.4 日报和快照渲染（等宽表 + emoji + 列定义）—— Tasks 6, 7
- [x] §3.5 列宽 + 简写 —— Task 6（STATUS_LABEL）
- [x] §3.6 上限保护 —— Task 6
- [x] §4 节流 —— Task 8
- [x] §5 错误处理（fail-safe）—— Tasks 9, 10, 11
- [x] §6 测试策略全覆盖 —— Tasks 1-12
- [x] §7 依赖、配置、回滚 —— Tasks 1, 11
- [x] §8 与现有的关系（slack.send_event 不变；publish_task 末尾追加调用）—— Tasks 2, 12

不在范围（spec §9）：
- 个人级 push / watch_inbox（V2 #1，独立 spec）
- Block Kit、个人视角看板（V2 #3）
- self-register endpoint（V2 #2 服务端）
- list 去重（V2 #5）

---

## 注意事项

- **Task 1 必须最先做**：依赖 + 配置先就位，后续才能 import
- **测试纪律**：所有时间相关测试用显式注入 `now=` 参数或 monkeypatch `time.time`，不引入 freezegun 全局 patch
- **digest.py 文件长度**：完工后约 ~250 行，仍可读，不需要拆分
- **回滚**：`SCHEDULER_ENABLED=false` 即可关掉 scheduler；`PUBLISH_INCLUDES_SNAPSHOT=false` 关掉新任务快照
