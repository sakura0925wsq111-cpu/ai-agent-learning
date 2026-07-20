# -*- coding: utf-8 -*-
"""Major Transfer Planning Agent — 转专业规划."""

from __future__ import annotations
from typing import Any
from planning.base import PlanningAgent
from planning.prompts.major import MAJOR_PLANNING_PROMPT, MAJOR_ANALYSIS_STRATEGY


class MajorPlanningAgent(PlanningAgent):
    """Major transfer growth planning agent.

    Focus: 转专业适配度, 兴趣分析, 能力匹配, 目标专业分析,
           转专业成本, 就业分析, 风险分析, 学习路线.
    """

    @property
    def agent_type(self) -> str:
        return "major"

    @property
    def agent_label(self) -> str:
        return "转专业规划"

    def build_system_prompt(self) -> str:
        return MAJOR_PLANNING_PROMPT

    def build_analysis_strategy(self) -> dict[str, Any]:
        return MAJOR_ANALYSIS_STRATEGY
