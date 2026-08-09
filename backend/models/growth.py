# -*- coding: utf-8 -*-
"""Growth Agent ORM models: GrowthSession, GrowthConversation, GrowthReport.

GrowthSession:   Tracks an agent session lifecycle.
GrowthConversation: Individual messages within a session.
GrowthReport:    Stores the final structured analysis report.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime, ForeignKey, Integer, Float, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base


class GrowthSession(Base):
    """A growth agent session tracking the full agent lifecycle.

    Lifecycle:
        active -> analyzing -> completed
    """

    __tablename__ = "growth_sessions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    agent_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="career"
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="active"
    )
    stage: Mapped[str] = mapped_column(
        String(20), nullable=False, default="questioning"
    )
    current_step: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_steps: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    finished: Mapped[bool] = mapped_column(default=False)
    state_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    answers_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
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

    # Relationships
    conversations: Mapped[list["GrowthConversation"]] = relationship(
        "GrowthConversation", back_populates="session", cascade="all, delete-orphan"
    )
    report: Mapped["GrowthReport | None"] = relationship(
        "GrowthReport", back_populates="session", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_growth_sessions_user_created", "user_id", "created_at"),
    )

    def __repr__(self) -> str:
        return "<GrowthSession(id={!r}, user_id={!r}, agent={!r}, status={!r})>".format(
            self.id, self.user_id, self.agent_type, self.status
        )


class GrowthConversation(Base):
    """A single message exchange within a growth session.

    Stores both user replies and agent questions/responses.
    """

    __tablename__ = "growth_conversations"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("growth_sessions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    step: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stage: Mapped[str] = mapped_column(String(20), nullable=False, default="questioning")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationship
    session: Mapped["GrowthSession"] = relationship("GrowthSession", back_populates="conversations")

    __table_args__ = (
        Index("ix_growth_conv_session_created", "session_id", "created_at"),
        Index("ix_growth_conv_user_created", "user_id", "created_at"),
    )

    def __repr__(self) -> str:
        return "<GrowthConversation(id={!r}, session_id={!r}, role={!r})>".format(
            self.id, self.session_id, self.role
        )


class GrowthReport(Base):
    """The final structured growth report for a completed session.

    One report per session (one-to-one).
    """

    __tablename__ = "growth_reports"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("growth_sessions.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    agent_type: Mapped[str] = mapped_column(String(20), nullable=False)
    report_type: Mapped[str] = mapped_column(String(50), nullable=False)
    profile_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    advantages_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    risks_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendations_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    plan_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    full_report_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationship
    session: Mapped["GrowthSession"] = relationship("GrowthSession", back_populates="report")

    __table_args__ = (
        Index("ix_growth_reports_user_created", "user_id", "created_at"),
    )

    def __repr__(self) -> str:
        return "<GrowthReport(id={!r}, session_id={!r}, agent={!r})>".format(
            self.id, self.session_id, self.agent_type
        )
