# -*- coding: utf-8 -*-
"""Growth Agent API ? chat-based conversation flow endpoints.

Endpoints:
  POST /growth/chat      ? Send a message, get next question or report
  POST /growth/start     ? Start a new growth session
  GET  /growth/state/{user_id}   ? Get current session state
  GET  /growth/history/{user_id}  ? Get session history
  GET  /growth/report/{session_id} ? Get final report
  GET  /growth/agents    ? List available agents
"""

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from loguru import logger

from database.session import get_db
from schemas.response import APIResponse
from schemas.growth import (
    GrowthChatRequest,
    GrowthStartRequest,
    GrowthChatResponse,
    GrowthStateResponse,
    GrowthHistoryResponse,
    GrowthReportResponse,
    AgentListResponse,
)
from services.growth_service import get_growth_service
from services.llm_service import get_llm_service
from agent.router import AgentRouter

router = APIRouter(prefix="/growth", tags=["growth"])


@router.post("/chat", response_model=APIResponse[GrowthChatResponse])
async def growth_chat(
    request: GrowthChatRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Send a message to a growth agent.

    If session_id is provided, continues an existing session.
    If session_id is None, auto-creates a new session.

    Example:
    ```json
    {
      "user_id": "1",
      "agent": "career",
      "message": "???????????"
    }
    ```
    """
    logger.info("POST /growth/chat user={}, agent={}", request.user_id, request.agent)
    llm = get_llm_service()
    service = get_growth_service(llm)
    result = service.chat(db, request=request)
    return APIResponse.ok(data=result).model_dump()


@router.post("/start", response_model=APIResponse[GrowthChatResponse])
async def growth_start(
    request: GrowthStartRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Start a new growth session (backward-compatible).

    Internally delegates to /chat with no session_id.
    Returns the first question card.

    Example:
    ```json
    {"user_id": "1", "agent": "career"}
    ```
    """
    logger.info("POST /growth/start user={}, agent={}", request.user_id, request.agent)
    llm = get_llm_service()
    service = get_growth_service(llm)
    # Convert to a chat request with empty message (auto-creates session)
    from schemas.growth import GrowthChatRequest
    chat_req = GrowthChatRequest(
        user_id=request.user_id,
        agent=request.agent,
        message="",  # not used when creating session
        session_id=None,
    )
    result = service.chat(db, request=chat_req)
    return APIResponse.ok(data=result).model_dump()


@router.get("/state/{user_id}", response_model=APIResponse[GrowthStateResponse])
async def growth_state(
    user_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Get the current growth session state for a user.

    Returns the most recent active session, or an empty response
    if no active session exists.
    """
    logger.debug("GET /growth/state user={}", user_id)
    llm = get_llm_service()
    service = get_growth_service(llm)
    result = service.get_state(db, user_id=user_id)
    return APIResponse.ok(data=result).model_dump()


@router.get("/history/{user_id}", response_model=APIResponse[GrowthHistoryResponse])
async def growth_history(
    user_id: str,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Get growth session history for a user.

    Returns a list of past growth sessions with summaries.
    """
    logger.debug("GET /growth/history user={}, limit={}", user_id, limit)
    llm = get_llm_service()
    service = get_growth_service(llm)
    result = service.get_history(db, user_id=user_id, limit=limit)
    return APIResponse.ok(data=result).model_dump()


@router.get("/report/{session_id}", response_model=APIResponse[GrowthReportResponse])
async def growth_report(
    session_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Get the final growth report for a completed session.

    Only available after the session has reached the REPORT stage.
    """
    logger.debug("GET /growth/report session={}", session_id)
    llm = get_llm_service()
    service = get_growth_service(llm)
    result = service.get_report(db, session_id=session_id)
    return APIResponse.ok(data=result).model_dump()


@router.get("/agents", response_model=APIResponse[AgentListResponse])
async def list_agents() -> dict[str, Any]:
    """List all available growth agents.

    Returns agent types and their Chinese labels for UI display.
    """
    agents = AgentRouter.list_agents()
    return APIResponse.ok(data={"agents": agents}).model_dump()
