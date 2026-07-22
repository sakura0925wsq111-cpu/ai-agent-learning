# -*- coding: utf-8 -*-
"""CampusPal PlanningAgent Framework.

Extensible multi-agent planning system for Chinese university students.

Architecture:
    PlanningAgent (base)
    ├── CareerPlanningAgent     — 就业规划
    ├── GraduatePlanningAgent   — 考研规划
    ├── CivilPlanningAgent      — 考公考编规划
    └── MajorPlanningAgent      — 转专业规划

LangGraph Integration (NEW):
    GrowthGraph — StateGraph orchestrating the growth workflow with
    interrupt/resume (SQLite checkpointer), human-in-the-loop, and SSE streaming.
"""

from planning.base import PlanningAgent, UNIFIED_OUTPUT_SCHEMA
from planning.state import PlanningState, WorkflowStep, MAX_FOLLOW_UP_ROUNDS
from planning.router import PlanningRouter
from planning.agents import (
    CareerPlanningAgent,
    GraduatePlanningAgent,
    CivilPlanningAgent,
    MajorPlanningAgent,
)

__all__ = [
    "PlanningAgent",
    "PlanningState",
    "PlanningRouter",
    "WorkflowStep",
    "UNIFIED_OUTPUT_SCHEMA",
    "MAX_FOLLOW_UP_ROUNDS",
    "CareerPlanningAgent",
    "GraduatePlanningAgent",
    "CivilPlanningAgent",
    "MajorPlanningAgent",
]
