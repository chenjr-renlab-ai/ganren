from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field

Tag = Literal["IC", "Builder", "Coach", "DRI"]
AIInvolvement = Literal["L1", "L2", "L3"]
AgentAutonomy = Literal["L1", "L2", "L3", "L4", "L5"]
Difficulty = Literal["routine", "hard"]
TaskStatus = Literal["open", "claimed", "awaiting_review", "closed"]
TagSource = Literal["auto", "override"]
ArtifactKind = Literal["file", "snippet", "link", "transcript"]

class Artifact(BaseModel):
    kind: ArtifactKind
    path: Optional[str] = None
    url: Optional[str] = None
    body: Optional[str] = None
    lang: Optional[str] = None

class DecisionRecord(BaseModel):
    options_considered: list[str] = Field(..., min_length=1)
    chosen: str
    prob_estimate: float = Field(..., ge=0.0, le=1.0)
    rationale: str

class Outcome(BaseModel):
    summary: str
    matched_estimate: Optional[bool] = None

class PublishTaskRequest(BaseModel):
    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    context_summary: str
    tags: list[Tag] = Field(..., min_length=1)
    ai_involvement: AIInvolvement
    agent_autonomy: AgentAutonomy
    difficulty: Difficulty
    artifacts: list[Artifact] = Field(default_factory=list)
    decision_record: Optional[DecisionRecord] = None
    unit_id: Optional[str] = None

class TaskListItem(BaseModel):
    id: str
    title: str
    description: str
    tags: list[Tag]
    ai_involvement: AIInvolvement
    agent_autonomy: AgentAutonomy
    difficulty: Difficulty
    created_by: str

class QuestionOut(BaseModel):
    id: str
    task_id: str
    asked_by: str
    question: str
    ctx_summary: Optional[str]
    ctx_full: Optional[str]
    answer: Optional[str]
    answered_by: Optional[str]
    status: Literal["open", "answered"]
    asked_at: str
    answered_at: Optional[str]

class TaskFull(BaseModel):
    id: str
    title: str
    description: str
    context_summary: str
    artifacts: list[Artifact]
    tags: list[Tag]
    tag_source: TagSource
    ai_involvement: AIInvolvement
    agent_autonomy: AgentAutonomy
    difficulty: Difficulty
    decision_record: Optional[DecisionRecord]
    outcome: Optional[Outcome]
    rework_count: int
    escalated: bool
    unit_id: Optional[str]
    status: TaskStatus
    created_by: str
    claimed_by: Optional[str]
    created_at: str
    claimed_at: Optional[str]
    submitted_at: Optional[str]
    closed_at: Optional[str]
    version: int
    question_history: list[QuestionOut] = Field(default_factory=list)

class AskQuestionRequest(BaseModel):
    task_id: str
    question: str = Field(..., min_length=1)
    ctx_summary: Optional[str] = None
    ctx_full: Optional[str] = None

class AnswerQuestionRequest(BaseModel):
    question_id: str
    answer: str = Field(..., min_length=1)

class AskQuestionBody(BaseModel):
    question: str = Field(..., min_length=1)
    ctx_summary: Optional[str] = None
    ctx_full: Optional[str] = None

class AnswerQuestionBody(BaseModel):
    answer: str = Field(..., min_length=1)

class InboxResponse(BaseModel):
    questions_to_answer: list[QuestionOut] = Field(default_factory=list)
    reviews_pending: list[TaskListItem] = Field(default_factory=list)
    answers_received: list[QuestionOut] = Field(default_factory=list)
    rejections_to_address: list[TaskListItem] = Field(default_factory=list)

class MyTasksResponse(BaseModel):
    created: list[TaskListItem] = Field(default_factory=list)
    claimed: list[TaskListItem] = Field(default_factory=list)

class UnitHealthResponse(BaseModel):
    unit_id: str
    task_count: int
    closed_count: int
    open_count: int
    abandoned_count: int
