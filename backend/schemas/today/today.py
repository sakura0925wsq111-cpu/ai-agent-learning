# -*- coding: utf-8 -*-
"""Today Mode core schemas — overview, suggestion, sync, import."""

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


# ── Today Overview ──────────────────────────────────────────────

class TodayOverviewResponse(BaseModel):
    """GET /today/overview — aggregated snapshot of the user's day."""
    user_id: str
    date: str
    greeting: str
    weather: dict[str, Any] | None
    courses_count: int
    todos_count: int
    nearest_exam: dict[str, Any] | None
    courses_today: list[dict[str, Any]] = Field(default_factory=list)
    pending_todos: list[dict[str, Any]] = Field(default_factory=list)


# ── AI Suggestion ───────────────────────────────────────────────

class TodaySuggestionRequest(BaseModel):
    """POST /today/suggestion — request an AI-generated daily suggestion."""
    user_id: str
    city: str = Field(default="北京")


class TodaySuggestionResponse(BaseModel):
    """AI-generated daily suggestion."""
    user_id: str
    date: str
    suggestion: str
    context_summary: dict[str, Any] = Field(default_factory=dict)


# ── Growth Plan Sync ────────────────────────────────────────────

class SyncPlanRequest(BaseModel):
    """POST /today/sync-plan — sync a Growth plan phase to daily todos."""
    user_id: str
    growth_session_id: str
    phase: str = Field(..., pattern=r"^phase_[1-4]$")


class SyncPlanResponse(BaseModel):
    """Result of syncing a growth plan phase."""
    user_id: str
    growth_session_id: str
    phase: str
    synced_count: int
    todos: list[dict[str, Any]] = Field(default_factory=list)


# ── Progress Feedback ───────────────────────────────────────────

class PhaseProgress(BaseModel):
    """Progress of a single growth plan phase."""
    phase_key: str
    label: str
    total: int
    completed: int
    todos: list[dict[str, Any]] = Field(default_factory=list)


class PlanProgressResponse(BaseModel):
    """GET /today/progress — overall plan completion status."""
    user_id: str
    growth_session_id: str
    phases: list[PhaseProgress] = Field(default_factory=list)
    overall_completion: float = 0.0


# ── PDF Import ──────────────────────────────────────────────────

class ImportPreviewResponse(BaseModel):
    """POST /today/import — preview parsed data before user confirms."""
    import_id: str
    import_type: str  # "course" or "exam"
    total: int
    items: list[dict[str, Any]] = Field(default_factory=list)


class ImportConfirmRequest(BaseModel):
    """POST /today/import/confirm — confirm and save parsed items."""
    import_id: str


class ImportConfirmResponse(BaseModel):
    """Result of confirming an import."""
    import_id: str
    saved_count: int
