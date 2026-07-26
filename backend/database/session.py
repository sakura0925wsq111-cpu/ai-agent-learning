"""Database engine and session management.

Uses SQLAlchemy 2.0 style with a sessionmaker factory.
The get_db dependency yields a session per request and closes it automatically.
"""

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from core.config import PROJECT_ROOT, settings


def _create_engine() -> Engine:
    """Create a SQLAlchemy engine from settings."""
    connect_args: dict = {}
    if settings.database_url.startswith("sqlite"):
        db_path = settings.database_url.replace("sqlite:///", "")
        if not Path(db_path).is_absolute():
            db_path = str(PROJECT_ROOT / db_path)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        connect_args["check_same_thread"] = False
        database_url = f"sqlite:///{db_path}"
    else:
        database_url = settings.database_url

    return create_engine(
        database_url,
        echo=settings.debug,
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
    """Create all tables and run column migrations.

    Called on application startup.
    Safe to call repeatedly - won't drop existing data.
    Adds missing columns for schema evolution.
    """
    from database.base import Base
    from sqlalchemy import inspect, text
    from loguru import logger

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
        }
        with engine.connect() as conn:
            for col_name, sql in migrations.items():
                if col_name not in existing_cols:
                    logger.info("Running migration: {}", sql)
                    conn.execute(text(sql))
                    conn.commit()
                    logger.info("Migration complete for column: {}", col_name)
