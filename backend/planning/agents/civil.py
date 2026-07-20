# -*- coding: utf-8 -*-
"""Civil Service Planning Agent — 考公考编规划."""

from __future__ import annotations
from typing import Any
from planning.base import PlanningAgent
from planning.prompts.civil import CIVIL_PLANNING_PROMPT, CIVIL_ANALYSIS_STRATEGY


class CivilPlanningAgent(PlanningAgent):
    """Civil service exam growth planning agent.

    Focus: 适配度, 岗位类型, 地区建议, 备考规划, 学习计划,
           时间成本, 风险分析, 90天备考计划.
    """

    @property
    def agent_type(self) -> str:
        return "civil"

    @property
    def agent_label(self) -> str:
        return "考公考编规划"

    def build_system_prompt(self) -> str:
        return CIVIL_PLANNING_PROMPT

    def build_analysis_strategy(self) -> dict[str, Any]:
        return CIVIL_ANALYSIS_STRATEGY
