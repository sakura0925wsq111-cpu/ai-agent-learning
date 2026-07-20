# -*- coding: utf-8 -*-
"""Graduate Planning Agent — 考研规划."""

from __future__ import annotations
from typing import Any
from planning.base import PlanningAgent
from planning.prompts.graduate import GRADUATE_PLANNING_PROMPT, GRADUATE_ANALYSIS_STRATEGY


class GraduatePlanningAgent(PlanningAgent):
    """Postgraduate exam growth planning agent.

    Focus: 考研必要性, 院校层级, 专业分析, 学习基础, 英语/数学,
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

    def build_analysis_strategy(self) -> dict[str, Any]:
        return GRADUATE_ANALYSIS_STRATEGY
