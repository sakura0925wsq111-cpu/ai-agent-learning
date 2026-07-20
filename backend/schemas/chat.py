"""Chat request and response schemas."""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Incoming chat message."""

    message: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="User message text",
    )


class ChatResponse(BaseModel):
    """LLM reply."""

    reply: str = Field(..., description="AI response text")
