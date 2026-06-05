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
