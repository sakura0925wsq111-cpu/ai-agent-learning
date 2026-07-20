# -*- coding: utf-8 -*-
"""Planning Agent Prompts — all system prompts and analysis strategies.

Each agent has two exports:
    XXX_PLANNING_PROMPT     — full system prompt for LLM
    XXX_ANALYSIS_STRATEGY   — analysis dimensions, rules, and question topics
"""

from planning.prompts.career import CAREER_PLANNING_PROMPT, CAREER_ANALYSIS_STRATEGY
from planning.prompts.graduate import GRADUATE_PLANNING_PROMPT, GRADUATE_ANALYSIS_STRATEGY
from planning.prompts.civil import CIVIL_PLANNING_PROMPT, CIVIL_ANALYSIS_STRATEGY
from planning.prompts.major import MAJOR_PLANNING_PROMPT, MAJOR_ANALYSIS_STRATEGY

__all__ = [
    "CAREER_PLANNING_PROMPT", "CAREER_ANALYSIS_STRATEGY",
    "GRADUATE_PLANNING_PROMPT", "GRADUATE_ANALYSIS_STRATEGY",
    "CIVIL_PLANNING_PROMPT", "CIVIL_ANALYSIS_STRATEGY",
    "MAJOR_PLANNING_PROMPT", "MAJOR_ANALYSIS_STRATEGY",
]
