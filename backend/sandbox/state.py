# -*- coding: utf-8 -*-
"""Sandbox Session — state machine for the DecisionSandbox multi-path comparison workflow.

Phases:
    1. DISCOVERY      — analysis plus up to 3 high-value clarifications
    2. PATH_PROBE     — at most 1 path-specific clarification per selected path
    3. PARALLEL_SIM   — Inject context into each planning agent, generate reports
    4. PROJECTION     — ProjectionAgent compares N reports + timeline projections
    5. COMPLETED      — Final result ready

All conversation data is written to Memory DB for cross-session continuity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SandboxPhase(str, Enum):
    DISCOVERY = "discovery"
    PATH_PROBE = "path_probe"
    PARALLEL_SIM = "parallel_sim"
    PROJECTION = "projection"
    COMPLETED = "completed"
    ERROR = "error"


PHASE_ORDER: list[SandboxPhase] = [
    SandboxPhase.DISCOVERY,
    SandboxPhase.PATH_PROBE,
    SandboxPhase.PARALLEL_SIM,
    SandboxPhase.PROJECTION,
    SandboxPhase.COMPLETED,
]

MAX_DISCOVERY_ROUNDS: int = 3
MIN_DISCOVERY_ROUNDS: int = 0
MAX_PATH_PROBE_ROUNDS: int = 1
MAX_TOTAL_QUESTIONS: int = 5

# ── Canonical path registry (single source of truth) ──────────

SANDBOX_PATHS: dict[str, str] = {
    "career": "就业规划",
    "graduate": "考研规划",
    "civil": "考公考编规划",
    "major": "转专业规划",
}

SANDBOX_PATH_LIST_STR: str = "、".join(SANDBOX_PATHS.values())

# ── Keyword-to-path matching for parsing user selections ───────

PATH_KEYWORDS: dict[str, list[str]] = {
    "career": [
        "就业", "工作", "求职", "上班", "职业", "校招", "社招", "offer",
        "打工", "实习",
    ],
    "graduate": [
        "考研", "读研", "研究生", "深造", "硕士", "备考", "学历提升",
    ],
    "civil": [
        "考公", "考编", "公务员", "体制", "事业编", "铁饭碗", "稳定",
        "公职", "国考", "省考",
    ],
    "major": [
        "转专业", "换专业", "跨专业", "辅修", "不喜欢现在的专业",
    ],
}

# ── Ambiguous answer patterns (reused from PlanningState) ──────

AMBIGUOUS_PATTERNS: frozenset[str] = frozenset({
    "不知道", "都行", "随便", "无所谓", "不确定",
    "看看再说", "看情况", "没想好", "不清楚",
    "都差不多", "都可以", "再说吧", "还没考虑",
})


@dataclass
class SandboxSession:
    """State machine for the DecisionSandbox multi-path comparison.

    Tracks progress through the 4-phase workflow, collects user profile,
    orchestrates parallel planning agents, and stores the final projection result.
    """

    session_id: str = ""
    user_id: str = ""
    current_phase: SandboxPhase = SandboxPhase.DISCOVERY
    phase_index: int = 0
    finished: bool = False
    error_message: str = ""

    # ── Phase 1: Discovery ─────────────────────────────────────

    discovery_round: int = 0
    discovery_history: list[dict[str, str]] = field(default_factory=list)
    discovery_answers: dict[str, str] = field(default_factory=dict)
    ambiguous_count: int = 0
    discovery_complete: bool = False
    user_profile: dict[str, Any] = field(default_factory=dict)
    # The question/response shown on the preceding turn.  Keeping these
    # separately prevents us from pairing a user's current answer with the
    # *new* question generated after that answer.
    last_discovery_question: str = ""
    last_discovery_response: str = ""
    questions_asked: int = 0

    # ── Phase 2: Path Probe ────────────────────────────────────

    path_selections: list[str] = field(default_factory=list)
    path_probe_history: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    path_probe_done: set[str] = field(default_factory=set)

    # ── Phase 3: Parallel Simulation ───────────────────────────

    path_reports: dict[str, dict[str, Any]] = field(default_factory=dict)
    parallel_sim_complete: bool = False

    # ── Phase 4: Projection ────────────────────────────────────

    projection_result: dict[str, Any] = field(default_factory=dict)

    # ── Memory ─────────────────────────────────────────────────

    memory_snapshot: dict[str, str] = field(default_factory=dict)

    # ── Serialized fields (single source of truth for to_dict/from_dict) ─

    _SERIALIZED_FIELDS: tuple[str, ...] = (
        "session_id", "user_id", "current_phase", "phase_index", "finished",
        "error_message", "discovery_round", "discovery_history", "discovery_answers",
        "ambiguous_count", "discovery_complete", "user_profile",
        "last_discovery_question", "last_discovery_response", "questions_asked",
        "path_selections",
        "path_probe_history", "path_probe_done", "path_reports",
        "parallel_sim_complete", "projection_result", "memory_snapshot",
    )

    # ── Phase control ──────────────────────────────────────────

    def advance_phase(self) -> SandboxPhase:
        """Move to the next phase in the workflow."""
        if self.phase_index < len(PHASE_ORDER) - 1:
            self.phase_index += 1
        else:
            self.finished = True
        self.current_phase = PHASE_ORDER[min(self.phase_index, len(PHASE_ORDER) - 1)]
        return self.current_phase

    def set_phase(self, phase: SandboxPhase) -> None:
        """Jump to a specific phase."""
        try:
            self.phase_index = PHASE_ORDER.index(phase)
        except ValueError:
            self.phase_index = len(PHASE_ORDER) - 1
        self.current_phase = phase

    def is_ambiguous(self, text: str) -> bool:
        """Check if an answer is ambiguous / non-committal."""
        if not text or not text.strip():
            return True
        cleaned = text.strip()
        return any(p in cleaned for p in AMBIGUOUS_PATTERNS)

    def record_discovery(
        self,
        question: str,
        answer: str,
        *,
        previous_response: str = "",
    ) -> None:
        """Record the user's answer against the question they actually saw."""
        self.discovery_answers[question] = answer
        entry = {"q": question, "a": answer}
        if previous_response:
            entry["response"] = previous_response
        self.discovery_history.append(entry)
        self.discovery_round += 1
        if self.is_ambiguous(answer):
            self.ambiguous_count += 1

    def should_continue_discovery(self) -> bool:
        """Return whether the hard discovery cap still allows another turn."""
        return self.discovery_round < MAX_DISCOVERY_ROUNDS

    def can_ask_more(self) -> bool:
        """Apply the five-question cap across the complete sandbox chain."""
        return self.questions_asked < MAX_TOTAL_QUESTIONS

    def mark_question_asked(self, text: str = "") -> bool:
        """Count a question only when it is actually shown to the user."""
        if not text or not self.can_ask_more():
            return False
        self.questions_asked += 1
        return True

    def record_path_probe(self, path_type: str, question: str, answer: str) -> None:
        """Record a path-specific probe Q&A pair."""
        if path_type not in self.path_probe_history:
            self.path_probe_history[path_type] = []
        self.path_probe_history[path_type].append({"q": question, "a": answer})

    def path_probe_rounds(self, path_type: str) -> int:
        """Return how many probe rounds have been done for a path."""
        return len(self.path_probe_history.get(path_type, []))

    # ── Context builders ───────────────────────────────────────

    def build_discovery_context(self) -> str:
        """Assemble discovery history as a string for prompt injection."""
        if not self.discovery_history:
            return "（暂无对话记录）"
        lines = ["## 发现层对话记录"]
        for i, entry in enumerate(self.discovery_history, 1):
            previous_response = str(entry.get("response", "")).strip()
            if previous_response:
                lines.append(f"AI{i}: {previous_response}")
            question = str(entry.get("q", "")).strip()
            if question and question != "用户主动说明":
                lines.append(f"Q{i}: {question}")
            lines.append(f"用户{i}: {entry['a']}")
        return "\n".join(lines)

    def build_user_context_for_agent(self) -> str:
        """Build context string for injection into a planning agent."""
        parts: list[str] = []
        if self.user_profile:
            parts.append("## 用户通用画像")
            for k, v in self.user_profile.items():
                parts.append(f"- {k}: {v}")
        if self.discovery_history:
            parts.append("\n## 发现层对话记录")
            for i, entry in enumerate(self.discovery_history, 1):
                parts.append(f"Q{i}: {entry['q']}")
                parts.append(f"A{i}: {entry['a']}")
        if self.memory_snapshot:
            parts.append("\n## 用户历史记忆")
            for k, v in self.memory_snapshot.items():
                parts.append(f"- {k}: {v}")
        return "\n".join(parts)

    # ── Serialization (driven by _SERIALIZED_FIELDS) ───────────

    def to_dict(self) -> dict[str, Any]:
        """Serialize session to a JSON-safe dict.

        All field names are derived from _SERIALIZED_FIELDS — add a field
        there and it is automatically included in serialization.
        """
        result: dict[str, Any] = {}
        for field_name in self._SERIALIZED_FIELDS:
            val = getattr(self, field_name)
            if isinstance(val, SandboxPhase):
                result[field_name] = val.value
            elif isinstance(val, set):
                result[field_name] = list(val)
            else:
                result[field_name] = val
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SandboxSession":
        """Restore session from a serialized dict.

        Uses _SERIALIZED_FIELDS to determine which fields to restore,
        keeping deserialization in sync with to_dict automatically.
        """
        kw: dict[str, Any] = {}
        for field_name in cls._SERIALIZED_FIELDS:
            val = data.get(field_name)
            if field_name == "path_probe_done":
                kw[field_name] = set(val) if isinstance(val, list) else set()
            elif field_name == "current_phase":
                try:
                    kw[field_name] = SandboxPhase(val) if val else SandboxPhase.DISCOVERY
                except ValueError:
                    kw[field_name] = SandboxPhase.DISCOVERY
            elif val is not None:
                kw[field_name] = val
            else:
                kw[field_name] = cls._default_for(field_name)
        return cls(**kw)

    @staticmethod
    def _default_for(field_name: str) -> Any:
        """Return the default value for a field (used when data is missing)."""
        defaults: dict[str, Any] = {
            "session_id": "", "user_id": "", "phase_index": 0,
            "finished": False, "error_message": "",
            "discovery_round": 0, "discovery_answers": {},
            "discovery_history": [], "ambiguous_count": 0,
            "discovery_complete": False, "user_profile": {},
            "last_discovery_question": "", "last_discovery_response": "",
            "questions_asked": 0,
            "path_selections": [], "path_probe_history": {},
            "path_reports": {}, "parallel_sim_complete": False,
            "projection_result": {}, "memory_snapshot": {},
        }
        return defaults.get(field_name, "")
