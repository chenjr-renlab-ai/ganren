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
