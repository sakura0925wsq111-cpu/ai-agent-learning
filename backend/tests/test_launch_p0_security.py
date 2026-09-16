from __future__ import annotations

import asyncio
import io
import os
import sys
import time
import types
import uuid
import zipfile
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models  # noqa: F401
from app.main import app
from app.api.v1.today.import_ import (
    _extract_courses_from_pdf,
    _extract_exams_from_xlsx,
    _run_parser,
    _validate_xlsx_archive,
)
from core.ai_quota import AIQuotaContext, AIQuotaManager
from core.config import settings
from core.rate_limit import _allow
from database.base import Base
from database.session import get_db
from models.user import User
from services.llm_service import LLMService, reset_llm_context, set_llm_context
from utils.auth import create_token, hash_password


@pytest.fixture()
def security_api():
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


def _direct_user(session_factory, label: str = "security-user") -> tuple[str, dict[str, str]]:
    with session_factory() as db:
        user = User(
            student_id=f"{label}-{uuid.uuid4().hex[:10]}",
            name=label,
            nickname=label,
            password_hash=hash_password("secure-pass"),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id
    return user_id, {
        "Authorization": f"Bearer {create_token(user_id)}",
        "X-Device-ID": f"device-{label}",
    }


def test_registration_abuse_is_limited_by_ip_and_device(security_api, monkeypatch):
    client, _ = security_api
    monkeypatch.setattr(settings, "registration_rate_limit", 2)
    monkeypatch.setattr(settings, "registration_global_daily_limit", 100)
    headers = {"X-Device-ID": "same-test-device"}

    statuses = []
    for index in range(3):
        statuses.append(client.post(
            "/api/v1/users",
            headers=headers,
            json={
                "student_id": f"security-register-{index}-{uuid.uuid4().hex[:6]}",
                "name": f"注册用户{index}",
                "password": "secure-pass",
            },
        ).status_code)

    assert statuses == [201, 201, 429]


def test_concurrent_registration_unique_conflict_returns_409(security_api):
    from sqlalchemy.exc import IntegrityError

    client, _ = security_api
    with (
        patch("app.api.v1.users.user_crud.get_by_student_id", return_value=None),
        patch(
            "app.api.v1.users.user_crud.create",
            side_effect=IntegrityError("insert user", {}, RuntimeError("unique violation")),
        ),
    ):
        response = client.post(
            "/api/v1/users",
            headers={"X-Device-ID": "registration-race-device"},
            json={"student_id": "registration-race", "name": "并发用户", "password": "secure-pass"},
        )

    assert response.status_code == 409


def test_upload_rejections_use_real_http_statuses(security_api, monkeypatch):
    client, session_factory = security_api
    user_id, headers = _direct_user(session_factory)
    monkeypatch.setattr(settings, "upload_max_bytes", 16)
    base = f"/api/v1/today/import?user_id={user_id}&import_type=course"

    wrong_magic = client.post(
        base,
        headers=headers,
        files={"file": ("bad.pdf", b"not-a-pdf", "application/pdf")},
    )
    oversized = client.post(
        base,
        headers=headers,
        files={"file": ("large.pdf", b"%PDF-" + b"x" * 20, "application/pdf")},
    )

    assert wrong_magic.status_code == 400
    assert oversized.status_code == 400


def test_upload_abuse_is_rate_limited(security_api, monkeypatch):
    client, session_factory = security_api
    user_id, headers = _direct_user(session_factory, "upload-rate")
    monkeypatch.setattr(settings, "upload_rate_limit", 1)
    url = f"/api/v1/today/import?user_id={user_id}&import_type=course"
    payload = {"file": ("bad.pdf", b"not-a-pdf", "application/pdf")}

    first = client.post(url, headers=headers, files=payload)
    second = client.post(url, headers=headers, files=payload)

    assert first.status_code == 400
    assert second.status_code == 429


def test_xlsx_zip_bomb_ratio_is_rejected(monkeypatch):
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "x")
        archive.writestr("xl/workbook.xml", "x")
        archive.writestr("xl/worksheets/sheet1.xml", "A" * 200_000)
    monkeypatch.setattr(settings, "upload_xlsx_max_compression_ratio", 10.0)

    with pytest.raises(ValueError, match="压缩比异常"):
        _validate_xlsx_archive(payload.getvalue())


