"""Authenticated Study API mounted at /api/v1/study."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from core.config import settings
from core.exceptions import NotFoundException, ValidationException
from database.session import get_db
from models.study import (
    StudyDocument,
    StudyDocumentUnit,
    StudyKnowledgeRun,
    StudyKnowledgeUnit,
    StudyChoiceQuestion,
)
from models.user import User
from schemas.response import APIResponse
from schemas.study import (
    StudyDocumentListResponse,
    StudyDocumentResponse,
    StudyDocumentUnitListResponse,
    StudyDocumentUnitResponse,
    StudyParseResponse,
    StudyKnowledgeRunListResponse,
    StudyKnowledgeRunResponse,
    StudyKnowledgeStartRequest,
    StudyKnowledgeStartResponse,
    StudyKnowledgeUnitListResponse,
    StudyKnowledgeUnitResponse,
    StudyKnowledgeVersionRequest,
    StudyKnowledgeEditRequest,
    StudyKnowledgeBatchConfirmRequest,
    StudyChoiceQuestionRunResponse,
    StudyChoiceQuestionResponse,
    StudyChoiceQuestionListResponse,
)
from services import study_review, study_choice_questions
from services.study_files import LocalStudyStorage
from services.study_parser import (
    StudyParseError,
    inspect_study_page_count,
    parse_and_store_document,
)
from services.study_knowledge import create_or_reuse_run, process_knowledge_run_by_id
from utils.auth import get_current_user_id


router = APIRouter(prefix="/study", tags=["study"])


@router.post(
    "/documents",
    response_model=APIResponse[StudyDocumentResponse],
    status_code=201,
)
async def upload_study_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """Validate and privately store one PDF or PPTX for the current user."""
    if db.get(User, current_user_id) is None:
        raise HTTPException(status_code=401, detail="登录用户不存在")

    document_id = str(uuid.uuid4())
    storage = LocalStudyStorage()
    stored = await storage.store_upload(
        upload=file,
        user_id=current_user_id,
        document_id=document_id,
    )
    try:
        page_count = inspect_study_page_count(
            stored.file_type, storage.resolve(stored.storage_path)
        )
        if page_count > settings.study_doubao_max_pages:
            raise ValidationException(
                f"学习资料页数不能超过 {settings.study_doubao_max_pages} 页"
            )
    except (StudyParseError, ValidationException) as exc:
        storage.delete(stored.storage_path)
        if isinstance(exc, StudyParseError):
            raise ValidationException(exc.message) from exc
        raise

    document = StudyDocument(
        id=document_id,
        user_id=current_user_id,
        original_filename=stored.original_filename,
        file_type=stored.file_type,
        storage_path=stored.storage_path,
        file_size=stored.size,
        sha256=stored.sha256,
        status="uploaded",
        page_count=page_count,
    )
    try:
        db.add(document)
        db.commit()
        db.refresh(document)
    except Exception:
        db.rollback()
        storage.delete(stored.storage_path)
        raise

    return APIResponse.ok(
        data=StudyDocumentResponse.model_validate(document),
        message="学习资料上传成功",
    )


@router.post(
    "/documents/{document_id}/parse",
    response_model=APIResponse[StudyParseResponse],
)
def parse_study_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """Parse one owned source file into page- or slide-level units."""
    document = (
        db.query(StudyDocument)
        .filter(
            StudyDocument.id == document_id,
            StudyDocument.user_id == current_user_id,
        )
        .first()
    )
    if document is None:
        raise NotFoundException("学习资料不存在")
    try:
        unit_count = parse_and_store_document(db, document)
    except StudyParseError as exc:
        raise ValidationException(exc.message) from exc
    db.refresh(document)
    return APIResponse.ok(data=StudyParseResponse(
        document=StudyDocumentResponse.model_validate(document),
        unit_count=unit_count,
    ))


@router.get(
    "/documents/{document_id}/units",
    response_model=APIResponse[StudyDocumentUnitListResponse],
)
def list_study_document_units(
    document_id: str,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """List parsed units only when the source document belongs to the user."""
    document = (
        db.query(StudyDocument.id)
        .filter(
            StudyDocument.id == document_id,
            StudyDocument.user_id == current_user_id,
        )
        .first()
    )
    if document is None:
        raise NotFoundException("学习资料不存在")
    units = (
        db.query(StudyDocumentUnit)
        .filter(StudyDocumentUnit.document_id == document_id)
        .order_by(StudyDocumentUnit.page_number, StudyDocumentUnit.unit_index)
        .all()
    )
    return APIResponse.ok(data=StudyDocumentUnitListResponse(
        total=len(units),
        units=[StudyDocumentUnitResponse.model_validate(unit) for unit in units],
    ))


@router.post(
    "/documents/{document_id}/knowledge-runs",
    response_model=APIResponse[StudyKnowledgeStartResponse],
    status_code=202,
)
def start_study_knowledge_run(
    document_id: str,
    payload: StudyKnowledgeStartRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """Queue a versioned extraction run; exact-version repeats are reused."""
    document = (
        db.query(StudyDocument)
        .filter(
            StudyDocument.id == document_id,
            StudyDocument.user_id == current_user_id,
        )
        .first()
    )
    if document is None:
        raise NotFoundException("学习资料不存在")
    run, reused = create_or_reuse_run(
        db,
        document,
        force=payload.force,
        pipeline_version=payload.pipeline_version,
    )
    resumable = (
        reused
        and run.pipeline_version == "doubao-vision-v2"
        and run.status == "failed"
        and bool((run.statistics or {}).get("failed_page_numbers"))
    )
    if resumable:
        run.status = "queued"
        run.error_code = None
        run.error_message = None
        run.finished_at = None
        db.commit()
        db.refresh(run)
    if not reused or resumable:
        background_tasks.add_task(process_knowledge_run_by_id, run.id)
    return APIResponse.ok(
        data=StudyKnowledgeStartResponse(
            run=StudyKnowledgeRunResponse.model_validate(run),
            reused=reused,
        ),
        message=("已从失败页面继续处理" if resumable else "已复用相同处理版本" if reused else "知识点处理已排队"),
    )


@router.get(
    "/documents/{document_id}/knowledge-runs",
    response_model=APIResponse[StudyKnowledgeRunListResponse],
)
def list_study_knowledge_runs(
    document_id: str,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    document = (
        db.query(StudyDocument.id)
        .filter(
            StudyDocument.id == document_id,
            StudyDocument.user_id == current_user_id,
        )
        .first()
    )
    if document is None:
        raise NotFoundException("学习资料不存在")
    runs = (
        db.query(StudyKnowledgeRun)
        .filter(StudyKnowledgeRun.document_id == document_id)
        .order_by(StudyKnowledgeRun.revision.desc())
        .all()
    )
    return APIResponse.ok(data=StudyKnowledgeRunListResponse(
        total=len(runs),
        runs=[StudyKnowledgeRunResponse.model_validate(run) for run in runs],
    ))


@router.get(
    "/knowledge-runs/{run_id}",
    response_model=APIResponse[StudyKnowledgeRunResponse],
)
def get_study_knowledge_run(
    run_id: str,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    run = (
        db.query(StudyKnowledgeRun)
        .join(StudyDocument, StudyDocument.id == StudyKnowledgeRun.document_id)
        .filter(
            StudyKnowledgeRun.id == run_id,
            StudyDocument.user_id == current_user_id,
        )
        .first()
    )
    if run is None:
        raise NotFoundException("知识点处理记录不存在")
    return APIResponse.ok(data=StudyKnowledgeRunResponse.model_validate(run))


@router.get(
    "/knowledge-runs/{run_id}/knowledge-units",
    response_model=APIResponse[StudyKnowledgeUnitListResponse],
)
def list_study_knowledge_units(
    run_id: str,
    disposition: str | None = Query(default=None, pattern="^(usable|uncertain|unsupported)$"),
    review_status: str | None = Query(default=None, pattern="^(pending|confirmed)$"),
    deleted: str = Query(default="active", pattern="^(active|deleted|all)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    study_review.require_run(db, current_user_id, run_id)
    query = study_review.owned_units(db, current_user_id).filter(StudyKnowledgeUnit.run_id == run_id)
    if disposition is not None:
        query = query.filter(StudyKnowledgeUnit.disposition == disposition)
    if review_status is not None:
        query = query.filter(StudyKnowledgeUnit.review_status == review_status)
    if deleted == "active":
        query = query.filter(StudyKnowledgeUnit.deleted_at.is_(None))
    elif deleted == "deleted":
        query = query.filter(StudyKnowledgeUnit.deleted_at.is_not(None))
    total = query.count()
    units = query.order_by(StudyKnowledgeUnit.created_at, StudyKnowledgeUnit.id).offset((page - 1) * page_size).limit(page_size).all()
    return APIResponse.ok(data=StudyKnowledgeUnitListResponse(
        total=total, page=page, page_size=page_size,
        statistics=study_review.review_statistics(db, current_user_id, run_id),
        units=[StudyKnowledgeUnitResponse.model_validate(unit) for unit in units],
    ))



@router.get(
    "/documents",
    response_model=APIResponse[StudyDocumentListResponse],
)
def list_study_documents(
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """List only the authenticated user's learning documents."""
    documents = (
        db.query(StudyDocument)
        .filter(StudyDocument.user_id == current_user_id)
        .order_by(StudyDocument.created_at.desc())
        .all()
    )
    return APIResponse.ok(
        data=StudyDocumentListResponse(
            total=len(documents),
            documents=[StudyDocumentResponse.model_validate(item) for item in documents],
        )
    )


