# -*- coding: utf-8 -*-
"""Civil Service Agent ? government exam direction analysis (placeholder)."""

from __future__ import annotations
from typing import Any
from agent.base import BaseGrowthAgent
from prompts.civil_service_prompt import CIVIL_SYSTEM_PROMPT, CIVIL_QUESTIONS


class CivilServiceAgent(BaseGrowthAgent):
    @property
    def agent_type(self) -> str:
        return "civil"

    @property
    def agent_label(self) -> str:
        return "??"

    @property
    def questions(self) -> list[dict[str, Any]]:
        return CIVIL_QUESTIONS

    def build_prompt(self) -> str:
        return CIVIL_SYSTEM_PROMPT
