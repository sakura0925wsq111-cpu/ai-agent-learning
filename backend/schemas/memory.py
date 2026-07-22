"""Memory Pydantic schemas."""

import json as _json
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

# Valid memory types
MEMORY_TYPES = ("profile", "goal", "action", "fact")


class MemoryCreate(BaseModel):
    """Payload for creating or setting a memory entry."""

    user_id: str = Field(..., description="ID of the user")
    key: str = Field(..., min_length=1, max_length=100, description="Memory key (e.g., major, goal)")
    value: str = Field(..., min_length=1, description="Memory value")
    memory_type: str = Field(default="fact", pattern=r"^(profile|goal|action|fact)$", description="Memory type")
    importance: int = Field(default=1, ge=1, le=10, description="Importance 1-10")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence 0-1")
    source: str = Field(default="", description="Source / evidence for this memory")


class MemoryUpdate(BaseModel):
    """Payload for updating an existing memory."""

    value: Optional[str] = Field(default=None, description="New value")
    memory_type: Optional[str] = Field(default=None, pattern=r"^(profile|goal|action|fact)$", description="New memory type")
    importance: Optional[int] = Field(default=None, ge=1, le=10, description="New importance")
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="New confidence")
    source: Optional[str] = Field(default=None, description="New source")


class MemoryResponse(BaseModel):
    """A single memory entry returned by the API."""

    id: str
    user_id: str
    key: str
    value: str
    memory_type: str = "fact"
    importance: int
    confidence: float = 1.0
    source: str = ""
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

    @property
    def parsed_value(self) -> Any:
        """Attempt to JSON-parse the value string."""
        try:
            return _json.loads(self.value)
        except (_json.JSONDecodeError, TypeError):
            return self.value


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
    memory_type: str = Field(default="fact", pattern=r"^(profile|goal|action|fact)$")
    importance: int = Field(default=1, ge=1, le=10)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source: str = Field(default="")