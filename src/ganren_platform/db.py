import sqlite3
from contextlib import contextmanager
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

def get_connection(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

@contextmanager
def transaction(conn: sqlite3.Connection):
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

def migrate(db_path: str) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS _migrations "
            "(name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        applied = {r["name"] for r in conn.execute("SELECT name FROM _migrations")}
        for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if sql_file.name in applied:
                continue
            sql = sql_file.read_text(encoding="utf-8")
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO _migrations (name, applied_at) VALUES (?, datetime('now'))",
                (sql_file.name,),
            )
    finally:
        conn.close()
