from ganren_platform.service.tasks import (
    publish_task, claim_task, submit_for_review, reject_task,
)
from ganren_platform.service.questions import ask_question, answer_question
from ganren_platform.service.inbox import inbox, my_tasks, unit_health
from ganren_platform.models import PublishTaskRequest, AskQuestionRequest, AnswerQuestionRequest

def _req(unit_id=None):
    req = PublishTaskRequest(
        title="T", description="D", context_summary="S",
        tags=["IC"], ai_involvement="L2", agent_autonomy="L3", difficulty="routine",
        unit_id=unit_id,
    )
    return req

def test_publisher_inbox_sees_open_questions_and_pending_reviews(conn):
    t1 = publish_task(conn, actor="alice", req=_req())
    t2 = publish_task(conn, actor="alice", req=_req())
    claim_task(conn, actor="bob", task_id=t1)
    claim_task(conn, actor="bob", task_id=t2)
    ask_question(conn, actor="bob", req=AskQuestionRequest(task_id=t1, question="?"))
    submit_for_review(conn, actor="bob", task_id=t2, summary="done")
    box = inbox(conn, actor="alice")
    assert len(box.questions_to_answer) == 1
    assert box.questions_to_answer[0].task_id == t1
    assert len(box.reviews_pending) == 1
    assert box.reviews_pending[0].id == t2

def test_collaborator_inbox_sees_answers_and_rejections(conn):
    t1 = publish_task(conn, actor="alice", req=_req())
    t2 = publish_task(conn, actor="alice", req=_req())
    claim_task(conn, actor="bob", task_id=t1)
    claim_task(conn, actor="bob", task_id=t2)
    qid = ask_question(conn, actor="bob", req=AskQuestionRequest(task_id=t1, question="?"))
    answer_question(conn, actor="alice", req=AnswerQuestionRequest(question_id=qid, answer="A"))
    submit_for_review(conn, actor="bob", task_id=t2, summary="done")
    reject_task(conn, actor="alice", task_id=t2, reason="redo")
    box = inbox(conn, actor="bob")
    assert len(box.answers_received) == 1
    assert box.answers_received[0].answer == "A"
    assert len(box.rejections_to_address) == 1
    assert box.rejections_to_address[0].id == t2

def test_my_tasks_returns_created_and_claimed(conn):
    t1 = publish_task(conn, actor="alice", req=_req())
    t2 = publish_task(conn, actor="alice", req=_req())
    claim_task(conn, actor="bob", task_id=t2)
    out = my_tasks(conn, actor="alice")
    created_ids = {t.id for t in out.created}
    assert created_ids == {t1, t2}
    out_bob = my_tasks(conn, actor="bob")
    claimed_ids = {t.id for t in out_bob.claimed}
    assert claimed_ids == {t2}

def test_unit_health_counts_by_unit(conn):
    conn.execute(
        "INSERT INTO units (id, name, type, created_at) VALUES ('u1','U','squad','now')"
    )
    publish_task(conn, actor="alice", req=_req(unit_id="u1"))
    publish_task(conn, actor="alice", req=_req(unit_id="u1"))
    publish_task(conn, actor="alice", req=_req())
    h = unit_health(conn, unit_id="u1")
    assert h.task_count == 2
    assert h.unit_id == "u1"
