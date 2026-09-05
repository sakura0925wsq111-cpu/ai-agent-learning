from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models  # noqa: F401
from app.main import app
from database.base import Base
from database.session import get_db
from models.study import (
    StudyDocument,
    StudyDocumentUnit,
    StudyKnowledgeRun,
    StudyKnowledgeUnit,
    StudyStructuredBlock,
)
from models.user import User
from services.study_knowledge import (
    ModelResult,
    StructuredBlock,
    StructuredDocument,
    StructuredSourceSpan,
    create_or_reuse_run,
    extract_from_structured_document,
    process_knowledge_run,
)
from utils.auth import create_token, hash_password


class FakeKnowledgeModel:
    model = "fake-grounded-model"

    def extract(self, blocks):
        return ModelResult(payload={"candidates": [
            {
                "candidate_id": "definition-ok",
                "type": "definition",
                "block_id": "p1",
                "extraction_text": "市场细分是指根据消费者需求差异划分市场。",
                "risk_flags": ["none"],
            },
            {
                "candidate_id": "rewritten",
                "type": "definition",
                "block_id": "p1",
                "extraction_text": "市场细分是按照需求划分市场。",
                "risk_flags": ["none"],
            },
            {
                "candidate_id": "formula",
                "type": "definition",
                "block_id": "f1",
                "extraction_text": "孔隙比是e=Vv/Vs。",
                "risk_flags": ["formula_dependency"],
            },
            {
                "candidate_id": "list-fragment",
                "type": "complete_list",
                "block_id": "p2",
                "extraction_text": "战略具有全局性、长远性。",
                "risk_flags": ["possible_incomplete"],
            },
            {
                "candidate_id": "list-ok",
                "type": "complete_list",
                "block_id": "p2",
                "extraction_text": "战略具有全局性、长远性、竞合性、纲领性、相对稳定性。",
                "risk_flags": ["none"],
            },
            {
                "candidate_id": "corrupt-list",
                "type": "complete_list",
                "block_id": "p3",
                "extraction_text": "按来源不同（中，中两方；中，中，中'合作；中外合作）",
                "risk_flags": ["none"],
            },
            {
                "candidate_id": "overbroad-definition",
                "type": "definition",
                "block_id": "p4",
                "extraction_text": "缓存是指暂时保存数据的机制。作用是减少重复读取。",
                "risk_flags": ["none"],
            },
        ]}, model=self.model, duration_ms=2.0)

    def review(self, blocks, candidates):
        return ModelResult(payload={"decisions": [
            {
                "candidate_id": "definition-ok",
                "decision": "usable",
                "error_types": ["none"],
                "related_source_block_ids": ["p1"],
            },
            {
                "candidate_id": "list-ok",
                "decision": "usable",
                "error_types": ["none"],
                "related_source_block_ids": ["p2"],
            }
        ]}, model=self.model, duration_ms=3.0)


