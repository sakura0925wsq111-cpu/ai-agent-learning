# -*- coding: utf-8 -*-
"""Graduate Agent ? postgraduate exam direction analysis (placeholder)."""

from __future__ import annotations
from typing import Any
from agent.base import BaseGrowthAgent
from prompts.graduate_prompt import GRADUATE_SYSTEM_PROMPT, GRADUATE_QUESTIONS


class GraduateAgent(BaseGrowthAgent):
    @property
    def agent_type(self) -> str:
        return "graduate"

    @property
    def agent_label(self) -> str:
        return "??"

    @property
    def questions(self) -> list[dict[str, Any]]:
        return GRADUATE_QUESTIONS

    def build_prompt(self) -> str:
        return GRADUATE_SYSTEM_PROMPT
