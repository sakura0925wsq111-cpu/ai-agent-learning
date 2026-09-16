"""Pydantic response schemas for the Study API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    pipeline_version: Literal[
        "doubao-vision-v2",
        "doubao-direct-v1",
        "knowledge-v1",
        "knowledge-v2",
    ] | None = None


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
    original_content: str
    review_status: Literal["pending", "confirmed"]
    confirmed_at: datetime | None
    updated_at: datetime
    deleted_at: datetime | None
    version: int
    is_edited: bool
    source_usage: Literal["reference_only", "extraction_evidence"]
    context_refs: list[dict]
    source_refs: list[dict]
    extraction_meta: dict
    check_meta: dict
    review_meta: dict
    disposition: str
    reasons: list[str]
    created_at: datetime


class StudyKnowledgeReviewStatistics(BaseModel):
    active_count: int
    pending_count: int
    confirmed_count: int
    deleted_count: int


class StudyKnowledgeUnitListResponse(BaseModel):
    page: int
    page_size: int
    statistics: StudyKnowledgeReviewStatistics
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


class StudyKnowledgeVersionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1, strict=True)


class StudyKnowledgeEditRequest(StudyKnowledgeVersionRequest):
    content: str = Field(min_length=1, max_length=5000)
    confirm: bool = False

    @field_validator("content")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("正文不能为空")
        return value


class StudyKnowledgeBatchItem(StudyKnowledgeVersionRequest):
    id: str


class StudyKnowledgeBatchConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[StudyKnowledgeBatchItem] = Field(min_length=1, max_length=100)

    @field_validator("items")
    @classmethod
    def unique_ids(cls, items):
        if len({item.id for item in items}) != len(items):
            raise ValueError("知识点 ID 不能重复")
        return items


class StudyChoiceQuestionRunResponse(BaseModel):
    question_run_id: str
    knowledge_run_id: str
    status: Literal["queued", "processing", "ready", "completed", "partial", "failed"]
    total_knowledge_count: int
    processed_count: int
    generated_count: int
    skipped_count: int
    error_count: int
    first_question_id: str | None
    reused: bool = False
    model: str
    prompt_version: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class StudyChoiceQuestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    question_run_id: str
    knowledge_unit_id: str
    knowledge_unit_version: int
    source_content: str
    prompt: str
    options: list[str]
    correct_option: Literal["A", "B", "C", "D"]
    answer_text: str
    answer_start: int
    answer_end: int
    answer_role: str
    explanation: str
    source_refs: list[dict]
    generation_meta: dict
    position: int
    created_at: datetime


class StudyChoiceQuestionListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    questions: list[StudyChoiceQuestionResponse]