@router.get(
    "/documents/{document_id}",
    response_model=APIResponse[StudyDocumentResponse],
)
def get_study_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """Return a document only when it belongs to the authenticated user."""
    document = (
        db.query(StudyDocument)
        .filter(
            StudyDocument.id == document_id,
            StudyDocument.user_id == current_user_id,
        )
        .first()
    )
    if document is None:
        raise NotFoundException("学习资料不存在")
    return APIResponse.ok(data=StudyDocumentResponse.model_validate(document))


@router.get("/knowledge-units/{unit_id}", response_model=APIResponse[StudyKnowledgeUnitResponse])
def get_knowledge_unit(unit_id: str, db: Session = Depends(get_db), current_user_id: str = Depends(get_current_user_id)):
    return APIResponse.ok(data=StudyKnowledgeUnitResponse.model_validate(study_review.get_unit(db, current_user_id, unit_id)))


@router.patch("/knowledge-units/{unit_id}", response_model=APIResponse[StudyKnowledgeUnitResponse])
def edit_knowledge_unit(unit_id: str, payload: StudyKnowledgeEditRequest, db: Session = Depends(get_db), current_user_id: str = Depends(get_current_user_id)):
    unit = study_review.mutate_unit(db, current_user_id, unit_id, payload.version, "edit", content=payload.content, confirm=payload.confirm)
    return APIResponse.ok(data=StudyKnowledgeUnitResponse.model_validate(unit))


