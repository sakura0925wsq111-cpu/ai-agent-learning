"""Database engine and session management.

Uses SQLAlchemy 2.0 style with a sessionmaker factory.
The get_db dependency yields a session per request and closes it automatically.
"""

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from core.config import PROJECT_ROOT, settings


def resolve_database_url(database_url: str) -> str:
    """Resolve repository-relative SQLite URLs while leaving server URLs intact."""
    if not database_url.startswith("sqlite:///"):
        return database_url

    db_path = database_url.removeprefix("sqlite:///")
    path = Path(db_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path.resolve().as_posix()}"


def _create_engine() -> Engine:
    """Create a SQLAlchemy engine from settings."""
    connect_args: dict = {}
    if settings.database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    database_url = resolve_database_url(settings.database_url)

    return create_engine(
        database_url,
        # SQL parameter echo can expose password hashes and private user data.
        echo=False,
        connect_args=connect_args,
        pool_pre_ping=True,
    )


engine = _create_engine()

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


def get_db() -> Generator[Session, None, None]:
    """Yield a database session and ensure it is closed after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Prepare the schema for the configured environment.

    Production schema changes are owned by Alembic and must run as a separate
    deployment step. Development and tests retain the legacy bootstrap path so
    existing local SQLite databases continue to work.
    """
    from database.base import Base
    from sqlalchemy import inspect, text
    from loguru import logger

    if settings.is_production:
        assert_database_schema_current()
        logger.info("Verified production database at the current Alembic head.")
        return

    Base.metadata.create_all(bind=engine)

    inspector = inspect(engine)

    # ── Users table migrations ──
    if "users" in inspector.get_table_names():
        existing_cols = {c["name"] for c in inspector.get_columns("users")}
        user_migrations = {
            "student_id": "ALTER TABLE users ADD COLUMN student_id VARCHAR(50)",
            "name": "ALTER TABLE users ADD COLUMN name VARCHAR(100) NOT NULL DEFAULT ''",
            "password_hash": "ALTER TABLE users ADD COLUMN password_hash VARCHAR(256)",
            "school": "ALTER TABLE users ADD COLUMN school VARCHAR(200)",
            "college": "ALTER TABLE users ADD COLUMN college VARCHAR(200)",
            "enroll_year": "ALTER TABLE users ADD COLUMN enroll_year VARCHAR(10)",
        }
        with engine.connect() as conn:
            for col_name, sql in user_migrations.items():
                if col_name not in existing_cols:
                    logger.info("Running migration: {}", sql)
                    conn.execute(text(sql))
                    conn.commit()
                    logger.info("Migration complete for column: {}", col_name)
            # Add unique index on student_id if column exists
            if "student_id" in existing_cols or any(
                c in existing_cols for c in user_migrations
            ):
                try:
                    conn.execute(text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_student_id ON users(student_id)"
                    ))
                    conn.commit()
                except Exception:
                    pass

    # ── Memories table migrations ──
    if "memories" in inspector.get_table_names():
        existing_cols = {c["name"] for c in inspector.get_columns("memories")}
        migrations = {
            "confidence": "ALTER TABLE memories ADD COLUMN confidence FLOAT NOT NULL DEFAULT 1.0",
            "source": "ALTER TABLE memories ADD COLUMN source TEXT NOT NULL DEFAULT ''",
            "conflict_history": "ALTER TABLE memories ADD COLUMN conflict_history TEXT NOT NULL DEFAULT '[]'",
            "expires_at": "ALTER TABLE memories ADD COLUMN expires_at DATETIME",
        }
        with engine.connect() as conn:
            for col_name, sql in migrations.items():
                if col_name not in existing_cols:
                    logger.info("Running migration: {}", sql)
                    conn.execute(text(sql))
                    conn.commit()
                    logger.info("Migration complete for column: {}", col_name)
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_memories_user_expires ON memories(user_id, expires_at)"
            ))
            conn.commit()

    # ── Courses table migrations ──
    if "courses" in inspector.get_table_names():
        existing_cols = {c["name"] for c in inspector.get_columns("courses")}
        if "semester_start" not in existing_cols:
            sql = "ALTER TABLE courses ADD COLUMN semester_start DATE"
            with engine.connect() as conn:
                logger.info("Running migration: {}", sql)
                conn.execute(text(sql))
                conn.commit()
                logger.info("Migration complete for column: semester_start")

    # ── Growth → Today bridge indexes ──
    # New databases receive this constraint from SQLAlchemy metadata.  Existing
    # SQLite databases need an explicit index because create_all never mutates
    # an already-created table.
    if "plan_tasks" in inspector.get_table_names():
        with engine.connect() as conn:
            try:
                conn.execute(text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS "
                    "uq_plan_tasks_growth_phase_index "
                    "ON plan_tasks(user_id, growth_session_id, phase_key, plan_task_index)"
                ))
                conn.commit()
            except Exception as exc:
                # Do not prevent application startup if a legacy database
                # already contains duplicates. The service remains idempotent
                # and the conflict is surfaced in logs for manual cleanup.
                logger.warning("Plan-task unique index migration skipped: {}", exc)

    # Seed only after legacy user columns have been migrated.
    if settings.demo_account_enabled and settings.app_env in {"dev", "test"}:
        from models.user import User
        from utils.auth import hash_password

        with SessionLocal() as db:
            existing_demo = db.query(User).filter(
                User.student_id == settings.demo_student_id
            ).first()
            if existing_demo is None:
                db.add(User(
                    student_id=settings.demo_student_id,
                    name="演示同学",
                    nickname="演示同学",
                    password_hash=hash_password(settings.demo_password),
                    school="某理工大学",
                    college="信息与控制工程学院",
                    major="计算机科学与技术",
                    enroll_year="2023",
                    grade="大三",
                ))
                db.commit()
                logger.info("Demo account initialized: {}", settings.demo_student_id)


def assert_database_schema_current() -> None:
    """Refuse production startup when the database is not at Alembic head."""
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    scripts = ScriptDirectory.from_config(config)
    expected = set(scripts.get_heads())
    with engine.connect() as connection:
        current = set(MigrationContext.configure(connection).get_current_heads())

    if current != expected:
        raise RuntimeError(
            "database schema is not at Alembic head: "
            f"current={sorted(current)}, expected={sorted(expected)}; "
            "run `python -m alembic -c alembic.ini upgrade head` before startup"
        )
