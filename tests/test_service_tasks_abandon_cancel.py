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
