"""apscheduler 包装：装载 morning/evening digest 两个 cron job。

fail-safe 原则：任何故障都不应阻塞 web server。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from ..config import Config
from ..db import get_connection
from . import digest

log = logging.getLogger(__name__)


def _parse_cron(expr: str, tz: str) -> Optional[CronTrigger]:
    try:
        return CronTrigger.from_crontab(expr, timezone=tz)
    except Exception as e:
        log.error("invalid cron expression %r: %s", expr, e)
        return None


def _make_morning_callback(
    db_path: str, webhook_url: Optional[str], max_rows: int, tz: str
):
    def job():
        try:
            conn = get_connection(db_path)
            try:
                asyncio.run(
                    digest.push_morning_digest(
                        conn,
                        webhook_url=webhook_url,
                        today=datetime.now(ZoneInfo(tz)).date(),
                        max_rows=max_rows,
                        tz=tz,
                    )
                )
            finally:
                conn.close()
        except Exception as e:
            log.warning("morning_digest job failed: %s", e)
    return job


def _make_evening_callback(
    db_path: str, webhook_url: Optional[str], max_rows: int, tz: str
):
    def job():
        try:
            conn = get_connection(db_path)
            try:
                asyncio.run(
                    digest.push_evening_digest(
                        conn,
                        webhook_url=webhook_url,
                        today=datetime.now(ZoneInfo(tz)).date(),
                        max_rows=max_rows,
                        tz=tz,
                    )
                )
            finally:
                conn.close()
        except Exception as e:
            log.warning("evening_digest job failed: %s", e)
    return job


def build_scheduler(cfg: Config) -> BackgroundScheduler:
    """装载 2 个 cron job。无效 cron 直接 skip 不抛。"""
    sched = BackgroundScheduler(timezone=cfg.scheduler_tz)
    digest_webhook = cfg.slack_digest_webhook or cfg.slack_webhook_url

    morning_trigger = _parse_cron(cfg.morning_digest_cron, cfg.scheduler_tz)
    if morning_trigger is not None:
        sched.add_job(
            _make_morning_callback(
                cfg.db_path, digest_webhook, cfg.snapshot_max, cfg.scheduler_tz
            ),
            trigger=morning_trigger,
            id="morning_digest",
        )

    evening_trigger = _parse_cron(cfg.evening_digest_cron, cfg.scheduler_tz)
    if evening_trigger is not None:
        sched.add_job(
            _make_evening_callback(
                cfg.db_path, digest_webhook, cfg.snapshot_max, cfg.scheduler_tz
            ),
            trigger=evening_trigger,
            id="evening_digest",
        )

    return sched


def start_scheduler_if_enabled(cfg: Config) -> Optional[BackgroundScheduler]:
    """启动入口，由 main.py 调用。返回 scheduler（用于优雅关闭）或 None。"""
    if not cfg.scheduler_enabled:
        log.info("scheduler disabled by config")
        return None
    try:
        sched = build_scheduler(cfg)
        sched.start()
        log.info("scheduler started with %d job(s)", len(sched.get_jobs()))
        return sched
    except Exception as e:
        log.error("scheduler failed to start: %s", e)
        return None
