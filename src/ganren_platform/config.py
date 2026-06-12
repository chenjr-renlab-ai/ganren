import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Config:
    bind_addr: str
    db_path: str
    slack_webhook_url: str | None
    log_level: str
    # V2 #4 新字段
    scheduler_enabled: bool
    scheduler_tz: str
    morning_digest_cron: str
    evening_digest_cron: str
    slack_digest_webhook: str | None
    publish_includes_snapshot: bool
    snapshot_max: int


def load_config() -> Config:
    return Config(
        bind_addr=os.environ.get("BIND_ADDR", "0.0.0.0:8787"),
        db_path=os.environ.get("GANREN_DB_PATH", "./data/ganren.db"),
        slack_webhook_url=os.environ.get("SLACK_WEBHOOK_URL") or None,
        log_level=os.environ.get("LOG_LEVEL", "info"),
        scheduler_enabled=_bool(os.environ.get("SCHEDULER_ENABLED"), True),
        scheduler_tz=os.environ.get("SCHEDULER_TZ", "Asia/Shanghai"),
        morning_digest_cron=os.environ.get("MORNING_DIGEST_CRON", "0 10 * * MON-FRI"),
        evening_digest_cron=os.environ.get("EVENING_DIGEST_CRON", "0 18 * * MON-FRI"),
        slack_digest_webhook=os.environ.get("SLACK_DIGEST_WEBHOOK") or None,
        publish_includes_snapshot=_bool(
            os.environ.get("PUBLISH_INCLUDES_SNAPSHOT"), True
        ),
        snapshot_max=int(os.environ.get("SNAPSHOT_MAX", "50")),
    )
