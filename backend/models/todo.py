# -*- coding: utf-8 -*-
"""Todo ORM model for task management."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime, ForeignKey, Integer, Index
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class Todo(Base):
    """A user todo item with a recoverable execution lifecycle."""

    __tablename__ = "todos"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending",
        comment="pending / done / archived / cancelled"
    )
    deadline: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source: Mapped[str | None] = mapped_column(
        String(50), nullable=True, default="manual",
        comment="manual / teacher / ai_plan"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_todos_user_status", "user_id", "status"),
        Index("ix_todos_user_created", "user_id", "created_at"),
    )
