# -*- coding: utf-8 -*-
"""Base Growth Agent and ConversationState for CampusPal.

Defines the state-driven multi-step flow:
    QUESTIONING -> ANALYZING -> REPORT

State is tracked in ConversationState (NOT inferred from prompts).
Each agent defines its own question flow and analysis logic.
Prompts are externalized to prompts/ directory.
Output is always structured JSON, never Markdown.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from loguru import logger


# Words that signal the user does not have a clear answer
AMBIGUOUS_WORDS: frozenset[str] = frozenset({
    "不知道", "都可以", "无所谓",
    "随便", "不确定", "看看再说",
    "看情况", "没想好", "不清楚",
    "随便吧", "都行",
})
MAX_RETRIES_PER_QUESTION: int = 2
SUPPLEMENTARY_THRESHOLD: int = 2


class AgentStage(str, Enum):
    QUESTIONING = "questioning"
    ANALYZING = "analyzing"
    REPORT = "report"


class AgentStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class ConversationState:
    agent_type: str = "career"
    current_step: int = 0
    total_steps: int = 5
    finished: bool = False
    stage: AgentStage = AgentStage.QUESTIONING
    status: AgentStatus = AgentStatus.ACTIVE
    answers: dict[str, str] = field(default_factory=dict)
    answer_history: list[dict[str, str]] = field(default_factory=list)
    analysis_raw: str = ""
    report_json: dict[str, Any] = field(default_factory=dict)
    error_message: str = ""
    # Ambiguous answer tracking
    ambiguous_count: int = 0
    retry_count: int = 0
    # Supplementary question tracking
    supplementary_asked: int = 0
    in_supplementary: bool = False

    def record_answer(self, question_id: str, answer: str) -> None:
        self.answers[question_id] = answer
        self.answer_history.append({"question_id": question_id, "answer": answer})
        self.current_step += 1

    def is_questioning_complete(self) -> bool:
        return self.current_step >= self.total_steps

    def advance_to_analyzing(self) -> None:
        self.stage = AgentStage.ANALYZING
        self.finished = False
        logger.debug("Agent Stage: QUESTIONING -> ANALYZING (agent={})", self.agent_type)

    def advance_to_report(self) -> None:
        self.stage = AgentStage.REPORT
        self.finished = True
        self.status = AgentStatus.COMPLETED
        logger.debug("Agent Stage: ANALYZING -> REPORT (agent={})", self.agent_type)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_type": self.agent_type,
            "current_step": self.current_step,
            "total_steps": self.total_steps,
            "finished": self.finished,
            "stage": self.stage.value,
            "status": self.status.value,
            "answers": self.answers,
            "answer_history": self.answer_history,
            "report_json": self.report_json,
            "ambiguous_count": self.ambiguous_count,
            "retry_count": self.retry_count,
            "supplementary_asked": self.supplementary_asked,
            "in_supplementary": self.in_supplementary,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConversationState":
        state = cls(
            agent_type=data.get("agent_type", "career"),
            current_step=data.get("current_step", 0),
            total_steps=data.get("total_steps", 5),
            finished=data.get("finished", False),
            stage=AgentStage(data.get("stage", "questioning")),
            status=AgentStatus(data.get("status", "active")),
            answers=data.get("answers", {}),
            answer_history=data.get("answer_history", []),
            report_json=data.get("report_json", {}),
            ambiguous_count=data.get("ambiguous_count", 0),
            retry_count=data.get("retry_count", 0),
            supplementary_asked=data.get("supplementary_asked", 0),
            in_supplementary=data.get("in_supplementary", False),
        )
        return state


class BaseGrowthAgent(ABC):
    def __init__(self, llm_service: Any) -> None:
        self.llm = llm_service
        self.state: ConversationState

    @property
    @abstractmethod
    def agent_type(self) -> str:
        ...

    @property
    @abstractmethod
    def agent_label(self) -> str:
        ...

    @property
    @abstractmethod
    def questions(self) -> list[dict[str, Any]]:
        ...

    @property
    def supplementary_questions(self) -> list[dict[str, Any]]:
        """Optional supplementary questions for ambiguous answers."""
        return []

    def init_state(self) -> ConversationState:
        self.state = ConversationState(
            agent_type=self.agent_type,
            total_steps=len(self.questions),
        )
        logger.info("Agent Init: {} (questions={})", self.agent_type, len(self.questions))
        return self.state

    def restore_state(self, state: ConversationState) -> None:
        self.state = state
        logger.debug("Agent State restored: {}, stage={}", self.agent_type, state.stage.value)

    def chat(self, message: str) -> dict[str, Any]:
        try:
            if self.state.stage == AgentStage.QUESTIONING:
                return self._handle_questioning(message)
            elif self.state.stage == AgentStage.ANALYZING:
                return self._handle_analyzing()
            elif self.state.stage == AgentStage.REPORT:
                return self._build_report_response()
            else:
                raise ValueError("Unknown stage: {}".format(self.state.stage))
        except Exception as exc:
            logger.error("Agent chat() error: {}", exc)
            return {
                "stage": "error", "finished": True,
                "next_question": None, "report": None,
                "message": "Error: {}".format(str(exc)),
            }

    def analyze(self) -> dict[str, Any]:
        logger.info("Agent Analyzing: {}", self.agent_type)
        answers_str = "\n".join(
            "{}. {}: {}".format(i+1, h["question_id"], h["answer"])
            for i, h in enumerate(self.state.answer_history)
        )
        system_prompt = self.build_prompt()
        user_prompt = self._build_analysis_user_prompt(answers_str)
        try:
            raw_response = self.llm.chat(
                user_message=user_prompt,
                system_prompt=system_prompt,
                temperature=0.3,
                max_tokens=4096,
            )
            self.state.analysis_raw = raw_response
            report = self._parse_report(raw_response)
            self.state.report_json = report
            self.state.advance_to_report()
            logger.info("Agent Analysis done: {}", self.agent_type)
            return report
        except Exception as exc:
            logger.error("Agent LLM failed: {}", exc)
            raise

    @abstractmethod
    def build_prompt(self) -> str:
        ...

    def get_next_question(self) -> dict[str, Any] | None:
        """Return the next question card, accepting any valid answer."""
        if self.state.in_supplementary:
            sup_qs = self.supplementary_questions
            idx = self.state.supplementary_asked
            if idx < len(sup_qs):
                q = sup_qs[idx]
                return {
                    "id": q["id"],
                    "title": q["title"],
                    "options": q.get("options", []),
                    "required": q.get("required", True),
                    "index": self.state.current_step + 1,
                    "total": self.state.total_steps + len(sup_qs),
                }
            return None

        questions = self.questions
        step = self.state.current_step
        if step >= len(questions):
            return None
        q = questions[step]
        return {
            "id": q["id"],
            "title": q["title"],
            "options": q.get("options", []),
            "required": q.get("required", True),
            "index": step + 1,
            "total": len(questions),
        }

    @staticmethod
    def _is_ambiguous(text: str) -> bool:
        """Check if the answer is too vague to be useful."""
        if not text or not text.strip():
            return True
        trimmed = text.strip()
        return trimmed in AMBIGUOUS_WORDS

    def _handle_questioning(self, message: str) -> dict[str, Any]:
        """Process a message during QUESTIONING stage with ambiguity detection."""
        questions = self.questions
        step = self.state.current_step
        is_ambiguous = self._is_ambiguous(message)

        # --- Supplementary mode ---
        if self.state.in_supplementary:
            sup_qs = self.supplementary_questions
            sup_idx = self.state.supplementary_asked
            if sup_idx < len(sup_qs):
                current_q = sup_qs[sup_idx]
                if is_ambiguous and self.state.retry_count < MAX_RETRIES_PER_QUESTION:
                    self.state.retry_count += 1
                    self.state.ambiguous_count += 1
                    logger.debug("Agent: supplementary retry {}/{} for {}",
                                 self.state.retry_count, MAX_RETRIES_PER_QUESTION, current_q["id"])
                    return {
                        "stage": "questioning", "finished": False,
                        "next_question": {
                            "id": current_q["id"],
                            "title": current_q.get("retry_prompt", "??????????????????~"),
                            "options": current_q.get("options", []),
                            "required": True,
                            "index": step + 1,
                            "total": self.state.total_steps + len(sup_qs),
                        },
                        "report": None,
                        "message": "??????????????????~",
                    }
                # Accept answer
                self.state.record_answer(current_q["id"], message)
                self.state.supplementary_asked += 1
                self.state.retry_count = 0
                if is_ambiguous:
                    self.state.ambiguous_count += 1
                logger.debug("Agent: supplementary Q done (asked={}/{})",
                             self.state.supplementary_asked, len(sup_qs))

                if self.state.supplementary_asked >= len(sup_qs):
                    # All supplementary done -> signal analyzing (async)
                    self.state.in_supplementary = False
                    self.state.advance_to_analyzing()
                    return {
                        "stage": "analyzing", "finished": False,
                        "next_question": None, "report": None,
                        "message": "All questions collected. Analyzing...",
                    }
                # Return next supplementary question
                return self._build_next_question_response()
            else:
                # No more supplementary -> signal analyzing (async)
                self.state.in_supplementary = False
                self.state.advance_to_analyzing()
                return {
                    "stage": "analyzing", "finished": False,
                    "next_question": None, "report": None,
                    "message": "All questions collected. Analyzing...",
                }

        # --- Core questioning mode ---
        if step < len(questions):
            current_q = questions[step]

            # Ambiguous answer -> retry
            if is_ambiguous and self.state.retry_count < MAX_RETRIES_PER_QUESTION:
                self.state.retry_count += 1
                self.state.ambiguous_count += 1
                logger.debug("Agent: retry {}/{} for Q{} ({})",
                             self.state.retry_count, MAX_RETRIES_PER_QUESTION,
                             step + 1, current_q["id"])
                # Return the SAME question with a gentle nudge
                return {
                    "stage": "questioning", "finished": False,
                    "next_question": {
                        "id": current_q["id"],
                        "title": current_q.get("retry_prompt",
                            "?????????~ ????????????????"),
                        "options": current_q.get("options", []),
                        "required": True,
                        "index": step + 1,
                        "total": self.state.total_steps,
                    },
                    "report": None,
                    "message": "?????????~",
                }

            # Valid answer (or max retries exceeded) -> accept and advance
            self.state.record_answer(current_q["id"], message)
            self.state.retry_count = 0
            if is_ambiguous:
                self.state.ambiguous_count += 1

        logger.debug("Agent QUESTIONING step={}/{} ambiguous={}",
                     self.state.current_step, self.state.total_steps,
                     self.state.ambiguous_count)

        # Core questions done -> check supplementary
        if self.state.current_step >= len(questions):
            sup_qs = self.supplementary_questions
            if (self.state.ambiguous_count >= SUPPLEMENTARY_THRESHOLD
                    and sup_qs
                    and self.state.supplementary_asked < len(sup_qs)):
                logger.info("Agent: triggering supplementary questions (ambiguous={})",
                            self.state.ambiguous_count)
                self.state.in_supplementary = True
                self.state.total_steps += len(sup_qs)
                return self._build_next_question_response()

            self.state.advance_to_analyzing()
            return {
                "stage": "analyzing", "finished": False,
                "next_question": None, "report": None,
                "message": "All questions collected. Analyzing...",
            }

        return self._build_next_question_response()

    def _build_next_question_response(self) -> dict[str, Any]:
        """Build the response for the next question."""
        next_q = self.get_next_question()
        return {
            "stage": "questioning", "finished": False,
            "next_question": next_q, "report": None,
            "message": next_q["title"] if next_q else "",
        }

    def _handle_analyzing(self) -> dict[str, Any]:
        try:
            self.analyze()
        except Exception:
            report = self._generate_fallback_report()
            self.state.report_json = report
            self.state.advance_to_report()
        return self._build_report_response()

    def _build_report_response(self) -> dict[str, Any]:
        return {
            "stage": "report", "finished": True,
            "next_question": None,
            "report": self.state.report_json,
            "message": "Analysis complete!",
        }

    def _build_analysis_user_prompt(self, answers_text: str) -> str:
        return "Please generate a growth analysis report based on the following answers.\n\n## User Answers\n{}\n\n## Requirements\nOutput strictly as JSON following the system prompt format. No extra text.\nBase all analysis on the actual user answers.\n".format(answers_text)

    def _parse_report(self, raw_response: str) -> dict[str, Any]:
        from utils.json_parser import safe_json_parse
        result = safe_json_parse(raw_response)
        if result is None:
            logger.warning("Agent JSON parse failed")
            return self._generate_fallback_report()
        return result

    def _generate_fallback_report(self) -> dict[str, Any]:
        return {
            "type": "{}_report".format(self.agent_type),
            "profile": {},
            "analysis": {"summary": "Analysis unavailable. Please try again."},
            "advantages": [],
            "risks": [],
            "recommendations": [],
            "plan": [],
        }
