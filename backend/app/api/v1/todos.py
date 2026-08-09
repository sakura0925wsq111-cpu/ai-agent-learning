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
    status: str | None = Field(default=None, pattern=r"^(pending|done|archived)$")
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

    items = [{
        "id": t.id, "title": t.title, "status": t.status,
        "deadline": t.deadline, "source": t.source,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    } for t in todos]

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
