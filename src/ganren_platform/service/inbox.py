import sqlite3
from ..models import InboxResponse, MyTasksResponse, UnitHealthResponse
from .tasks import _row_to_list_item, _row_to_question

def inbox(conn: sqlite3.Connection, *, actor: str) -> InboxResponse:
    q_to_answer = [
        _row_to_question(r) for r in conn.execute(
            "SELECT q.* FROM questions q JOIN tasks t ON q.task_id=t.id "
            "WHERE t.created_by=? AND q.status='open' ORDER BY q.asked_at",
            (actor,),
        )
    ]
    reviews = [
        _row_to_list_item(r) for r in conn.execute(
            "SELECT * FROM tasks WHERE created_by=? AND status='awaiting_review' "
            "ORDER BY submitted_at",
            (actor,),
        )
    ]
    answers = [
        _row_to_question(r) for r in conn.execute(
            "SELECT * FROM questions WHERE asked_by=? AND status='answered' "
            "ORDER BY answered_at DESC LIMIT 50",
            (actor,),
        )
    ]
    rejections = [
        _row_to_list_item(r) for r in conn.execute(
            "SELECT t.* FROM tasks t "
            "JOIN events e ON e.task_id=t.id "
            "WHERE e.type='task.rejected' AND t.claimed_by=? AND t.status='claimed' "
            "GROUP BY t.id ORDER BY MAX(e.created_at)",
            (actor,),
        )
    ]
    return InboxResponse(
        questions_to_answer=q_to_answer,
        reviews_pending=reviews,
        answers_received=answers,
        rejections_to_address=rejections,
    )

def my_tasks(conn: sqlite3.Connection, *, actor: str) -> MyTasksResponse:
    created = [_row_to_list_item(r) for r in conn.execute(
        "SELECT * FROM tasks WHERE created_by=? ORDER BY created_at DESC",
        (actor,),
    )]
    claimed = [_row_to_list_item(r) for r in conn.execute(
        "SELECT * FROM tasks WHERE claimed_by=? ORDER BY claimed_at DESC",
        (actor,),
    )]
    return MyTasksResponse(created=created, claimed=claimed)

def unit_health(conn: sqlite3.Connection, *, unit_id: str) -> UnitHealthResponse:
    counts = conn.execute(
        "SELECT "
        "COUNT(*) AS total, "
        "SUM(CASE WHEN status='closed' THEN 1 ELSE 0 END) AS closed, "
        "SUM(CASE WHEN status='open' THEN 1 ELSE 0 END) AS opened "
        "FROM tasks WHERE unit_id=?",
        (unit_id,),
    ).fetchone()
    abandoned = conn.execute(
        "SELECT COUNT(*) AS c FROM events e JOIN tasks t ON e.task_id=t.id "
        "WHERE t.unit_id=? AND e.type='task.abandoned'",
        (unit_id,),
    ).fetchone()
    return UnitHealthResponse(
        unit_id=unit_id,
        task_count=counts["total"] or 0,
        closed_count=counts["closed"] or 0,
        open_count=counts["opened"] or 0,
        abandoned_count=abandoned["c"] or 0,
    )
