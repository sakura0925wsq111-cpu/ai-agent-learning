# -*- coding: utf-8 -*-
"""Planning API schemas — request/response models for the PlanningAgent framework.

All agents share the same unified output schema.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Enums ───────────────────────────────────────────────────────

class PlanningAgentType(str, Enum):
    CAREER = "career"
    GRADUATE = "graduate"
    CIVIL = "civil"
    MAJOR = "major"


class PlanningStep(str, Enum):
    READ_PROFILE = "read_profile"
    READ_DIAGNOSIS = "read_diagnosis"
    FOLLOW_UP = "follow_up"
    ANALYZE = "analyze"
    IDENTIFY_PROBLEMS = "identify_problems"
    SET_GOALS = "set_goals"
    BUILD_PLAN = "build_plan"
    GENERATE_OUTPUT = "generate_output"
    COMPLETED = "completed"
    ERROR = "error"


# ── Request Models ──────────────────────────────────────────────

class PlanningChatRequest(BaseModel):
    """POST /planning/chat — send a message to a planning agent."""
    user_id: str = Field(..., description="User ID")
    agent: PlanningAgentType = Field(..., description="Agent type")
    message: str = Field("", min_length=0, max_length=2000, description="User message")
    session_id: str | None = Field(None, description="Existing session ID (creates new if omitted)")


class PlanningStartRequest(BaseModel):
    """POST /planning/start — start a new planning session."""
    user_id: str = Field(..., description="User ID")
    agent: PlanningAgentType = Field(..., description="Agent type")


class PlanningResumeRequest(BaseModel):
    """POST /planning/resume — resume a planning session with saved state."""
    user_id: str = Field(..., description="User ID")
    session_id: str = Field(..., description="Session ID to resume")
    message: str = Field("", max_length=2000, description="User message")


# ── Unified Output (Risk / Advantage / Plan items) ──────────────

class RiskItem(BaseModel):
    point: str = Field(..., description="风险点标题")
    detail: str = Field(..., description="风险详细解释")
    level: str = Field("medium", description="风险等级: low/medium/high")


class AdvantageItem(BaseModel):
    point: str = Field(..., description="优势点标题")
    detail: str = Field(..., description="优势详细解释")


class PlanPhase(BaseModel):
    phase: str = Field(..., description="阶段名称，如：第1-2周：基础准备")
    tasks: list[str] = Field(default_factory=list, description="具体任务列表")
    expected_outcome: str = Field("", description="本阶段预期成果")


class PlanningReport(BaseModel):
    """Unified output report — all agents produce this exact structure."""
    summary: str = Field("", description="200字以内的总体评估摘要")
    current_status: str = Field("", description="用户当前状态描述")
    main_problem: str = Field("", description="识别出的最核心问题")
    goal: str = Field("", description="建议的长期目标")
    advantages: list[AdvantageItem] = Field(default_factory=list, description="优势列表")
    risks: list[RiskItem] = Field(default_factory=list, description="风险列表")
    action_plan: list[PlanPhase] = Field(default_factory=list, description="90天行动计划")
    next_question: str = Field("", description="引导用户继续思考的问题")


# ── Response Models ─────────────────────────────────────────────

class PlanningChatResponse(BaseModel):
    """Response for /planning/chat and /planning/start."""
    session_id: str | None = None
    agent: str
    agent_label: str
    step: str
    finished: bool
    message: str
    follow_up_round: int = 0
    max_follow_up_rounds: int = 7
    report: PlanningReport | None = None
    state: dict[str, Any] | None = None


class PlanningAgentInfo(BaseModel):
    """Agent metadata for the agent list endpoint."""
    type: str
    label: str


class PlanningAgentListResponse(BaseModel):
    """GET /planning/agents — list all available planning agents."""
    agents: list[PlanningAgentInfo]
