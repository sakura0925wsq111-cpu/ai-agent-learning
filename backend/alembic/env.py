"""Alembic runtime configuration for iCampus."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, create_engine, pool

import models  # noqa: F401 - register every ORM model on Base.metadata
from core.config import settings
from database.base import Base
from database.session import resolve_database_url


config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _configure(connection: Connection | None = None, *, url: str | None = None) -> None:
    context.configure(
        connection=connection,
        url=url,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        transaction_per_migration=True,
        literal_binds=connection is None,
        dialect_opts={"paramstyle": "named"} if connection is None else None,
    )


def run_migrations_offline() -> None:
    _configure(url=resolve_database_url(settings.database_url))
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    provided_connection = config.attributes.get("connection")
    if provided_connection is not None:
        _configure(provided_connection)
        with context.begin_transaction():
            context.run_migrations()
        return

    connectable = create_engine(
        resolve_database_url(settings.database_url),
        poolclass=pool.NullPool,
        future=True,
    )
    with connectable.connect() as connection:
        _configure(connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
