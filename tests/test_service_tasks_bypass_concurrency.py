import threading
from ganren_platform.db import get_connection, migrate
from ganren_platform.service.tasks import (
    publish_task, claim_task, submit_for_review, sign_off_task,
    retag_task, record_outcome, report_escalation,
)
from ganren_platform.models import PublishTaskRequest, Outcome
from ganren_platform.errors import VersionConflict


def _routine_req(unit_id=None):
    req = PublishTaskRequest(
        title="T", description="D", context_summary="S",
        tags=["IC"], ai_involvement="L2", agent_autonomy="L3", difficulty="routine",
    )
    if unit_id is not None:
        object.__setattr__(req, "unit_id", unit_id)
    return req


def test_concurrent_retag_one_wins(temp_db_path):
    migrate(temp_db_path)
    setup = get_connection(temp_db_path)
    setup.execute("INSERT INTO actors (handle, display) VALUES ('a','A'),('b','B')")
    # Make 'a' the creator and 'b' the unit coach, so both have retag permission.
    setup.execute(
        "INSERT INTO units (id, name, type, created_at, coach_handle) "
        "VALUES ('u1','U','squad','now','b')"
    )
    tid = publish_task(setup, actor="a", req=_routine_req(unit_id="u1"))
    setup.close()

    results: dict[str, object] = {}
    barrier = threading.Barrier(2)

    def attempt(actor: str, new_tags: list[str]):
        conn = get_connection(temp_db_path)
        try:
            barrier.wait()
            retag_task(conn, actor=actor, task_id=tid, new_tags=new_tags, reason="r")
            results[actor] = "ok"
        except Exception as e:
            results[actor] = e
        finally:
            conn.close()

    t1 = threading.Thread(target=attempt, args=("a", ["Builder"]))
    t2 = threading.Thread(target=attempt, args=("b", ["Coach"]))
    t1.start(); t2.start()
    t1.join(); t2.join()

    successes = [v for v in results.values() if v == "ok"]
    conflicts = [v for v in results.values() if isinstance(v, VersionConflict)]
    assert len(successes) == 1, results
    assert len(conflicts) == 1, results


def test_concurrent_record_outcome_one_wins(temp_db_path):
    migrate(temp_db_path)
    setup = get_connection(temp_db_path)
    setup.execute("INSERT INTO actors (handle, display) VALUES ('a','A'),('b','B')")
    tid = publish_task(setup, actor="a", req=_routine_req())
    claim_task(setup, actor="b", task_id=tid)
    submit_for_review(setup, actor="b", task_id=tid, summary="done")
    sign_off_task(setup, actor="a", task_id=tid, comment="lgtm")
    setup.close()

    results: dict[str, object] = {}
    barrier = threading.Barrier(2)

    def attempt(key: str, outcome_summary: str):
        conn = get_connection(temp_db_path)
        try:
            barrier.wait()
            record_outcome(
                conn, actor="a", task_id=tid,
                outcome=Outcome(summary=outcome_summary, matched_estimate=True),
            )
            results[key] = "ok"
        except Exception as e:
            results[key] = e
        finally:
            conn.close()

    t1 = threading.Thread(target=attempt, args=("t1", "shipped-1"))
    t2 = threading.Thread(target=attempt, args=("t2", "shipped-2"))
    t1.start(); t2.start()
    t1.join(); t2.join()

    successes = [v for v in results.values() if v == "ok"]
    conflicts = [v for v in results.values() if isinstance(v, VersionConflict)]
    assert len(successes) == 1, results
    assert len(conflicts) == 1, results


def test_concurrent_report_escalation_one_wins(temp_db_path):
    migrate(temp_db_path)
    setup = get_connection(temp_db_path)
    setup.execute("INSERT INTO actors (handle, display) VALUES ('a','A'),('b','B')")
    tid = publish_task(setup, actor="a", req=_routine_req())
    claim_task(setup, actor="b", task_id=tid)
    setup.close()

    results: dict[str, object] = {}
    barrier = threading.Barrier(2)

    def attempt(key: str, note: str):
        conn = get_connection(temp_db_path)
        try:
            barrier.wait()
            report_escalation(conn, actor="b", task_id=tid, note=note)
            results[key] = "ok"
        except Exception as e:
            results[key] = e
        finally:
            conn.close()

    t1 = threading.Thread(target=attempt, args=("t1", "stuck-1"))
    t2 = threading.Thread(target=attempt, args=("t2", "stuck-2"))
    t1.start(); t2.start()
    t1.join(); t2.join()

    successes = [v for v in results.values() if v == "ok"]
    conflicts = [v for v in results.values() if isinstance(v, VersionConflict)]
    assert len(successes) == 1, results
    assert len(conflicts) == 1, results
