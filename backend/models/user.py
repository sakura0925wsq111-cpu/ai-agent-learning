"""User ORM model."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class User(Base):
    """CampusPal user profile."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    nickname: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    avatar: Mapped[str | None] = mapped_column(String(500), nullable=True)
    major: Mapped[str | None] = mapped_column(String(200), nullable=True)
    grade: Mapped[str | None] = mapped_column(String(50), nullable=True)
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
        return f"<User(id={self.id!r}, nickname={self.nickname!r})>"
