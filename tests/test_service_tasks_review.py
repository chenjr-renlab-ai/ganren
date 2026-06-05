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
