"""Database factory and numbered SQL migration runner."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from .config import DEFAULT_DATABASE_URL, ensure_data_directories


class CareerDataDatabase:
    """Owns the isolated career-data engine and migration lifecycle."""

    def __init__(self, database_url: str | None = None) -> None:
        ensure_data_directories()
        self.database_url = database_url or DEFAULT_DATABASE_URL
        connect_args = {"check_same_thread": False} if self.database_url.startswith("sqlite") else {}
        self.engine: Engine = create_engine(
            self.database_url, connect_args=connect_args, pool_pre_ping=True
        )
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)

    def session(self) -> Session:
        return self.session_factory()

    def migrate(self) -> list[str]:
        """Apply every not-yet-applied numbered SQL migration atomically."""
        migrations_dir = Path(__file__).with_name("migrations")
        applied: list[str] = []
        with self.engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version VARCHAR(100) PRIMARY KEY, applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            ))
            known = set(connection.execute(text("SELECT version FROM schema_migrations")).scalars())
            for path in sorted(migrations_dir.glob("*.sql")):
                if path.name in known:
                    continue
                sql = path.read_text(encoding="utf-8")
                if self.engine.dialect.name == "sqlite":
                    raw = connection.connection.driver_connection
                    raw.executescript(sql)
                else:
                    for statement in filter(str.strip, sql.split(";")):
                        connection.execute(text(statement))
                connection.execute(
                    text("INSERT INTO schema_migrations(version) VALUES (:version)"),
                    {"version": path.name},
                )
                applied.append(path.name)
        return applied
