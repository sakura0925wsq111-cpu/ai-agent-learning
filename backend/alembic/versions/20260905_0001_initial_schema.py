"""Create the initial production schema.

Revision ID: 20260905_0001
Revises:
Create Date: 2026-09-05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260905_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("student_id", sa.String(length=50), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("nickname", sa.String(length=100), nullable=False),
        sa.Column("password_hash", sa.String(length=256), nullable=True),
        sa.Column("avatar", sa.String(length=500), nullable=True),
        sa.Column("school", sa.String(length=200), nullable=True),
        sa.Column("college", sa.String(length=200), nullable=True),
        sa.Column("major", sa.String(length=200), nullable=True),
        sa.Column("grade", sa.String(length=50), nullable=True),
        sa.Column("enroll_year", sa.String(length=10), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_student_id", "users", ["student_id"], unique=True)

    op.create_table(
        "courses",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("teacher", sa.String(length=100), nullable=True),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column(
            "schedule_json",
            sa.Text(),
            nullable=True,
            comment="JSON: [{'weekday':1,'start':1,'end':2,'weeks':'1-16周','weeks_parsed':{...}}]",
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("color", sa.String(length=20), nullable=True),
        sa.Column(
            "source",
            sa.String(length=20),
            nullable=False,
            comment="manual / pdf_import",
        ),
        sa.Column(
            "semester_start",
            sa.Date(),
            nullable=True,
            comment="Semester start date for week-range calculation",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_courses_user_id", "courses", ["user_id"], unique=False)
    op.create_index("ix_courses_user_weekday", "courses", ["user_id", "name"], unique=False)

    op.create_table(
        "exams",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("exam_date", sa.Date(), nullable=False),
        sa.Column(
            "start_time", sa.String(length=10), nullable=True, comment="HH:MM"
        ),
        sa.Column(
            "end_time", sa.String(length=10), nullable=True, comment="HH:MM"
        ),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "source",
            sa.String(length=20),
            nullable=False,
            comment="manual / pdf_import",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_exams_user_date", "exams", ["user_id", "exam_date"], unique=False)
    op.create_index("ix_exams_user_id", "exams", ["user_id"], unique=False)

    op.create_table(
        "growth_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("agent_type", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("stage", sa.String(length=20), nullable=False),
        sa.Column("current_step", sa.Integer(), nullable=False),
        sa.Column("total_steps", sa.Integer(), nullable=False),
        sa.Column("finished", sa.Boolean(), nullable=False),
        sa.Column("state_json", sa.Text(), nullable=True),
        sa.Column("answers_json", sa.Text(), nullable=True),
        sa.Column("report_json", sa.Text(), nullable=True),
        sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_growth_sessions_user_created",
        "growth_sessions",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index("ix_growth_sessions_user_id", "growth_sessions", ["user_id"], unique=False)

    op.create_table(
        "import_previews",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("import_type", sa.String(length=20), nullable=False),
        sa.Column("items_json", sa.Text(), nullable=False),
        sa.Column("semester_start", sa.String(length=10), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            comment="pending / done / archived / cancelled",
        ),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_import_previews_user_id", "import_previews", ["user_id"], unique=False)
    op.create_index(
        "ix_import_previews_user_status",
        "import_previews",
        ["user_id", "status"],
        unique=False,
    )

    op.create_table(
        "memories",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("memory_type", sa.String(length=20), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("importance", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("conflict_history", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_memories_expires_at", "memories", ["expires_at"], unique=False)
    op.create_index("ix_memories_memory_type", "memories", ["memory_type"], unique=False)
    op.create_index("ix_memories_user_expires", "memories", ["user_id", "expires_at"], unique=False)
    op.create_index("ix_memories_user_id", "memories", ["user_id"], unique=False)
    op.create_index("ix_memories_user_key", "memories", ["user_id", "key"], unique=True)
    op.create_index("ix_memories_user_type", "memories", ["user_id", "memory_type"], unique=False)

    op.create_table(
        "todos",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("deadline", sa.String(length=50), nullable=True),
        sa.Column(
            "source",
            sa.String(length=50),
            nullable=True,
            comment="manual / teacher / ai_plan",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_todos_user_created", "todos", ["user_id", "created_at"], unique=False)
    op.create_index("ix_todos_user_id", "todos", ["user_id"], unique=False)
    op.create_index("ix_todos_user_status", "todos", ["user_id", "status"], unique=False)

    op.create_table(
        "growth_conversations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("step", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"], ["growth_sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_growth_conv_session_created",
        "growth_conversations",
        ["session_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_growth_conv_user_created",
        "growth_conversations",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_growth_conversations_session_id",
        "growth_conversations",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        "ix_growth_conversations_user_id",
        "growth_conversations",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "growth_reports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("agent_type", sa.String(length=20), nullable=False),
        sa.Column("report_type", sa.String(length=50), nullable=False),
        sa.Column("profile_json", sa.Text(), nullable=True),
        sa.Column("analysis_json", sa.Text(), nullable=True),
        sa.Column("advantages_json", sa.Text(), nullable=True),
        sa.Column("risks_json", sa.Text(), nullable=True),
        sa.Column("recommendations_json", sa.Text(), nullable=True),
        sa.Column("plan_json", sa.Text(), nullable=True),
        sa.Column("full_report_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"], ["growth_sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_growth_reports_session_id", "growth_reports", ["session_id"], unique=True)
    op.create_index(
        "ix_growth_reports_user_created",
        "growth_reports",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index("ix_growth_reports_user_id", "growth_reports", ["user_id"], unique=False)

    op.create_table(
        "plan_tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column(
            "growth_session_id",
            sa.String(length=36),
            nullable=True,
            comment="Source Growth session",
        ),
        sa.Column(
            "growth_report_id",
            sa.String(length=36),
            nullable=True,
            comment="Source Growth report",
        ),
        sa.Column(
            "todo_id",
            sa.String(length=36),
            nullable=False,
            comment="Synced Todo item",
        ),
        sa.Column(
            "phase_key",
            sa.String(length=20),
            nullable=False,
            comment="phase_1 / phase_2 / phase_3 / phase_4",
        ),
        sa.Column(
            "plan_task_index",
            sa.Integer(),
            nullable=False,
            comment="Task index within the phase",
        ),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["growth_report_id"], ["growth_reports.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["growth_session_id"], ["growth_sessions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["todo_id"], ["todos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "growth_session_id",
            "phase_key",
            "plan_task_index",
            name="uq_plan_tasks_growth_phase_index",
        ),
    )
    op.create_index("ix_plan_tasks_growth_report_id", "plan_tasks", ["growth_report_id"], unique=False)
    op.create_index("ix_plan_tasks_growth_session_id", "plan_tasks", ["growth_session_id"], unique=False)
    op.create_index(
        "ix_plan_tasks_session_phase",
        "plan_tasks",
        ["growth_session_id", "phase_key"],
        unique=False,
    )
    op.create_index("ix_plan_tasks_todo", "plan_tasks", ["todo_id"], unique=False)
    op.create_index("ix_plan_tasks_todo_id", "plan_tasks", ["todo_id"], unique=False)
    op.create_index("ix_plan_tasks_user_id", "plan_tasks", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_plan_tasks_user_id", table_name="plan_tasks")
    op.drop_index("ix_plan_tasks_todo_id", table_name="plan_tasks")
    op.drop_index("ix_plan_tasks_todo", table_name="plan_tasks")
    op.drop_index("ix_plan_tasks_session_phase", table_name="plan_tasks")
    op.drop_index("ix_plan_tasks_growth_session_id", table_name="plan_tasks")
    op.drop_index("ix_plan_tasks_growth_report_id", table_name="plan_tasks")
    op.drop_table("plan_tasks")

    op.drop_index("ix_growth_reports_user_id", table_name="growth_reports")
    op.drop_index("ix_growth_reports_user_created", table_name="growth_reports")
    op.drop_index("ix_growth_reports_session_id", table_name="growth_reports")
    op.drop_table("growth_reports")

    op.drop_index("ix_growth_conversations_user_id", table_name="growth_conversations")
    op.drop_index("ix_growth_conversations_session_id", table_name="growth_conversations")
    op.drop_index("ix_growth_conv_user_created", table_name="growth_conversations")
    op.drop_index("ix_growth_conv_session_created", table_name="growth_conversations")
    op.drop_table("growth_conversations")

    op.drop_index("ix_todos_user_status", table_name="todos")
    op.drop_index("ix_todos_user_id", table_name="todos")
    op.drop_index("ix_todos_user_created", table_name="todos")
    op.drop_table("todos")

    op.drop_index("ix_memories_user_type", table_name="memories")
    op.drop_index("ix_memories_user_key", table_name="memories")
    op.drop_index("ix_memories_user_id", table_name="memories")
    op.drop_index("ix_memories_user_expires", table_name="memories")
    op.drop_index("ix_memories_memory_type", table_name="memories")
    op.drop_index("ix_memories_expires_at", table_name="memories")
    op.drop_table("memories")

    op.drop_index("ix_import_previews_user_status", table_name="import_previews")
    op.drop_index("ix_import_previews_user_id", table_name="import_previews")
    op.drop_table("import_previews")

    op.drop_index("ix_growth_sessions_user_id", table_name="growth_sessions")
    op.drop_index("ix_growth_sessions_user_created", table_name="growth_sessions")
    op.drop_table("growth_sessions")

    op.drop_index("ix_exams_user_id", table_name="exams")
    op.drop_index("ix_exams_user_date", table_name="exams")
    op.drop_table("exams")

    op.drop_index("ix_courses_user_weekday", table_name="courses")
    op.drop_index("ix_courses_user_id", table_name="courses")
    op.drop_table("courses")

    op.drop_index("ix_users_student_id", table_name="users")
    op.drop_table("users")
