# -*- coding: utf-8 -*-
"""PlanningAgent Framework — state management for the 7-step planning workflow.

Steps:
    1. Read user profile
    2. Dynamic follow-up questions (5-7 rounds max)
    3. Analyze user situation
    4. Identify main problems
    5. Set long-term goals
    6. Decompose into 90-day action plan
    7. Generate structured JSON output

All agents share this state model — only prompts, analysis strategies,
and output templates differ per agent type.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class WorkflowStep(str, Enum):
    READ_PROFILE = "read_profile"
    FOLLOW_UP = "follow_up"
    ANALYZE = "analyze"
    IDENTIFY_PROBLEMS = "identify_problems"
    SET_GOALS = "set_goals"
    BUILD_PLAN = "build_plan"
    GENERATE_OUTPUT = "generate_output"
    COMPLETED = "completed"
    ERROR = "error"


WORKFLOW_ORDER: list[WorkflowStep] = [
    WorkflowStep.READ_PROFILE,
    WorkflowStep.FOLLOW_UP,
    WorkflowStep.ANALYZE,
    WorkflowStep.IDENTIFY_PROBLEMS,
    WorkflowStep.SET_GOALS,
    WorkflowStep.BUILD_PLAN,
    WorkflowStep.GENERATE_OUTPUT,
]

MAX_FOLLOW_UP_ROUNDS: int = 7
MIN_FOLLOW_UP_ROUNDS: int = 5
MAX_RETRIES_PER_QUESTION: int = 2


AMBIGUOUS_PATTERNS: frozenset[str] = frozenset({
    "不知道", "都行", "随便", "无所谓", "不确定",
    "看看再说", "看情况", "没想好", "不清楚",
    "都差不多", "都可以", "再说吧", "还没考虑",
})


@dataclass
class PlanningState:
    """State machine for the PlanningAgent 7-step workflow.

    Tracks progress through each step, collected information,
    follow-up question rounds, and the final structured output.
    """

    agent_type: str = "career"
    current_step: WorkflowStep = WorkflowStep.READ_PROFILE
    step_index: int = 0
    finished: bool = False

    # Step 1: User profile
    user_profile: dict[str, Any] = field(default_factory=dict)
    has_profile: bool = False

    # Step 3: Follow-up rounds
    follow_up_round: int = 0
    follow_up_answers: dict[str, str] = field(default_factory=dict)
    follow_up_history: list[dict[str, str]] = field(default_factory=list)
    ambiguous_count: int = 0
    retry_count: int = 0
    follow_up_complete: bool = False

    # Steps 4-7: Analysis results (populated by LLM during GENERATE_OUTPUT)
    analysis_raw: str = ""
    identified_problems: list[str] = field(default_factory=list)
    long_term_goal: str = ""
    action_plan: list[dict[str, Any]] = field(default_factory=list)

    # Step 8: Final unified output
    output: dict[str, Any] = field(default_factory=dict)

    # Error tracking
    error_message: str = ""

    def advance_step(self) -> WorkflowStep:
        """Move to the next workflow step."""
        if self.step_index < len(WORKFLOW_ORDER) - 1:
            self.step_index += 1
        else:
            self.finished = True
        self.current_step = WORKFLOW_ORDER[min(self.step_index, len(WORKFLOW_ORDER) - 1)]
        return self.current_step

    def set_step(self, step: WorkflowStep) -> None:
        """Jump to a specific workflow step."""
        try:
            self.step_index = WORKFLOW_ORDER.index(step)
        except ValueError:
            self.step_index = len(WORKFLOW_ORDER) - 1
        self.current_step = step

    def is_ambiguous(self, text: str) -> bool:
        """Check if an answer is ambiguous / non-committal."""
        if not text or not text.strip():
            return True
        cleaned = text.strip()
        return any(p in cleaned for p in AMBIGUOUS_PATTERNS)

    def record_follow_up(self, question: str, answer: str) -> None:
        """Record a follow-up Q&A pair."""
        self.follow_up_answers[question] = answer
        self.follow_up_history.append({"q": question, "a": answer})
        self.follow_up_round += 1

    def should_continue_follow_up(self) -> bool:
        """Determine if more follow-up questions are needed.

        Strategy:
        - Rounds 1-4: always continue (build sufficient context)
        - Rounds 5-6: continue only if still ambiguous (probe deeper),
          or stop if user has been consistently clear
        - Round 7: always stop (hard cap)
        """
        if self.follow_up_round >= MAX_FOLLOW_UP_ROUNDS:
            return False
        if self.follow_up_round < MIN_FOLLOW_UP_ROUNDS:
            return True
        # Rounds 5-6: continue only when user is still ambiguous
        # If user gave clear answers (low ambiguity), we likely have enough
        return self.ambiguous_count >= 2

    def build_context_for_llm(self) -> str:
        """Assemble all collected context for LLM analysis."""
        parts: list[str] = []

        if self.has_profile and self.user_profile:
            parts.append("## 用户画像")
            for k, v in self.user_profile.items():
                parts.append(f"- {k}: {v}")

        if self.follow_up_history:
            parts.append("\n## 追问记录")
            for i, entry in enumerate(self.follow_up_history, 1):
                parts.append(f"Q{i}: {entry['q']}")
                parts.append(f"A{i}: {entry['a']}")

        return "\n".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_type": self.agent_type,
            "current_step": self.current_step.value,
            "step_index": self.step_index,
            "finished": self.finished,
            "has_profile": self.has_profile,
            "user_profile": self.user_profile,
            "follow_up_round": self.follow_up_round,
            "follow_up_answers": self.follow_up_answers,
            "follow_up_history": self.follow_up_history,
            "ambiguous_count": self.ambiguous_count,
            "follow_up_complete": self.follow_up_complete,
            "identified_problems": self.identified_problems,
            "long_term_goal": self.long_term_goal,
            "action_plan": self.action_plan,
            "output": self.output,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlanningState":
        state = cls(
            agent_type=data.get("agent_type", "career"),
            step_index=data.get("step_index", 0),
            finished=data.get("finished", False),
            user_profile=data.get("user_profile", {}),
            has_profile=data.get("has_profile", False),
            follow_up_round=data.get("follow_up_round", 0),
            follow_up_answers=data.get("follow_up_answers", {}),
            follow_up_history=data.get("follow_up_history", []),
            ambiguous_count=data.get("ambiguous_count", 0),
            follow_up_complete=data.get("follow_up_complete", False),
            identified_problems=data.get("identified_problems", []),
            long_term_goal=data.get("long_term_goal", ""),
            action_plan=data.get("action_plan", []),
            output=data.get("output", {}),
        )
        if "current_step" in data:
            try:
                state.current_step = WorkflowStep(data["current_step"])
            except ValueError:
                state.current_step = state._step_from_index(state.step_index)
        else:
            state.current_step = state._step_from_index(state.step_index)
        return state

    def _step_from_index(self, index: int) -> WorkflowStep:
        if 0 <= index < len(WORKFLOW_ORDER):
            return WORKFLOW_ORDER[index]
        return WorkflowStep.COMPLETED
