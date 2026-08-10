"""User ORM model."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class User(Base):
    """iCampus user profile."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    student_id: Mapped[str | None] = mapped_column(
        String(50), unique=True, nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    nickname: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    password_hash: Mapped[str | None] = mapped_column(String(256), nullable=True)
    avatar: Mapped[str | None] = mapped_column(String(500), nullable=True)
    school: Mapped[str | None] = mapped_column(String(200), nullable=True)
    college: Mapped[str | None] = mapped_column(String(200), nullable=True)
    major: Mapped[str | None] = mapped_column(String(200), nullable=True)
    grade: Mapped[str | None] = mapped_column(String(50), nullable=True)
    enroll_year: Mapped[str | None] = mapped_column(String(10), nullable=True)
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

    def __repr__(self) -> str:
        return f"<User(id={self.id!r}, name={self.name!r})>"
