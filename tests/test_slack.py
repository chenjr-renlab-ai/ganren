import pytest
import respx
import httpx
from ganren_platform.notifications.slack import send_event, format_event

def test_format_task_created():
    text = format_event(
        "task.created",
        {"task_id": "t1", "title": "Login", "tags": ["IC"], "created_by": "alice"},
    )
    assert "📌" in text
    assert "Login" in text
    assert "alice" in text

def test_format_question_asked_includes_summary_not_full():
    text = format_event(
        "question.asked",
        {"task_id": "t1", "ctx_summary": "stuck on choice", "ctx_full": "should-not-appear"},
    )
    assert "stuck on choice" in text
    assert "should-not-appear" not in text

def test_format_abandoned_has_no_mention():
    text = format_event("task.abandoned", {"task_id": "t1"})
    assert "@" not in text

def test_format_unknown_event_returns_none():
    assert format_event("nonexistent.event", {}) is None

@respx.mock
async def test_send_event_posts_to_webhook_when_configured():
    route = respx.post("https://hooks.slack.com/x").mock(return_value=httpx.Response(200))
    ok = await send_event(
        "https://hooks.slack.com/x",
        "task.created",
        {"task_id": "t1", "title": "T", "tags": ["IC"], "created_by": "alice"},
    )
    assert ok is True
    assert route.called

@respx.mock
async def test_send_event_returns_false_on_http_error():
    respx.post("https://hooks.slack.com/x").mock(return_value=httpx.Response(500))
    ok = await send_event(
        "https://hooks.slack.com/x",
        "task.created",
        {"task_id": "t1", "title": "T", "tags": ["IC"], "created_by": "alice"},
    )
    assert ok is False

async def test_send_event_returns_false_without_webhook():
    ok = await send_event(None, "task.created", {"task_id": "t1"})
    assert ok is False
