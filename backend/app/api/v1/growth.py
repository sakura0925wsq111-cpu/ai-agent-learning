# -*- coding: utf-8 -*-
"""Growth Agent API — chat-based conversation flow + SSE streaming + human-in-the-loop.

Endpoints (existing, backward-compatible):
  POST /growth/chat      — Send a message, get next question or report
  POST /growth/start     — Start a new growth session
  GET  /growth/state/{user_id}   — Get current session state
  GET  /growth/history/{user_id} — Get session history
  GET  /growth/report/{session_id} — Get final report
  GET  /growth/agents    — List available agents

Endpoints (NEW — LangGraph capabilities):
  GET  /growth/stream/{session_id}  — SSE streaming endpoint
  POST /growth/correct   — Re-run analysis with user correction
  POST /growth/approve   — Approve analysis, proceed to full report
"""

from typing import Any

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
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
from planning.router import PlanningRouter

router = APIRouter(prefix="/growth", tags=["growth"])


# ── Existing endpoints (backward-compatible) ──────────────────

@router.post("/chat", response_model=APIResponse[GrowthChatResponse])
async def growth_chat(
    request: GrowthChatRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Send a message to a growth agent.

    If session_id is provided, continues an existing session.
    If session_id is None, auto-creates a new session.
    """
    logger.info("POST /growth/chat user={}, agent={}", request.user_id, request.agent)
    llm = get_llm_service()
    service = get_growth_service(llm)
    result = await service.chat(db, request=request)
    return APIResponse.ok(data=result).model_dump()


@router.post("/start", response_model=APIResponse[GrowthChatResponse])
async def growth_start(
    request: GrowthStartRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Start a new growth session.

    Returns the first dynamic follow-up question.
    """
    logger.info("POST /growth/start user={}, agent={}", request.user_id, request.agent)
    llm = get_llm_service()
    service = get_growth_service(llm)
    result = await service.start_session(db, request=request)
    return APIResponse.ok(data=result).model_dump()


@router.get("/state/{user_id}", response_model=APIResponse[GrowthStateResponse])
async def growth_state(
    user_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Get the current growth session state for a user."""
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
    """Get growth session history for a user."""
    llm = get_llm_service()
    service = get_growth_service(llm)
    result = service.get_history(db, user_id=user_id, limit=limit)
    return APIResponse.ok(data=result).model_dump()


@router.get("/report/{session_id}", response_model=APIResponse[GrowthReportResponse])
async def growth_report(
    session_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Get the final growth report for a completed session."""
    llm = get_llm_service()
    service = get_growth_service(llm)
    result = service.get_report(db, session_id=session_id)
    return APIResponse.ok(data=result).model_dump()



@router.get("/conversation/{session_id}", response_model=APIResponse[list])
async def growth_conversation(
    session_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Get all messages for a growth session."""
    llm = get_llm_service()
    service = get_growth_service(llm)
    result = service.get_conversation(db, session_id=session_id)
    return APIResponse.ok(data=result).model_dump()

@router.get("/agents", response_model=APIResponse[AgentListResponse])
async def list_agents() -> dict[str, Any]:
    """List all available growth agents."""
    agents = PlanningRouter.list_agents()
    return APIResponse.ok(data={"agents": agents}).model_dump()


# ── NEW: SSE Streaming ────────────────────────────────────────

@router.get("/stream/{session_id}")
async def growth_stream(
    session_id: str,
    user_id: str = Query(..., description="User ID"),
    message: str = Query("", description="User message (empty = continue)"),
    agent: str = Query("career", description="Agent type"),
    db: Session = Depends(get_db),
):
    """Stream graph execution as SSE events.

    Each node completion emits:
        {"step":"<node_name>","status":"done","data":{"session_id":...,"stage":...,"message":...}}

    Usage from frontend:
        const es = new EventSource("/growth/stream/sess_123?user_id=u1");
        es.onmessage = (e) => { const {step, status, data} = JSON.parse(e.data); ... };
    """
    logger.info("SSE /growth/stream session={}, user={}, msg={}", session_id, user_id, message[:50])
    llm = get_llm_service()
    service = get_growth_service(llm)

    async def event_generator():
        async for sse in service.chat_stream(
            db, session_id=session_id, user_id=user_id,
            message=message, agent_type=agent,
        ):
            yield sse

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── NEW: Human-in-the-loop ────────────────────────────────────

from pydantic import BaseModel, Field


class CorrectionRequest(BaseModel):
    """Request to correct the analysis direction."""
    session_id: str = Field(..., description="Session ID")
    user_id: str = Field(..., description="User ID")
    correction: str = Field(..., min_length=1, max_length=2000, description="Correction text, e.g. 'I want to do frontend instead'")


class ApprovalRequest(BaseModel):
    """Request to approve the analysis and continue."""
    session_id: str = Field(..., description="Session ID")
    user_id: str = Field(..., description="User ID")


@router.post("/correct", response_model=APIResponse[GrowthChatResponse])
async def growth_correct(
    request: CorrectionRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Re-run analysis with a user correction.

    Called when the user disagrees with the AI''s analysis direction.
    The graph will go back to the analyze node with the correction text.
    """
    logger.info("POST /growth/correct session={}, correction={}", request.session_id, request.correction[:50])
    llm = get_llm_service()
    service = get_growth_service(llm)
    result = await service.correct_analysis(
        db, session_id=request.session_id,
        user_id=request.user_id, correction=request.correction,
    )
    return APIResponse.ok(data=result).model_dump()


@router.post("/approve", response_model=APIResponse[GrowthChatResponse])
async def growth_approve(
    request: ApprovalRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Approve the analysis and proceed to generate the full report.

    Called when the user clicks 'continue' after reviewing the analysis.
    Resumes the graph past the interrupt_before barrier.
    """
    logger.info("POST /growth/approve session={}", request.session_id)
    llm = get_llm_service()
    service = get_growth_service(llm)
    result = await service.approve_analysis(
        db, session_id=request.session_id,
        user_id=request.user_id,
    )
    return APIResponse.ok(data=result).model_dump()
