import pytest
from datetime import date
from unittest.mock import AsyncMock, patch


def test_build_scheduler_returns_background_scheduler(tmp_path):
    from ganren_platform.notifications.scheduler import build_scheduler
    from ganren_platform.config import Config
    cfg = Config(
        bind_addr="x", db_path=str(tmp_path / "x.db"),
        slack_webhook_url=None, log_level="info",
        scheduler_enabled=True, scheduler_tz="UTC",
        morning_digest_cron="0 10 * * MON-FRI",
        evening_digest_cron="0 18 * * MON-FRI",
        slack_digest_webhook=None,
        publish_includes_snapshot=True, snapshot_max=50,
    )
    sched = build_scheduler(cfg)
    job_ids = {j.id for j in sched.get_jobs()}
    assert "morning_digest" in job_ids
    assert "evening_digest" in job_ids


def test_build_scheduler_invalid_cron_skips_job(tmp_path, caplog):
    from ganren_platform.notifications.scheduler import build_scheduler
    from ganren_platform.config import Config
    cfg = Config(
        bind_addr="x", db_path=str(tmp_path / "x.db"),
        slack_webhook_url=None, log_level="info",
        scheduler_enabled=True, scheduler_tz="UTC",
        morning_digest_cron="invalid cron expr",   # bad
        evening_digest_cron="0 18 * * MON-FRI",
        slack_digest_webhook=None,
        publish_includes_snapshot=True, snapshot_max=50,
    )
    sched = build_scheduler(cfg)
    job_ids = {j.id for j in sched.get_jobs()}
    assert "morning_digest" not in job_ids
    assert "evening_digest" in job_ids


def test_start_scheduler_if_enabled_returns_none_when_disabled(tmp_path):
    from ganren_platform.notifications.scheduler import start_scheduler_if_enabled
    from ganren_platform.config import Config
    cfg = Config(
        bind_addr="x", db_path=str(tmp_path / "x.db"),
        slack_webhook_url=None, log_level="info",
        scheduler_enabled=False, scheduler_tz="UTC",
        morning_digest_cron="0 10 * * MON-FRI",
        evening_digest_cron="0 18 * * MON-FRI",
        slack_digest_webhook=None,
        publish_includes_snapshot=True, snapshot_max=50,
    )
    sched = start_scheduler_if_enabled(cfg)
    assert sched is None
