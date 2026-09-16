from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import create_engine, text

from app.main import app
from database.study_review_migration import migrate_study_review
from models.study import StudyDocument, StudyKnowledgeUnit as Unit
from services import study_review
from services.study_knowledge import create_or_reuse_run
from tests.test_study_knowledge import _api_fixture, _create_user


@pytest.fixture
def review():
    client, factory, engine = _api_fixture()
    owner, headers = _create_user(factory, "review-owner")
    other, other_headers = _create_user(factory, "review-other")
    with factory() as db:
        doc = StudyDocument(user_id=owner, original_filename="review.pdf", file_type="pdf",
                            storage_path="unused", file_size=1, sha256="a" * 64)
        db.add(doc)
        db.commit()
        run, _ = create_or_reuse_run(db, doc)
        run.status = "completed"
        run_id, doc_id = run.id, doc.id
        for index, disposition in enumerate(["usable", "usable", "uncertain", "unsupported"]):
            db.add(Unit(id=f"unit-{index}", run_id=run.id, document_id=doc.id,
                        knowledge_type="definition", structured_revision_id="r1",
                        content="原始正文", content_hash="old", source_key=str(index),
                        source_refs=[{"page": 1}], disposition=disposition))
        db.commit()
    yield client, factory, owner, headers, other_headers, run_id, doc_id
    app.dependency_overrides.clear()
    engine.dispose()


def call(review, method, suffix, **kwargs):
    return review[0].request(method, "/api/v1/study/" + suffix, headers=review[3], **kwargs)


def test_complete_persistent_review_lifecycle(review):
    path = "knowledge-units/unit-0"
    initial = call(review, "GET", path).json()["data"]
    assert initial["original_content"] == initial["content"] == "原始正文"
    assert initial["review_status"] == "pending" and initial["version"] == 1
    assert not initial["is_edited"]
    with review[1]() as db:
        assert study_review.learning_knowledge_query(db, review[2]).count() == 0
    edited = call(review, "PATCH", path, json={"content": "用户编辑正文", "confirm": True, "version": 1})
    assert edited.status_code == 200
    data = edited.json()["data"]
    assert data["review_status"] == "confirmed" and data["confirmed_at"]
    assert data["is_edited"] and data["source_usage"] == "reference_only"
    assert data["original_content"] == "原始正文" and data["source_refs"] == [{"page": 1}]
    with review[1]() as db:
        unit = db.get(Unit, "unit-0")
        assert unit.content == "用户编辑正文"
        assert unit.content_hash == hashlib.sha256(unit.content.encode()).hexdigest()
        assert study_review.learning_knowledge_query(db, review[2], review[5]).count() == 1
    assert call(review, "POST", path + "/unconfirm", json={"version": 2}).status_code == 200
    assert call(review, "POST", path + "/confirm", json={"version": 3}).status_code == 200
    pending = call(review, "PATCH", path, json={"content": "再次编辑", "confirm": False, "version": 4}).json()["data"]
    assert pending["review_status"] == "pending" and pending["confirmed_at"] is None
    assert call(review, "POST", path + "/confirm", json={"version": 5}).status_code == 200
    assert call(review, "DELETE", path + "?version=6").json()["data"]["deleted_at"]
    with review[1]() as db:
        assert study_review.learning_knowledge_query(db, review[2]).count() == 0
    assert call(review, "POST", path + "/confirm", json={"version": 7}).status_code == 409
    restored = call(review, "POST", path + "/restore", json={"version": 7}).json()["data"]
    assert restored["deleted_at"] is None and restored["confirmed_at"] is None
    assert restored["review_status"] == "pending" and restored["content"] == "再次编辑"
    assert restored["version"] == 8


def test_list_filters_pagination_and_unfiltered_statistics(review):
    call(review, "POST", "knowledge-units/unit-0/confirm", json={"version": 1})
    call(review, "DELETE", "knowledge-units/unit-1?version=1")
    path = f"knowledge-runs/{review[5]}/knowledge-units"
    data = call(review, "GET", path + "?review_status=pending&page_size=1&page=2").json()["data"]
    assert data["total"] == 2 and len(data["units"]) == 1 and data["page"] == 2
    assert data["statistics"] == {"active_count": 3, "pending_count": 2, "confirmed_count": 1, "deleted_count": 1}
    assert call(review, "GET", path).json()["data"]["total"] == 3
    assert call(review, "GET", path + "?deleted=all").json()["data"]["total"] == 4
    assert call(review, "GET", path + "?deleted=deleted").json()["data"]["units"][0]["id"] == "unit-1"
    assert call(review, "GET", path + "?disposition=usable").json()["data"]["total"] == 1


