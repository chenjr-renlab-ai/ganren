import sqlite3
from ganren_platform.db import get_connection, transaction, migrate

def test_migrate_creates_tables(temp_db_path):
    migrate(temp_db_path)
    conn = get_connection(temp_db_path)
    tables = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert {"tasks", "events", "questions", "actors", "units", "_migrations"} <= tables

def test_wal_mode_enabled(temp_db_path):
    migrate(temp_db_path)
    conn = get_connection(temp_db_path)
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"

def test_transaction_rolls_back_on_exception(temp_db_path):
    migrate(temp_db_path)
    conn = get_connection(temp_db_path)
    conn.execute(
        "INSERT INTO actors (handle, display) VALUES (?, ?)",
        ("alice", "Alice"),
    )
    try:
        with transaction(conn):
            conn.execute(
                "INSERT INTO actors (handle, display) VALUES (?, ?)",
                ("bob", "Bob"),
            )
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    handles = {r["handle"] for r in conn.execute("SELECT handle FROM actors")}
    assert handles == {"alice"}
