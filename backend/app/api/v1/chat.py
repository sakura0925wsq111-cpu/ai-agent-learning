"""Chat REST API v1 — POST /api/v1/chat with memory integration.

This replaces the simple /chat endpoint with one that:
- Reads user memory from DB
- Injects it into the system prompt
- Calls the LLM
- Auto-extracts new user information into memory
- Saves the conversation history
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from database.session import get_db
from schemas.response import APIResponse
from schemas.chat import ChatRequest, ChatResponse
from services.chat_service import get_chat_service
from services.llm_service import get_llm_service

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequestV1(BaseModel):
    """Chat request with user_id."""

    user_id: str = Field(..., description="ID of the user chatting")
    message: str = Field(..., min_length=1, max_length=2000, description="User message text")


class ChatResponseV1(BaseModel):
    """Chat response with reply."""

    user_id: str
    reply: str


@router.post("", response_model=APIResponse[ChatResponseV1])
def chat_v1(
    request: ChatRequestV1,
    db: Session = Depends(get_db),
):
    """Send a message to the AI coach.

    The system automatically:
    - Loads the user's memory and profile
    - Injects context into the system prompt
    - Calls the LLM for a response
    - Extracts any new user information into memory
    - Saves the conversation history

    Returns the AI's reply.
    """
    llm = get_llm_service()
    chat_service = get_chat_service(llm)

    reply = chat_service.chat(
        db=db,
        user_id=request.user_id,
        message=request.message,
    )

    return APIResponse.ok(
        data=ChatResponseV1(user_id=request.user_id, reply=reply)
    )


# Also keep the legacy /chat endpoint for backward compatibility
@router.post("/legacy", response_model=APIResponse[ChatResponse])
def chat_legacy(request: ChatRequest):
    """Legacy chat endpoint (no memory, no user context)."""
    llm = get_llm_service()
    reply = llm.chat(request.message)
    return APIResponse.ok(data=ChatResponse(reply=reply))
