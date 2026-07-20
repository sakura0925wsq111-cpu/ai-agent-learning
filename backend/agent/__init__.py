# -*- coding: utf-8 -*-
"""Agent package ? Growth Agent implementations for CampusPal.

Architecture:
    BaseGrowthAgent (abstract)
      +-- CareerAgent       (MVP)
      +-- GraduateAgent     (placeholder)
      +-- CivilServiceAgent (placeholder)
      +-- MajorTransferAgent (placeholder)

Each agent follows a state-driven multi-step flow:
    QUESTIONING -> ANALYZING -> REPORT
"""

from agent.base import BaseGrowthAgent, ConversationState, AgentStage, AgentStatus
from agent.career_agent import CareerAgent
from agent.graduate_agent import GraduateAgent
from agent.civil_service_agent import CivilServiceAgent
from agent.major_transfer_agent import MajorTransferAgent
from agent.router import AgentRouter

__all__ = [
    "BaseGrowthAgent",
    "ConversationState",
    "AgentStage",
    "AgentStatus",
    "CareerAgent",
    "GraduateAgent",
    "CivilServiceAgent",
    "MajorTransferAgent",
    "AgentRouter",
]
