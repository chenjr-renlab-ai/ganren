import os
from ganren_platform.config import load_config

def test_load_config_with_v2_defaults(monkeypatch):
    monkeypatch.delenv("SCHEDULER_ENABLED", raising=False)
    monkeypatch.delenv("MORNING_DIGEST_CRON", raising=False)
    monkeypatch.delenv("EVENING_DIGEST_CRON", raising=False)
    monkeypatch.delenv("SCHEDULER_TZ", raising=False)
    monkeypatch.delenv("PUBLISH_INCLUDES_SNAPSHOT", raising=False)
    monkeypatch.delenv("SNAPSHOT_MAX", raising=False)
    monkeypatch.delenv("SLACK_DIGEST_WEBHOOK", raising=False)
    cfg = load_config()
    assert cfg.scheduler_enabled is True
    assert cfg.scheduler_tz == "Asia/Shanghai"
    assert cfg.morning_digest_cron == "0 10 * * MON-FRI"
    assert cfg.evening_digest_cron == "0 18 * * MON-FRI"
    assert cfg.slack_digest_webhook is None
    assert cfg.publish_includes_snapshot is True
    assert cfg.snapshot_max == 50

def test_load_config_with_v2_overrides(monkeypatch):
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")
    monkeypatch.setenv("SCHEDULER_TZ", "UTC")
    monkeypatch.setenv("SNAPSHOT_MAX", "100")
    monkeypatch.setenv("SLACK_DIGEST_WEBHOOK", "https://hooks.slack.com/A/B/C")
    cfg = load_config()
    assert cfg.scheduler_enabled is False
    assert cfg.scheduler_tz == "UTC"
    assert cfg.snapshot_max == 100
    assert cfg.slack_digest_webhook == "https://hooks.slack.com/A/B/C"
