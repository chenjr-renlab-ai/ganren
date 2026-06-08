"""加成员到 actors 表。用法：

    uv run python tools/add_actor.py <handle> [display] [unit_id]

例：
    uv run python tools/add_actor.py teammate "Teammate Name"
    uv run python tools/add_actor.py bob "Bob 王" squad_frontend
"""

from __future__ import annotations
import sqlite3
import sys
from datetime import date
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "ganren.db"


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 1

    handle = argv[1]
    display = argv[2] if len(argv) > 2 else handle.title()
    unit_id = argv[3] if len(argv) > 3 else None

    conn = sqlite3.connect(DB)
    try:
        conn.execute(
            "INSERT INTO actors (handle, display, onboarding_date, primary_unit_id) "
            "VALUES (?, ?, ?, ?)",
            (handle, display, date.today().isoformat(), unit_id),
        )
        conn.commit()
        print(f"OK: actor {handle} ({display}) added")
    except sqlite3.IntegrityError:
        print(f"actor {handle} already exists, skipping")

    rows = conn.execute(
        "SELECT handle, display, onboarding_date, primary_unit_id "
        "FROM actors ORDER BY handle"
    ).fetchall()
    print(f"\nactors table now has {len(rows)} member(s):")
    for h, d, on, unit in rows:
        unit_str = f"  unit={unit}" if unit else ""
        print(f"  {h:<12} {d:<24} onboard={on}{unit_str}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
