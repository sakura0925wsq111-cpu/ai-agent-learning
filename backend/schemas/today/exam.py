# -*- coding: utf-8 -*-
"""Exam Pydantic schemas."""

from datetime import date

from pydantic import BaseModel, Field


class ExamCreate(BaseModel):
    """Request: create an exam."""
    subject: str = Field(..., min_length=1, max_length=200)
    exam_date: date
    start_time: str | None = Field(None, pattern=r"^\d{2}:\d{2}$")
    end_time: str | None = Field(None, pattern=r"^\d{2}:\d{2}$")
    location: str | None = None
    notes: str | None = None
    source: str = Field(default="manual")


class ExamUpdate(BaseModel):
    """Request: update an exam."""
    subject: str | None = None
    exam_date: date | None = None
    start_time: str | None = None
    end_time: str | None = None
    location: str | None = None
    notes: str | None = None


class ExamResponse(BaseModel):
    """Response: a single exam."""
    id: str
    user_id: str
    subject: str
    exam_date: str
    start_time: str | None
    end_time: str | None
    location: str | None
    notes: str | None
    source: str
    created_at: str
    updated_at: str


class ExamListResponse(BaseModel):
    """Response: list of exams."""
    user_id: str
    total: int
    exams: list[ExamResponse]
