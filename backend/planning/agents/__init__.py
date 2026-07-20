# -*- coding: utf-8 -*-
"""Planning Agents — concrete implementations.

Each agent inherits PlanningAgent and only swaps:
    1. System prompt
    2. Analysis strategy
"""

from planning.agents.career import CareerPlanningAgent
from planning.agents.graduate import GraduatePlanningAgent
from planning.agents.civil import CivilPlanningAgent
from planning.agents.major import MajorPlanningAgent

__all__ = [
    "CareerPlanningAgent",
    "GraduatePlanningAgent",
    "CivilPlanningAgent",
    "MajorPlanningAgent",
]
