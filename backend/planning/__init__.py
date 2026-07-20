# -*- coding: utf-8 -*-
"""CampusPal PlanningAgent Framework.

Extensible multi-agent planning system for Chinese university students.

Architecture:
    PlanningAgent (base)
    ├── CareerPlanningAgent     — 就业规划
    ├── GraduatePlanningAgent   — 考研规划
    ├── CivilPlanningAgent      — 考公考编规划
    └── MajorPlanningAgent      — 转专业规划

To add a new agent (e.g. 留学规划):
    1. Create planning/prompts/study_abroad.py
    2. Create planning/agents/study_abroad.py
    3. Register in planning/router.py
    4. Done — all workflows, state management, and API are inherited.
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
