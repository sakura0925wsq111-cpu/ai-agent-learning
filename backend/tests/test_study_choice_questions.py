import copy
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, inspect

from models.study import StudyChoiceQuestion as Question, StudyChoiceQuestionRun as Run, StudyKnowledgeUnit as Unit
from services import study_choice_questions as service
from tests.test_study_review import review

CONTENT = "经营战略的特点包括全局性、长远性、竞合性、纲领性和相对稳定性。"


def candidate(content=CONTENT):
    return dict(answer_text="竞合性",
                answer_role="core_term", distractors=["竞争性", "协同性", "阶段性"])


def generate(batch):
    return {"items": [{"knowledge_unit_id": s["knowledge_unit_id"], "answer_candidates": [candidate(s["content"])]} for s in batch]}


def seed(review, count=2):
    with review[1]() as db:
        for i in range(count):
            unit = db.get(Unit, f"unit-{i}")
            if unit is None:
                unit = Unit(id=f"unit-{i}", run_id=review[5], document_id=review[6],
                    knowledge_type="definition", structured_revision_id="r1", content_hash="hash", source_key=str(i),
                    disposition="usable", source_refs=[{"page": 1}])
                db.add(unit)
            unit.content = CONTENT
            unit.disposition = "usable"
        db.commit()
        run, reused = service.create_run(db, review[2], review[5])
        return run.id


@pytest.mark.parametrize("changes,reason", [
    ({"answer_text": "无此内容"}, "answer_not_in_source"),
    ({"answer_text": ""}, "invalid_answer"),
    ({"answer_text": []}, "invalid_answer"),
    ({"answer_role": "ordinary"}, "answer_role"),
    ({"answer_role": []}, "answer_role"),
    ({"distractors": ["竞争性"]}, "distractor_count"),
    ({"distractors": ["竞争性", "竞争性", "协同性"]}, "duplicate_option"),
    ({"distractors": ["长远性", "协同性", "阶段性"]}, "distractor_in_source_or_generic"),
    ({"distractors": ["以上都是", "协同性", "阶段性"]}, "distractor_in_source_or_generic"),
    ({"distractors": [{}, "协同性", "阶段性"]}, "distractor_length"),
])
def test_rejects_bad_candidates(changes, reason):
    assert service.validate_candidate(CONTENT, {**candidate(), **changes}) == reason


@pytest.mark.parametrize("offsets", [{}, {"answer_start": 0, "answer_end": 2},
                                    {"answer_start": True, "answer_end": "bad"}])
def test_program_locates_answer_without_trusting_model_offsets(offsets):
    content = "😀AI说明\n" + CONTENT
    c = {**candidate(), **offsets}
    original = copy.deepcopy(c)
    snapshot = {"content": content, "knowledge_unit_id": "unit", "version": 1,
                "source_refs": [], "source_usage": "extraction_evidence"}
    q, reason = service.assemble(snapshot, {"answer_candidates": [c]}, "run", 1)
    assert reason is None
    assert q.answer_start == content.index("竞合性")
    assert q.source_content[q.answer_start:q.answer_end] == "竞合性"
    assert q.prompt.endswith(content.replace("竞合性", "____"))
    assert q.options["ABCD".index(q.correct_option)] == "竞合性"
    assert q.generation_meta["span_source"] == "program_exact_unique_match"
    assert c == original


@pytest.mark.parametrize("content,answer,reason", [
    ("aaaa", "aaa", "repeated_answer"),
    (CONTENT, "竞 合性", "answer_not_in_source"),
    ("这里的 AI 技术需要学习", "ai", "answer_not_in_source"),
    (CONTENT + "竞合性", "竞合性", "repeated_answer"),
])
def test_exact_location_rejects_ambiguous_or_rewritten_answers(content, answer, reason):
    assert service.locate_answer(content, answer) == (None, reason)


def test_missing_answer_falls_back_to_next_candidate():
    snapshot = {"content": CONTENT, "knowledge_unit_id": "unit", "version": 1,
                "source_refs": [], "source_usage": "extraction_evidence"}
    q, reason = service.assemble(snapshot, {"answer_candidates": [
        {**candidate(), "answer_text": "改写的答案"}, candidate()]}, "run", 1)
    assert reason is None and q.answer_text == "竞合性"
    assert q.generation_meta["rejected_candidates"] == ["answer_not_in_source"]


