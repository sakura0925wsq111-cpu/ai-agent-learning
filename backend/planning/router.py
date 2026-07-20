# -*- coding: utf-8 -*-
"""PlanningRouter — registry and factory for all PlanningAgent types.

=================================
EXTENSION GUIDE: Adding a New Agent
=================================

Example: Adding a "留学规划" (Study Abroad) agent.

**Step 1: Create the prompt file**
    File: planning/prompts/study_abroad.py

    STUDY_ABROAD_PLANNING_PROMPT = \"\"\"You are a study abroad planning coach...\"\"\"
    STUDY_ABROAD_ANALYSIS_STRATEGY = {
        "focus_dimensions": [...],
        "special_rules": [...],
        "question_topics": [...],
    }

**Step 2: Create the agent class**
    File: planning/agents/study_abroad.py

    from planning.base import PlanningAgent
    from planning.prompts.study_abroad import STUDY_ABROAD_PLANNING_PROMPT, STUDY_ABROAD_ANALYSIS_STRATEGY

    class StudyAbroadPlanningAgent(PlanningAgent):
        @property
        def agent_type(self) -> str:
            return "study_abroad"

        @property
        def agent_label(self) -> str:
            return "留学规划"

        def build_system_prompt(self) -> str:
            return STUDY_ABROAD_PLANNING_PROMPT

        def build_analysis_strategy(self) -> dict[str, Any]:
            return STUDY_ABROAD_ANALYSIS_STRATEGY

**Step 3: Register in this router**
    Add to AGENT_REGISTRY:
        "study_abroad": StudyAbroadPlanningAgent,

    Add to AGENT_LABELS:
        "study_abroad": "留学规划",

    Add import at top:
        from planning.agents.study_abroad import StudyAbroadPlanningAgent

**Step 4: (Optional) Add API route**
    The generic /planning/chat endpoint works for all agents automatically.
    No new route needed unless you want a dedicated endpoint.

That''s it — the agent inherits the full 8-step workflow, state management,
dynamic follow-up engine, and structured JSON output automatically.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from planning.base import PlanningAgent
from planning.agents.career import CareerPlanningAgent
from planning.agents.graduate import GraduatePlanningAgent
from planning.agents.civil import CivilPlanningAgent
from planning.agents.major import MajorPlanningAgent


AGENT_LABELS: dict[str, str] = {
    "career": "就业规划",
    "graduate": "考研规划",
    "civil": "考公考编规划",
    "major": "转专业规划",
}

AGENT_REGISTRY: dict[str, type[PlanningAgent]] = {
    "career": CareerPlanningAgent,
    "graduate": GraduatePlanningAgent,
    "civil": CivilPlanningAgent,
    "major": MajorPlanningAgent,
}


class PlanningRouter:
    """Central registry and factory for PlanningAgent instances.

    Usage:
        router = PlanningRouter(llm_service)
        agent = router.get_agent("career")
        agent.init_state(user_profile={"major": "计算机"})
        result = agent.chat("我想找Java开发的工作")
    """

    def __init__(self, llm_service: Any) -> None:
        self._llm = llm_service
        self._instances: dict[str, PlanningAgent] = {}

    def get_agent(self, agent_type: str) -> PlanningAgent:
        """Create (or return cached) a PlanningAgent instance.

        Args:
            agent_type: One of 'career', 'graduate', 'civil', 'major'.

        Returns:
            An initialized PlanningAgent instance.

        Raises:
            ValueError: If agent_type is not recognized.
        """
        agent_cls = AGENT_REGISTRY.get(agent_type)
        if agent_cls is None:
            valid = ", ".join(AGENT_REGISTRY.keys())
            raise ValueError(
                f"Unknown agent type: {agent_type}. Valid types: {valid}"
            )

        # Always create a fresh instance for isolation
        logger.info("PlanningRouter: creating {} agent", agent_type)
        return agent_cls(self._llm)

    def get_agent_for_session(
        self, session_id: str, agent_type: str
    ) -> PlanningAgent:
        """Get or create a cached agent instance for a specific session.

        Args:
            session_id: Unique session identifier.
            agent_type: Agent type string.

        Returns:
            A PlanningAgent instance (cached or new).
        """
        cache_key = f"{session_id}:{agent_type}"
        if cache_key not in self._instances:
            self._instances[cache_key] = self.get_agent(agent_type)
            logger.debug("PlanningRouter: cached agent for session {}", session_id)
        return self._instances[cache_key]

    def evict_session(self, session_id: str, agent_type: str) -> None:
        """Remove a cached agent for a completed session."""
        cache_key = f"{session_id}:{agent_type}"
        self._instances.pop(cache_key, None)

    @staticmethod
    def list_agents() -> list[dict[str, str]]:
        """List all available planning agents with labels for UI."""
        return [
            {"type": k, "label": v} for k, v in AGENT_LABELS.items()
        ]

    @staticmethod
    def register_agent(
        agent_type: str,
        agent_cls: type[PlanningAgent],
        label: str,
    ) -> None:
        """Programmatically register a new agent type at runtime.

        Useful for plugin-style extensions.

        Args:
            agent_type: Unique agent type key.
            agent_cls: PlanningAgent subclass.
            label: Human-readable Chinese label.
        """
        AGENT_REGISTRY[agent_type] = agent_cls
        AGENT_LABELS[agent_type] = label
        logger.info(
            "PlanningRouter: registered new agent '{}' ({})",
            agent_type, label,
        )