def _structured_document() -> StructuredDocument:
    return StructuredDocument(
        revision_id="revision-1",
        source_sha256="a" * 64,
        parser_name="test-parser",
        parser_version="1",
        parser_config={},
        blocks=[
            StructuredBlock(
                id="h1", type="heading", raw_text="市场战略", reading_order=0,
                source_spans=[StructuredSourceSpan(1, [0.1, 0.1, 0.5, 0.2], 0, 4)],
                quality_signals={"usable_text": True},
            ),
            StructuredBlock(
                id="p1", type="paragraph",
                raw_text="市场细分是指根据消费者需求差异划分市场。", reading_order=1,
                source_spans=[StructuredSourceSpan(1, [0.1, 0.2, 0.9, 0.3], 0, 20)],
                quality_signals={"usable_text": True},
            ),
            StructuredBlock(
                id="p2", type="paragraph",
                raw_text="战略具有全局性、长远性、竞合性、纲领性、相对稳定性。", reading_order=2,
                source_spans=[StructuredSourceSpan(1, [0.1, 0.3, 0.9, 0.4], 0, 26)],
                quality_signals={"usable_text": True},
            ),
            StructuredBlock(
                id="f1", type="formula", raw_text="孔隙比是e=Vv/Vs。", reading_order=3,
                source_spans=[StructuredSourceSpan(1, [0.1, 0.4, 0.9, 0.5], 0, 12)],
                quality_signals={"usable_text": False},
            ),
            StructuredBlock(
                id="p3", type="paragraph",
                raw_text="按来源不同（中，中两方；中，中，中'合作；中外合作）", reading_order=4,
                source_spans=[StructuredSourceSpan(1, [0.1, 0.5, 0.9, 0.6], 0, 27)],
                quality_signals={"usable_text": True},
            ),
            StructuredBlock(
                id="p4", type="paragraph",
                raw_text="缓存是指暂时保存数据的机制。作用是减少重复读取。", reading_order=5,
                source_spans=[StructuredSourceSpan(1, [0.1, 0.6, 0.9, 0.7], 0, 24)],
                quality_signals={"usable_text": True},
            ),
        ],
    )


def test_pipeline_rebuilds_exact_source_and_rejects_rewrite_formula_and_fragment():
    records, audit = extract_from_structured_document(
        _structured_document(), FakeKnowledgeModel(), max_chars=5000
    )
    by_id = {record["extraction_meta"]["candidate"]["candidate_id"]: record for record in records}

    accepted = by_id["definition-ok"]
    assert accepted["disposition"] == "usable"
    assert accepted["content"] == "市场细分是指根据消费者需求差异划分市场。"
    assert accepted["check_meta"]["exact_slice"] is True
    assert accepted["source_refs"][0]["block_id"] == "p1"
    assert accepted["source_refs"][0]["char_start"] == 0

    assert by_id["rewritten"]["disposition"] == "uncertain"
    assert by_id["rewritten"]["content"] == ""
    assert "source_slice_mismatch" in by_id["rewritten"]["reasons"]
    assert by_id["formula"]["disposition"] == "unsupported"
    assert "unsupported_block_type:formula" in by_id["formula"]["reasons"]
    assert by_id["list-fragment"]["disposition"] == "uncertain"
    assert "model_risk:possible_incomplete" in by_id["list-fragment"]["reasons"]
    assert by_id["list-ok"]["disposition"] == "usable"
    assert by_id["list-ok"]["knowledge_type"] == "complete_list"
    assert by_id["corrupt-list"]["disposition"] == "uncertain"
    assert "suspicious_mixed_script_glyph" in by_id["corrupt-list"]["reasons"]
    assert by_id["overbroad-definition"]["disposition"] == "uncertain"
    assert "definition_shape_incomplete" in by_id["overbroad-definition"]["reasons"]
    assert audit["model_call_count"] == 2


def _api_fixture():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), factory, engine