@pytest.mark.parametrize("method,suffix,payload", [
    ("GET", "", None), ("PATCH", "", {"version": 1, "content": "修改"}),
    ("POST", "/confirm", {"version": 1}), ("POST", "/unconfirm", {"version": 1}),
    ("DELETE", "?version=1", None), ("POST", "/restore", {"version": 1}),
])
def test_every_unit_endpoint_hides_other_accounts_and_missing_ids(review, method, suffix, payload):
    for unit_id, headers in [("unit-0", review[4]), ("missing", review[3])]:
        response = review[0].request(method, f"/api/v1/study/knowledge-units/{unit_id}{suffix}",
                                     headers=headers, json=payload)
        assert response.status_code == 404


@pytest.mark.parametrize("bad_item,status", [
    ({"id": "unit-1", "version": 99}, 409),
    ({"id": "unit-2", "version": 1}, 409),
    ({"id": "zz-missing", "version": 1}, 404),
])
def test_batch_failure_rolls_back_earlier_updates(review, bad_item, status):
    response = call(review, "POST", f"knowledge-runs/{review[5]}/confirm", json={
        "items": [{"id": "unit-0", "version": 1}, bad_item]})
    assert response.status_code == status
    with review[1]() as db:
        unit = db.get(Unit, "unit-0")
        assert unit.version == 1 and unit.review_status == "pending"


def test_batch_success_limits_and_run_isolation(review):
    path = f"knowledge-runs/{review[5]}/confirm"
    items = [{"id": "unit-0", "version": 1}, {"id": "unit-1", "version": 1}]
    assert call(review, "POST", path, json={"items": items}).status_code == 200
    assert call(review, "POST", path, json={"items": []}).status_code == 422
    assert call(review, "POST", path, json={"items": items * 51}).status_code == 422
    assert call(review, "POST", path, json={"items": [items[0]] * 2}).status_code == 422
    for method, suffix in [("GET", "/knowledge-units"), ("POST", "/confirm")]:
        assert review[0].request(method, f"/api/v1/study/knowledge-runs/{review[5]}{suffix}",
                                 headers=review[4], json={"items": items} if method == "POST" else None).status_code == 404
    with review[1]() as db:
        new_run, _ = create_or_reuse_run(db, db.get(StudyDocument, review[6]), force=True)
        new_id = new_run.id
    assert call(review, "POST", f"knowledge-runs/{new_id}/confirm", json={"items": [{"id": "unit-0", "version": 2}]}).status_code == 404


def test_foreign_batch_item_rolls_back_and_downstream_is_owner_scoped(review):
    foreign_owner, _ = _create_user(review[1], "foreign-batch-owner")
    with review[1]() as db:
        doc = StudyDocument(user_id=foreign_owner, original_filename="foreign.pdf", file_type="pdf",
                            storage_path="unused", file_size=1, sha256="b" * 64)
        db.add(doc)
        db.commit()
        run, _ = create_or_reuse_run(db, doc)
        db.add(Unit(id="zz-foreign", run_id=run.id, document_id=doc.id, knowledge_type="definition",
                    structured_revision_id="r", content="private", content_hash="hash", source_key="key",
                    disposition="usable", review_status="confirmed"))
        db.commit()
        assert study_review.learning_knowledge_query(db, review[2]).count() == 0
        assert study_review.learning_knowledge_query(db, foreign_owner).count() == 1
    response = call(review, "POST", f"knowledge-runs/{review[5]}/confirm", json={"items": [
        {"id": "unit-0", "version": 1}, {"id": "zz-foreign", "version": 1}]})
    assert response.status_code == 404
    with review[1]() as db:
        assert db.get(Unit, "unit-0").version == 1


