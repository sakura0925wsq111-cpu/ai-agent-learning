"""Data structures for decision coach sessions."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class Phase(str, Enum):
    """Agent workflow phases."""

    COLLECT = "collect"
    ANALYZE = "analyze"
    PLAN = "plan"
    RECOMMEND = "recommend"
    MEMORY = "memory"
    DONE = "done"


COLLECT_DIMENSIONS = (
    "background",
    "goal",
    "constraints",
    "preference",
    "risk_tolerance",
)


def now_iso() -> str:
    """Return current local time in ISO format."""
    return datetime.now().replace(microsecond=0).isoformat()


def new_session_id() -> str:
    """Generate a session id like 20260719_104500."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


@dataclass
class Message:
    role: str
    content: str
    phase: str
    structured: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if data["structured"] is None:
            del data["structured"]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Message:
        return cls(
            role=data["role"],
            content=data["content"],
            phase=data["phase"],
            structured=data.get("structured"),
        )


@dataclass
class CollectState:
    covered_dimensions: list[str] = field(default_factory=list)
    turn_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CollectState:
        return cls(
            covered_dimensions=list(data.get("covered_dimensions", [])),
            turn_count=int(data.get("turn_count", 0)),
        )


@dataclass
class Session:
    session_id: str
    decision_question: str
    phase: Phase
    created_at: str
    updated_at: str
    messages: list[Message] = field(default_factory=list)
    collect_state: CollectState = field(default_factory=CollectState)
    analysis: dict[str, Any] | None = None
    options: dict[str, Any] | None = None
    recommendation: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "decision_question": self.decision_question,
            "phase": self.phase.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "messages": [message.to_dict() for message in self.messages],
            "collect_state": self.collect_state.to_dict(),
            "analysis": self.analysis,
            "options": self.options,
            "recommendation": self.recommendation,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Session:
        return cls(
            session_id=data["session_id"],
            decision_question=data["decision_question"],
            phase=Phase(data["phase"]),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            messages=[Message.from_dict(item) for item in data.get("messages", [])],
            collect_state=CollectState.from_dict(data.get("collect_state", {})),
            analysis=data.get("analysis"),
            options=data.get("options"),
            recommendation=data.get("recommendation"),
        )


@dataclass
class ConversationIndexEntry:
    session_id: str
    decision_question: str
    phase: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConversationIndexEntry:
        return cls(
            session_id=data["session_id"],
            decision_question=data["decision_question"],
            phase=data["phase"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )
