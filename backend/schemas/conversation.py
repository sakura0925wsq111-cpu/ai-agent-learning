"""Conversation Pydantic schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ConversationCreate(BaseModel):
    """Payload for creating a conversation message."""

    user_id: str = Field(..., description="ID of the user")
    role: str = Field(..., pattern=r"^(user|assistant|system)$", description="Message role")
    content: str = Field(..., min_length=1, description="Message content")


class ConversationBatchCreate(BaseModel):
    """Create multiple messages at once."""

    user_id: str = Field(..., description="ID of the user")
    messages: list["ConversationMessageItem"] = Field(..., min_length=1)


class ConversationMessageItem(BaseModel):
    """A single message within a batch create."""

    role: str = Field(..., pattern=r"^(user|assistant|system)$")
    content: str = Field(..., min_length=1)


class ConversationResponse(BaseModel):
    """A single conversation message returned by the API."""

    id: str
    user_id: str
    role: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationListResponse(BaseModel):
    """Paginated list of messages."""

    user_id: str
    total: int
    messages: list[ConversationResponse]
