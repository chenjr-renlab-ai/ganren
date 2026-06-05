from fastapi import APIRouter, BackgroundTasks, Depends, Request
from ..db import get_connection
from ..models import (
    AskQuestionRequest, AnswerQuestionRequest,
    AskQuestionBody, AnswerQuestionBody,
)
from ..service import questions as q_svc
from .app import get_actor, schedule_slack

router = APIRouter(prefix="/v1", tags=["questions"])

@router.post("/tasks/{task_id}/questions", status_code=201)
def ask(task_id: str, body: AskQuestionBody, request: Request,
        background_tasks: BackgroundTasks, actor: str = Depends(get_actor)):
    req = AskQuestionRequest(
        task_id=task_id,
        question=body.question,
        ctx_summary=body.ctx_summary,
        ctx_full=body.ctx_full,
    )
    conn = get_connection(request.app.state.db_path)
    try:
        qid = q_svc.ask_question(conn, actor=actor, req=req)
        row = conn.execute("SELECT created_by FROM tasks WHERE id=?", (task_id,)).fetchone()
    finally:
        conn.close()
    schedule_slack(
        background_tasks,
        request.app.state.slack_webhook_url,
        "question.asked",
        {"task_id": task_id, "ctx_summary": req.ctx_summary,
         "created_by": row["created_by"]},
    )
    return {"id": qid}

@router.post("/questions/{question_id}/answer")
def answer(question_id: str, body: AnswerQuestionBody, request: Request,
           background_tasks: BackgroundTasks, actor: str = Depends(get_actor)):
    req = AnswerQuestionRequest(question_id=question_id, answer=body.answer)
    conn = get_connection(request.app.state.db_path)
    try:
        q_svc.answer_question(conn, actor=actor, req=req)
        row = conn.execute(
            "SELECT t.id AS task_id, q.asked_by FROM questions q "
            "JOIN tasks t ON t.id=q.task_id WHERE q.id=?", (question_id,)
        ).fetchone()
    finally:
        conn.close()
    schedule_slack(
        background_tasks,
        request.app.state.slack_webhook_url,
        "question.answered",
        {"task_id": row["task_id"], "asked_by": row["asked_by"]},
    )
    return {"ok": True}
