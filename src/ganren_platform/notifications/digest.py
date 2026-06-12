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

from .slack import post_text


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