def test_prompt_version_change_creates_new_run(review, monkeypatch):
    with monkeypatch.context() as old:
        old.setattr(service, "PROMPT_VERSION", "choice-source-v1")
        old_id = seed(review)
    with review[1]() as db:
        run, reused = service.create_run(db, review[2], review[5])
        assert not reused and run.id != old_id
        assert run.prompt_version == "choice-source-v2"
        assert service.create_run(db, review[2], review[5])[1]


def test_repetition_context_stopwords_and_numeric_formats():
    assert service.validate_candidate(CONTENT + "竞合性", candidate()) == "repeated_answer"
    for answer in ["包括", "该内容"]:
        content = "这个知识点" + answer + "若干重要内容需要完整记忆和掌握。"
        c = {**candidate(), "answer_text": answer, "answer_start": 5, "answer_end": 5 + len(answer)}
        assert service.validate_candidate(content, c) == "ordinary_word"
    content = "本项大型历史事件正式发生于1949年，具有十分重要的历史意义。"
    c = {**candidate(), "answer_text": "1949年", "answer_start": content.index("1949"),
         "answer_end": content.index("1949") + 5, "answer_role": "date", "distractors": ["1948年", "1950年", "1951年"]}
    assert service.validate_candidate(content, c) is None
    c["distractors"][0] = "自然科学"
    assert service.validate_candidate(content, c) == "numeric_type"
    c["distractors"][0] = "1948月"
    assert service.validate_candidate(content, c) == "numeric_format"


def test_all_pending_units_snapshot_reuse_version_and_deletion(review):
    run_id = seed(review)
    with review[1]() as db:
        run = db.get(Run, run_id)
        assert run.total_count == 2  # uncertain/unsupported excluded; pending accepted
        assert service.create_run(db, review[2], review[5])[1]
        unit = db.get(Unit, "unit-0")
        unit.content = "用户修改后的新内容"
        unit.version += 1
        db.commit()
        new, reused = service.create_run(db, review[2], review[5])
        assert new.id != run_id and not reused
        assert run.snapshots[0]["content"] == CONTENT
        unit.deleted_at = datetime.now(timezone.utc)
        db.commit()
        assert service.create_run(db, review[2], review[5])[0].total_count == 1
    service.process_run(run_id, review[1], generate)
    with review[1]() as db:
        questions = db.query(Question).filter_by(question_run_id=run_id).all()
        assert len(questions) == 2
        for q in questions:
            assert q.source_content == CONTENT and q.knowledge_unit_version == 1
            assert q.source_content[q.answer_start:q.answer_end] == q.answer_text
            assert len(set(q.options)) == 4
            assert q.options["ABCD".index(q.correct_option)] == q.answer_text
            assert CONTENT in q.explanation
    service.process_run(run_id, review[1], lambda batch: pytest.fail("claimed twice"))


def test_ready_visible_between_batches_and_partial_survives_retry(review):
    run_id = seed(review, 12)
    calls = []
    def batch_generator(batch):
        calls.append(len(batch))
        if len(calls) == 1:
            return generate(batch)
        with review[1]() as db:
            run = db.get(Run, run_id)
            assert run.status == "ready" and run.generated_count == 10
            assert db.query(Question).count() == 10
        raise TimeoutError()
    service.process_run(run_id, review[1], batch_generator)
    assert calls == [10, 2, 2]
    with review[1]() as db:
        run = db.get(Run, run_id)
        assert (run.status, run.processed_count, run.generated_count, run.error_count) == ("partial", 12, 10, 2)
        assert len(run.audit["outcomes"]) == 12


def test_candidate_fallback_bad_item_isolation_and_json_retry(review):
    run_id = seed(review)
    attempts = []
    def generator(batch):
        attempts.append(1)
        if len(attempts) == 1:
            return []
        result = generate(batch)
        result["items"][0]["answer_candidates"].insert(0, {**candidate(), "answer_role": []})
        result["items"][1]["answer_candidates"] = "bad"
        return result
    service.process_run(run_id, review[1], generator)
    with review[1]() as db:
        run = db.get(Run, run_id)
        assert len(attempts) == 2
        assert (run.status, run.generated_count, run.skipped_count) == ("completed", 1, 1)


def test_api_start_progress_pagination_detail_and_ownership(review, monkeypatch):
    seed(review)
    monkeypatch.setattr(service, "process_run", lambda run_id: None)
    client, factory, _, headers, other_headers, knowledge_id, _ = review
    path = f"/api/v1/study/knowledge-runs/{knowledge_id}/choice-question-runs"
    response = client.post(path, headers=headers)
    assert response.status_code == 202
    data = response.json()["data"]
    assert data["reused"] and data["total_knowledge_count"] == 2
    assert client.post(path, headers=other_headers).status_code == 404
    # Invoke the original processor after restoring the patch.
    monkeypatch.undo()
    service.process_run(data["question_run_id"], factory, generate)
    base = "/api/v1/study/choice-question-runs/" + data["question_run_id"]
    progress = client.get(base, headers=headers).json()["data"]
    assert progress["status"] == "completed" and progress["first_question_id"]
    page = client.get(base + "/questions?page_size=1&page=2", headers=headers).json()["data"]
    assert page["total"] == 2 and len(page["questions"]) == 1
    detail = base + "/questions/" + progress["first_question_id"]
    assert client.get(detail, headers=headers).status_code == 200
    for url in [base, base + "/questions", detail]:
        assert client.get(url, headers=other_headers).status_code == 404
        assert client.get(url).status_code == 401
    assert client.get(base + "/questions?page=0", headers=headers).status_code == 422
    assert client.get(base + "/questions/missing", headers=headers).status_code == 404


def test_migration_idempotent(review):
    from database.study_choice_question_migration import migrate_study_choice_questions
    with review[1]() as db:
        engine = db.get_bind()
        migrate_study_choice_questions(engine)
        migrate_study_choice_questions(engine)
        assert "study_choice_questions" in inspect(engine).get_table_names()


def test_failed_batch_then_later_batch_still_processed(review):
    run_id = seed(review, 12)
    calls = []
    def generator(batch):
        calls.append(len(batch))
        if len(batch) == 10:
            raise ValueError("invalid JSON")
        return generate(batch)
    service.process_run(run_id, review[1], generator)
    with review[1]() as db:
        run = db.get(Run, run_id)
        assert calls == [10, 10, 2]
        assert (run.status, run.generated_count, run.error_count, run.processed_count) == ("partial", 2, 10, 12)


def test_all_errors_and_zero_eligible(review):
    from fastapi import HTTPException
    run_id = seed(review)
    service.process_run(run_id, review[1], lambda batch: {"invalid": True})
    with review[1]() as db:
        run = db.get(Run, run_id)
        assert run.status == "failed" and run.error_count == 2 and run.finished_at
        db.query(Unit).filter_by(run_id=review[5]).update({"deleted_at": datetime.now(timezone.utc)})
        db.commit()
        with pytest.raises(HTTPException) as error:
            service.create_run(db, review[2], review[5])
        assert error.value.status_code == 409


def test_duplicate_and_foreign_model_ids_cannot_create_extra_questions(review):
    run_id = seed(review)
    def generator(batch):
        payload = generate(batch)
        payload["items"].append(copy.deepcopy(payload["items"][0]))
        payload["items"].append({"knowledge_unit_id": "foreign", "answer_candidates": [candidate()]})
        return payload
    service.process_run(run_id, review[1], generator)
    with review[1]() as db:
        run = db.get(Run, run_id)
        assert run.generated_count == 1 and run.skipped_count == 1


def test_database_enforces_one_question_per_unit(review):
    from sqlalchemy.exc import IntegrityError
    run_id = seed(review)
    service.process_run(run_id, review[1], generate)
    with review[1]() as db:
        run = db.get(Run, run_id)
        snapshot = run.snapshots[0]
        question, _ = service.assemble(snapshot, generate([snapshot])["items"][0], run_id, 999)
        db.add(question)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        assert db.query(Question).filter_by(question_run_id=run_id).count() == 2
