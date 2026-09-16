"""Verify real HTTP background execution and first-batch readiness with Uvicorn."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import time
import uuid
from pathlib import Path


OUTPUT = Path("tmp/study-choice-async-probe-20260916").resolve()
OUTPUT.mkdir(parents=True, exist_ok=True)
probe_database = OUTPUT / "probe.sqlite"
probe_database.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{(OUTPUT / 'probe.sqlite').as_posix()}"
os.environ["STUDY_UPLOAD_DIR"] = str(OUTPUT / "uploads")

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import httpx
import uvicorn

import models  # noqa: F401
from app.main import app
from database.base import Base
from database.session import SessionLocal, engine
from models.study import StudyChoiceQuestionRun, StudyDocument, StudyKnowledgeRun, StudyKnowledgeUnit
from models.user import User
from services import study_choice_questions
from utils.auth import create_token, hash_password

LABELS = list("甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥天地玄黄宇宙洪荒日月")


def _generator(snapshots: list[dict]) -> dict:
    """A deterministic slow model stand-in isolates task scheduling from model quality."""
    time.sleep(1.5)
    items = []
    for snapshot in snapshots:
        label = LABELS[int(snapshot["knowledge_unit_id"].rsplit("-", 1)[1])]
        answer = f"核心名词{label}"
        items.append({
            "knowledge_unit_id": snapshot["knowledge_unit_id"],
            "answer_candidates": [{
                "answer_text": answer,
                "answer_role": "core_term",
                "distractors": [f"近义名词甲{label}", f"近义名词乙{label}", f"近义名词丙{label}"],
            }],
        })
    return {"items": items}


def main() -> None:
    Base.metadata.create_all(engine)
    real_process = study_choice_questions.process_run
    study_choice_questions.process_run = lambda run_id: real_process(run_id, generator=_generator)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8876, log_level="warning", lifespan="off"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    report: dict = {"test": "real_http_background_first_ten", "events": []}
    started = time.perf_counter()
    try:
        for _ in range(40):
            try:
                httpx.get("http://127.0.0.1:8876/docs", timeout=0.2)
                break
            except httpx.TransportError:
                time.sleep(0.05)
        else:
            raise RuntimeError("uvicorn_not_ready")
        with SessionLocal() as db:
            user = User(student_id="async-" + uuid.uuid4().hex[:8], name="async", nickname="async", password_hash=hash_password("pass"))
            db.add(user)
            db.flush()
            document = StudyDocument(user_id=user.id, original_filename="probe.pdf", file_type="pdf", storage_path="unused", file_size=1, sha256="a" * 64)
            db.add(document)
            db.flush()
            knowledge_run = StudyKnowledgeRun(document_id=document.id, revision=1, request_key=uuid.uuid4().hex, pipeline_version="probe", source_sha256=document.sha256)
            db.add(knowledge_run)
            db.flush()
            for index in range(31):
                unit_id = f"unit-{index:02d}"
                content = f"异步验证资料中的核心名词{LABELS[index]}，用于验证第一批题目先可见且后台继续生成。"
                db.add(StudyKnowledgeUnit(id=unit_id, run_id=knowledge_run.id, document_id=document.id, knowledge_type="statement", structured_revision_id="probe", content=content, content_hash=hashlib.sha256(content.encode()).hexdigest(), source_key=unit_id, disposition="usable", source_refs=[{"page": 1}]))
            db.commit()
            knowledge_run_id = knowledge_run.id
            headers = {"Authorization": "Bearer " + create_token(user.id)}
        with httpx.Client(base_url="http://127.0.0.1:8876", headers=headers, timeout=10) as client:
            sent = time.perf_counter()
            response = client.post(f"/api/v1/study/knowledge-runs/{knowledge_run_id}/choice-question-runs")
            elapsed = time.perf_counter() - sent
            response.raise_for_status()
            run_id = response.json()["data"]["question_run_id"]
            report["start_response_seconds"] = round(elapsed, 3)
            report["start_status"] = response.json()["data"]["status"]
            report["events"].append({"event": "start_returned", "seconds": round(time.perf_counter() - started, 3)})
            ready = None
            completed = None
            while time.perf_counter() - started < 20:
                state = client.get(f"/api/v1/study/choice-question-runs/{run_id}").json()["data"]
                event = {"seconds": round(time.perf_counter() - started, 3), "status": state["status"], "processed": state["processed_count"], "generated": state["generated_count"]}
                if not report["events"] or report["events"][-1] != event:
                    report["events"].append(event)
                if ready is None and state["status"] == "ready" and state["generated_count"] >= 10 and state["processed_count"] < state["total_knowledge_count"]:
                    ready = event
                if state["status"] == "completed":
                    completed = event
                    break
                time.sleep(0.1)
            report["ready_during_background"] = ready
            report["completed"] = completed
            assert report["start_response_seconds"] < 1
            assert ready is not None
            assert completed is not None and completed["generated"] == 31
            report["result"] = "PASS"
    except Exception as exc:
        report["result"] = "FAILED"
        report["error"] = str(exc)
        raise
    finally:
        report["total_seconds"] = round(time.perf_counter() - started, 3)
        (OUTPUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        server.should_exit = True
        thread.join(timeout=3)
        engine.dispose()
        study_choice_questions.process_run = real_process
        print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
