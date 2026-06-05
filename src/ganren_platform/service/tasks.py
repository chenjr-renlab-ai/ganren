import json
import sqlite3
from typing import Optional
from ..models import (
    PublishTaskRequest, TaskFull, TaskListItem, Artifact, DecisionRecord, Outcome,
    QuestionOut,
)
from ..errors import TaskNotFound
from ..db import transaction
from .events import insert_event, new_id, now_iso

def _row_to_task_full(row: sqlite3.Row, questions: list[QuestionOut]) -> TaskFull:
    return TaskFull(
        id=row["id"],
        title=row["title"],
        description=row["description"],
        context_summary=row["context_summary"],
        artifacts=[Artifact(**a) for a in json.loads(row["artifacts"])],
        tags=json.loads(row["tags"]),
        tag_source=row["tag_source"],
        ai_involvement=row["ai_involvement"],
        agent_autonomy=row["agent_autonomy"],
        difficulty=row["difficulty"],
        decision_record=(
            DecisionRecord(**json.loads(row["decision_record"]))
            if row["decision_record"] else None
        ),
        outcome=(
            Outcome(**json.loads(row["outcome"]))
            if row["outcome"] else None
        ),
        rework_count=row["rework_count"],
        escalated=bool(row["escalated"]),
        unit_id=row["unit_id"],
        status=row["status"],
        created_by=row["created_by"],
        claimed_by=row["claimed_by"],
        created_at=row["created_at"],
        claimed_at=row["claimed_at"],
        submitted_at=row["submitted_at"],
        closed_at=row["closed_at"],
        version=row["version"],
        question_history=questions,
    )

def _row_to_question(row: sqlite3.Row) -> QuestionOut:
    return QuestionOut(
        id=row["id"],
        task_id=row["task_id"],
        asked_by=row["asked_by"],
        question=row["question"],
        ctx_summary=row["ctx_summary"],
        ctx_full=row["ctx_full"],
        answer=row["answer"],
        answered_by=row["answered_by"],
        status=row["status"],
        asked_at=row["asked_at"],
        answered_at=row["answered_at"],
    )

def _row_to_list_item(row: sqlite3.Row) -> TaskListItem:
    return TaskListItem(
        id=row["id"],
        title=row["title"],
        description=row["description"],
        tags=json.loads(row["tags"]),
        ai_involvement=row["ai_involvement"],
        agent_autonomy=row["agent_autonomy"],
        difficulty=row["difficulty"],
        created_by=row["created_by"],
    )

def publish_task(conn: sqlite3.Connection, *, actor: str, req: PublishTaskRequest) -> str:
    if (req.difficulty == "hard" or "DRI" in req.tags) and req.decision_record is None:
        from ..errors import MissingDecisionRecord
        raise MissingDecisionRecord(
            "decision_record is required when difficulty='hard' or tags contain 'DRI'"
        )
    task_id = new_id()
    created_at = now_iso()
    with transaction(conn):
        conn.execute(
            "INSERT INTO tasks ("
            "id, title, description, context_summary, artifacts, tags, "
            "tag_source, ai_involvement, agent_autonomy, difficulty, "
            "decision_record, status, created_by, created_at, version, unit_id"
            ") VALUES (?, ?, ?, ?, ?, ?, 'auto', ?, ?, ?, ?, 'open', ?, ?, 0, ?)",
            (
                task_id, req.title, req.description, req.context_summary,
                json.dumps([a.model_dump(exclude_none=True) for a in req.artifacts]),
                json.dumps(req.tags),
                req.ai_involvement, req.agent_autonomy, req.difficulty,
                json.dumps(req.decision_record.model_dump()) if req.decision_record else None,
                actor, created_at, req.unit_id,
            ),
        )
        insert_event(
            conn,
            task_id=task_id,
            type="task.created",
            actor=actor,
            payload={"title": req.title, "tags": req.tags},
            tags_snapshot=req.tags,
            ai_involvement_snap=req.ai_involvement,
            agent_autonomy_snap=req.agent_autonomy,
            unit_id_snap=req.unit_id,
        )
    return task_id

def get_task(conn: sqlite3.Connection, *, task_id: str) -> TaskFull:
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if row is None:
        raise TaskNotFound(f"task {task_id} not found", task_id=task_id)
    q_rows = conn.execute(
        "SELECT * FROM questions WHERE task_id=? ORDER BY asked_at",
        (task_id,),
    ).fetchall()
    return _row_to_task_full(row, [_row_to_question(q) for q in q_rows])

