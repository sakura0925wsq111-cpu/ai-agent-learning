"""Memory ORM model — key-value store for user profile information."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, Integer, Float, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class Memory(Base):
    """Persistent memory entry for a user (e.g., major=交通工程, goal=考研)."""

    __tablename__ = "memories"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    importance: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    source: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_memories_user_key", "user_id", "key", unique=True),
    )

    def __repr__(self) -> str:
        return f"<Memory(id={self.id!r}, user_id={self.user_id!r}, key={self.key!r}, value={self.value!r}, confidence={self.confidence})>"
