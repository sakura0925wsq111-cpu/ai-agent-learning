"""Authenticated Study API mounted at /api/v1/study."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from core.exceptions import NotFoundException, ValidationException
from database.session import get_db
from models.study import (
    StudyDocument,
    StudyDocumentUnit,
    StudyKnowledgeRun,
    StudyKnowledgeUnit,
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
)
from services.study_files import LocalStudyStorage
from services.study_parser import StudyParseError, parse_and_store_document
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

    document = StudyDocument(
        id=document_id,
        user_id=current_user_id,
        original_filename=stored.original_filename,
        file_type=stored.file_type,
        storage_path=stored.storage_path,
        file_size=stored.size,
        sha256=stored.sha256,
        status="uploaded",
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
    run, reused = create_or_reuse_run(db, document, force=payload.force)
    if not reused:
        background_tasks.add_task(process_knowledge_run_by_id, run.id)
    return APIResponse.ok(
        data=StudyKnowledgeStartResponse(
            run=StudyKnowledgeRunResponse.model_validate(run),
            reused=reused,
        ),
        message="已复用相同处理版本" if reused else "知识点处理已排队",
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
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    run = (
        db.query(StudyKnowledgeRun.id)
        .join(StudyDocument, StudyDocument.id == StudyKnowledgeRun.document_id)
        .filter(
            StudyKnowledgeRun.id == run_id,
            StudyDocument.user_id == current_user_id,
        )
        .first()
    )
    if run is None:
        raise NotFoundException("知识点处理记录不存在")
    query = db.query(StudyKnowledgeUnit).filter(StudyKnowledgeUnit.run_id == run_id)
    if disposition is not None:
        query = query.filter(StudyKnowledgeUnit.disposition == disposition)
    units = query.order_by(StudyKnowledgeUnit.created_at, StudyKnowledgeUnit.id).all()
    return APIResponse.ok(data=StudyKnowledgeUnitListResponse(
        total=len(units),
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