def claim_task(conn: sqlite3.Connection, *, actor: str, task_id: str) -> TaskFull:
    from ..errors import AlreadyClaimed
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if row is None:
        raise TaskNotFound(f"task {task_id} not found", task_id=task_id)
    if row["status"] != "open":
        raise AlreadyClaimed(
            f"task {task_id} status is {row['status']}",
            task_id=task_id,
            current_status=row["status"],
            current_claimed_by=row["claimed_by"],
        )
    claimed_at = now_iso()
    with transaction(conn):
        cursor = conn.execute(
            "UPDATE tasks SET status='claimed', claimed_by=?, claimed_at=?, "
            "version=version+1 WHERE id=? AND status='open' AND version=?",
            (actor, claimed_at, task_id, row["version"]),
        )
        if cursor.rowcount == 0:
            raise AlreadyClaimed(
                f"task {task_id} was claimed by another actor",
                task_id=task_id,
            )
        insert_event(
            conn,
            task_id=task_id,
            type="task.claimed",
            actor=actor,
            payload={},
            tags_snapshot=json.loads(row["tags"]),
            ai_involvement_snap=row["ai_involvement"],
            agent_autonomy_snap=row["agent_autonomy"],
            unit_id_snap=row["unit_id"],
        )
    return get_task(conn, task_id=task_id)

def list_open_tasks(
    conn: sqlite3.Connection,
    *,
    tags: Optional[list[str]] = None,
    ai_involvement: Optional[str] = None,
    difficulty: Optional[str] = None,
) -> list[TaskListItem]:
    sql = "SELECT * FROM tasks WHERE status='open'"
    params: list = []
    if ai_involvement:
        sql += " AND ai_involvement = ?"
        params.append(ai_involvement)
    if difficulty:
        sql += " AND difficulty = ?"
        params.append(difficulty)
    sql += " ORDER BY created_at"
    rows = conn.execute(sql, params).fetchall()
    items = [_row_to_list_item(r) for r in rows]
    if tags:
        wanted = set(tags)
        items = [it for it in items if wanted & set(it.tags)]
    return items

def abandon_task(conn: sqlite3.Connection, *, actor: str, task_id: str, reason: str) -> None:
    from ..errors import InvalidState, NotAllowed
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if row is None:
        raise TaskNotFound(f"task {task_id} not found", task_id=task_id)
    if row["status"] != "claimed":
        raise InvalidState(
            f"cannot abandon task in status {row['status']}",
            task_id=task_id, current_status=row["status"],
        )
    if row["claimed_by"] != actor:
        raise NotAllowed(
            f"only claimer can abandon",
            task_id=task_id, claimed_by=row["claimed_by"],
        )
    with transaction(conn):
        cursor = conn.execute(
            "UPDATE tasks SET status='open', claimed_by=NULL, claimed_at=NULL, "
            "version=version+1 WHERE id=? AND status='claimed' AND version=?",
            (task_id, row["version"]),
        )
        if cursor.rowcount == 0:
            raise InvalidState("task state changed concurrently", task_id=task_id)
        insert_event(
            conn,
            task_id=task_id,
            type="task.abandoned",
            actor=actor,
            payload={"reason": reason},
            tags_snapshot=json.loads(row["tags"]),
            ai_involvement_snap=row["ai_involvement"],
            agent_autonomy_snap=row["agent_autonomy"],
            unit_id_snap=row["unit_id"],
        )

def cancel_task(conn: sqlite3.Connection, *, actor: str, task_id: str, reason: str) -> None:
    from ..errors import InvalidState, NotAllowed
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if row is None:
        raise TaskNotFound(f"task {task_id} not found", task_id=task_id)
    if row["created_by"] != actor:
        raise NotAllowed("only creator can cancel", task_id=task_id)
    if row["status"] not in ("open", "claimed"):
        raise InvalidState(
            f"cannot cancel task in status {row['status']}",
            task_id=task_id, current_status=row["status"],
        )
    closed_at = now_iso()
    with transaction(conn):
        cursor = conn.execute(
            "UPDATE tasks SET status='closed', closed_at=?, version=version+1 "
            "WHERE id=? AND status IN ('open','claimed') AND version=?",
            (closed_at, task_id, row["version"]),
        )
        if cursor.rowcount == 0:
            raise InvalidState("task state changed concurrently", task_id=task_id)
        insert_event(
            conn,
            task_id=task_id,
            type="task.cancelled",
            actor=actor,
            payload={"reason": reason},
            tags_snapshot=json.loads(row["tags"]),
            ai_involvement_snap=row["ai_involvement"],
            agent_autonomy_snap=row["agent_autonomy"],
            unit_id_snap=row["unit_id"],
        )

