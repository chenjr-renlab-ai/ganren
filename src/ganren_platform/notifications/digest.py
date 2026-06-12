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
