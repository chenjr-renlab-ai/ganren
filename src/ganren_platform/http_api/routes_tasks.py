from typing import Optional
from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel
from ..models import (
    PublishTaskRequest, TaskFull, TaskListItem, Outcome,
    AIInvolvement, Difficulty, Tag,
)
from ..db import get_connection
from ..service import tasks as task_svc
from .app import get_actor, schedule_slack

router = APIRouter(prefix="/v1/tasks", tags=["tasks"])

class RetagRequest(BaseModel):
    new_tags: list[Tag]
    reason: str

class CancelRequest(BaseModel):
    reason: str

class AbandonRequest(BaseModel):
    reason: str

class SubmitRequest(BaseModel):
    summary: str

class RejectRequest(BaseModel):
    reason: str
    hints: Optional[str] = None

class SignOffRequest(BaseModel):
    comment: Optional[str] = None

class EscalateRequest(BaseModel):
    note: str

class RecordOutcomeRequest(BaseModel):
    outcome: Outcome

@router.post("", status_code=201)
def publish(req: PublishTaskRequest, request: Request, background_tasks: BackgroundTasks,
            actor: str = Depends(get_actor)):
    conn = get_connection(request.app.state.db_path)
    try:
        tid = task_svc.publish_task(conn, actor=actor, req=req)
    finally:
        conn.close()
    schedule_slack(
        background_tasks,
        request.app.state.slack_webhook_url,
        "task.created",
        {"task_id": tid, "title": req.title, "tags": req.tags, "created_by": actor},
    )
    # V2 #4 · publish 完成后追加一条池快照消息
    from ..config import load_config
    _cfg = load_config()
    if _cfg.publish_includes_snapshot:
        snapshot_webhook = _cfg.slack_digest_webhook or request.app.state.slack_webhook_url
        # 用一个独立 conn 拿快照，因为前面的已经 close 了
        background_tasks.add_task(
            _push_publish_snapshot_bg,
            request.app.state.db_path,
            snapshot_webhook,
            _cfg.snapshot_max,
        )
    return {"id": tid}

@router.get("", response_model=list[TaskListItem])
def list_open(
    request: Request,
    tag: Optional[list[Tag]] = None,
    ai_involvement: Optional[AIInvolvement] = None,
    difficulty: Optional[Difficulty] = None,
):
    conn = get_connection(request.app.state.db_path)
    try:
        return task_svc.list_open_tasks(
            conn, tags=tag, ai_involvement=ai_involvement, difficulty=difficulty,
        )
    finally:
        conn.close()

@router.get("/{task_id}", response_model=TaskFull)
def get_one(task_id: str, request: Request):
    conn = get_connection(request.app.state.db_path)
    try:
        return task_svc.get_task(conn, task_id=task_id)
    finally:
        conn.close()

@router.post("/{task_id}/claim", response_model=TaskFull)
def claim(task_id: str, request: Request, background_tasks: BackgroundTasks,
          actor: str = Depends(get_actor)):
    conn = get_connection(request.app.state.db_path)
    try:
        task = task_svc.claim_task(conn, actor=actor, task_id=task_id)
    finally:
        conn.close()
    schedule_slack(
        background_tasks,
        request.app.state.slack_webhook_url,
        "task.claimed",
        {"task_id": task_id, "claimed_by": actor},
    )
    return task

@router.post("/{task_id}/abandon")
def abandon(task_id: str, body: AbandonRequest, request: Request,
            background_tasks: BackgroundTasks, actor: str = Depends(get_actor)):
    conn = get_connection(request.app.state.db_path)
    try:
        task_svc.abandon_task(conn, actor=actor, task_id=task_id, reason=body.reason)
    finally:
        conn.close()
    schedule_slack(
        background_tasks,
        request.app.state.slack_webhook_url,
        "task.abandoned",
        {"task_id": task_id},
    )
    return {"ok": True}