def test_xlsx_row_limit_is_rejected_before_materializing_rows(monkeypatch):
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["考试课程", "考试日期"])
    sheet.append(["课程一", "2026-09-20"])
    sheet.append(["课程二", "2026-09-21"])
    payload = io.BytesIO()
    workbook.save(payload)
    workbook.close()
    monkeypatch.setattr(settings, "upload_excel_max_rows", 2)

    with pytest.raises(ValueError, match="Excel 行数不能超过 2"):
        _extract_exams_from_xlsx(payload.getvalue())


def test_pdf_page_limit_is_checked_before_extraction(monkeypatch):
    class FakePDF:
        pages = [object(), object()]

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setitem(sys.modules, "pdfplumber", types.SimpleNamespace(open=lambda _stream: FakePDF()))
    monkeypatch.setattr(settings, "upload_pdf_max_pages", 1)

    with pytest.raises(ValueError, match="PDF 页数不能超过 1 页"):
        _extract_courses_from_pdf(b"%PDF-test")


def test_parser_timeout_returns_408(monkeypatch):
    monkeypatch.setattr(settings, "upload_parser_timeout_seconds", 0.01)
    with pytest.raises(HTTPException) as raised:
        asyncio.run(_run_parser(time.sleep, 0.05))
    assert raised.value.status_code == 408
    time.sleep(0.06)  # let the bounded worker release its slot


def test_xlsx_parser_runs_in_isolated_process():
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["考试课程", "考试日期", "考试地点"])
    sheet.append(["人工智能导论", "2026-09-20(09:00-11:00)", "A101"])
    payload = io.BytesIO()
    workbook.save(payload)
    workbook.close()

    items = asyncio.run(_run_parser(_extract_exams_from_xlsx, payload.getvalue()))
    assert len(items) == 1
    assert items[0]["subject"] == "人工智能导论"


class _FakeCompletions:
    def __init__(self, contents: list[str]) -> None:
        self.contents = iter(contents)
        self.calls = 0

    def create(self, **_kwargs):
        self.calls += 1
        content = next(self.contents)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )


class _FakeOpenAIClient:
    def __init__(self, contents: list[str]) -> None:
        self.chat = SimpleNamespace(completions=_FakeCompletions(contents))

    def with_options(self, **_kwargs):
        return self


class _FakeStreamingCompletions:
    def __init__(self) -> None:
        self.calls = 0

    def create(self, **_kwargs):
        self.calls += 1
        return iter([
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="流"))]),
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="式"))]),
        ])


def _one_page_pdf(text: str) -> bytes:
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    payload = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(payload))
        payload.extend(f"{index} 0 obj\n".encode("ascii"))
        payload.extend(obj)
        payload.extend(b"\nendobj\n")
    xref = len(payload)
    payload.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    payload.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        payload.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    payload.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii")
    )
    return bytes(payload)


def test_exam_pdf_fallback_uses_the_same_ai_quota(security_api, monkeypatch):
    client, session_factory = security_api
    user_id, headers = _direct_user(session_factory, "exam-quota")
    monkeypatch.setattr(settings, "llm_api_key", "configured-for-test")
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "ai_daily_limit", 1)
    monkeypatch.setattr(settings, "ai_ip_daily_limit", 20)
    monkeypatch.setattr(settings, "ai_device_daily_limit", 20)
    monkeypatch.setattr(settings, "ai_global_daily_limit", 20)
    monkeypatch.setattr(settings, "ai_global_concurrency_limit", 2)
    manager = AIQuotaManager(prefix=f"exam:{uuid.uuid4().hex}", use_configured_redis=False)
    monkeypatch.setattr("services.llm_service.get_ai_quota_manager", lambda: manager)
    monkeypatch.setattr("core.rate_limit.get_ai_quota_manager", lambda: manager)

    service = object.__new__(LLMService)
    service._model = "fake-model"
    service._client = _FakeOpenAIClient([
        '[{"subject":"AI","exam_date":"2026-09-20","start_time":"09:00","end_time":"11:00","location":"A101"}]'
    ])
    monkeypatch.setattr("app.api.v1.today.import_.get_llm_service", lambda: service)
    url = f"/api/v1/today/import?user_id={user_id}&import_type=exam"
    pdf = _one_page_pdf("Exam schedule")

    first = client.post(url, headers=headers, files={"file": ("exam.pdf", pdf, "application/pdf")})
    second = client.post(url, headers=headers, files={"file": ("exam.pdf", pdf, "application/pdf")})

    assert first.status_code == 200, first.text
    assert service._client.chat.completions.calls == 1
    assert second.status_code == 429


