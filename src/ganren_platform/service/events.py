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