@router.post("/{task_id}/cancel")
def cancel(task_id: str, body: CancelRequest, request: Request,
           background_tasks: BackgroundTasks, actor: str = Depends(get_actor)):
    conn = get_connection(request.app.state.db_path)
    try:
        task_svc.cancel_task(conn, actor=actor, task_id=task_id, reason=body.reason)
    finally:
        conn.close()
    schedule_slack(
        background_tasks,
        request.app.state.slack_webhook_url,
        "task.cancelled",
        {"task_id": task_id},
    )
    return {"ok": True}

@router.post("/{task_id}/submit")
def submit(task_id: str, body: SubmitRequest, request: Request,
           background_tasks: BackgroundTasks, actor: str = Depends(get_actor)):
    conn = get_connection(request.app.state.db_path)
    try:
        task_svc.submit_for_review(conn, actor=actor, task_id=task_id, summary=body.summary)
        row = conn.execute("SELECT created_by FROM tasks WHERE id=?", (task_id,)).fetchone()
    finally:
        conn.close()
    schedule_slack(
        background_tasks,
        request.app.state.slack_webhook_url,
        "task.submitted",
        {"task_id": task_id, "created_by": row["created_by"]},
    )
    return {"ok": True}

@router.post("/{task_id}/reject")
def reject(task_id: str, body: RejectRequest, request: Request,
           background_tasks: BackgroundTasks, actor: str = Depends(get_actor)):
    conn = get_connection(request.app.state.db_path)
    try:
        task_svc.reject_task(conn, actor=actor, task_id=task_id,
                             reason=body.reason, hints=body.hints)
        row = conn.execute("SELECT claimed_by FROM tasks WHERE id=?", (task_id,)).fetchone()
    finally:
        conn.close()
    schedule_slack(
        background_tasks,
        request.app.state.slack_webhook_url,
        "task.rejected",
        {"task_id": task_id, "claimed_by": row["claimed_by"], "reason": body.reason},
    )
    return {"ok": True}

@router.post("/{task_id}/sign_off")
def sign_off(task_id: str, body: SignOffRequest, request: Request,
             background_tasks: BackgroundTasks, actor: str = Depends(get_actor)):
    conn = get_connection(request.app.state.db_path)
    try:
        task_svc.sign_off_task(conn, actor=actor, task_id=task_id, comment=body.comment)
    finally:
        conn.close()
    schedule_slack(
        background_tasks,
        request.app.state.slack_webhook_url,
        "task.signed_off",
        {"task_id": task_id},
    )
    return {"ok": True}

@router.post("/{task_id}/retag")
def retag(task_id: str, body: RetagRequest, request: Request, actor: str = Depends(get_actor)):
    conn = get_connection(request.app.state.db_path)
    try:
        task_svc.retag_task(conn, actor=actor, task_id=task_id,
                            new_tags=body.new_tags, reason=body.reason)
    finally:
        conn.close()
    return {"ok": True}

@router.post("/{task_id}/outcome")
def post_outcome(task_id: str, body: RecordOutcomeRequest, request: Request,
                 actor: str = Depends(get_actor)):
    conn = get_connection(request.app.state.db_path)
    try:
        task_svc.record_outcome(conn, actor=actor, task_id=task_id, outcome=body.outcome)
    finally:
        conn.close()
    return {"ok": True}

@router.post("/{task_id}/escalate")
def escalate(task_id: str, body: EscalateRequest, request: Request,
             actor: str = Depends(get_actor)):
    conn = get_connection(request.app.state.db_path)
    try:
        task_svc.report_escalation(conn, actor=actor, task_id=task_id, note=body.note)
    finally:
        conn.close()
    return {"ok": True}


async def _push_publish_snapshot_bg(db_path: str, webhook_url: Optional[str], max_rows: int):
    from ..notifications.digest import push_publish_snapshot
    conn = get_connection(db_path)
    try:
        await push_publish_snapshot(
            conn, webhook_url=webhook_url, enabled=True, max_rows=max_rows
        )
    finally:
        conn.close()
