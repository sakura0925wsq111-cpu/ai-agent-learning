# -*- coding: utf-8 -*-
"""Course ORM model for Today Mode."""

import uuid
from datetime import datetime, date, timezone

from sqlalchemy import String, Text, DateTime, ForeignKey, Date, Integer, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class Course(Base):
    """A course in the user's weekly schedule."""

    __tablename__ = "courses"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    teacher: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    schedule_json: Mapped[str | None] = mapped_column(Text, nullable=True,
        comment="JSON: [{'weekday':1,'start':1,'end':2,'weeks':'1-16周','weeks_parsed':{...}}]"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True, default="#4A90D9")
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="manual",
        comment="manual / pdf_import"
    )
    semester_start: Mapped[date | None] = mapped_column(
        Date, nullable=True,
        comment="Semester start date for week-range calculation"
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
        Index("ix_courses_user_weekday", "user_id", "name"),
    )
