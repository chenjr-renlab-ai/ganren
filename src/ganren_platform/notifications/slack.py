from typing import Optional
import httpx

_TEMPLATES: dict[str, str] = {
    "task.created":   "📌 PUBLISH #{task_id} {title} [{tags}] 由 {created_by} 发布",
    "task.claimed":   "🙋 CLAIM #{task_id} 被 {claimed_by} 接走",
    "task.submitted": "✅ REVIEW @{created_by} #{task_id} 待 review",
    "task.signed_off":"🎉 CLOSE #{task_id} 关闭",
    "task.rejected":  "↩️ REJECT @{claimed_by} #{task_id} 打回：{reason}",
    "task.abandoned": "🪂 ABANDON #{task_id} 回池",
    "task.cancelled": "🛑 CANCEL #{task_id} 已取消",
    "question.asked": "❓ Q @{created_by} #{task_id}: {ctx_summary}",
    "question.answered":"💬 A @{asked_by} #{task_id} 已回复",
}


def format_event(event_type: str, payload: dict) -> Optional[str]:
    template = _TEMPLATES.get(event_type)
    if template is None:
        return None
    safe = {
        "task_id": payload.get("task_id", ""),
        "title": payload.get("title", ""),
        "tags": ",".join(payload.get("tags", []) or []),
        "created_by": payload.get("created_by", ""),
        "claimed_by": payload.get("claimed_by", ""),
        "asked_by": payload.get("asked_by", ""),
        "reason": payload.get("reason", ""),
        "ctx_summary": payload.get("ctx_summary", "") or "",
    }
    return template.format(**safe)


async def post_text(webhook_url: Optional[str], text: str) -> bool:
    """通用 Slack 推送：直接发任意预格式化文本到 webhook。"""
    if not webhook_url:
        return False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(webhook_url, json={"text": text})
            return resp.status_code < 400
    except Exception:
        return False


async def send_event(
    webhook_url: Optional[str],
    event_type: str,
    payload: dict,
) -> bool:
    text = format_event(event_type, payload)
    if text is None:
        return False
    return await post_text(webhook_url, text)
