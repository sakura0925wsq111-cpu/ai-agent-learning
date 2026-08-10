# -*- coding: utf-8 -*-
"""Growth Agent schemas for the chat-based growth flow.

Replaces the old card-based schemas with conversation-driven state flow.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# Enums

class AgentTypeEnum(str, Enum):
    CAREER = "career"
    GRADUATE = "graduate"
    CIVIL = "civil"
    MAJOR = "major"


class AgentStageEnum(str, Enum):
    QUESTIONING = "questioning"
    AWAITING = "awaiting"
    ANALYZING = "analyzing"
    REPORT = "report"
    ERROR = "error"


# Request Models

class GrowthChatRequest(BaseModel):
    """POST /growth/chat sends a message to the growth agent."""
    user_id: str = Field(..., description="User ID")
    agent: AgentTypeEnum = Field(AgentTypeEnum.CAREER, description="Agent type")
    message: str = Field("", min_length=0, max_length=2000, description="User message (empty when creating new session)")
    session_id: str | None = Field(None, description="Existing session ID (optional, creates new if omitted)")


class GrowthStartRequest(BaseModel):
    """POST /growth/start starts a new growth session."""
    user_id: str = Field(..., description="User ID")
    agent: AgentTypeEnum = Field(AgentTypeEnum.CAREER, description="Agent type")

    sandbox_session_id: str | None = Field(None, description="Sandbox session ID for context inheritance")

# Response Models

class QuestionCard(BaseModel):
    """A question card returned to the frontend."""
    id: str
    title: str
    options: list[str] = Field(default_factory=list)
    required: bool = True
    index: int = 1
    total: int = 5


class GrowthChatResponse(BaseModel):
    progress: float | None = Field(None, description="Report generation progress 0-100")
    """Response for POST /growth/chat and /growth/start."""
    session_id: str
    agent: str
    stage: str
    finished: bool
    current_step: int = 0
    total_steps: int = 5
    next_question: QuestionCard | None = None
    report: dict[str, Any] | None = None
    message: str = ""


class GrowthStateResponse(BaseModel):
    """Response for GET /growth/state/{user_id}."""
    session_id: str | None = None
    agent: str | None = None
    status: str | None = None
    stage: str | None = None
    finished: bool = False
    current_step: int = 0
    total_steps: int = 5
    answers: dict[str, str] = Field(default_factory=dict)
    has_report: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ConversationMessage(BaseModel):
    """A single conversation message in history."""
    id: str
    role: str
    content: str
    step: int = 0
    stage: str = "questioning"
    created_at: datetime

    model_config = {"from_attributes": True}


class GrowthHistoryResponse(BaseModel):
    """Response for GET /growth/history/{user_id}."""
    user_id: str
    sessions: list["GrowthSessionSummary"] = Field(default_factory=list)


class GrowthSessionSummary(BaseModel):
    """Summary of a growth session."""
    session_id: str
    agent: str
    status: str
    stage: str = "questioning"
    finished: bool
    has_report: bool = False
    created_at: datetime
    updated_at: datetime | None = None
    message_count: int = 0

    model_config = {"from_attributes": True}


class GrowthReportResponse(BaseModel):
    """Response for GET /growth/report/{session_id}."""
    session_id: str
    agent: str
    report: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class GrowthReportSummary(BaseModel):
    """Stable, discoverable summary shown in the Growth report center."""
    report_id: str
    session_id: str
    agent: str
    title: str
    summary: str = ""
    created_at: datetime | None = None
    is_executing: bool = False
    progress: float = 0.0


class GrowthReportListResponse(BaseModel):
    user_id: str
    total: int = 0
    reports: list[GrowthReportSummary] = Field(default_factory=list)


class GrowthDashboardResponse(BaseModel):
    """One-call snapshot used to render the state-aware Growth home page."""
    user_id: str
    page_state: str = "new"
    report_count: int = 0
    active_session: dict[str, Any] | None = None
    latest_report: dict[str, Any] | None = None
    active_plan: dict[str, Any] | None = None
    coach: dict[str, Any] = Field(default_factory=dict)


class AgentListResponse(BaseModel):
    """Response listing all available agents."""
    agents: list[dict[str, str]]
