from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models  # noqa: F401
from app.main import app
from core.config import Settings
from database.base import Base
from database.session import get_db
from models.today import Course, ImportPreview
from models.user import User
from services.llm_service import LLMService
from utils.auth import create_token, hash_password


@pytest.fixture()
def api():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app), session_factory
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def _user(session_factory, label: str) -> tuple[str, dict[str, str]]:
    with session_factory() as db:
        user = User(
            student_id=f"{label}-{uuid.uuid4().hex[:8]}",
            name=label,
            nickname=label,
            password_hash=hash_password("secure-pass"),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id
    return user_id, {"Authorization": f"Bearer {create_token(user_id)}"}


def test_production_configuration_rejects_missing_or_unsafe_secrets():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="prod",
            debug=False,
            jwt_secret_key="short",
            DEEPSEEK_API_KEY="configured",
            cors_origins="https://app.example.com",
            demo_account_enabled=False,
        )

    valid = Settings(
        _env_file=None,
        app_env="prod",
        debug=False,
        jwt_secret_key="x" * 32,
        DEEPSEEK_API_KEY="configured",
        cors_origins="https://app.example.com",
        demo_account_enabled=False,
    )
    assert valid.is_production
    assert valid.cors_allowed_origins == ["https://app.example.com"]


def test_health_and_readiness_probes_are_separate(api):
    client, _ = api
    health = client.get("/health")
    ready = client.get("/ready")
    assert health.status_code == 200
    assert health.json()["data"] == {"status": "healthy"}
    assert ready.status_code == 200
    assert ready.json()["data"]["checks"]["database"]["ok"] is True


def test_import_confirmation_is_persistent_owner_scoped_and_idempotent(api):
    client, session_factory = api
    owner, owner_headers = _user(session_factory, "owner")
    _, other_headers = _user(session_factory, "other")
    items = [{
        "name": "人工智能导论",
        "teacher": "张老师",
        "location": "主教学楼",
        "schedule": [{"weekday": 1, "start": 1, "end": 2, "weeks": "1-16周"}],
    }]
    with session_factory() as db:
        preview = ImportPreview(
            user_id=owner,
            import_type="course",
            items_json=json.dumps(items, ensure_ascii=False),
            semester_start="2026-09-01",
            status="pending",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
        db.add(preview)
        db.commit()
        preview_id = preview.id

    forbidden = client.get(
        f"/api/v1/today/import/preview?import_id={preview_id}",
        headers=other_headers,
    )
    assert forbidden.status_code == 403

    first = client.post(
        "/api/v1/today/import/confirm",
        json={"import_id": preview_id},
        headers=owner_headers,
    )
    second = client.post(
        "/api/v1/today/import/confirm",
        json={"import_id": preview_id},
        headers=owner_headers,
    )
    assert first.status_code == 200
    assert first.json()["data"]["saved_count"] == 1
    assert second.status_code == 200
    assert second.json()["data"] == first.json()["data"]
    with session_factory() as db:
        assert db.query(Course).filter(Course.user_id == owner).count() == 1


def test_memory_growth_and_sandbox_require_the_authenticated_owner(api):
    client, session_factory = api
    owner, owner_headers = _user(session_factory, "secure-owner")
    _, other_headers = _user(session_factory, "secure-other")

    assert client.get(f"/api/v1/memory/panel/{owner}").status_code == 401
    assert client.get(
        f"/api/v1/memory/panel/{owner}", headers=other_headers
    ).status_code == 403
    assert client.get(
        f"/api/v1/growth/state/{owner}", headers=other_headers
    ).status_code == 403
    assert client.get("/api/v1/sandbox/paths").status_code == 401
    assert client.get(
        f"/api/v1/memory/panel/{owner}", headers=owner_headers
    ).status_code == 200


def test_chat_json_repairs_invalid_structured_output_once():
    service = object.__new__(LLMService)
    responses = iter(["not-json", '{"summary":"ok","tasks":[]}'])
    service.chat = lambda *args, **kwargs: next(responses)  # type: ignore[method-assign]
    parsed = service.chat_json(
        "build report",
        "return JSON",
        validator=lambda value: "summary" in value and isinstance(value.get("tasks"), list),
    )
    assert parsed == {"summary": "ok", "tasks": []}
