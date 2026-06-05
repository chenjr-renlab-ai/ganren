import pytest
import httpx
import respx
from ganren_platform.http_api.app import create_app
from ganren_platform.db import migrate, get_connection

@pytest.fixture
def app(temp_db_path):
    migrate(temp_db_path)
    conn = get_connection(temp_db_path)
    for h in ("alice", "bob", "carol"):
        conn.execute("INSERT INTO actors (handle, display) VALUES (?, ?)", (h, h.title()))
    conn.close()
    return create_app(db_path=temp_db_path, slack_webhook_url=None)

@pytest.fixture
async def client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

@pytest.fixture
def app_with_slack(temp_db_path):
    migrate(temp_db_path)
    conn = get_connection(temp_db_path)
    for h in ("alice", "bob", "carol"):
        conn.execute("INSERT INTO actors (handle, display) VALUES (?, ?)", (h, h.title()))
    conn.close()
    return create_app(db_path=temp_db_path, slack_webhook_url="https://hooks.slack.com/test")

@pytest.fixture
async def client_with_slack(app_with_slack):
    transport = httpx.ASGITransport(app=app_with_slack)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

async def test_publish_then_list_then_claim(client):
    r = await client.post(
        "/v1/tasks",
        headers={"X-Actor": "alice"},
        json={
            "title": "Build login",
            "description": "endpoint",
            "context_summary": "see spec",
            "tags": ["Builder"],
            "ai_involvement": "L2",
            "agent_autonomy": "L3",
            "difficulty": "routine",
        },
    )
    assert r.status_code == 201, r.text
    tid = r.json()["id"]

    r = await client.get("/v1/tasks", headers={"X-Actor": "bob"})
    assert r.status_code == 200
    assert any(t["id"] == tid for t in r.json())

    r = await client.post(f"/v1/tasks/{tid}/claim", headers={"X-Actor": "bob"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "claimed"
    assert body["claimed_by"] == "bob"

async def test_publish_missing_decision_record_for_hard_returns_400(client):
    r = await client.post(
        "/v1/tasks",
        headers={"X-Actor": "alice"},
        json={
            "title": "T", "description": "D", "context_summary": "S",
            "tags": ["IC"], "ai_involvement": "L2", "agent_autonomy": "L3",
            "difficulty": "hard",
        },
    )
    assert r.status_code == 400
    assert r.json()["code"] == "missing_decision_record"

async def test_claim_already_claimed_returns_409(client):
    r = await client.post(
        "/v1/tasks", headers={"X-Actor": "alice"},
        json={"title":"T","description":"D","context_summary":"S",
              "tags":["IC"],"ai_involvement":"L2","agent_autonomy":"L3","difficulty":"routine"},
    )
    tid = r.json()["id"]
    await client.post(f"/v1/tasks/{tid}/claim", headers={"X-Actor": "bob"})
    r2 = await client.post(f"/v1/tasks/{tid}/claim", headers={"X-Actor": "carol"})
    assert r2.status_code == 409
    assert r2.json()["code"] == "already_claimed"

async def test_e2e_publish_claim_ask_answer_submit_signoff(client):
    r = await client.post(
        "/v1/tasks", headers={"X-Actor": "alice"},
        json={"title":"T","description":"D","context_summary":"S",
              "tags":["IC"],"ai_involvement":"L2","agent_autonomy":"L3","difficulty":"routine"},
    )
    tid = r.json()["id"]
    await client.post(f"/v1/tasks/{tid}/claim", headers={"X-Actor": "bob"})
    r = await client.post(
        f"/v1/tasks/{tid}/questions", headers={"X-Actor": "bob"},
        json={"question": "which path?", "ctx_summary": "stuck"},
    )
    qid = r.json()["id"]

    r = await client.get("/v1/inbox", headers={"X-Actor": "alice"})
    assert any(q["id"] == qid for q in r.json()["questions_to_answer"])

    await client.post(f"/v1/questions/{qid}/answer", headers={"X-Actor": "alice"},
                      json={"answer": "use path A"})
    r = await client.get("/v1/inbox", headers={"X-Actor": "bob"})
    assert any(q["id"] == qid for q in r.json()["answers_received"])

    await client.post(f"/v1/tasks/{tid}/submit", headers={"X-Actor": "bob"},
                      json={"summary": "done"})
    await client.post(f"/v1/tasks/{tid}/sign_off", headers={"X-Actor": "alice"},
                      json={"comment": "lgtm"})

    r = await client.get(f"/v1/tasks/{tid}", headers={"X-Actor": "alice"})
    assert r.json()["status"] == "closed"

@respx.mock
async def test_publish_triggers_slack_when_configured(client_with_slack):
    route = respx.post("https://hooks.slack.com/test").mock(return_value=httpx.Response(200))
    r = await client_with_slack.post(
        "/v1/tasks", headers={"X-Actor": "alice"},
        json={"title":"T","description":"D","context_summary":"S",
              "tags":["IC"],"ai_involvement":"L2","agent_autonomy":"L3","difficulty":"routine"},
    )
    assert r.status_code == 201
    assert route.called
