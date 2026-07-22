# -*- coding: utf-8 -*-
"""Graduate Planning Agent — 方案 B: 考研规划.

ANALYZE → IDENTIFY_PROBLEMS → SET_GOALS → BUILD_PLAN → GENERATE_OUTPUT
"""

from __future__ import annotations
from typing import Any
from planning.base import PlanningAgent
from planning.prompts.graduate import (
    GRADUATE_ANALYZE_PROMPT,
    GRADUATE_GOAL_PROMPT,
    GRADUATE_TASK_FILL_PROMPT,
    GRADUATE_ANALYSIS_STRATEGY,
    GRADUATE_PLANNING_PROMPT,
)


class GraduatePlanningAgent(PlanningAgent):
    """Postgraduate exam growth planning agent.

    Focus: 考研必要性, 院校层级, 专业分析, 英语/数学,
           择校策略, 复习计划, 阶段目标, 90天学习计划.
    """

    @property
    def agent_type(self) -> str:
        return "graduate"

    @property
    def agent_label(self) -> str:
        return "考研规划"

    def build_system_prompt(self) -> str:
        return GRADUATE_PLANNING_PROMPT

    def build_analyze_prompt(self) -> str:
        return GRADUATE_ANALYZE_PROMPT

    def build_goal_prompt(self) -> str:
        return GRADUATE_GOAL_PROMPT

    def build_task_fill_prompt(self) -> str:
        return GRADUATE_TASK_FILL_PROMPT

    def build_analysis_strategy(self) -> dict[str, Any]:
        return GRADUATE_ANALYSIS_STRATEGY
