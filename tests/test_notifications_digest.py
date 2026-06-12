from datetime import date, datetime, timezone, timedelta
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
