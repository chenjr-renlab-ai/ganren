from fastapi import APIRouter, Depends, Request
from ..db import get_connection
from ..models import InboxResponse, MyTasksResponse, UnitHealthResponse
from ..service import inbox as inbox_svc
from .app import get_actor

router = APIRouter(prefix="/v1", tags=["inbox"])

@router.get("/inbox", response_model=InboxResponse)
def get_inbox(request: Request, actor: str = Depends(get_actor)):
    conn = get_connection(request.app.state.db_path)
    try:
        return inbox_svc.inbox(conn, actor=actor)
    finally:
        conn.close()

@router.get("/my_tasks", response_model=MyTasksResponse)
def get_my_tasks(request: Request, actor: str = Depends(get_actor)):
    conn = get_connection(request.app.state.db_path)
    try:
        return inbox_svc.my_tasks(conn, actor=actor)
    finally:
        conn.close()

@router.get("/units/{unit_id}/health", response_model=UnitHealthResponse)
def get_unit_health(unit_id: str, request: Request):
    conn = get_connection(request.app.state.db_path)
    try:
        return inbox_svc.unit_health(conn, unit_id=unit_id)
    finally:
        conn.close()
