import asyncio
from typing import Optional
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from ..db import get_connection
from ..errors import PlatformError
from ..notifications.slack import send_event

def get_actor(x_actor: str = Header(...)) -> str:
    return x_actor

def create_app(*, db_path: str, slack_webhook_url: Optional[str]) -> FastAPI:
    app = FastAPI(title="ganren-platform")
    app.state.db_path = db_path
    app.state.slack_webhook_url = slack_webhook_url

    @app.exception_handler(PlatformError)
    async def handle_platform_error(request: Request, exc: PlatformError):
        return JSONResponse(
            status_code=exc.http_status,
            content={"code": exc.code, "message": str(exc), **exc.extras},
        )

    from .routes_tasks import router as tasks_router
    from .routes_questions import router as questions_router
    from .routes_inbox import router as inbox_router
    app.include_router(tasks_router)
    app.include_router(questions_router)
    app.include_router(inbox_router)

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    return app

def schedule_slack(app: FastAPI, event_type: str, payload: dict) -> None:
    url = app.state.slack_webhook_url
    if not url:
        return
    asyncio.create_task(send_event(url, event_type, payload))
