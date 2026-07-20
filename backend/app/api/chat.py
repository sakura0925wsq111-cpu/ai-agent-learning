"""Chat API — POST /chat."""

from fastapi import APIRouter, Depends

from schemas.chat import ChatRequest, ChatResponse
from schemas.response import APIResponse
from services.llm_service import LLMService, get_llm_service

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=APIResponse[ChatResponse])
async def chat(
    request: ChatRequest,
    llm: LLMService = Depends(get_llm_service),
):
    """Send a message to the AI and get a reply."""
    reply = llm.chat(request.message)
    return APIResponse.ok(data=ChatResponse(reply=reply))