def test_json_repair_charges_each_real_model_attempt(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "configured-for-test")
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "ai_daily_limit", 2)
    monkeypatch.setattr(settings, "ai_ip_daily_limit", 20)
    monkeypatch.setattr(settings, "ai_device_daily_limit", 20)
    monkeypatch.setattr(settings, "ai_global_daily_limit", 20)
    monkeypatch.setattr(settings, "ai_global_concurrency_limit", 2)
    manager = AIQuotaManager(prefix=f"test:{uuid.uuid4().hex}", use_configured_redis=False)
    monkeypatch.setattr("services.llm_service.get_ai_quota_manager", lambda: manager)

    service = object.__new__(LLMService)
    service._model = "fake-model"
    service._client = _FakeOpenAIClient(["not-json", '{"summary":"ok","tasks":[]}'])
    context = AIQuotaContext("quota-user", "json-repair", "127.0.0.1", "device-1")
    token = set_llm_context(
        user_id=context.user_id,
        feature=context.feature,
        client_ip=context.client_ip,
        device_id=context.device_id,
    )
    try:
        parsed = service.chat_json(
            "build report",
            "return JSON",
            validator=lambda value: "summary" in value and isinstance(value.get("tasks"), list),
        )
    finally:
        reset_llm_context(token)

    assert parsed["summary"] == "ok"
    assert service._client.chat.completions.calls == 2
    with pytest.raises(HTTPException) as raised:
        manager.assert_available(context)
    assert raised.value.status_code == 429


def test_streaming_charges_and_holds_the_same_quota(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "configured-for-test")
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "ai_daily_limit", 1)
    monkeypatch.setattr(settings, "ai_ip_daily_limit", 20)
    monkeypatch.setattr(settings, "ai_device_daily_limit", 20)
    monkeypatch.setattr(settings, "ai_global_daily_limit", 20)
    monkeypatch.setattr(settings, "ai_global_concurrency_limit", 2)
    manager = AIQuotaManager(prefix=f"stream:{uuid.uuid4().hex}", use_configured_redis=False)
    monkeypatch.setattr("services.llm_service.get_ai_quota_manager", lambda: manager)
    completions = _FakeStreamingCompletions()
    service = object.__new__(LLMService)
    service._model = "fake-model"
    service._client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    token = set_llm_context(
        user_id="stream-user",
        feature="stream-test",
        client_ip="127.0.0.1",
        device_id="stream-device",
    )
    try:
        assert "".join(service.chat_stream("hello")) == "流式"
        with pytest.raises(HTTPException) as exhausted:
            list(service.chat_stream("again"))
    finally:
        reset_llm_context(token)

    assert completions.calls == 1
    assert exhausted.value.status_code == 429


def test_ai_global_concurrency_and_kill_switch(monkeypatch):
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "ai_daily_limit", 20)
    monkeypatch.setattr(settings, "ai_ip_daily_limit", 20)
    monkeypatch.setattr(settings, "ai_device_daily_limit", 20)
    monkeypatch.setattr(settings, "ai_global_daily_limit", 20)
    monkeypatch.setattr(settings, "ai_global_concurrency_limit", 1)
    manager = AIQuotaManager(prefix=f"test:{uuid.uuid4().hex}", use_configured_redis=False)
    first = AIQuotaContext("u1", client_ip="ip1", device_id="d1")
    second = AIQuotaContext("u2", client_ip="ip2", device_id="d2")

    with manager.lease(first):
        with pytest.raises(HTTPException) as busy:
            with manager.lease(second):
                pass
        assert busy.value.status_code == 429

    monkeypatch.setattr(settings, "ai_enabled", False)
    with pytest.raises(HTTPException) as disabled:
        manager.assert_available(first)
    assert disabled.value.status_code == 503


