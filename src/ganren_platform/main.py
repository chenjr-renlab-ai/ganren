import sys
import uvicorn
from .config import load_config
from .db import migrate
from .http_api.app import create_app

def main() -> int:
    cfg = load_config()
    migrate(cfg.db_path)
    app = create_app(db_path=cfg.db_path, slack_webhook_url=cfg.slack_webhook_url)
    host, _, port = cfg.bind_addr.rpartition(":")
    uvicorn.run(app, host=host or "0.0.0.0", port=int(port), log_level=cfg.log_level)
    return 0

if __name__ == "__main__":
    sys.exit(main())