def submit_for_review(conn: sqlite3.Connection, *, actor: str, task_id: str, summary: str) -> None:
    from ..errors import InvalidState, NotAllowed
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if row is None:
        raise TaskNotFound(f"task {task_id} not found", task_id=task_id)
    if row["status"] != "claimed":
        raise InvalidState(
            f"cannot submit task in status {row['status']}",
            task_id=task_id, current_status=row["status"],
        )
    if row["claimed_by"] != actor:
        raise NotAllowed("only claimer can submit", task_id=task_id)
    submitted_at = now_iso()
    with transaction(conn):
        cursor = conn.execute(
            "UPDATE tasks SET status='awaiting_review', submitted_at=?, "
            "version=version+1 WHERE id=? AND status='claimed' AND version=?",
            (submitted_at, task_id, row["version"]),
        )
        if cursor.rowcount == 0:
            raise InvalidState("task state changed concurrently", task_id=task_id)
        insert_event(
            conn,
            task_id=task_id,
            type="task.submitted",
            actor=actor,
            payload={"summary": summary},
            tags_snapshot=json.loads(row["tags"]),
            ai_involvement_snap=row["ai_involvement"],
            agent_autonomy_snap=row["agent_autonomy"],
            unit_id_snap=row["unit_id"],
        )

def reject_task(
    conn: sqlite3.Connection, *, actor: str, task_id: str, reason: str,
    hints: Optional[str] = None,
) -> None:
    from ..errors import InvalidState, NotAllowed
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if row is None:
        raise TaskNotFound(f"task {task_id} not found", task_id=task_id)
    if row["created_by"] != actor:
        raise NotAllowed("only creator can reject", task_id=task_id)
    if row["status"] != "awaiting_review":
        raise InvalidState(
            f"cannot reject task in status {row['status']}",
            task_id=task_id, current_status=row["status"],
        )
    with transaction(conn):
        cursor = conn.execute(
            "UPDATE tasks SET status='claimed', rework_count=rework_count+1, "
            "submitted_at=NULL, version=version+1 "
            "WHERE id=? AND status='awaiting_review' AND version=?",
            (task_id, row["version"]),
        )
        if cursor.rowcount == 0:
            raise InvalidState("task state changed concurrently", task_id=task_id)
        insert_event(
            conn,
            task_id=task_id,
            type="task.rejected",
            actor=actor,
            payload={"reason": reason, "hints": hints},
            tags_snapshot=json.loads(row["tags"]),
            ai_involvement_snap=row["ai_involvement"],
            agent_autonomy_snap=row["agent_autonomy"],
            unit_id_snap=row["unit_id"],
        )

def sign_off_task(
    conn: sqlite3.Connection, *, actor: str, task_id: str, comment: Optional[str] = None,
) -> None:
    from ..errors import InvalidState, NotAllowed
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if row is None:
        raise TaskNotFound(f"task {task_id} not found", task_id=task_id)
    if row["created_by"] != actor:
        raise NotAllowed("only creator can sign off", task_id=task_id)
    if row["status"] != "awaiting_review":
        raise InvalidState(
            f"cannot sign off task in status {row['status']}",
            task_id=task_id, current_status=row["status"],
        )
    closed_at = now_iso()
    with transaction(conn):
        cursor = conn.execute(
            "UPDATE tasks SET status='closed', closed_at=?, version=version+1 "
            "WHERE id=? AND status='awaiting_review' AND version=?",
            (closed_at, task_id, row["version"]),
        )
        if cursor.rowcount == 0:
            raise InvalidState("task state changed concurrently", task_id=task_id)
        insert_event(
            conn,
            task_id=task_id,
            type="task.signed_off",
            actor=actor,
            payload={"comment": comment},
            tags_snapshot=json.loads(row["tags"]),
            ai_involvement_snap=row["ai_involvement"],
            agent_autonomy_snap=row["agent_autonomy"],
            unit_id_snap=row["unit_id"],
        )

