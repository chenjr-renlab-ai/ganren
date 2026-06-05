import json
import sqlite3
from ..models import AskQuestionRequest, AnswerQuestionRequest
from ..errors import (
    NotAllowed, TaskNotFound, QuestionNotFound, CtxTooLarge, InvalidState,
)
from ..db import transaction
from .events import insert_event, new_id, now_iso

CTX_SUMMARY_MAX = 500
CTX_FULL_MAX = 4096

def ask_question(conn: sqlite3.Connection, *, actor: str, req: AskQuestionRequest) -> str:
    if req.ctx_summary and len(req.ctx_summary.encode("utf-8")) > CTX_SUMMARY_MAX:
        raise CtxTooLarge(
            f"ctx_summary exceeds {CTX_SUMMARY_MAX} bytes",
            limit=CTX_SUMMARY_MAX,
        )
    if req.ctx_full and len(req.ctx_full.encode("utf-8")) > CTX_FULL_MAX:
        raise CtxTooLarge(
            f"ctx_full exceeds {CTX_FULL_MAX} bytes",
            limit=CTX_FULL_MAX,
        )
    task = conn.execute("SELECT * FROM tasks WHERE id=?", (req.task_id,)).fetchone()
    if task is None:
        raise TaskNotFound(f"task {req.task_id} not found", task_id=req.task_id)
    if task["claimed_by"] != actor:
        raise NotAllowed("only claimer can ask questions", task_id=req.task_id)
    qid = new_id()
    asked_at = now_iso()
    with transaction(conn):
        conn.execute(
            "INSERT INTO questions ("
            "id, task_id, asked_by, question, ctx_summary, ctx_full, "
            "status, asked_at"
            ") VALUES (?, ?, ?, ?, ?, ?, 'open', ?)",
            (qid, req.task_id, actor, req.question, req.ctx_summary, req.ctx_full, asked_at),
        )
        insert_event(
            conn,
            task_id=req.task_id,
            type="question.asked",
            actor=actor,
            payload={"question_id": qid, "ctx_summary": req.ctx_summary},
            tags_snapshot=json.loads(task["tags"]),
            ai_involvement_snap=task["ai_involvement"],
            agent_autonomy_snap=task["agent_autonomy"],
            unit_id_snap=task["unit_id"],
        )
    return qid

def answer_question(conn: sqlite3.Connection, *, actor: str, req: AnswerQuestionRequest) -> None:
    q = conn.execute("SELECT * FROM questions WHERE id=?", (req.question_id,)).fetchone()
    if q is None:
        raise QuestionNotFound(f"question {req.question_id} not found", question_id=req.question_id)
    if q["status"] == "answered":
        raise InvalidState("question already answered", question_id=req.question_id)
    task = conn.execute("SELECT * FROM tasks WHERE id=?", (q["task_id"],)).fetchone()
    if task["created_by"] != actor:
        raise NotAllowed("only task creator can answer", task_id=q["task_id"])
    answered_at = now_iso()
    with transaction(conn):
        conn.execute(
            "UPDATE questions SET answer=?, answered_by=?, answered_at=?, status='answered' "
            "WHERE id=? AND status='open'",
            (req.answer, actor, answered_at, req.question_id),
        )
        insert_event(
            conn,
            task_id=q["task_id"],
            type="question.answered",
            actor=actor,
            payload={"question_id": req.question_id},
            tags_snapshot=json.loads(task["tags"]),
            ai_involvement_snap=task["ai_involvement"],
            agent_autonomy_snap=task["agent_autonomy"],
            unit_id_snap=task["unit_id"],
        )
