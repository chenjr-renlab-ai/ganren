from ganren_platform.service.tasks import publish_task, list_open_tasks
from ganren_platform.models import PublishTaskRequest

def _req(tags, ai="L2", autonomy="L3", difficulty="routine", dr=None):
    return PublishTaskRequest(
        title="T", description="D", context_summary="S",
        tags=tags, ai_involvement=ai, agent_autonomy=autonomy,
        difficulty=difficulty, decision_record=dr,
    )

def test_list_open_tasks_returns_only_open(conn):
    t1 = publish_task(conn, actor="alice", req=_req(["IC"]))
    t2 = publish_task(conn, actor="alice", req=_req(["Builder"]))
    conn.execute("UPDATE tasks SET status='closed' WHERE id=?", (t2,))
    items = list_open_tasks(conn)
    ids = {it.id for it in items}
    assert ids == {t1}

def test_list_open_tasks_omits_context_summary_fields(conn):
    publish_task(conn, actor="alice", req=_req(["IC"]))
    items = list_open_tasks(conn)
    # TaskListItem 没有 context_summary 字段
    assert not hasattr(items[0], "context_summary")

def test_list_open_tasks_filters_by_tag(conn):
    publish_task(conn, actor="alice", req=_req(["IC"]))
    t_builder = publish_task(conn, actor="alice", req=_req(["Builder"]))
    items = list_open_tasks(conn, tags=["Builder"])
    assert [it.id for it in items] == [t_builder]

def test_list_open_tasks_filters_by_ai_involvement(conn):
    t1 = publish_task(conn, actor="alice", req=_req(["IC"], ai="L1"))
    publish_task(conn, actor="alice", req=_req(["IC"], ai="L3"))
    items = list_open_tasks(conn, ai_involvement="L1")
    assert [it.id for it in items] == [t1]

def test_list_open_tasks_filters_by_difficulty(conn):
    from ganren_platform.models import DecisionRecord
    dr = DecisionRecord(options_considered=["a"], chosen="a", prob_estimate=0.5, rationale="r")
    t_hard = publish_task(conn, actor="alice", req=_req(["IC"], difficulty="hard", dr=dr))
    publish_task(conn, actor="alice", req=_req(["IC"]))
    items = list_open_tasks(conn, difficulty="hard")
    assert [it.id for it in items] == [t_hard]
