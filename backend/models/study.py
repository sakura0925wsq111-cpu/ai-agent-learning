"""ORM models for the source-grounded Study MVP."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StudyDocument(Base):
    """A private learning document owned by one iCampus user."""

    __tablename__ = "study_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(10), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="uploaded")
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_study_documents_user_created", "user_id", "created_at"),
    )


class StudyDocumentUnit(Base):
    """A page-local source unit preserved for citation and card generation."""

    __tablename__ = "study_document_units"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("study_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_index: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="paragraph"
    )
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    safe_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    extraction_method: Mapped[str] = mapped_column(
        String(20), nullable=False, default="native"
    )
    ocr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    ocr_blocks: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    quality_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="accepted"
    )
    quality_reasons: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "document_id", "page_number", "unit_index", name="uq_study_unit_position"
        ),
        Index("ix_study_units_document_page", "document_id", "page_number"),
    )


class StudyKnowledgeRun(Base):
    """One immutable, versioned knowledge-extraction attempt."""

    __tablename__ = "study_knowledge_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("study_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    request_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    pipeline_version: Mapped[str] = mapped_column(String(80), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    structured_revision_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    parser_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    parser_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    parser_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    extractor_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    reviewer_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    statistics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    audit: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("document_id", "revision", name="uq_study_knowledge_run_revision"),
        Index(
            "ix_study_knowledge_run_reuse",
            "document_id",
            "source_sha256",
            "pipeline_version",
            "status",
        ),
    )


class StudyKnowledgePageCheckpoint(Base):
    """Durable page-level result for resumable direct multimodal extraction."""

    __tablename__ = "study_knowledge_page_checkpoints"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("study_knowledge_runs.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    statistics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        UniqueConstraint("run_id", "page_number", name="uq_study_knowledge_checkpoint_page"),
        Index("ix_study_knowledge_checkpoint_run_status", "run_id", "status"),
    )


class StudyStructuredBlock(Base):
    """A lossless source block used by a particular knowledge run."""

    __tablename__ = "study_structured_blocks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("study_knowledge_runs.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("study_documents.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    block_id: Mapped[str] = mapped_column(String(255), nullable=False)
    block_type: Mapped[str] = mapped_column(String(30), nullable=False)
    parent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    children: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    reading_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_spans: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    extraction_method: Mapped[str] = mapped_column(String(30), nullable=False)
    quality_signals: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    provider_raw_ref: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("run_id", "block_id", name="uq_study_structured_run_block"),
        Index("ix_study_structured_document_run", "document_id", "run_id"),
    )


class StudyKnowledgeUnit(Base):
    """A source-rebuilt knowledge candidate, including rejected dispositions."""

    __tablename__ = "study_knowledge_units"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("study_knowledge_runs.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("study_documents.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    knowledge_type: Mapped[str] = mapped_column(String(30), nullable=False)
    structured_revision_id: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    original_content: Mapped[str] = mapped_column(
        Text, nullable=False, default=lambda ctx: ctx.get_current_parameters()["content"]
    )
    review_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default="pending")
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    @property
    def is_edited(self) -> bool:
        return self.content != self.original_content

    @property
    def source_usage(self) -> str:
        return "reference_only" if self.is_edited else "extraction_evidence"

    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_key: Mapped[str] = mapped_column(String(64), nullable=False)
    context_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    source_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    extraction_meta: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    check_meta: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    review_meta: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    disposition: Mapped[str] = mapped_column(String(20), nullable=False)
    reasons: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_study_knowledge_document_run", "document_id", "run_id"),
        Index("ix_study_knowledge_run_disposition", "run_id", "disposition"),
    )


class StudyCard(Base):
    """A generated knowledge card with its source evidence stored inline."""

    __tablename__ = "study_cards"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("study_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_unit_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("study_document_units.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    front: Mapped[str] = mapped_column(Text, nullable=False)
    back: Mapped[str] = mapped_column(Text, nullable=False)
    highlights: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="candidate")
    reject_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_study_cards_document_status", "document_id", "status"),
    )


class StudyQuiz(Base):
    """A practice item generated from one validated card."""

    __tablename__ = "study_quizzes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    card_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("study_cards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quiz_type: Mapped[str] = mapped_column(String(20), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class StudyAttempt(Base):
    """One authenticated user's answer to a study quiz."""

    __tablename__ = "study_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    quiz_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("study_quizzes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_answer: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_study_attempts_user_created", "user_id", "created_at"),
    )


class StudyUserCardState(Base):
    """A user's accumulated learning state for one card."""

    __tablename__ = "study_user_card_states"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    card_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("study_cards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="new")
    study_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_attempted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("user_id", "card_id", name="uq_study_user_card_state"),
    )


class StudyChoiceQuestionRun(Base):
    __tablename__ = "study_choice_question_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    knowledge_run_id: Mapped[str] = mapped_column(ForeignKey("study_knowledge_runs.id", ondelete="CASCADE"), index=True)
    request_key: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    total_count: Mapped[int] = mapped_column(Integer)
    processed_count: Mapped[int] = mapped_column(Integer, default=0)
    generated_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    model: Mapped[str] = mapped_column(String(255))
    prompt_version: Mapped[str] = mapped_column(String(80))
    snapshots: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    statistics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    audit: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StudyChoiceQuestion(Base):
    __tablename__ = "study_choice_questions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    question_run_id: Mapped[str] = mapped_column(ForeignKey("study_choice_question_runs.id", ondelete="CASCADE"), index=True)
    knowledge_unit_id: Mapped[str] = mapped_column(ForeignKey("study_knowledge_units.id", ondelete="CASCADE"))
    knowledge_unit_version: Mapped[int] = mapped_column(Integer)
    source_content: Mapped[str] = mapped_column(Text)
    prompt: Mapped[str] = mapped_column(Text)
    options: Mapped[list[str]] = mapped_column(JSON)
    correct_option: Mapped[str] = mapped_column(String(1))
    answer_text: Mapped[str] = mapped_column(String(30))
    answer_start: Mapped[int] = mapped_column(Integer)
    answer_end: Mapped[int] = mapped_column(Integer)
    answer_role: Mapped[str] = mapped_column(String(30))
    explanation: Mapped[str] = mapped_column(Text)
    source_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    generation_meta: Mapped[dict[str, Any]] = mapped_column(JSON)
    position: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    __table_args__ = (UniqueConstraint("question_run_id", "knowledge_unit_id", name="uq_choice_run_unit"),)


__all__ = [
    "StudyChoiceQuestionRun",
    "StudyChoiceQuestion",
    "StudyDocument",
    "StudyDocumentUnit",
    "StudyKnowledgeRun",
    "StudyKnowledgePageCheckpoint",
    "StudyStructuredBlock",
    "StudyKnowledgeUnit",
    "StudyCard",
    "StudyQuiz",
    "StudyAttempt",
    "StudyUserCardState",
]
