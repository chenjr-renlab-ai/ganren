from contextlib import asynccontextmanager
from typing import Optional
from fastapi import BackgroundTasks, FastAPI, Header, Request
from fastapi.responses import JSONResponse
from ..db import get_connection
from ..errors import PlatformError
from ..notifications.slack import send_event

def get_actor(x_actor: str = Header(...)) -> str:
    return x_actor

def create_app(*, db_path: str, slack_webhook_url: Optional[str]) -> FastAPI:
    from ..mcp_api.server import build_mcp
    mcp = build_mcp(db_path=db_path)
    mcp_app = mcp.streamable_http_app()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # Run the FastMCP session manager so its task group is initialized.
        async with mcp.session_manager.run():
            yield

    app = FastAPI(title="ganren-platform", lifespan=lifespan)
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

    app.mount("/mcp", mcp_app)

    return app

def schedule_slack(
    background_tasks: BackgroundTasks,
    slack_webhook_url: Optional[str],
    event_type: str,
    payload: dict,
) -> None:
    if not slack_webhook_url:
        return
    background_tasks.add_task(send_event, slack_webhook_url, event_type, payload)
