import pytest
import sqlite3
import tempfile
from pathlib import Path
from ganren_platform.db import get_connection, migrate
from ganren_platform.models import PublishTaskRequest, DecisionRecord

@pytest.fixture
def temp_db_path():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        yield str(Path(tmp) / "test.db")

@pytest.fixture
def conn(temp_db_path) -> sqlite3.Connection:
    migrate(temp_db_path)
    c = get_connection(temp_db_path)
    c.execute("INSERT INTO actors (handle, display) VALUES (?, ?)", ("alice", "Alice"))
    c.execute("INSERT INTO actors (handle, display) VALUES (?, ?)", ("bob", "Bob"))
    c.execute("INSERT INTO actors (handle, display) VALUES (?, ?)", ("carol", "Carol"))
    yield c
    c.close()

@pytest.fixture
def routine_publish_req() -> PublishTaskRequest:
    return PublishTaskRequest(
        title="Build login",
        description="Implement login endpoint",
        context_summary="See spec section 2",
        tags=["Builder"],
        ai_involvement="L2",
        agent_autonomy="L3",
        difficulty="routine",
    )

@pytest.fixture
def hard_publish_req() -> PublishTaskRequest:
    return PublishTaskRequest(
        title="Pick auth provider",
        description="Decide between Auth0 and Cognito",
        context_summary="Constraints listed",
        tags=["DRI"],
        ai_involvement="L1",
        agent_autonomy="L1",
        difficulty="hard",
        decision_record=DecisionRecord(
            options_considered=["Auth0", "Cognito", "self-built"],
            chosen="Auth0",
            prob_estimate=0.6,
            rationale="Lower ops overhead",
        ),
    )
