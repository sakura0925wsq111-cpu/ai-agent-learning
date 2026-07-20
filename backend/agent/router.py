# -*- coding: utf-8 -*-
"""Agent Router ? maps agent type strings to agent instances.

Central registry for all Growth Agents. To add a new agent:
    1. Create a new agent class inheriting BaseGrowthAgent
    2. Register it in AGENT_REGISTRY below
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from agent.base import BaseGrowthAgent
from agent.career_agent import CareerAgent
from agent.graduate_agent import GraduateAgent
from agent.civil_service_agent import CivilServiceAgent
from agent.major_transfer_agent import MajorTransferAgent


# Agent label mapping for UI display
AGENT_LABELS: dict[str, str] = {
    "career": "??",
    "graduate": "??",
    "civil": "??",
    "major": "???",
}


class AgentRouter:
    """Routes agent_type strings to the correct Agent implementation.

    Usage:
        router = AgentRouter(llm_service)
        agent = router.get_agent("career")
        agent.init_state()
        result = agent.chat("I want to find a job")
    """

    def __init__(self, llm_service: Any) -> None:
        self._llm = llm_service
        self._registry: dict[str, type[BaseGrowthAgent]] = {
            "career": CareerAgent,
            "graduate": GraduateAgent,
            "civil": CivilServiceAgent,
            "major": MajorTransferAgent,
        }
        # Cache of instantiated agents per session
        self._instances: dict[str, BaseGrowthAgent] = {}

    def get_agent(self, agent_type: str) -> BaseGrowthAgent:
        """Get or create an agent instance for the given type.

        Args:
            agent_type: One of 'career', 'graduate', 'civil', 'major'.

        Returns:
            An initialized BaseGrowthAgent instance.

        Raises:
            ValueError: If agent_type is not recognized.
        """
        agent_cls = self._registry.get(agent_type)
        if agent_cls is None:
            valid = ", ".join(self._registry.keys())
            raise ValueError(
                "Unknown agent type: {}. Valid types: {}".format(agent_type, valid)
            )
        logger.info("Router: creating agent instance for {}", agent_type)
        return agent_cls(self._llm)

    def get_agent_for_session(
        self, session_id: str, agent_type: str
    ) -> BaseGrowthAgent:
        """Get or create a cached agent instance for a session.

        Args:
            session_id: Unique session identifier.
            agent_type: Agent type string.

        Returns:
            A BaseGrowthAgent instance (cached or new).
        """
        cache_key = "{}:{}".format(session_id, agent_type)
        if cache_key not in self._instances:
            self._instances[cache_key] = self.get_agent(agent_type)
            logger.debug("Router: cached agent for session {}", session_id)
        return self._instances[cache_key]

    @staticmethod
    def list_agents() -> list[dict[str, str]]:
        """List all available agents with labels for UI display."""
        return [
            {"type": k, "label": v} for k, v in AGENT_LABELS.items()
        ]
