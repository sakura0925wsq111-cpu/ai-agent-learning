"""Memory Pydantic schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class MemoryCreate(BaseModel):
    """Payload for creating or setting a memory entry."""

    user_id: str = Field(..., description="ID of the user")
    key: str = Field(..., min_length=1, max_length=100, description="Memory key (e.g., major, goal)")
    value: str = Field(..., min_length=1, description="Memory value")
    importance: int = Field(default=1, ge=1, le=10, description="Importance 1-10")


class MemoryUpdate(BaseModel):
    """Payload for updating an existing memory."""

    value: Optional[str] = Field(default=None, description="New value")
    importance: Optional[int] = Field(default=None, ge=1, le=10, description="New importance")


class MemoryResponse(BaseModel):
    """A single memory entry returned by the API."""

    id: str
    user_id: str
    key: str
    value: str
    importance: int
    created_at: datetime

    model_config = {"from_attributes": True}


class MemoryListResponse(BaseModel):
    """List of memory entries."""

    user_id: str
    total: int
    memories: list[MemoryResponse]


class MemoryBatchUpsert(BaseModel):
    """Batch upsert: merge multiple key-value pairs for a user."""

    user_id: str = Field(..., description="ID of the user")
    items: list["MemoryBatchItem"] = Field(..., min_length=1)


class MemoryBatchItem(BaseModel):
    """Single item in a batch upsert."""

    key: str = Field(..., min_length=1, max_length=100)
    value: str = Field(..., min_length=1)
    importance: int = Field(default=1, ge=1, le=10)