@router.delete("/knowledge-units/{unit_id}", response_model=APIResponse[StudyKnowledgeUnitResponse])
def delete_knowledge_unit(unit_id: str, version: int = Query(..., ge=1), db: Session = Depends(get_db), current_user_id: str = Depends(get_current_user_id)):
    unit = study_review.mutate_unit(db, current_user_id, unit_id, version, "delete")
    return APIResponse.ok(data=StudyKnowledgeUnitResponse.model_validate(unit))


@router.post("/knowledge-runs/{run_id}/confirm", response_model=APIResponse[list[StudyKnowledgeUnitResponse]])
def batch_confirm_knowledge_units(run_id: str, payload: StudyKnowledgeBatchConfirmRequest, db: Session = Depends(get_db), current_user_id: str = Depends(get_current_user_id)):
    units = study_review.confirm_batch(db, current_user_id, run_id, payload.items)
    return APIResponse.ok(data=[StudyKnowledgeUnitResponse.model_validate(unit) for unit in units])


@router.post("/knowledge-units/{unit_id}/confirm", response_model=APIResponse[StudyKnowledgeUnitResponse])
def confirm_knowledge_unit(unit_id: str, payload: StudyKnowledgeVersionRequest, db: Session = Depends(get_db), current_user_id: str = Depends(get_current_user_id)):
    unit = study_review.mutate_unit(db, current_user_id, unit_id, payload.version, "confirm")
    return APIResponse.ok(data=StudyKnowledgeUnitResponse.model_validate(unit))


