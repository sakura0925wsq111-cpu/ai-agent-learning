# -*- coding: utf-8 -*-
"""Career Agent ? employment direction growth analysis.

Multi-step conversational flow:
    Round 1: Major/background
    Round 2: Why employment
    Round 3: Work style preference
    Round 4: Personal strengths
    Round 5: City preference
    -> (if ambiguous) Supplementary Q1-Q2
    -> Auto-analyze -> Report

State-driven: QUESTIONING -> ANALYZING -> REPORT
Supports free-text answers and ambiguous answer retry.
"""

from __future__ import annotations

from typing import Any

from agent.base import BaseGrowthAgent
from prompts.career_prompt import (
    CAREER_SYSTEM_PROMPT,
    CAREER_QUESTIONS,
    CAREER_SUPPLEMENTARY_QUESTIONS,
)


class CareerAgent(BaseGrowthAgent):
    """Career (employment) Growth Agent ? MVP implementation.

    Collects 5 rounds of user preferences, with:
    - Free-text answer support (not limited to options)
    - Ambiguous answer detection + retry (up to 2x per question)
    - Supplementary questions when user is consistently unsure
    - Generates structured career analysis report via LLM.
    """

    @property
    def agent_type(self) -> str:
        return "career"

    @property
    def agent_label(self) -> str:
        return "就业"

    @property
    def questions(self) -> list[dict[str, Any]]:
        return CAREER_QUESTIONS

    @property
    def supplementary_questions(self) -> list[dict[str, Any]]:
        return CAREER_SUPPLEMENTARY_QUESTIONS

    def build_prompt(self) -> str:
        """Build the career analysis system prompt."""
        return CAREER_SYSTEM_PROMPT
