# -*- coding: utf-8 -*-
"""Career Planning Agent — 就业规划."""

from __future__ import annotations
from typing import Any
from planning.base import PlanningAgent
from planning.prompts.career import CAREER_PLANNING_PROMPT, CAREER_ANALYSIS_STRATEGY


class CareerPlanningAgent(PlanningAgent):
    """Employment direction growth planning agent.

    Focus: 岗位定位, 职业方向, 能力缺口, 技能学习, 项目建议,
           简历优化, 模拟面试, 90天求职计划.
    """

    @property
    def agent_type(self) -> str:
        return "career"

    @property
    def agent_label(self) -> str:
        return "就业规划"

    def build_system_prompt(self) -> str:
        return CAREER_PLANNING_PROMPT

    def build_analysis_strategy(self) -> dict[str, Any]:
        return CAREER_ANALYSIS_STRATEGY
