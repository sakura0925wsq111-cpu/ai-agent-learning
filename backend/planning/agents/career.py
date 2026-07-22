# -*- coding: utf-8 -*-
"""Career Planning Agent — 方案 B: 就业规划。

5 步拆分执行: ANALYZE → IDENTIFY_PROBLEMS → SET_GOALS → BUILD_PLAN → GENERATE_OUTPUT
"""

from __future__ import annotations
from typing import Any
from planning.base import PlanningAgent
from planning.prompts.career import (
    CAREER_ANALYZE_PROMPT,
    CAREER_GOAL_PROMPT,
    CAREER_TASK_FILL_PROMPT,
    CAREER_ANALYSIS_STRATEGY,
    CAREER_PLANNING_PROMPT,
)


class CareerPlanningAgent(PlanningAgent):
    """Employment direction growth planning agent.

    Focus: 岗位定位, 职业方向, 能力缺口, 技能学习, 项目建议,
           简历优化, 模拟面试, 90天求职计划.

    方案 B: LLM 做文案，代码做结构和校验。
    """

    @property
    def agent_type(self) -> str:
        return "career"

    @property
    def agent_label(self) -> str:
        return "就业规划"

    # ── Legacy (backward compat) ────────────────────────────────

    def build_system_prompt(self) -> str:
        return CAREER_PLANNING_PROMPT

    # ── 方案 B: 三份拆分 Prompt ─────────────────────────────────

    def build_analyze_prompt(self) -> str:
        return CAREER_ANALYZE_PROMPT

    def build_goal_prompt(self) -> str:
        return CAREER_GOAL_PROMPT

    def build_task_fill_prompt(self) -> str:
        return CAREER_TASK_FILL_PROMPT

    # ── 追问策略（不变）────────────────────────────────────────

    def build_analysis_strategy(self) -> dict[str, Any]:
        return CAREER_ANALYSIS_STRATEGY
