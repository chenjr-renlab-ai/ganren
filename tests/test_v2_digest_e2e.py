import pytest
import respx
import httpx
import json
from ganren_platform.http_api.app import create_app
from ganren_platform.db import migrate, get_connection


@pytest.fixture
def app(temp_db_path):
    migrate(temp_db_path)
    conn = get_connection(temp_db_path)
    for h in ("alice",):
        conn.execute("INSERT INTO actors (handle, display) VALUES (?, ?)", (h, h.title()))
    conn.close()
    return create_app(db_path=temp_db_path, slack_webhook_url="https://hooks.slack.com/x")


@pytest.fixture
async def client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@respx.mock
async def test_publish_triggers_event_then_snapshot(client):
    from ganren_platform.notifications import digest
    digest._last_push.clear()
    route = respx.post("https://hooks.slack.com/x").mock(return_value=httpx.Response(200))
    r = await client.post(
        "/v1/tasks", headers={"X-Actor": "alice"},
        json={"title":"T","description":"D","context_summary":"S",
              "tags":["IC"],"ai_involvement":"L2","agent_autonomy":"L3","difficulty":"routine"},
    )
    assert r.status_code == 201
    # 等 BackgroundTasks 执行完
    await client.get("/healthz")  # 让 event loop 转一圈
    # 至少有 2 条推送（一条 task.created + 一条 publish_snapshot）
    assert route.call_count >= 2
    bodies = [c.request.content.decode("utf-8") for c in route.calls]
    assert any("📌 PUBLISH" in b for b in bodies)
    assert any("当前任务池" in b for b in bodies)
