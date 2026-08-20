# -*- coding: utf-8 -*-
"""Exams CRUD API — manual creation + batch import target."""

from datetime import date, timedelta
from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from loguru import logger

from database.session import get_db
from schemas.response import APIResponse
from core.exceptions import NotFoundException
from core.time import business_today
from crud.user import user as user_crud
from models.today import Exam
from schemas.today import ExamCreate, ExamUpdate
from crud.base import CRUDBase
from utils.auth import get_current_user_id, require_user_access

router = APIRouter()
exam_crud = CRUDBase[Exam](Exam)


def _exam_to_dict(e: Exam) -> dict:
    return {
        "id": e.id, "user_id": e.user_id, "subject": e.subject,
        "exam_date": e.exam_date.isoformat() if e.exam_date else "",
        "start_time": e.start_time, "end_time": e.end_time,
        "location": e.location, "notes": e.notes, "source": e.source,
        "created_at": e.created_at.isoformat() if e.created_at else "",
        "updated_at": e.updated_at.isoformat() if e.updated_at else "",
    }


@router.post("", response_model=APIResponse[dict], status_code=201)
def create_exam(
    payload: ExamCreate,
    user_id: str = Query(..., description="User ID"),
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """Manually create an exam."""
    require_user_access(user_id, current_user_id)
    if user_crud.get(db, id=user_id) is None:
        raise NotFoundException(f"User {user_id} not found")

    obj = exam_crud.create(db, obj_in={
        "user_id": user_id,
        "subject": payload.subject,
        "exam_date": payload.exam_date,
        "start_time": payload.start_time,
        "end_time": payload.end_time,
        "location": payload.location,
        "notes": payload.notes,
        "source": payload.source,
    })
    logger.info("Exam created: {} (user={})", obj.id, user_id)
    return APIResponse.ok(data=_exam_to_dict(obj))


@router.get("", response_model=APIResponse[dict])
def list_exams(
    user_id: str = Query(..., description="User ID"),
    upcoming: bool = Query(False, description="Only exams in next 14 days"),
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """List exams for a user."""
    require_user_access(user_id, current_user_id)
    if user_crud.get(db, id=user_id) is None:
        raise NotFoundException(f"User {user_id} not found")

    query = db.query(Exam).filter(Exam.user_id == user_id)

    if upcoming:
        today = business_today()
        two_weeks = today + timedelta(days=14)
        query = query.filter(Exam.exam_date >= today, Exam.exam_date <= two_weeks)

    exams = query.order_by(Exam.exam_date.asc()).all()
    items = [_exam_to_dict(e) for e in exams]
    return APIResponse.ok(data={
        "user_id": user_id, "total": len(items), "exams": items,
    })


@router.get("/{exam_id}", response_model=APIResponse[dict])
def get_exam(
    exam_id: str,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """Get a single exam by ID."""
    obj = db.query(Exam).filter(
        Exam.id == exam_id, Exam.user_id == current_user_id
    ).first()
    if obj is None:
        raise NotFoundException(f"Exam {exam_id} not found")
    return APIResponse.ok(data=_exam_to_dict(obj))


@router.put("/{exam_id}", response_model=APIResponse[dict])
def update_exam(
    exam_id: str,
    payload: ExamUpdate,
    user_id: str = Query(..., description="User ID"),
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """Update an exam."""
    require_user_access(user_id, current_user_id)
    obj = db.query(Exam).filter(
        Exam.id == exam_id, Exam.user_id == user_id
    ).first()
    if obj is None:
        raise NotFoundException(f"Exam {exam_id} not found")

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if value is not None:
            setattr(obj, key, value)
    db.commit()
    db.refresh(obj)
    logger.info("Exam updated: {}", exam_id)
    return APIResponse.ok(data=_exam_to_dict(obj))


@router.delete("/{exam_id}", response_model=APIResponse[dict])
def delete_exam(
    exam_id: str,
    user_id: str = Query(..., description="User ID"),
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """Delete an exam."""
    require_user_access(user_id, current_user_id)
    obj = db.query(Exam).filter(
        Exam.id == exam_id, Exam.user_id == user_id
    ).first()
    if obj is None:
        raise NotFoundException(f"Exam {exam_id} not found")
    db.delete(obj)
    db.commit()
    logger.info("Exam deleted: {}", exam_id)
    return APIResponse.ok(data={"deleted": exam_id})


class ExamBatchItem(BaseModel):
    subject: str = Field(..., min_length=1, max_length=200)
    exam_date: date
    start_time: str | None = Field(None, pattern=r"^\d{2}:\d{2}$")
    end_time: str | None = Field(None, pattern=r"^\d{2}:\d{2}$")
    location: str | None = None
    notes: str | None = None
    source: str = Field(default="manual")


class ExamBatchRequest(BaseModel):
    exams: list[ExamBatchItem] = Field(..., min_length=1, max_length=100)


@router.post("/batch", response_model=APIResponse[dict], status_code=201)
def batch_create_exams(
    payload: ExamBatchRequest,
    user_id: str = Query(..., description="User ID"),
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """Batch create multiple exams at once."""
    require_user_access(user_id, current_user_id)
    if user_crud.get(db, id=user_id) is None:
        raise NotFoundException(f"User {user_id} not found")

    created = []
    for item in payload.exams:
        obj = exam_crud.create(db, obj_in={
            "user_id": user_id,
            "subject": item.subject,
            "exam_date": item.exam_date,
            "start_time": item.start_time,
            "end_time": item.end_time,
            "location": item.location,
            "notes": item.notes,
            "source": item.source,
        })
        created.append({"id": obj.id, "subject": obj.subject})

    logger.info("Batch created {} exams for user {}", len(created), user_id)
    return APIResponse.ok(data={
        "user_id": user_id,
        "created": len(created),
        "exams": created,
    })

