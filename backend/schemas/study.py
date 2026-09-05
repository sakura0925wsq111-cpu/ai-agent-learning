"""Pydantic response schemas for the Study API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class StudyDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    original_filename: str
    file_type: str
    file_size: int
    status: str
    page_count: int | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class StudyDocumentListResponse(BaseModel):
    total: int
    documents: list[StudyDocumentResponse]


class StudyDocumentUnitResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    page_number: int
    unit_index: int
    unit_type: str
    raw_text: str
    normalized_text: str
    safe_text: str
    extraction_method: str
    ocr_confidence: float | None
    ocr_blocks: list[dict]
    quality_status: str
    quality_reasons: list[str]


class StudyDocumentUnitListResponse(BaseModel):
    total: int
    units: list[StudyDocumentUnitResponse]


class StudyParseResponse(BaseModel):
    document: StudyDocumentResponse
    unit_count: int


class StudyKnowledgeStartRequest(BaseModel):
    force: bool = False


class StudyKnowledgeRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    revision: int
    pipeline_version: str
    source_sha256: str
    structured_revision_id: str | None
    status: str
    parser_name: str | None
    parser_version: str | None
    parser_config: dict
    extractor_config: dict
    reviewer_config: dict
    statistics: dict
    error_code: str | None
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class StudyKnowledgeStartResponse(BaseModel):
    run: StudyKnowledgeRunResponse
    reused: bool


class StudyKnowledgeRunListResponse(BaseModel):
    total: int
    runs: list[StudyKnowledgeRunResponse]


class StudyKnowledgeUnitResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    document_id: str
    knowledge_type: str
    structured_revision_id: str
    content: str
    context_refs: list[dict]
    source_refs: list[dict]
    extraction_meta: dict
    check_meta: dict
    review_meta: dict
    disposition: str
    reasons: list[str]
    created_at: datetime


class StudyKnowledgeUnitListResponse(BaseModel):
    total: int
    units: list[StudyKnowledgeUnitResponse]


__all__ = [
    "StudyDocumentResponse",
    "StudyDocumentListResponse",
    "StudyDocumentUnitResponse",
    "StudyDocumentUnitListResponse",
    "StudyParseResponse",
    "StudyKnowledgeStartRequest",
    "StudyKnowledgeRunResponse",
    "StudyKnowledgeStartResponse",
    "StudyKnowledgeRunListResponse",
    "StudyKnowledgeUnitResponse",
    "StudyKnowledgeUnitListResponse",
]
