# -*- coding: utf-8 -*-
"""Sandbox Session — state machine for the DecisionSandbox multi-path comparison workflow.

Phases:
    1. DISCOVERY      — 5-7 rounds of general user profile building
    2. PATH_PROBE     — 1-2 path-specific questions per selected path
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

MAX_DISCOVERY_ROUNDS: int = 7
MIN_DISCOVERY_ROUNDS: int = 5
MAX_PATH_PROBE_ROUNDS: int = 2

# ── Available planning paths that can be compared ──────────────

SANDBOX_PATHS: dict[str, str] = {
    "career": "就业规划",
    "graduate": "考研规划",
    "civil": "考公考编规划",
    "major": "转专业规划",
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

    # ── Phase 1: Discovery ──────────────────────────────────────

    discovery_round: int = 0
    discovery_history: list[dict[str, str]] = field(default_factory=list)
    discovery_answers: dict[str, str] = field(default_factory=dict)
    ambiguous_count: int = 0
    discovery_complete: bool = False

    # User profile accumulated during discovery (generic, cross-path)
    user_profile: dict[str, Any] = field(default_factory=dict)

    # ── Phase 2: Path Probe ─────────────────────────────────────

    path_selections: list[str] = field(default_factory=list)
    # {path_agent_type: [{"q": ..., "a": ...}, ...]}
    path_probe_history: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    path_probe_done: set[str] = field(default_factory=set)

    # ── Phase 3: Parallel Simulation ────────────────────────────

    # {path_agent_type: report_dict}
    path_reports: dict[str, dict[str, Any]] = field(default_factory=dict)
    parallel_sim_complete: bool = False

    # ── Phase 4: Projection ─────────────────────────────────────

    projection_result: dict[str, Any] = field(default_factory=dict)

    # ── Memory snapshot at session start (for consistency) ──────

    memory_snapshot: dict[str, str] = field(default_factory=dict)

    # ── Orchestration ────────────────────────────────────────────

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

    def record_discovery(self, question: str, answer: str) -> None:
        """Record a discovery-phase Q&A pair."""
        self.discovery_answers[question] = answer
        self.discovery_history.append({"q": question, "a": answer})
        self.discovery_round += 1
        if self.is_ambiguous(answer):
            self.ambiguous_count += 1

    def should_continue_discovery(self) -> bool:
        """Determine if more discovery rounds are needed.

        Strategy matches PlanningState:
        - Rounds 1-4: always continue
        - Rounds 5-6: continue only if still ambiguous
        - Round 7: always stop
        """
        if self.discovery_round >= MAX_DISCOVERY_ROUNDS:
            return False
        if self.discovery_round < MIN_DISCOVERY_ROUNDS:
            return True
        return self.ambiguous_count >= 2

    def record_path_probe(self, path_type: str, question: str, answer: str) -> None:
        """Record a path-specific probe Q&A pair."""
        if path_type not in self.path_probe_history:
            self.path_probe_history[path_type] = []
        self.path_probe_history[path_type].append({"q": question, "a": answer})

    def path_probe_rounds(self, path_type: str) -> int:
        """Return how many probe rounds have been done for a path."""
        return len(self.path_probe_history.get(path_type, []))

    def build_discovery_context(self) -> str:
        """Assemble discovery history as a string for prompt injection."""
        if not self.discovery_history:
            return "（暂无对话记录）"
        lines = ["## 发现层对话记录"]
        for i, entry in enumerate(self.discovery_history, 1):
            lines.append(f"Q{i}: {entry['q']}")
            lines.append(f"A{i}: {entry['a']}")
        return "\n".join(lines)

    def build_user_context_for_agent(self) -> str:
        """Build context string for injection into a planning agent.

        Combines user profile, discovery history, and path-specific probes.
        """
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

    def to_dict(self) -> dict[str, Any]:
        """Serialize session to a JSON-safe dict."""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "current_phase": self.current_phase.value,
            "phase_index": self.phase_index,
            "finished": self.finished,
            "error_message": self.error_message,
            "discovery_round": self.discovery_round,
            "discovery_history": self.discovery_history,
            "discovery_answers": self.discovery_answers,
            "ambiguous_count": self.ambiguous_count,
            "discovery_complete": self.discovery_complete,
            "user_profile": self.user_profile,
            "path_selections": self.path_selections,
            "path_probe_history": self.path_probe_history,
            "path_probe_done": list(self.path_probe_done),
            "path_reports": self.path_reports,
            "parallel_sim_complete": self.parallel_sim_complete,
            "projection_result": self.projection_result,
            "memory_snapshot": self.memory_snapshot,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SandboxSession":
        """Restore session from a serialized dict."""
        session = cls(
            session_id=data.get("session_id", ""),
            user_id=data.get("user_id", ""),
            phase_index=data.get("phase_index", 0),
            finished=data.get("finished", False),
            error_message=data.get("error_message", ""),
            discovery_round=data.get("discovery_round", 0),
            discovery_history=data.get("discovery_history", []),
            discovery_answers=data.get("discovery_answers", {}),
            ambiguous_count=data.get("ambiguous_count", 0),
            discovery_complete=data.get("discovery_complete", False),
            user_profile=data.get("user_profile", {}),
            path_selections=data.get("path_selections", []),
            path_probe_history=data.get("path_probe_history", {}),
            path_probe_done=set(data.get("path_probe_done", [])),
            path_reports=data.get("path_reports", {}),
            parallel_sim_complete=data.get("parallel_sim_complete", False),
            projection_result=data.get("projection_result", {}),
            memory_snapshot=data.get("memory_snapshot", {}),
        )
        phase_str = data.get("current_phase", "discovery")
        try:
            session.current_phase = SandboxPhase(phase_str)
        except ValueError:
            session.current_phase = SandboxPhase.DISCOVERY
        return session
