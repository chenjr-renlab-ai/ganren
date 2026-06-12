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
from datetime import date, datetime, timedelta, timezone


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


def previous_workday(today: date) -> date:
    """周一 → 上周五；周二-周五 → 昨天。

    cron 限定 MON-FRI 触发，所以 today 总是工作日。
    节假日不特殊处理：如果上一个日历日是节假日（无活动），
    日报里"上一个工作日摘要"会全是 0，这是可接受的。
    """
    if today.weekday() == 0:
        return today - timedelta(days=3)
    return today - timedelta(days=1)


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
