import json
import pytest
from ganren_platform.service.tasks import publish_task, get_task
from ganren_platform.models import PublishTaskRequest
from ganren_platform.errors import MissingDecisionRecord

def test_publish_routine_task_inserts_row_and_event(conn, routine_publish_req):
    task_id = publish_task(conn, actor="alice", req=routine_publish_req)
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    assert row["status"] == "open"
    assert row["created_by"] == "alice"
    assert row["tag_source"] == "auto"
    assert json.loads(row["tags"]) == ["Builder"]
    assert row["version"] == 0
    events = conn.execute(
        "SELECT * FROM events WHERE task_id=? ORDER BY created_at", (task_id,)
    ).fetchall()
    assert len(events) == 1
    assert events[0]["type"] == "task.created"

def test_publish_hard_task_persists_decision_record(conn, hard_publish_req):
    task_id = publish_task(conn, actor="alice", req=hard_publish_req)
    row = conn.execute("SELECT decision_record FROM tasks WHERE id=?", (task_id,)).fetchone()
    dr = json.loads(row["decision_record"])
    assert dr["chosen"] == "Auth0"
    assert dr["prob_estimate"] == 0.6

def test_get_task_returns_full_payload(conn, routine_publish_req):
    task_id = publish_task(conn, actor="alice", req=routine_publish_req)
    task = get_task(conn, task_id=task_id)
    assert task.id == task_id
    assert task.title == "Build login"
    assert task.tags == ["Builder"]
    assert task.status == "open"
    assert task.version == 0

def test_get_task_raises_when_missing(conn):
    from ganren_platform.errors import TaskNotFound
    with pytest.raises(TaskNotFound):
        get_task(conn, task_id="does-not-exist")

def test_publish_task_requires_decision_record_for_hard(conn):
    req = PublishTaskRequest(
        title="T", description="D", context_summary="S",
        tags=["IC"], ai_involvement="L2", agent_autonomy="L3", difficulty="hard",
    )
    with pytest.raises(MissingDecisionRecord) as excinfo:
        publish_task(conn, actor="alice", req=req)
    assert excinfo.value.code == "missing_decision_record"

def test_publish_task_requires_decision_record_for_dri(conn):
    req = PublishTaskRequest(
        title="T", description="D", context_summary="S",
        tags=["DRI"], ai_involvement="L2", agent_autonomy="L3", difficulty="routine",
    )
    with pytest.raises(MissingDecisionRecord) as excinfo:
        publish_task(conn, actor="alice", req=req)
    assert excinfo.value.code == "missing_decision_record"