def _create_user(factory, label):
    with factory() as db:
        user = User(
            student_id=f"{label}-{uuid.uuid4().hex[:8]}",
            name=label,
            nickname=label,
            password_hash=hash_password("pass"),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id, {"Authorization": f"Bearer {create_token(user.id)}"}


def test_knowledge_api_is_owner_scoped_and_reuses_same_revision(monkeypatch):
    client, factory, engine = _api_fixture()
    monkeypatch.setattr(
        "app.api.v1.study.process_knowledge_run_by_id", lambda _run_id: None
    )
    try:
        owner_id, owner_headers = _create_user(factory, "owner")
        _, other_headers = _create_user(factory, "other")
        with factory() as db:
            document = StudyDocument(
                user_id=owner_id,
                original_filename="notes.pdf",
                file_type="pdf",
                storage_path="private/notes.pdf",
                file_size=10,
                sha256="b" * 64,
                status="parsed",
            )
            db.add(document)
            db.commit()
            db.refresh(document)
            document_id = document.id

        first = client.post(
            f"/api/v1/study/documents/{document_id}/knowledge-runs",
            headers=owner_headers,
            json={"force": False},
        )
        assert first.status_code == 202, first.text
        first_id = first.json()["data"]["run"]["id"]
        assert first.json()["data"]["reused"] is False

        repeated = client.post(
            f"/api/v1/study/documents/{document_id}/knowledge-runs",
            headers=owner_headers,
            json={"force": False},
        )
        assert repeated.json()["data"]["run"]["id"] == first_id
        assert repeated.json()["data"]["reused"] is True

        forced = client.post(
            f"/api/v1/study/documents/{document_id}/knowledge-runs",
            headers=owner_headers,
            json={"force": True},
        )
        assert forced.json()["data"]["run"]["revision"] == 2
        assert forced.json()["data"]["run"]["id"] != first_id

        hidden = client.get(
            f"/api/v1/study/knowledge-runs/{first_id}", headers=other_headers
        )
        assert hidden.status_code == 404
        own = client.get(
            f"/api/v1/study/knowledge-runs/{first_id}", headers=owner_headers
        )
        assert own.status_code == 200
        hidden_units = client.get(
            f"/api/v1/study/knowledge-runs/{first_id}/knowledge-units",
            headers=other_headers,
        )
        assert hidden_units.status_code == 404

        with factory() as db:
            document = db.get(StudyDocument, document_id)
            same, reused = create_or_reuse_run(db, document, force=False)
            assert reused is True
            assert same.revision == 1
            assert db.query(StudyKnowledgeRun).count() == 2
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


class RuntimeFakeModel:
    model = "runtime-fake"

    def extract(self, blocks):
        block = next(item for item in blocks if "缓存是指" in item["text"])
        return ModelResult(payload={"candidates": [{
            "candidate_id": "runtime-definition",
            "type": "definition",
            "block_id": block["block_id"],
            "extraction_text": "缓存是指暂时保存数据以减少重复读取的机制。",
            "risk_flags": ["none"],
        }]}, model=self.model, duration_ms=1.0)

    def review(self, blocks, candidates):
        return ModelResult(payload={"decisions": [{
            "candidate_id": "runtime-definition",
            "decision": "usable",
            "error_types": ["none"],
            "related_source_block_ids": [candidates[0]["block_id"]],
        }]}, model=self.model, duration_ms=1.0)


def test_database_run_persists_structured_revision_and_grounded_unit():
    _, factory, engine = _api_fixture()
    try:
        user_id, _ = _create_user(factory, "runtime")
        with factory() as db:
            document = StudyDocument(
                user_id=user_id,
                original_filename="runtime.pdf",
                file_type="pdf",
                storage_path="private/runtime.pdf",
                file_size=10,
                sha256="c" * 64,
                status="parsed",
            )
            db.add(document)
            db.flush()
            db.add(StudyDocumentUnit(
                document_id=document.id,
                page_number=1,
                unit_index=0,
                unit_type="page",
                raw_text="缓存是指暂时保存数据以减少重复读取的机制。",
                normalized_text="缓存是指暂时保存数据以减少重复读取的机制。",
                safe_text="缓存是指暂时保存数据以减少重复读取的机制。",
                text_hash="d" * 64,
                extraction_method="native",
                quality_status="accepted",
            ))
            db.commit()
            db.refresh(document)
            run, reused = create_or_reuse_run(db, document)
            assert reused is False
            completed = process_knowledge_run(db, run, model=RuntimeFakeModel())
            assert completed.status == "completed"
            assert completed.structured_revision_id
            assert completed.statistics["usable_count"] == 1
            stored = db.query(StudyKnowledgeUnit).filter_by(run_id=run.id).one()
            assert stored.content == "缓存是指暂时保存数据以减少重复读取的机制。"
            assert stored.structured_revision_id == completed.structured_revision_id
            assert stored.source_refs[0]["page_number"] == 1
            assert db.query(StudyStructuredBlock).filter_by(run_id=run.id).count() == 1
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