@pytest.mark.parametrize("method,suffix,payload", [
    ("PATCH", "", {"version": 1, "content": "stale"}),
    ("POST", "/confirm", {"version": 1}), ("POST", "/unconfirm", {"version": 1}),
    ("DELETE", "?version=1", None), ("POST", "/restore", {"version": 1}),
])
def test_all_mutations_require_current_version(review, method, suffix, payload):
    path = "knowledge-units/unit-0"
    assert call(review, "PATCH", path, json={"content": "saved", "version": 1}).status_code == 200
    assert call(review, method, path + suffix, json=payload).status_code == 409
    saved = call(review, "GET", path).json()["data"]
    assert saved["version"] == 2 and saved["content"] == "saved"


@pytest.mark.parametrize("payload", [
    {"content": "   \n\t", "version": 1}, {"content": "a" * 5001, "version": 1},
    {"content": "正文"}, {"content": "正文", "version": 0},
    {"content": "正文", "version": 1, "source_refs": []},
    {"content": "正文", "version": 1, "disposition": "usable"},
    {"content": "正文", "version": 1, "original_content": "伪造"},
])
def test_edit_validation(review, payload):
    assert call(review, "PATCH", "knowledge-units/unit-0", json=payload).status_code == 422


def test_nonusable_cannot_be_confirmed_or_edited_into_confirmed(review):
    for unit_id in ["unit-2", "unit-3"]:
        path = f"knowledge-units/{unit_id}"
        assert call(review, "POST", path + "/confirm", json={"version": 1}).status_code == 409
        assert call(review, "PATCH", path, json={"version": 1, "content": "修正", "confirm": True}).status_code == 409
        assert call(review, "PATCH", path, json={"version": 1, "content": "修正"}).status_code == 200


def test_atomic_update_rejects_race_after_version_read(review, monkeypatch):
    # Force a second session to win after the first session's read, before its UPDATE.
    real_get = study_review.get_unit
    raced = False

    def racing_get(db, user_id, unit_id):
        nonlocal raced
        unit = real_get(db, user_id, unit_id)
        if not raced:
            raced = True
            with review[1]() as winner:
                study_review.mutate_unit(winner, user_id, unit_id, 1, "edit", content="并发赢家")
        return unit

    monkeypatch.setattr(study_review, "get_unit", racing_get)
    response = call(review, "PATCH", "knowledge-units/unit-0", json={"version": 1, "content": "过时覆盖"})
    assert response.status_code == 409
    assert "内容已更新，请刷新后重试" in response.text
    with review[1]() as db:
        unit = db.get(Unit, "unit-0")
        assert unit.version == 2 and unit.content == "并发赢家"


def test_reextraction_keeps_old_edits(review):
    call(review, "PATCH", "knowledge-units/unit-0", json={"version": 1, "content": "保留用户修改"})
    with review[1]() as db:
        run, reused = create_or_reuse_run(db, db.get(StudyDocument, review[6]), force=True)
        assert not reused and run.id != review[5]
        unit = db.get(Unit, "unit-0")
        assert unit.run_id == review[5] and unit.content == "保留用户修改" and unit.version == 2


def test_legacy_migration_backfill_and_repeat_preserves_user_review(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE study_knowledge_units (id TEXT PRIMARY KEY, content TEXT NOT NULL, created_at DATETIME NOT NULL)"))
        conn.execute(text("INSERT INTO study_knowledge_units VALUES ('old', 'AI original', '2026-09-01 00:00:00')"))
    migrate_study_review(engine)
    with engine.begin() as conn:
        row = conn.execute(text("SELECT * FROM study_knowledge_units")).mappings().one()
        assert row["original_content"] == "AI original" and row["review_status"] == "pending"
        assert row["version"] == 1 and row["confirmed_at"] is None
        assert row["updated_at"] == row["created_at"]
        conn.execute(text("UPDATE study_knowledge_units SET content='edited', review_status='confirmed', version=2"))
    migrate_study_review(engine)
    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM study_knowledge_units")).mappings().one()
        assert row["original_content"] == "AI original" and row["content"] == "edited"
        assert row["review_status"] == "confirmed" and row["version"] == 2
    engine.dispose()
