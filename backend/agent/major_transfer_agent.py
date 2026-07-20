# -*- coding: utf-8 -*-
"""Major Transfer Agent ? major change direction analysis (placeholder)."""

from __future__ import annotations
from typing import Any
from agent.base import BaseGrowthAgent
from prompts.major_transfer_prompt import MAJOR_SYSTEM_PROMPT, MAJOR_QUESTIONS


class MajorTransferAgent(BaseGrowthAgent):
    @property
    def agent_type(self) -> str:
        return "major"

    @property
    def agent_label(self) -> str:
        return "???"

    @property
    def questions(self) -> list[dict[str, Any]]:
        return MAJOR_QUESTIONS

    def build_prompt(self) -> str:
        return MAJOR_SYSTEM_PROMPT