def test_redis_lua_quota_and_rate_limit_are_shared(monkeypatch):
    import fakeredis

    client = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "ai_daily_limit", 1)
    monkeypatch.setattr(settings, "ai_ip_daily_limit", 20)
    monkeypatch.setattr(settings, "ai_device_daily_limit", 20)
    monkeypatch.setattr(settings, "ai_global_daily_limit", 20)
    monkeypatch.setattr(settings, "ai_global_concurrency_limit", 2)
    prefix = f"fake-redis:{uuid.uuid4().hex}"
    first = AIQuotaManager(redis_client=client, prefix=prefix)
    second = AIQuotaManager(redis_client=client, prefix=prefix)
    context = AIQuotaContext("shared-user", client_ip="127.0.0.1", device_id="shared-device")

    with first.lease(context):
        pass
    with pytest.raises(HTTPException) as exhausted:
        second.assert_available(context)
    assert exhausted.value.status_code == 429

    client.set(f"{prefix}:enabled", "0")
    with pytest.raises(HTTPException) as killed:
        second.assert_available(AIQuotaContext("another-user", client_ip="10.0.0.2"))
    assert killed.value.status_code == 503

    monkeypatch.setattr("core.rate_limit.get_redis_client", lambda: client)
    key = f"test-rate-{uuid.uuid4().hex}"
    assert _allow(key, limit=1, window_seconds=60)
    assert not _allow(key, limit=1, window_seconds=60)


def test_production_limits_fail_closed_when_redis_is_unavailable(monkeypatch):
    class BrokenRedis:
        def eval(self, *_args, **_kwargs):
            raise ConnectionError("unavailable")

    monkeypatch.setattr(settings, "app_env", "prod")
    monkeypatch.setattr(settings, "ai_enabled", True)
    context = AIQuotaContext("fail-closed-user", client_ip="127.0.0.1")
    manager = AIQuotaManager(redis_client=BrokenRedis(), prefix=f"broken:{uuid.uuid4().hex}")

    with pytest.raises(HTTPException) as ai_error:
        manager.assert_available(context)
    assert ai_error.value.status_code == 503

    monkeypatch.setattr("core.rate_limit.get_redis_client", lambda: BrokenRedis())
    with pytest.raises(HTTPException) as rate_error:
        _allow("fail-closed-rate", limit=1, window_seconds=60)
    assert rate_error.value.status_code == 503


def test_redis_quota_is_shared_across_manager_instances(monkeypatch):
    url = os.getenv("REDIS_INTEGRATION_URL", "")
    if not url:
        pytest.skip("REDIS_INTEGRATION_URL is not configured")
    from redis import Redis

    client = Redis.from_url(url, decode_responses=True)
    try:
        client.ping()
    except Exception as exc:
        pytest.skip(f"Redis integration service unavailable: {type(exc).__name__}")

    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "ai_daily_limit", 1)
    monkeypatch.setattr(settings, "ai_ip_daily_limit", 20)
    monkeypatch.setattr(settings, "ai_device_daily_limit", 20)
    monkeypatch.setattr(settings, "ai_global_daily_limit", 20)
    monkeypatch.setattr(settings, "ai_global_concurrency_limit", 2)
    prefix = f"integration:{uuid.uuid4().hex}"
    first = AIQuotaManager(redis_client=client, prefix=prefix)
    second = AIQuotaManager(redis_client=client, prefix=prefix)
    context = AIQuotaContext("shared-user", client_ip="127.0.0.1", device_id="shared-device")
    try:
        with first.lease(context):
            pass
        with pytest.raises(HTTPException) as exhausted:
            second.assert_available(context)
        assert exhausted.value.status_code == 429
    finally:
        keys = list(client.scan_iter(f"{prefix}:*"))
        if keys:
            client.delete(*keys)
        client.close()


def test_sandbox_resume_rejects_client_authoritative_state(security_api):
    client, session_factory = security_api
    user_id, headers = _direct_user(session_factory, "sandbox-owner")
    response = client.post(
        "/api/v1/sandbox/resume",
        headers=headers,
        json={
            "user_id": user_id,
            "session_id": "forged-session",
            "message": "",
            "state": {
                "user_id": user_id,
                "session_id": "forged-session",
                "current_phase": "completed",
                "finished": True,
                "projection_result": {"summary": "fake-client-result"},
            },
        },
    )
    assert response.status_code == 422
