# -*- coding: utf-8 -*-
"""Todo REST API -- CRUD endpoints for /api/v1/todos."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from loguru import logger

from database.session import get_db
from schemas.response import APIResponse
from core.exceptions import NotFoundException
from crud.base import CRUDBase
from models.todo import Todo
from crud.user import user as user_crud
from utils.auth import get_current_user_id, require_user_access

router = APIRouter(prefix="/todos", tags=["todos"])
todo_crud = CRUDBase[Todo](Todo)


class TodoCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    deadline: str | None = None
    source: str = Field(default="manual")


class TodoUpdate(BaseModel):
    title: str | None = None
    status: str | None = Field(default=None, pattern=r"^(pending|done|archived|cancelled)$")
    deadline: str | None = None


class TodoResponse(BaseModel):
    id: str
    user_id: str
    title: str
    status: str
    deadline: str | None
    source: str | None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


@router.post("", response_model=APIResponse[dict], status_code=201)
def create_todo(
    payload: TodoCreate,
    user_id: str = Query(..., description="User ID"),
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """Create a new todo item."""
    require_user_access(user_id, current_user_id)
    if user_crud.get(db, id=user_id) is None:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")

    obj = todo_crud.create(db, obj_in={
        "user_id": user_id,
        "title": payload.title,
        "deadline": payload.deadline,
        "source": payload.source,
        "status": "pending",
    })
    return APIResponse.ok(data={
        "id": obj.id, "title": obj.title, "status": obj.status,
        "deadline": obj.deadline, "source": obj.source,
    })


@router.get("", response_model=APIResponse[dict])
def list_todos(
    user_id: str = Query(..., description="User ID"),
    status: str = Query(default="pending", description="Filter: pending / done / archived / all"),
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """List todos for a user, optionally filtered by status."""
    require_user_access(user_id, current_user_id)
    if user_crud.get(db, id=user_id) is None:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")

    query = db.query(Todo).filter(Todo.user_id == user_id)
    if status != "all":
        query = query.filter(Todo.status == status)
    query = query.order_by(Todo.created_at.desc())
    todos = query.all()

    from models.today import PlanTask
    from models.growth import GrowthReport
    links = db.query(PlanTask).filter(
        PlanTask.user_id == user_id,
        PlanTask.todo_id.in_([item.id for item in todos]),
    ).all() if todos else []
    link_map = {item.todo_id: item for item in links}
    report_ids = [item.growth_report_id for item in links if item.growth_report_id]
    reports = db.query(GrowthReport).filter(
        GrowthReport.user_id == user_id,
        GrowthReport.id.in_(report_ids),
    ).all() if report_ids else []
    report_map = {item.id: item for item in reports}
    agent_labels = {
        "graduate": "考研", "career": "就业", "employment": "就业",
        "civil": "考公", "major": "转专业",
    }
    items = []
    for todo in todos:
        link = link_map.get(todo.id)
        report = report_map.get(link.growth_report_id) if link else None
        items.append({
            "id": todo.id, "title": todo.title, "status": todo.status,
            "deadline": todo.deadline, "source": todo.source,
            "source_label": (
                f"成长计划·{agent_labels.get(report.agent_type, '规划')}"
                if report else None
            ),
            "growth_session_id": link.growth_session_id if link else None,
            "growth_agent": report.agent_type if report else None,
            "created_at": todo.created_at.isoformat() if todo.created_at else None,
        })

    return APIResponse.ok(data={"user_id": user_id, "total": len(items), "todos": items})


@router.put("/{todo_id}", response_model=APIResponse[dict])
def update_todo(
    todo_id: str,
    payload: TodoUpdate,
    user_id: str = Query(..., description="User ID"),
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """Update a todo (title, status, deadline)."""
    require_user_access(user_id, current_user_id)
    obj = db.query(Todo).filter(Todo.id == todo_id, Todo.user_id == user_id).first()
    if obj is None:
        raise NotFoundException(f"Todo {todo_id} not found")

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if value is not None:
            setattr(obj, key, value)
    db.commit()
    db.refresh(obj)
    return APIResponse.ok(data={
        "id": obj.id, "title": obj.title, "status": obj.status,
        "deadline": obj.deadline, "source": obj.source,
    })


@router.delete("/{todo_id}", response_model=APIResponse[dict])
def delete_todo(
    todo_id: str,
    user_id: str = Query(..., description="User ID"),
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """Permanently delete a todo."""
    require_user_access(user_id, current_user_id)
    obj = db.query(Todo).filter(Todo.id == todo_id, Todo.user_id == user_id).first()
    if obj is None:
        raise NotFoundException(f"Todo {todo_id} not found")
    # Growth-plan tasks are execution evidence.  Keep the bridge intact and
    # treat removal as an explicit "no longer executing" decision instead of
    # erasing it from progress history.
    from models.today import PlanTask
    linked_plan_task = db.query(PlanTask).filter(
        PlanTask.user_id == user_id,
        PlanTask.todo_id == todo_id,
    ).first()
    if linked_plan_task is not None:
        obj.status = "cancelled"
        db.commit()
        return APIResponse.ok(data={"cancelled": todo_id, "source": "ai_plan"})

    db.delete(obj)
    db.commit()
    return APIResponse.ok(data={"deleted": todo_id})


@router.post("/{todo_id}/toggle", response_model=APIResponse[dict])
def toggle_todo(
    todo_id: str,
    user_id: str = Query(..., description="User ID"),
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """Toggle todo status: pending -> done -> archived.
    After archived, the item is effectively removed from active view."""
    require_user_access(user_id, current_user_id)
    obj = db.query(Todo).filter(Todo.id == todo_id, Todo.user_id == user_id).first()
    if obj is None:
        raise NotFoundException(f"Todo {todo_id} not found")

    transitions = {"pending": "done", "done": "archived", "archived": "pending"}
    obj.status = transitions.get(obj.status, "pending")
    db.commit()
    db.refresh(obj)
    return APIResponse.ok(data={
        "id": obj.id, "title": obj.title, "status": obj.status,
    })
