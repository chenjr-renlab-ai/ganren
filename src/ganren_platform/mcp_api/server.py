from typing import Optional
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from ..db import get_connection
from ..models import (
    PublishTaskRequest, AskQuestionRequest, AnswerQuestionRequest,
    Outcome, Tag, AIInvolvement, Difficulty,
)
from ..service import tasks as task_svc
from ..service import questions as q_svc
from ..service import inbox as inbox_svc

def build_mcp(*, db_path: str) -> FastMCP:
    # streamable_http_path="/" so the mount at /mcp exposes the endpoint at /mcp/
    # (default streamable_http_path is /mcp which would expose it at /mcp/mcp)
    #
    # 关掉 DNS rebinding protection：FastMCP 默认只接受 Host=localhost/127.0.0.1，
    # 队友通过局域网 IP 访问会被拒成 HTTP 421。本平台是内部信任环境，关掉这层。
    mcp = FastMCP(
        "ganren-platform",
        streamable_http_path="/",
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=False,
        ),
    )

    def _conn():
        return get_connection(db_path)

    @mcp.tool()
    def publish_task(
        actor: str,
        title: str,
        description: str,
        context_summary: str,
        tags: list[Tag],
        ai_involvement: AIInvolvement,
        agent_autonomy: str,
        difficulty: Difficulty,
        artifacts: Optional[list[dict]] = None,
        decision_record: Optional[dict] = None,
        unit_id: Optional[str] = None,
    ) -> dict:
        req = PublishTaskRequest(
            title=title, description=description, context_summary=context_summary,
            tags=tags, ai_involvement=ai_involvement, agent_autonomy=agent_autonomy,
            difficulty=difficulty,
            artifacts=artifacts or [],
            decision_record=decision_record,
            unit_id=unit_id,
        )
        c = _conn()
        try:
            tid = task_svc.publish_task(c, actor=actor, req=req)
        finally:
            c.close()
        return {"id": tid}

    @mcp.tool()
    def list_open_tasks(
        tags: Optional[list[Tag]] = None,
        ai_involvement: Optional[AIInvolvement] = None,
        difficulty: Optional[Difficulty] = None,
    ) -> list[dict]:
        c = _conn()
        try:
            items = task_svc.list_open_tasks(
                c, tags=tags, ai_involvement=ai_involvement, difficulty=difficulty
            )
        finally:
            c.close()
        return [it.model_dump() for it in items]

    @mcp.tool()
    def get_task(task_id: str) -> dict:
        c = _conn()
        try:
            return task_svc.get_task(c, task_id=task_id).model_dump()
        finally:
            c.close()

    @mcp.tool()
    def claim_task(actor: str, task_id: str) -> dict:
        c = _conn()
        try:
            return task_svc.claim_task(c, actor=actor, task_id=task_id).model_dump()
        finally:
            c.close()

    @mcp.tool()
    def abandon_task(actor: str, task_id: str, reason: str) -> dict:
        c = _conn()
        try:
            task_svc.abandon_task(c, actor=actor, task_id=task_id, reason=reason)
        finally:
            c.close()
        return {"ok": True}

    @mcp.tool()
    def cancel_task(actor: str, task_id: str, reason: str) -> dict:
        c = _conn()
        try:
            task_svc.cancel_task(c, actor=actor, task_id=task_id, reason=reason)
        finally:
            c.close()
        return {"ok": True}

    @mcp.tool()
    def submit_for_review(actor: str, task_id: str, summary: str) -> dict:
        c = _conn()
        try:
            task_svc.submit_for_review(c, actor=actor, task_id=task_id, summary=summary)
        finally:
            c.close()
        return {"ok": True}

    @mcp.tool()
    def reject_task(actor: str, task_id: str, reason: str, hints: Optional[str] = None) -> dict:
        c = _conn()
        try:
            task_svc.reject_task(c, actor=actor, task_id=task_id, reason=reason, hints=hints)
        finally:
            c.close()
        return {"ok": True}

    @mcp.tool()
    def sign_off_task(actor: str, task_id: str, comment: Optional[str] = None) -> dict:
        c = _conn()
        try:
            task_svc.sign_off_task(c, actor=actor, task_id=task_id, comment=comment)
        finally:
            c.close()
        return {"ok": True}

    @mcp.tool()
    def retag_task(actor: str, task_id: str, new_tags: list[Tag], reason: str) -> dict:
        c = _conn()
        try:
            task_svc.retag_task(c, actor=actor, task_id=task_id,
                                new_tags=new_tags, reason=reason)
        finally:
            c.close()
        return {"ok": True}

    @mcp.tool()
    def record_outcome(actor: str, task_id: str, outcome: dict) -> dict:
        c = _conn()
        try:
            task_svc.record_outcome(c, actor=actor, task_id=task_id,
                                    outcome=Outcome(**outcome))
        finally:
            c.close()
        return {"ok": True}

    @mcp.tool()
    def report_escalation(actor: str, task_id: str, note: str) -> dict:
        c = _conn()
        try:
            task_svc.report_escalation(c, actor=actor, task_id=task_id, note=note)
        finally:
            c.close()
        return {"ok": True}

    @mcp.tool()
    def ask_question(
        actor: str, task_id: str, question: str,
        ctx_summary: Optional[str] = None, ctx_full: Optional[str] = None,
    ) -> dict:
        c = _conn()
        try:
            qid = q_svc.ask_question(c, actor=actor, req=AskQuestionRequest(
                task_id=task_id, question=question,
                ctx_summary=ctx_summary, ctx_full=ctx_full,
            ))
        finally:
            c.close()
        return {"id": qid}

    @mcp.tool()
    def answer_question(actor: str, question_id: str, answer: str) -> dict:
        c = _conn()
        try:
            q_svc.answer_question(c, actor=actor, req=AnswerQuestionRequest(
                question_id=question_id, answer=answer,
            ))
        finally:
            c.close()
        return {"ok": True}

    @mcp.tool()
    def inbox(actor: str) -> dict:
        c = _conn()
        try:
            return inbox_svc.inbox(c, actor=actor).model_dump()
        finally:
            c.close()

    @mcp.tool()
    def my_tasks(actor: str) -> dict:
        c = _conn()
        try:
            return inbox_svc.my_tasks(c, actor=actor).model_dump()
        finally:
            c.close()

    @mcp.tool()
    def unit_health(unit_id: str) -> dict:
        c = _conn()
        try:
            return inbox_svc.unit_health(c, unit_id=unit_id).model_dump()
        finally:
            c.close()

    return mcp
