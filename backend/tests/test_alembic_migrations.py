from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, inspect

import database.session as database_session
import models  # noqa: F401 - populate metadata
from database.base import Base


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _alembic_config(connection) -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.attributes["connection"] = connection
    return config


def test_production_schema_guard_rejects_an_unversioned_database(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{(tmp_path / 'unversioned.db').as_posix()}")
    try:
        monkeypatch.setattr(database_session, "engine", engine)
        with pytest.raises(RuntimeError, match="not at Alembic head"):
            database_session.assert_database_schema_current()
    finally:
        engine.dispose()


def test_initial_migration_matches_orm_metadata(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{(tmp_path / 'migration.db').as_posix()}")
    try:
        with engine.begin() as connection:
            command.upgrade(_alembic_config(connection), "head")

        tables = set(inspect(engine).get_table_names())
        assert set(Base.metadata.tables).issubset(tables)
        assert "alembic_version" in tables

        with engine.begin() as connection:
            command.check(_alembic_config(connection))

        monkeypatch.setattr(database_session, "engine", engine)
        database_session.assert_database_schema_current()
    finally:
        engine.dispose()


def test_initial_migration_can_downgrade_and_reapply(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'roundtrip.db').as_posix()}")
    try:
        with engine.begin() as connection:
            command.upgrade(_alembic_config(connection), "head")
        with engine.begin() as connection:
            command.downgrade(_alembic_config(connection), "base")
        assert set(inspect(engine).get_table_names()) == {"alembic_version"}
        with engine.begin() as connection:
            command.upgrade(_alembic_config(connection), "head")
        assert set(Base.metadata.tables).issubset(inspect(engine).get_table_names())
    finally:
        engine.dispose()