@router.post("/knowledge-units/{unit_id}/unconfirm", response_model=APIResponse[StudyKnowledgeUnitResponse])
def unconfirm_knowledge_unit(unit_id: str, payload: StudyKnowledgeVersionRequest, db: Session = Depends(get_db), current_user_id: str = Depends(get_current_user_id)):
    unit = study_review.mutate_unit(db, current_user_id, unit_id, payload.version, "unconfirm")
    return APIResponse.ok(data=StudyKnowledgeUnitResponse.model_validate(unit))


@router.post("/knowledge-units/{unit_id}/restore", response_model=APIResponse[StudyKnowledgeUnitResponse])
def restore_knowledge_unit(unit_id: str, payload: StudyKnowledgeVersionRequest, db: Session = Depends(get_db), current_user_id: str = Depends(get_current_user_id)):
    unit = study_review.mutate_unit(db, current_user_id, unit_id, payload.version, "restore")
    return APIResponse.ok(data=StudyKnowledgeUnitResponse.model_validate(unit))


# Independent batch choice questions (no card or per-unit confirmation required).


def _choice_run_response(db, run, reused=False):
    first = db.query(StudyChoiceQuestion.id).filter_by(question_run_id=run.id).order_by(StudyChoiceQuestion.position).first()
    return StudyChoiceQuestionRunResponse(
        question_run_id=run.id, knowledge_run_id=run.knowledge_run_id, status=run.status,
        total_knowledge_count=run.total_count, processed_count=run.processed_count,
        generated_count=run.generated_count, skipped_count=run.skipped_count,
        error_count=run.error_count, first_question_id=first[0] if first else None, reused=reused,
        model=run.model, prompt_version=run.prompt_version, created_at=run.created_at,
        started_at=run.started_at, finished_at=run.finished_at)


@router.post("/knowledge-runs/{knowledge_run_id}/choice-question-runs",
             response_model=APIResponse[StudyChoiceQuestionRunResponse], status_code=202)
def start_choice_questions(knowledge_run_id: str, background_tasks: BackgroundTasks,
                           db: Session = Depends(get_db), current_user_id: str = Depends(get_current_user_id)):
    run, reused = study_choice_questions.create_run(db, current_user_id, knowledge_run_id)
    if run.status == "queued":
        background_tasks.add_task(study_choice_questions.process_run, run.id)
    return APIResponse.ok(data=_choice_run_response(db, run, reused))


@router.get("/choice-question-runs/{question_run_id}", response_model=APIResponse[StudyChoiceQuestionRunResponse])
def get_choice_run(question_run_id: str, db: Session = Depends(get_db), current_user_id: str = Depends(get_current_user_id)):
    run = study_choice_questions.owned_run(db, current_user_id, question_run_id)
    return APIResponse.ok(data=_choice_run_response(db, run))


@router.get("/choice-question-runs/{question_run_id}/questions", response_model=APIResponse[StudyChoiceQuestionListResponse])
def list_choice_questions(question_run_id: str, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                          db: Session = Depends(get_db), current_user_id: str = Depends(get_current_user_id)):
    study_choice_questions.owned_run(db, current_user_id, question_run_id)
    query = db.query(StudyChoiceQuestion).filter_by(question_run_id=question_run_id)
    return APIResponse.ok(data=StudyChoiceQuestionListResponse(total=query.count(), page=page, page_size=page_size,
        questions=[StudyChoiceQuestionResponse.model_validate(q) for q in query.order_by(StudyChoiceQuestion.position).offset((page - 1) * page_size).limit(page_size).all()]))


@router.get("/choice-question-runs/{question_run_id}/questions/{question_id}", response_model=APIResponse[StudyChoiceQuestionResponse])
def get_choice_question(question_run_id: str, question_id: str, db: Session = Depends(get_db), current_user_id: str = Depends(get_current_user_id)):
    study_choice_questions.owned_run(db, current_user_id, question_run_id)
    question = db.query(StudyChoiceQuestion).filter_by(question_run_id=question_run_id, id=question_id).first()
    if question is None:
        raise HTTPException(404, "选择题不存在")
    return APIResponse.ok(data=StudyChoiceQuestionResponse.model_validate(question))
