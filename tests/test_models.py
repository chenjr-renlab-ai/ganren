import pytest
from pydantic import ValidationError
from ganren_platform.models import PublishTaskRequest, DecisionRecord, Artifact

def _base_publish_kwargs(**overrides):
    base = dict(
        title="t",
        description="d",
        context_summary="s",
        tags=["IC"],
        ai_involvement="L2",
        agent_autonomy="L3",
        difficulty="routine",
    )
    base.update(overrides)
    return base

def test_publish_request_accepts_minimal_routine_task():
    req = PublishTaskRequest(**_base_publish_kwargs())
    assert req.tags == ["IC"]
    assert req.decision_record is None

def test_publish_request_accepts_hard_with_decision_record():
    dr = DecisionRecord(
        options_considered=["A", "B"],
        chosen="A",
        prob_estimate=0.7,
        rationale="A is safer",
    )
    req = PublishTaskRequest(**_base_publish_kwargs(difficulty="hard", decision_record=dr))
    assert req.decision_record.chosen == "A"

def test_publish_request_rejects_empty_tags():
    with pytest.raises(ValidationError):
        PublishTaskRequest(**_base_publish_kwargs(tags=[]))

def test_publish_request_rejects_invalid_tag():
    with pytest.raises(ValidationError):
        PublishTaskRequest(**_base_publish_kwargs(tags=["IC", "Other"]))

def test_decision_record_clamps_probability():
    with pytest.raises(ValidationError):
        DecisionRecord(
            options_considered=["A"],
            chosen="A",
            prob_estimate=1.5,
            rationale="r",
        )

def test_artifact_kinds():
    Artifact(kind="file", path="src/a.py")
    Artifact(kind="link", url="https://example.com")
    Artifact(kind="snippet", lang="python", body="x = 1")
    Artifact(kind="transcript", body="...")
