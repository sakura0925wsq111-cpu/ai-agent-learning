# -*- coding: utf-8 -*-
"""Sandbox API schemas — request/response models for the DecisionSandbox.

These schemas mirror the Planning API patterns but are tailored for the
multi-path sandbox workflow.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, TypedDict

from pydantic import BaseModel, Field


# ── Enums ───────────────────────────────────────────────────────

class SandboxPathType(str, Enum):
    CAREER = "career"
    GRADUATE = "graduate"
    CIVIL = "civil"
    MAJOR = "major"


class SandboxPhaseEnum(str, Enum):
    DISCOVERY = "discovery"
    PATH_PROBE = "path_probe"
    PARALLEL_SIM = "parallel_sim"
    PROJECTION = "projection"
    COMPLETED = "completed"
    ERROR = "error"


# ── Request Models ──────────────────────────────────────────────

class SandboxStartRequest(BaseModel):
    """POST /sandbox/start — start a new sandbox session."""
    user_id: str = Field(..., description="User ID")
    paths: list[SandboxPathType] | None = Field(
        None,
        description="Pre-selected paths to compare (optional; if omitted, paths are collected during discovery)",
    )


class SandboxChatRequest(BaseModel):
    """POST /sandbox/chat — send a message during a sandbox session."""
    user_id: str = Field(..., description="User ID")
    session_id: str = Field(..., description="Session ID")
    message: str = Field("", min_length=0, max_length=3000, description="User message")


class SandboxResumeRequest(BaseModel):
    """POST /sandbox/resume — resume a session with saved state."""
    user_id: str = Field(..., description="User ID")
    session_id: str = Field(..., description="Session ID to resume")
    message: str = Field("", max_length=3000, description="User message")
    state: dict[str, Any] = Field(..., description="Previously saved session state")


# ── Projection Result Sub-models ────────────────────────────────

class TimeProjection(BaseModel):
    short_term: str = Field("", description="3个月内的发展")
    mid_term: str = Field("", description="1年内的发展")
    long_term: str = Field("", description="2-3年的可能状态")
    key_milestones: list[str] = Field(default_factory=list, description="关键节点")


class PathProjection(BaseModel):
    path_type: str = Field(..., description="路径类型标识")
    path_label: str = Field(..., description="路径中文标签")
    core_insight: str = Field("", description="核心洞察")
    time_projection: TimeProjection | None = None
    strengths: list[dict[str, str]] = Field(default_factory=list)
    challenges: list[dict[str, str]] = Field(default_factory=list)
    best_for: str = Field("", description="最适合什么样的人")
    deal_breakers: str = Field("", description="什么样的人应该避开")


class ComparisonMatrix(BaseModel):
    dimensions: list[str] = Field(default_factory=list)
    scores: dict[str, list[int]] = Field(default_factory=dict)


class RelationshipAnalysis(BaseModel):
    mutually_exclusive: list[Any] = Field(default_factory=list)
    can_be_sequential: list[Any] = Field(default_factory=list)
    complementary: list[Any] = Field(default_factory=list)
    note: str = Field("", description="总体关系概述")


class DecisionGuide(BaseModel):
    questions_to_ask_yourself: list[str] = Field(default_factory=list)
    if_you_value_X_then_Y: list[dict[str, str]] = Field(default_factory=list)
    possible_hybrid_strategies: list[dict[str, str]] = Field(default_factory=list)


class KeyUncertainty(BaseModel):
    factor: str = Field(..., description="不确定性因素")
    impact: str = Field("", description="对决策的影响")
    how_to_reduce: str = Field("", description="如何降低不确定性")


class ProjectionResult(BaseModel):
    """Full projection/comparison output from the ProjectionAgent."""
    projections: list[PathProjection] = Field(default_factory=list)
    comparison_matrix: ComparisonMatrix | None = None
    relationship_analysis: RelationshipAnalysis | None = None
    decision_guide: DecisionGuide | None = None
    key_uncertainties: list[KeyUncertainty] = Field(default_factory=list)
    summary: str = Field("", description="总体对比总结")


# ── Response Models ─────────────────────────────────────────────



class SandboxStateDict(TypedDict, total=False):
    session_id: str
    user_id: str
    current_phase: str
    phase_index: int
    finished: bool
    error_message: str
    discovery_round: int
    discovery_history: list
    discovery_answers: dict
    ambiguous_count: int
    discovery_complete: bool
    user_profile: dict
    path_selections: list
    path_probe_history: dict
    path_probe_done: list
    path_reports: dict
    parallel_sim_complete: bool
    projection_result: dict
    memory_snapshot: dict

class SandboxChatResponse(BaseModel):
    """Response for /sandbox/chat and /sandbox/start."""
    session_id: str
    user_id: str
    phase: str
    finished: bool
    message: str
    discovery_round: int = 0
    max_discovery_rounds: int = 7
    path_selections: list[str] = Field(default_factory=list)
    path_reports: dict[str, dict[str, Any]] | None = None
    projection_result: ProjectionResult | None = None
    show_cards: bool = False
    cards: list[dict[str, Any]] = Field(default_factory=list)
    report_text: str = ""
    state: dict[str, Any] | None = None
    error: str | None = None


class SandboxPathInfo(BaseModel):
    """Path metadata for the path list endpoint."""
    type: str
    label: str


class SandboxPathListResponse(BaseModel):
    """GET /sandbox/paths — list all available comparison paths."""
    paths: list[SandboxPathInfo]


class SandboxResultResponse(BaseModel):
    """GET /sandbox/result/{session_id} — get the final result."""
    session_id: str
    user_id: str
    finished: bool
    path_selections: list[str]
    path_reports: dict[str, dict[str, Any]] | None = None
    projection_result: ProjectionResult | None = None
