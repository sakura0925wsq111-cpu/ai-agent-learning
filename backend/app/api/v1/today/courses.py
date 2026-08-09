# -*- coding: utf-8 -*-
"""Courses CRUD API — manual creation + batch import target."""

import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from loguru import logger

from database.session import get_db
from pydantic import BaseModel, Field
from schemas.response import APIResponse
from core.exceptions import NotFoundException
from crud.user import user as user_crud
from models.today import Course
from schemas.today import CourseCreate, CourseUpdate, CourseResponse, CourseListResponse, CourseSchedule
from crud.base import CRUDBase
from utils.auth import get_current_user_id, require_user_access

router = APIRouter()
course_crud = CRUDBase[Course](Course)


def _course_to_dict(c: Course) -> dict:
    try:
        schedule = json.loads(c.schedule_json or "[]")
    except (json.JSONDecodeError, TypeError):
        schedule = []
    return {
        "id": c.id, "user_id": c.user_id, "name": c.name,
        "teacher": c.teacher, "location": c.location,
        "schedule": schedule, "notes": c.notes, "color": c.color,
        "source": c.source,
        "created_at": c.created_at.isoformat() if c.created_at else "",
        "updated_at": c.updated_at.isoformat() if c.updated_at else "",
    }


@router.post("", response_model=APIResponse[dict], status_code=201)
def create_course(
    payload: CourseCreate,
    user_id: str = Query(..., description="User ID"),
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """Manually create a course."""
    require_user_access(user_id, current_user_id)
    if user_crud.get(db, id=user_id) is None:
        raise NotFoundException(f"User {user_id} not found")

    obj = course_crud.create(db, obj_in={
        "user_id": user_id,
        "name": payload.name,
        "teacher": payload.teacher,
        "location": payload.location,
        "schedule_json": json.dumps(
            [s.model_dump() for s in payload.schedule], ensure_ascii=False
        ) if payload.schedule else "[]",
        "notes": payload.notes,
        "color": payload.color,
        "source": payload.source,
    })
    logger.info("Course created: {} (user={})", obj.id, user_id)
    return APIResponse.ok(data=_course_to_dict(obj))


@router.get("", response_model=APIResponse[dict])
def list_courses(
    user_id: str = Query(..., description="User ID"),
    weekday: int | None = Query(None, ge=1, le=7, description="Filter by weekday 1-7"),
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """List all courses for a user, optionally filtered by weekday."""
    require_user_access(user_id, current_user_id)
    if user_crud.get(db, id=user_id) is None:
        raise NotFoundException(f"User {user_id} not found")

    courses = db.query(Course).filter(Course.user_id == user_id).all()

    if weekday is not None:
        filtered: list[dict] = []
        for c in courses:
            d = _course_to_dict(c)
            if any(s.get("weekday") == weekday for s in d["schedule"]):
                filtered.append(d)
        return APIResponse.ok(data={
            "user_id": user_id, "total": len(filtered),
            "courses": filtered,
        })

    items = [_course_to_dict(c) for c in courses]
    return APIResponse.ok(data={
        "user_id": user_id, "total": len(items), "courses": items,
    })


@router.get("/{course_id}", response_model=APIResponse[dict])
def get_course(
    course_id: str,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """Get a single course by ID."""
    obj = db.query(Course).filter(
        Course.id == course_id, Course.user_id == current_user_id
    ).first()
    if obj is None:
        raise NotFoundException(f"Course {course_id} not found")
    return APIResponse.ok(data=_course_to_dict(obj))


@router.put("/{course_id}", response_model=APIResponse[dict])
def update_course(
    course_id: str,
    payload: CourseUpdate,
    user_id: str = Query(..., description="User ID"),
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """Update a course."""
    require_user_access(user_id, current_user_id)
    obj = db.query(Course).filter(
        Course.id == course_id, Course.user_id == user_id
    ).first()
    if obj is None:
        raise NotFoundException(f"Course {course_id} not found")

    update_data = payload.model_dump(exclude_unset=True)
    if "schedule" in update_data:
        update_data["schedule_json"] = json.dumps(
            [s.model_dump() if hasattr(s, "model_dump") else s
             for s in update_data.pop("schedule")],
            ensure_ascii=False,
        )

    for key, value in update_data.items():
        if value is not None:
            setattr(obj, key, value)
    db.commit()
    db.refresh(obj)
    logger.info("Course updated: {}", course_id)
    return APIResponse.ok(data=_course_to_dict(obj))


@router.delete("/{course_id}", response_model=APIResponse[dict])
def delete_course(
    course_id: str,
    user_id: str = Query(..., description="User ID"),
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """Delete a course."""
    require_user_access(user_id, current_user_id)
    obj = db.query(Course).filter(
        Course.id == course_id, Course.user_id == user_id
    ).first()
    if obj is None:
        raise NotFoundException(f"Course {course_id} not found")
    db.delete(obj)
    db.commit()
    logger.info("Course deleted: {}", course_id)
    return APIResponse.ok(data={"deleted": course_id})


class CourseBatchItem(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    teacher: str | None = None
    location: str | None = None
    schedule: list[CourseSchedule] = Field(default_factory=list)
    notes: str | None = None
    color: str = Field(default="#4A90D9")
    source: str = Field(default="manual")


class CourseBatchRequest(BaseModel):
    courses: list[CourseBatchItem] = Field(..., min_length=1, max_length=100)


@router.post("/batch", response_model=APIResponse[dict], status_code=201)
def batch_create_courses(
    payload: CourseBatchRequest,
    user_id: str = Query(..., description="User ID"),
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """Batch create multiple courses at once (manual or after PDF preview edit)."""
    require_user_access(user_id, current_user_id)
    if user_crud.get(db, id=user_id) is None:
        raise NotFoundException(f"User {user_id} not found")

    created = []
    for item in payload.courses:
        obj = course_crud.create(db, obj_in={
            "user_id": user_id,
            "name": item.name,
            "teacher": item.teacher,
            "location": item.location,
            "schedule_json": json.dumps(
                [s.model_dump() for s in item.schedule], ensure_ascii=False
            ) if item.schedule else "[]",
            "notes": item.notes,
            "color": item.color,
            "source": item.source,
        })
        created.append({"id": obj.id, "name": obj.name})

    logger.info("Batch created {} courses for user {}", len(created), user_id)
    return APIResponse.ok(data={
        "user_id": user_id,
        "created": len(created),
        "courses": created,
    })

