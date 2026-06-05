import threading
import pytest
from ganren_platform.db import get_connection, migrate
from ganren_platform.service.tasks import publish_task, claim_task
from ganren_platform.models import PublishTaskRequest
from ganren_platform.errors import AlreadyClaimed

def _req():
    return PublishTaskRequest(
        title="T", description="D", context_summary="S",
        tags=["IC"], ai_involvement="L2", agent_autonomy="L3", difficulty="routine",
    )

def test_two_concurrent_claims_one_wins(temp_db_path):
    migrate(temp_db_path)
    setup = get_connection(temp_db_path)
    setup.execute("INSERT INTO actors (handle, display) VALUES ('a','A'),('b','B'),('c','C')")
    tid = publish_task(setup, actor="a", req=_req())
    setup.close()

    results: dict[str, object] = {}
    barrier = threading.Barrier(2)

    def attempt(actor: str):
        conn = get_connection(temp_db_path)
        try:
            barrier.wait()
            results[actor] = claim_task(conn, actor=actor, task_id=tid)
        except Exception as e:
            results[actor] = e
        finally:
            conn.close()

    t1 = threading.Thread(target=attempt, args=("b",))
    t2 = threading.Thread(target=attempt, args=("c",))
    t1.start(); t2.start()
    t1.join(); t2.join()

    successes = [v for v in results.values() if not isinstance(v, Exception)]
    failures = [v for v in results.values() if isinstance(v, AlreadyClaimed)]
    assert len(successes) == 1
    assert len(failures) == 1
