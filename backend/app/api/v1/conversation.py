"""Conversation REST API — CRUD endpoints for /api/v1/conversation."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database.session import get_db
from schemas.response import APIResponse
from schemas.conversation import (
    ConversationCreate,
    ConversationResponse,
    ConversationListResponse,
)
from crud.conversation import conversation as conversation_crud
from crud.user import user as user_crud
from core.exceptions import NotFoundException

router = APIRouter(prefix="/conversation", tags=["conversation"])


@router.post("", response_model=APIResponse[ConversationResponse], status_code=201)
def create_message(payload: ConversationCreate, db: Session = Depends(get_db)):
    """Save a conversation message (user or assistant)."""
    # Verify user exists
    if user_crud.get(db, id=payload.user_id) is None:
        raise NotFoundException(f"User {payload.user_id} not found")

    data = payload.model_dump()
    obj = conversation_crud.create(db, obj_in=data)
    return APIResponse.ok(data=ConversationResponse.model_validate(obj))


@router.get("/{user_id}", response_model=APIResponse[ConversationListResponse])
def get_user_conversation(
    user_id: str,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Get conversation messages for a user (paginated, oldest first)."""
    if user_crud.get(db, id=user_id) is None:
        raise NotFoundException(f"User {user_id} not found")

    messages = conversation_crud.get_by_user(db, user_id=user_id, skip=skip, limit=limit)
    total = conversation_crud.count(db, user_id=user_id)

    return APIResponse.ok(
        data=ConversationListResponse(
            user_id=user_id,
            total=total,
            messages=[ConversationResponse.model_validate(m) for m in messages],
        )
    )


@router.delete("/{user_id}", response_model=APIResponse[dict])
def delete_user_conversation(user_id: str, db: Session = Depends(get_db)):
    """Delete all conversation messages for a user."""
    if user_crud.get(db, id=user_id) is None:
        raise NotFoundException(f"User {user_id} not found")

    count = conversation_crud.delete_by_user(db, user_id=user_id)
    return APIResponse.ok(data={"deleted_count": count})
