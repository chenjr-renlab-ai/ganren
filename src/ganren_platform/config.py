import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Config:
    bind_addr: str
    db_path: str
    slack_webhook_url: str | None
    log_level: str

def load_config() -> Config:
    return Config(
        bind_addr=os.environ.get("BIND_ADDR", "0.0.0.0:8787"),
        db_path=os.environ.get("GANREN_DB_PATH", "./data/ganren.db"),
        slack_webhook_url=os.environ.get("SLACK_WEBHOOK_URL") or None,
        log_level=os.environ.get("LOG_LEVEL", "info"),
    )
