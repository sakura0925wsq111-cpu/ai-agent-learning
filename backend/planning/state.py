# -*- coding: utf-8 -*-
"""PlanningAgent framework for the seven-step planning workflow.

Steps:
    1. Read user profile
    2. Answer-first advisory turns (up to 5 high-value clarifications)
    3. Analyze user situation
    4. Identify main problems
    5. Set long-term goals
    6. Decompose into 90-day action plan
    7. Generate structured JSON output

All agents share this state model; only prompts, analysis strategies,
and output templates differ per agent type.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class WorkflowStep(str, Enum):
    READ_PROFILE = "read_profile"
    FOLLOW_UP = "follow_up"
    AWAIT_TRIGGER = "await_trigger"
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
    WorkflowStep.AWAIT_TRIGGER,
    WorkflowStep.ANALYZE,
    WorkflowStep.IDENTIFY_PROBLEMS,
    WorkflowStep.SET_GOALS,
    WorkflowStep.BUILD_PLAN,
    WorkflowStep.GENERATE_OUTPUT,
]

# The first useful analysis should not be blocked by a fixed questionnaire.
# A turn-level readiness decision now controls whether another clarification is
# needed; this value is only a hard safety cap.
MAX_FOLLOW_UP_ROUNDS: int = 5
MIN_FOLLOW_UP_ROUNDS: int = 0
MAX_RETRIES_PER_QUESTION: int = 1


AMBIGUOUS_PATTERNS: frozenset[str] = frozenset({
    "不知道", "都行", "随便", "无所谓", "不确定",
    "看看再说", "看情况", "没想好", "不清楚",
    "都差不多", "都可以", "再说吧", "还没考虑",
})

# -- Phase template for 90-day action plan --

PLAN_PHASE_TEMPLATE: list[dict[str, Any]] = [
    {"phase": "第1-2周", "tasks_count": 3, "key": "phase_1"},
    {"phase": "第3-4周", "tasks_count": 3, "key": "phase_2"},
    {"phase": "第5-8周", "tasks_count": 4, "key": "phase_3"},
    {"phase": "第9-12周", "tasks_count": 4, "key": "phase_4"},
]

MIN_ADVANTAGES: int = 3
MIN_RISKS: int = 3
MIN_PLAN_PHASES: int = 4


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

    # Step 2: Follow-up rounds
    follow_up_round: int = 0
    questions_asked: int = 0
    follow_up_answers: dict[str, str] = field(default_factory=dict)
    follow_up_history: list[dict[str, str]] = field(default_factory=list)
    unavailable_dimensions: dict[str, str] = field(default_factory=dict)
    ambiguous_count: int = 0
    retry_count: int = 0
    follow_up_complete: bool = False
    last_asked_question: str = ""
    last_asked_dimension: str = ""
    advice_readiness: dict[str, Any] = field(default_factory=dict)

    # Step 3: Analyze (LLM output parsed into this structure)
    analysis_raw: str = ""
    analysis: dict[str, Any] = field(default_factory=dict)
    # Expected shape:
    # {
    #     "current_status": "...",
    #     "directions": [{"name": "...", "match_score": 85, "reasoning": "..."}],
    #     "advantages": [{"point": "...", "detail": "..."}],
    # }

    # Step 4: Identified problems (computed by deterministic rules)
    identified_problems: list[dict[str, Any]] = field(default_factory=list)
    # Expected shape:
    # [{"skill": "Redis基础", "status": "缺失", "priority": "high"}, ...]

    # Step 5: Long-term goal (LLM generates text only)
    long_term_goal: str = ""

    # Step 6: Action plan (deterministic skeleton + LLM tasks per phase)
    action_plan: list[dict[str, Any]] = field(default_factory=list)

    # Step 7: Final unified output (assembled and validated by code)
    output: dict[str, Any] = field(default_factory=dict)

    # Error tracking
    error_message: str = ""

    # Step helpers

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

    def record_follow_up(
        self,
        question: str,
        answer: str,
        *,
        dimension: str = "",
        availability: str = "answered",
    ) -> None:
        """Record a follow-up Q&A pair and whether the answer was available."""
        self.follow_up_answers[question] = answer
        entry = {"q": question, "a": answer}
        if dimension:
            entry["dimension"] = dimension
        if availability != "answered":
            entry["availability"] = availability
            if dimension and availability in ("unknown", "declined"):
                self.unavailable_dimensions[dimension] = availability
        self.follow_up_history.append(entry)
        # Only count if it is not an ambiguous/non-answer
        if availability == "answered" and not self.is_ambiguous(answer):
            self.follow_up_round += 1

    def mark_question_asked(self, question: str, dimension: str = "") -> None:
        """Count one user-facing clarification and remember its information target."""
        self.questions_asked += 1
        self.last_asked_question = question
        self.last_asked_dimension = dimension

    def should_continue_follow_up(self) -> bool:
        """Return whether the hard clarification cap still allows a question.

        Whether a question is actually valuable is decided by the turn-analysis
        layer.  This method deliberately has no minimum-round requirement.
        """
        return self.questions_asked < MAX_FOLLOW_UP_ROUNDS

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
                if entry.get("availability") in ("unknown", "declined"):
                    reason = "用户暂时不知道" if entry["availability"] == "unknown" else "用户选择不回答"
                    parts.append(f"信息状态: {reason}；后续不要重复追问这一项")

        if self.advice_readiness:
            missing = "、".join(self.advice_readiness.get("missing_labels", [])) or "无"
            parts.append("\n## 建议充分度")
            parts.append(f"- 建议层级: {self.advice_readiness.get('advice_level', 'general_only')}")
            parts.append(f"- 尚缺信息: {missing}")
            if self.advice_readiness.get("advice_level") == "conditional":
                parts.append("- 只能给条件式建议：明确列出假设和不确定性，不能伪装成充分个性化结论")

        return "\n".join(parts)

    def get_user_skills(self) -> list[str]:
        """Extract a flat list of user skill strings from profile + follow-up history.

        Tries known keys in user_profile, then scans follow-up answers.
        """
        skills: list[str] = []

        # Try explicit skill keys in profile
        for key in ("skills", "技能", "编程语言", "languages", "tools"):
            val = self.user_profile.get(key)
            if isinstance(val, str):
                skills.append(val)
            elif isinstance(val, list):
                skills.extend(val)

        # Also scan follow-up answers for skill mentions
        for entry in self.follow_up_history:
            ans = entry.get("a", "")
            if ans and len(ans) < 200:
                skills.append(ans)

        return skills

    # Serialization

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_type": self.agent_type,
            "current_step": self.current_step.value,
            "step_index": self.step_index,
            "finished": self.finished,
            "has_profile": self.has_profile,
            "user_profile": self.user_profile,
            "follow_up_round": self.follow_up_round,
            "questions_asked": self.questions_asked,
            "follow_up_answers": self.follow_up_answers,
            "follow_up_history": self.follow_up_history,
            "unavailable_dimensions": self.unavailable_dimensions,
            "ambiguous_count": self.ambiguous_count,
            "follow_up_complete": self.follow_up_complete,
            "last_asked_question": self.last_asked_question,
            "last_asked_dimension": self.last_asked_dimension,
            "advice_readiness": self.advice_readiness,
            "analysis": self.analysis,
            "identified_problems": self.identified_problems,
            "long_term_goal": self.long_term_goal,
            "action_plan": self.action_plan,
            "output": self.output,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlanningState":
        history = data.get("follow_up_history", [])
        last_question = data.get("last_asked_question", "")
        inferred_questions = len(history) + (1 if last_question else 0)
        state = cls(
            agent_type=data.get("agent_type", "career"),
            step_index=data.get("step_index", 0),
            finished=data.get("finished", False),
            user_profile=data.get("user_profile", {}),
            has_profile=data.get("has_profile", False),
            follow_up_round=data.get("follow_up_round", 0),
            questions_asked=data.get("questions_asked", inferred_questions),
            follow_up_answers=data.get("follow_up_answers", {}),
            follow_up_history=history,
            unavailable_dimensions=data.get("unavailable_dimensions", {}),
            ambiguous_count=data.get("ambiguous_count", 0),
            follow_up_complete=data.get("follow_up_complete", False),
            last_asked_question=last_question,
            last_asked_dimension=data.get("last_asked_dimension", ""),
            advice_readiness=data.get("advice_readiness", {}),
            analysis=data.get("analysis", {}),
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
