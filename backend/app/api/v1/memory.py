# -*- coding: utf-8 -*-
"""Memory REST API — CRUD endpoints for /api/v1/memory."""

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database.session import get_db
from schemas.response import APIResponse
from schemas.memory import (
    MemoryCreate,
    MemoryUpdate,
    MemoryResponse,
    MemoryListResponse,
    MemoryBatchUpsert,
)
from services.memory_service import memory_service
from crud.user import user as user_crud
from core.exceptions import NotFoundException

router = APIRouter(prefix="/memory", tags=["memory"])


@router.post("", response_model=APIResponse[MemoryResponse], status_code=201)
def create_or_update_memory(payload: MemoryCreate, db: Session = Depends(get_db)):
    """Save or update a memory entry for a user (upsert)."""
    if user_crud.get(db, id=payload.user_id) is None:
        raise NotFoundException(f"User {payload.user_id} not found")
    result = memory_service.save_memory(db, data=payload)
    return APIResponse.ok(data=result)


@router.post("/batch", response_model=APIResponse[list[MemoryResponse]], status_code=201)
def batch_upsert_memory(payload: MemoryBatchUpsert, db: Session = Depends(get_db)):
    """Batch upsert multiple memory entries for a user."""
    if user_crud.get(db, id=payload.user_id) is None:
        raise NotFoundException(f"User {payload.user_id} not found")
    items = [item.model_dump() for item in payload.items]
    results = memory_service.save_batch(db, user_id=payload.user_id, items=items)
    return APIResponse.ok(data=results)


@router.get("/{user_id}", response_model=APIResponse[MemoryListResponse])
def get_user_memories(
    user_id: str,
    as_dict: bool = Query(default=False, description="Return as {key: value} dict"),
    db: Session = Depends(get_db),
):
    """Get all memory entries for a user."""
    if user_crud.get(db, id=user_id) is None:
        raise NotFoundException(f"User {user_id} not found")
    if as_dict:
        result = memory_service.load_memory(db, user_id=user_id, as_dict=True)
        return APIResponse.ok(data={"user_id": user_id, "memories": result})
    memories = memory_service.load_memory(db, user_id=user_id, as_dict=False)
    return APIResponse.ok(
        data=MemoryListResponse(user_id=user_id, total=len(memories), memories=memories)
    )


@router.get("/{user_id}/{key}", response_model=APIResponse[MemoryResponse])
def get_user_memory_by_key(user_id: str, key: str, db: Session = Depends(get_db)):
    """Get a specific memory entry by key."""
    result = memory_service.get_memory(db, user_id=user_id, key=key)
    if result is None:
        raise NotFoundException(f"Memory key '{key}' not found for user {user_id}")
    return APIResponse.ok(data=result)


@router.put("/{user_id}/{key}", response_model=APIResponse[MemoryResponse])
def update_memory_by_key(
    user_id: str, key: str, payload: MemoryUpdate, db: Session = Depends(get_db),
):
    """Update a specific memory entry by key."""
    result = memory_service.update_memory(db, user_id=user_id, key=key, data=payload)
    return APIResponse.ok(data=result)


@router.delete("/{user_id}/{key}", response_model=APIResponse[dict])
def delete_memory_by_key(user_id: str, key: str, db: Session = Depends(get_db)):
    """Delete a specific memory entry by key."""
    memory_service.delete_memory(db, user_id=user_id, key=key)
    return APIResponse.ok(data={"deleted": {"user_id": user_id, "key": key}})


# === Memory Panel endpoints (P3) ======================================


class MemoryPanelUpdate(BaseModel):
    """Payload for updating a memory via the panel."""
    value: str = Field(..., min_length=1, description="New memory value")


@router.get("/panel/{user_id}", response_model=APIResponse[dict])
def get_memory_panel(user_id: str, db: Session = Depends(get_db)):
    """Get the user-visible memory panel.

    Returns all memories with key, value, confidence, source
    for user review and correction.
    """
    if user_crud.get(db, id=user_id) is None:
        raise NotFoundException(f"User {user_id} not found")
    memories = memory_service.load_memory(db, user_id=user_id)
    total = memory_service.load_memory_count(db, user_id=user_id)
    panel_items: list[dict[str, Any]] = []
    for m in memories:
        panel_items.append({
            "key": m.key,
            "value": m.value,
            "confidence": m.confidence,
            "source": m.source,
            "importance": m.importance,
        })
    return APIResponse.ok(data={
        "user_id": user_id,
        "total": total,
        "max_capacity": 50,
        "memories": panel_items,
    })


@router.delete("/panel/{user_id}/{key:path}", response_model=APIResponse[dict])
def delete_memory_panel_item(user_id: str, key: str, db: Session = Depends(get_db)):
    """Delete a single memory entry from the panel by key."""
    memory_service.delete_memory(db, user_id=user_id, key=key)
    return APIResponse.ok(data={"deleted": {"user_id": user_id, "key": key}})


@router.patch("/panel/{user_id}/{key:path}", response_model=APIResponse[MemoryResponse])
def update_memory_panel_item(
    user_id: str, key: str, payload: MemoryPanelUpdate, db: Session = Depends(get_db),
):
    """Update a single memory entry's value from the panel."""
    update_data = MemoryUpdate(value=payload.value)
    result = memory_service.update_memory(db, user_id=user_id, key=key, data=update_data)
    return APIResponse.ok(data=result)
