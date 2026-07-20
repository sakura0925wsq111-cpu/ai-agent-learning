# -*- coding: utf-8 -*-
"""Prompts package ? all LLM prompts externalized from agent logic."""

from prompts.career_prompt import CAREER_SYSTEM_PROMPT, CAREER_QUESTIONS
from prompts.graduate_prompt import GRADUATE_SYSTEM_PROMPT, GRADUATE_QUESTIONS
from prompts.civil_service_prompt import CIVIL_SYSTEM_PROMPT, CIVIL_QUESTIONS
from prompts.major_transfer_prompt import MAJOR_SYSTEM_PROMPT, MAJOR_QUESTIONS

__all__ = [
    "CAREER_SYSTEM_PROMPT", "CAREER_QUESTIONS",
    "GRADUATE_SYSTEM_PROMPT", "GRADUATE_QUESTIONS",
    "CIVIL_SYSTEM_PROMPT", "CIVIL_QUESTIONS",
    "MAJOR_SYSTEM_PROMPT", "MAJOR_QUESTIONS",
]
