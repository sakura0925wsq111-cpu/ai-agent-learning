# -*- coding: utf-8 -*-
"""Exam ORM model for Today Mode."""

import uuid
from datetime import datetime, date, timezone

from sqlalchemy import String, Text, DateTime, ForeignKey, Date, Time, Index
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class Exam(Base):
    """An exam event for the user."""

    __tablename__ = "exams"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    exam_date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[str | None] = mapped_column(String(10), nullable=True, comment="HH:MM")
    end_time: Mapped[str | None] = mapped_column(String(10), nullable=True, comment="HH:MM")
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="manual",
        comment="manual / pdf_import"
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
        Index("ix_exams_user_date", "user_id", "exam_date"),
    )
