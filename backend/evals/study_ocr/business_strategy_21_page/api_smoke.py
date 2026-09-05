"""Isolated in-process API validation; no real iCampus DB or account is changed."""

import argparse
import json
import tempfile
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models  # noqa: F401
from app.main import app
from core.config import settings
from database.base import Base
from database.session import get_db
from models.study import StudyCard, StudyDocument, StudyDocumentUnit
from services.study_files import LocalStudyStorage, sha256_file


def run(source: Path, output: Path) -> None:
    if output.exists():
        raise FileExistsError(output)
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    sessions = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    previous_overrides = dict(app.dependency_overrides)
    previous_upload_dir = settings.study_upload_dir
    client = TestClient(app)  # Do not run the real application's startup DB hook.

    def isolated_db():
        with sessions() as db:
            yield db

    try:
        with tempfile.TemporaryDirectory(prefix="icampus-strategy-eval-") as temporary:
            settings.study_upload_dir = temporary
            app.dependency_overrides[get_db] = isolated_db
            accounts = []
            for label in ("owner", "other"):
                payload = {
                    "student_id": f"strategy-{label}-{uuid.uuid4().hex[:8]}",
                    "name": label, "password": uuid.uuid4().hex,
                }
                registration = client.post("/api/v1/users", json=payload)
                assert registration.status_code == 201, registration.text
                login = client.post("/api/v1/users/login", json={
                    "student_id": payload["student_id"], "password": payload["password"],
                })
                assert login.status_code == 200, login.text
                accounts.append({"Authorization": f"Bearer {login.json()['data']['token']}"})
            headers, other_headers = accounts
            with source.open("rb") as file:
                started = time.perf_counter()
                uploaded = client.post("/api/v1/study/documents", headers=headers,
                                       files={"file": (source.name, file, "application/pdf")})
                upload_seconds = time.perf_counter() - started
            assert uploaded.status_code == 201, uploaded.text
            document_id = uploaded.json()["data"]["id"]
            path = f"/api/v1/study/documents/{document_id}"
            with patch("services.study_parser.get_ocr_engine", side_effect=AssertionError("Unexpected OCR")):
                started = time.perf_counter()
                parsed = client.post(path + "/parse", headers=headers)
                parse_seconds = time.perf_counter() - started
                assert parsed.status_code == 200, parsed.text
                units_response = client.get(path + "/units", headers=headers)
                assert units_response.status_code == 200, units_response.text
                units = units_response.json()["data"]["units"]
                repeated = client.post(path + "/parse", headers=headers)
                assert repeated.status_code == 200
            repeat_units = client.get(path + "/units", headers=headers).json()["data"]["units"]
            assert [unit["id"] for unit in units] == [unit["id"] for unit in repeat_units]
            assert [unit["page_number"] for unit in units] == list(range(1, 22))
            assert client.get(path).status_code == 401
            assert client.get(path, headers=other_headers).status_code == 404
            assert client.get(path + "/units", headers=other_headers).status_code == 404
            assert client.post(path + "/parse", headers=other_headers).status_code == 404
            assert client.get("/api/v1/study/documents", headers=other_headers).json()["data"]["total"] == 0
            with sessions() as db:
                document = db.get(StudyDocument, document_id)
                checksum = sha256_file(LocalStudyStorage().resolve(document.storage_path))
                assert checksum == sha256_file(source) == document.sha256
                assert db.query(StudyDocument).count() == 1
                assert db.query(StudyDocumentUnit).count() == 21
                assert db.query(StudyCard).count() == 0
            result = {
                "tested_at": datetime.now(timezone.utc).isoformat(),
                "test_mode": "FastAPI TestClient, isolated in-memory SQLite, temporary upload directory",
                "source_filename": source.name, "source_sha256": checksum,
                "upload_seconds": round(upload_seconds, 4),
                "parse_seconds": round(parse_seconds, 4),
                "page_count": parsed.json()["data"]["document"]["page_count"],
                "unit_count": len(units), "text_characters": sum(len(unit["raw_text"]) for unit in units),
                "extraction_methods": dict(Counter(unit["extraction_method"] for unit in units)),
                "quality_status_counts": dict(Counter(unit["quality_status"] for unit in units)),
                "ocr_called": False, "llm_called": False, "cards_created": 0,
                "checks_passed": ["registration", "login", "upload", "stored_sha256", "parse", "unit_query",
                                  "page_order", "repeat_idempotency", "anonymous_401", "cross_account_404", "no_cards"],
                "quality_caveat": "Native text is accepted directly; this is not OCR paragraph-gate or semantic-quality validation.",
            }
    finally:
        client.close()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        settings.study_upload_dir = previous_upload_dir
        engine.dispose()
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    run(arguments.source, arguments.output)