def _is_unit_coach(conn: sqlite3.Connection, actor: str, unit_id: Optional[str]) -> bool:
    if not unit_id:
        return False
    row = conn.execute(
        "SELECT coach_handle FROM units WHERE id=?", (unit_id,)
    ).fetchone()
    return row is not None and row["coach_handle"] == actor

def retag_task(
    conn: sqlite3.Connection, *, actor: str, task_id: str,
    new_tags: list[str], reason: str,
) -> None:
    from ..errors import NotAllowed, InvalidTags, VersionConflict
    if not new_tags:
        raise InvalidTags("new_tags must be non-empty", task_id=task_id)
    allowed_tags = {"IC", "Builder", "Coach", "DRI"}
    if not set(new_tags) <= allowed_tags:
        raise InvalidTags(f"unknown tags: {set(new_tags) - allowed_tags}", task_id=task_id)
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if row is None:
        raise TaskNotFound(f"task {task_id} not found", task_id=task_id)
    is_creator = row["created_by"] == actor
    is_coach = _is_unit_coach(conn, actor, row["unit_id"])
    if not (is_creator or is_coach):
        raise NotAllowed("only creator or unit coach can retag", task_id=task_id)
    with transaction(conn):
        cursor = conn.execute(
            "UPDATE tasks SET tags=?, tag_source='override', version=version+1 "
            "WHERE id=? AND version=?",
            (json.dumps(new_tags), task_id, row["version"]),
        )
        if cursor.rowcount == 0:
            raise VersionConflict("task state changed concurrently", task_id=task_id)
        insert_event(
            conn,
            task_id=task_id,
            type="task.retagged",
            actor=actor,
            payload={"reason": reason, "old_tags": json.loads(row["tags"])},
            tags_snapshot=new_tags,
            ai_involvement_snap=row["ai_involvement"],
            agent_autonomy_snap=row["agent_autonomy"],
            unit_id_snap=row["unit_id"],
        )

def record_outcome(
    conn: sqlite3.Connection, *, actor: str, task_id: str, outcome: Outcome,
) -> None:
    from ..errors import InvalidState, VersionConflict
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if row is None:
        raise TaskNotFound(f"task {task_id} not found", task_id=task_id)
    if row["status"] != "closed":
        raise InvalidState(
            f"cannot record outcome on status {row['status']}",
            task_id=task_id, current_status=row["status"],
        )
    with transaction(conn):
        cursor = conn.execute(
            "UPDATE tasks SET outcome=?, version=version+1 "
            "WHERE id=? AND version=?",
            (json.dumps(outcome.model_dump()), task_id, row["version"]),
        )
        if cursor.rowcount == 0:
            raise VersionConflict("task state changed concurrently", task_id=task_id)
        insert_event(
            conn,
            task_id=task_id,
            type="task.outcome_recorded",
            actor=actor,
            payload=outcome.model_dump(),
            tags_snapshot=json.loads(row["tags"]),
            ai_involvement_snap=row["ai_involvement"],
            agent_autonomy_snap=row["agent_autonomy"],
            unit_id_snap=row["unit_id"],
        )

def report_escalation(
    conn: sqlite3.Connection, *, actor: str, task_id: str, note: str,
) -> None:
    from ..errors import NotAllowed, VersionConflict
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if row is None:
        raise TaskNotFound(f"task {task_id} not found", task_id=task_id)
    if row["claimed_by"] != actor:
        raise NotAllowed("only claimer can report escalation", task_id=task_id)
    with transaction(conn):
        cursor = conn.execute(
            "UPDATE tasks SET escalated=1, version=version+1 "
            "WHERE id=? AND version=?",
            (task_id, row["version"]),
        )
        if cursor.rowcount == 0:
            raise VersionConflict("task state changed concurrently", task_id=task_id)
        insert_event(
            conn,
            task_id=task_id,
            type="task.escalated",
            actor=actor,
            payload={"note": note},
            tags_snapshot=json.loads(row["tags"]),
            ai_involvement_snap=row["ai_involvement"],
            agent_autonomy_snap=row["agent_autonomy"],
            unit_id_snap=row["unit_id"],
        )
