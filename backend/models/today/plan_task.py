# -*- coding: utf-8 -*-
"""PlanTask bridge model — links GrowthReport plans to daily Todo items.

This is the core bridge between Growth Mode and Today Mode.
When a user confirms a growth plan, each task gets a Todo (Today) and
a PlanTask record (for bidirectional traceability).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, ForeignKey, Integer, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class PlanTask(Base):
    """Bridges a GrowthReport action-plan task to a concrete Todo item.

    Allows:
      - Tracing a Todo back to its source Growth session & phase
      - Querying progress per phase for Growth Agent feedback
      - Preventing duplicate sync (idempotency via unique constraint)
    """

    __tablename__ = "plan_tasks"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    growth_session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("growth_sessions.id", ondelete="SET NULL"),
        nullable=True, index=True, comment="Source Growth session"
    )
    growth_report_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("growth_reports.id", ondelete="SET NULL"),
        nullable=True, index=True, comment="Source Growth report"
    )
    todo_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("todos.id", ondelete="CASCADE"),
        nullable=False, index=True, comment="Synced Todo item"
    )
    phase_key: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="phase_1 / phase_2 / phase_3 / phase_4"
    )
    plan_task_index: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Task index within the phase"
    )
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_plan_tasks_todo", "todo_id"),
        Index("ix_plan_tasks_session_phase", "growth_session_id", "phase_key"),
        UniqueConstraint(
            "user_id", "growth_session_id", "phase_key", "plan_task_index",
            name="uq_plan_tasks_growth_phase_index",
        ),
    )
