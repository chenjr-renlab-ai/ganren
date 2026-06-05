import json
import pytest
from ganren_platform.service.tasks import (
    publish_task, claim_task, submit_for_review, sign_off_task,
    retag_task, record_outcome, report_escalation,
)
from ganren_platform.models import PublishTaskRequest, Outcome
from ganren_platform.errors import InvalidState, NotAllowed

def _req(tags=None):
    return PublishTaskRequest(
        title="T", description="D", context_summary="S",
        tags=tags or ["IC"], ai_involvement="L2", agent_autonomy="L3", difficulty="routine",
    )

def test_retag_by_creator_sets_override_source(conn):
    tid = publish_task(conn, actor="alice", req=_req())
    retag_task(conn, actor="alice", task_id=tid, new_tags=["Builder"], reason="cleaned scope")
    row = conn.execute("SELECT tags, tag_source FROM tasks WHERE id=?", (tid,)).fetchone()
    assert json.loads(row["tags"]) == ["Builder"]
    assert row["tag_source"] == "override"

def test_retag_by_outsider_forbidden(conn):
    tid = publish_task(conn, actor="alice", req=_req())
    with pytest.raises(NotAllowed):
        retag_task(conn, actor="bob", task_id=tid, new_tags=["Builder"], reason="x")

def test_retag_by_unit_coach_allowed(conn):
    conn.execute(
        "INSERT INTO units (id, name, type, created_at) VALUES ('u1','U','squad','now')"
    )
    conn.execute("UPDATE units SET coach_handle='carol' WHERE id='u1'")
    req = _req()
    object.__setattr__(req, "unit_id", "u1")
    tid = publish_task(conn, actor="alice", req=req)
    retag_task(conn, actor="carol", task_id=tid, new_tags=["Coach"], reason="coach reclassified")
    row = conn.execute("SELECT tags FROM tasks WHERE id=?", (tid,)).fetchone()
    assert json.loads(row["tags"]) == ["Coach"]

def test_retag_event_carries_snapshot(conn):
    tid = publish_task(conn, actor="alice", req=_req())
    retag_task(conn, actor="alice", task_id=tid, new_tags=["Builder"], reason="x")
    ev = conn.execute(
        "SELECT type, tags_snapshot FROM events WHERE task_id=? AND type='task.retagged'",
        (tid,),
    ).fetchone()
    assert json.loads(ev["tags_snapshot"]) == ["Builder"]

def test_record_outcome_only_after_closed(conn):
    tid = publish_task(conn, actor="alice", req=_req())
    with pytest.raises(InvalidState):
        record_outcome(conn, actor="alice", task_id=tid,
                       outcome=Outcome(summary="x", matched_estimate=True))

def test_record_outcome_after_signoff_persists(conn):
    tid = publish_task(conn, actor="alice", req=_req())
    claim_task(conn, actor="bob", task_id=tid)
    submit_for_review(conn, actor="bob", task_id=tid, summary="done")
    sign_off_task(conn, actor="alice", task_id=tid)
    record_outcome(conn, actor="alice", task_id=tid,
                   outcome=Outcome(summary="shipped", matched_estimate=True))
    row = conn.execute("SELECT outcome FROM tasks WHERE id=?", (tid,)).fetchone()
    assert json.loads(row["outcome"])["matched_estimate"] is True

def test_report_escalation_sets_flag(conn):
    tid = publish_task(conn, actor="alice", req=_req())
    claim_task(conn, actor="bob", task_id=tid)
    report_escalation(conn, actor="bob", task_id=tid, note="agent stuck")
    row = conn.execute("SELECT escalated FROM tasks WHERE id=?", (tid,)).fetchone()
    assert row["escalated"] == 1

def test_report_escalation_by_non_claimer_forbidden(conn):
    tid = publish_task(conn, actor="alice", req=_req())
    claim_task(conn, actor="bob", task_id=tid)
    with pytest.raises(NotAllowed):
        report_escalation(conn, actor="carol", task_id=tid, note="x")
