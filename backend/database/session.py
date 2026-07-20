"""Database engine and session management.

Uses SQLAlchemy 2.0 style with a sessionmaker factory.
The get_db dependency yields a session per request and closes it automatically.
"""

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from core.config import PROJECT_ROOT, settings


# ── Engine (connection pool) ────────────────────────────────────
# `echo` logs all SQL — great for learning, disable in production
# `connect_args` is SQLite-specific; remove when switching to PostgreSQL


def _create_engine() -> Engine:
    """Create a SQLAlchemy engine from settings.

    For SQLite, ensure the parent directory exists and set
    check_same_thread=False for FastAPI compatibility.
    When switching to PostgreSQL, remove the connect_args entirely.
    """
    connect_args: dict = {}
    if settings.database_url.startswith("sqlite"):
        # SQLite relative path → resolve relative to PROJECT_ROOT
        db_path = settings.database_url.replace("sqlite:///", "")
        # If still relative, make absolute
        if not Path(db_path).is_absolute():
            db_path = str(PROJECT_ROOT / db_path)
        # Ensure the parent directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        connect_args["check_same_thread"] = False
        database_url = f"sqlite:///{db_path}"
    else:
        database_url = settings.database_url

    return create_engine(
        database_url,
        echo=settings.debug,        # Log SQL in debug mode
        connect_args=connect_args,  # SQLite-specific
        pool_pre_ping=True,          # Verify connections before use
    )


engine = _create_engine()


# ── Session factory ─────────────────────────────────────────────

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


# ── FastAPI dependency ──────────────────────────────────────────


def get_db() -> Generator[Session, None, None]:
    """Yield a database session and ensure it's closed after the request.

    Usage in FastAPI routes:
        @router.get("/users")
        def list_users(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Initialization ──────────────────────────────────────────────


def init_db() -> None:
    """Create all tables and run column migrations.

    Called on application startup.
    Safe to call repeatedly  won't drop existing data.
    Adds missing columns for schema evolution.
    """
    from database.base import Base  # noqa: F811
    from sqlalchemy import inspect, text

    Base.metadata.create_all(bind=engine)

    # ── Schema migrations (add columns if they don't exist) ──
    from loguru import logger

    inspector = inspect(engine)
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
