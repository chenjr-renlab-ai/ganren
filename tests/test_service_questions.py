import pytest
from ganren_platform.service.tasks import publish_task, claim_task
from ganren_platform.service.questions import ask_question, answer_question
from ganren_platform.models import PublishTaskRequest, AskQuestionRequest, AnswerQuestionRequest
from ganren_platform.errors import NotAllowed, QuestionNotFound, CtxTooLarge

def _req():
    return PublishTaskRequest(
        title="T", description="D", context_summary="S",
        tags=["IC"], ai_involvement="L2", agent_autonomy="L3", difficulty="routine",
    )

def test_ask_by_claimer_succeeds(conn):
    tid = publish_task(conn, actor="alice", req=_req())
    claim_task(conn, actor="bob", task_id=tid)
    qid = ask_question(conn, actor="bob", req=AskQuestionRequest(
        task_id=tid, question="which option?", ctx_summary="stuck on choice"
    ))
    row = conn.execute("SELECT * FROM questions WHERE id=?", (qid,)).fetchone()
    assert row["status"] == "open"
    assert row["asked_by"] == "bob"

def test_ask_by_non_claimer_forbidden(conn):
    tid = publish_task(conn, actor="alice", req=_req())
    claim_task(conn, actor="bob", task_id=tid)
    with pytest.raises(NotAllowed):
        ask_question(conn, actor="carol", req=AskQuestionRequest(
            task_id=tid, question="?"
        ))

def test_ask_with_oversize_ctx_summary_rejected(conn):
    tid = publish_task(conn, actor="alice", req=_req())
    claim_task(conn, actor="bob", task_id=tid)
    with pytest.raises(CtxTooLarge):
        ask_question(conn, actor="bob", req=AskQuestionRequest(
            task_id=tid, question="?", ctx_summary="x" * 501,
        ))

def test_ask_with_oversize_ctx_full_rejected(conn):
    tid = publish_task(conn, actor="alice", req=_req())
    claim_task(conn, actor="bob", task_id=tid)
    with pytest.raises(CtxTooLarge):
        ask_question(conn, actor="bob", req=AskQuestionRequest(
            task_id=tid, question="?", ctx_full="x" * 4097,
        ))

def test_answer_by_creator_succeeds(conn):
    tid = publish_task(conn, actor="alice", req=_req())
    claim_task(conn, actor="bob", task_id=tid)
    qid = ask_question(conn, actor="bob", req=AskQuestionRequest(
        task_id=tid, question="?"))
    answer_question(conn, actor="alice", req=AnswerQuestionRequest(
        question_id=qid, answer="use option A"
    ))
    row = conn.execute("SELECT status, answer, answered_by FROM questions WHERE id=?", (qid,)).fetchone()
    assert row["status"] == "answered"
    assert row["answer"] == "use option A"
    assert row["answered_by"] == "alice"

def test_answer_by_non_creator_forbidden(conn):
    tid = publish_task(conn, actor="alice", req=_req())
    claim_task(conn, actor="bob", task_id=tid)
    qid = ask_question(conn, actor="bob", req=AskQuestionRequest(
        task_id=tid, question="?"))
    with pytest.raises(NotAllowed):
        answer_question(conn, actor="bob", req=AnswerQuestionRequest(
            question_id=qid, answer="x"
        ))

def test_answer_unknown_question_raises(conn):
    with pytest.raises(QuestionNotFound):
        answer_question(conn, actor="alice", req=AnswerQuestionRequest(
            question_id="missing", answer="x"
        ))
