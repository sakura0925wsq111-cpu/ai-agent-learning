# -*- coding: utf-8 -*-
"""Course Pydantic schemas."""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class CourseSchedule(BaseModel):
    """A single schedule entry within a course."""
    weekday: int = Field(..., ge=1, le=7)
    start: int = Field(..., ge=1, le=12)
    end: int = Field(..., ge=1, le=12)
    weeks: str = Field(default="1-16")


class CourseCreate(BaseModel):
    """Request: create a course."""
    name: str = Field(..., min_length=1, max_length=200)
    teacher: str | None = None
    location: str | None = None
    schedule: list[CourseSchedule] = Field(default_factory=list)
    notes: str | None = None
    color: str = Field(default="#4A90D9")
    source: str = Field(default="manual")
    semester_start: date | None = None


class CourseUpdate(BaseModel):
    """Request: update a course."""
    name: str | None = None
    teacher: str | None = None
    location: str | None = None
    schedule: list[CourseSchedule] | None = None
    notes: str | None = None
    color: str | None = None
    semester_start: date | None = None


class CourseResponse(BaseModel):
    """Response: a single course."""
    id: str
    user_id: str
    name: str
    teacher: str | None
    location: str | None
    schedule: list[dict[str, Any]]
    notes: str | None
    color: str | None
    source: str
    semester_start: date | None = None
    created_at: str
    updated_at: str


class CourseListResponse(BaseModel):
    """Response: list of courses."""
    user_id: str
    total: int
    courses: list[CourseResponse]
