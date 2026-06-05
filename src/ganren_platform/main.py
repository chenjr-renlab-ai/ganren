import sys
from .config import load_config

def main() -> int:
    cfg = load_config()
    print(f"ganren-platform config loaded: bind={cfg.bind_addr} db={cfg.db_path}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
