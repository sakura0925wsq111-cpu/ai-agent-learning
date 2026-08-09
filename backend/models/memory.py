"""Memory ORM model — key-value store for user profile information.

Supports typed memories (profile, goal, action, fact) with
confidence scoring, source tracking, and conflict history.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, Integer, Float, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base

# Valid memory types. Context memories are session-scoped and may expire.
MEMORY_TYPES = ("profile", "goal", "action", "fact", "context")


class Memory(Base):
    """Persistent memory entry for a user.

    Supports five types:
      - profile: long-term user profile (major, grade, personality...)
      - goal:    growth goals and targets
      - action:  action/behavior records
      - fact:    general facts (default)
      - context: resumable session/handoff context with an expiry time
    """

    __tablename__ = "memories"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    memory_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="fact", index=True
    )
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    importance: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    source: Mapped[str] = mapped_column(Text, nullable=False, default="")
    conflict_history: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_memories_user_key", "user_id", "key", unique=True),
        Index("ix_memories_user_type", "user_id", "memory_type"),
        Index("ix_memories_user_expires", "user_id", "expires_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<Memory(id={self.id!r}, user_id={self.user_id!r}, "
            f"type={self.memory_type!r}, key={self.key!r}, "
            f"value={self.value!r}, confidence={self.confidence})>"
        )
