# -*- coding: utf-8 -*-
"""Planning API — FastAPI routes for the PlanningAgent framework.

Endpoints:
    GET  /planning/agents          — list all available agents
    POST /planning/start           — start a new planning session
    POST /planning/chat            — send a message (auto-creates session if needed)
    POST /planning/resume          — resume a session with saved state
    GET  /planning/report/{id}     — get the final report for a session
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from pydantic import ValidationError

from planning.router import PlanningRouter
from planning.state import PlanningState
from schemas.planning import (
    PlanningAgentType,
    PlanningChatRequest,
    PlanningChatResponse,
    PlanningStartRequest,
    PlanningResumeRequest,
    PlanningReport,
    PlanningAgentListResponse,
    PlanningAgentInfo,
    RiskItem,
    AdvantageItem,
    PlanPhase,
)

router = APIRouter(prefix="/planning", tags=["planning"])

# ── In-memory session store (replace with DB in production) ────
# Structure: {session_id: {"agent_type": str, "state": dict, "report": dict}}
_sessions: dict[str, dict[str, Any]] = {}

# ── Router singleton (initialized at app startup) ──────────────
_planning_router: PlanningRouter | None = None


def get_router() -> PlanningRouter:
    """Dependency: get the PlanningRouter singleton."""
    global _planning_router
    if _planning_router is None:
        from services.llm_service import get_llm_service
        _planning_router = PlanningRouter(get_llm_service())
    return _planning_router


# ── Helper: parse report into PlanningReport ───────────────────

def _build_report(raw: dict[str, Any] | None) -> PlanningReport | None:
    """Parse raw report dict into a PlanningReport model."""
    if not raw:
        return None
    try:
        return PlanningReport(
            summary=raw.get("summary", ""),
            current_status=raw.get("current_status", ""),
            main_problem=raw.get("main_problem", ""),
            goal=raw.get("goal", ""),
            advantages=[
                AdvantageItem(**a) for a in raw.get("advantages", [])
                if isinstance(a, dict)
            ],
            risks=[
                RiskItem(**r) for r in raw.get("risks", [])
                if isinstance(r, dict)
            ],
            action_plan=[
                PlanPhase(**p) for p in raw.get("action_plan", [])
                if isinstance(p, dict)
            ],
            next_question=raw.get("next_question", ""),
        )
    except ValidationError as e:
        logger.warning("Report validation error: {}", e)
        return None


# ── Endpoints ──────────────────────────────────────────────────

@router.get("/agents", response_model=PlanningAgentListResponse)
async def list_agents(router_: PlanningRouter = Depends(get_router)):
    """List all available planning agents with labels."""
    agents = router_.list_agents()
    return PlanningAgentListResponse(
        agents=[PlanningAgentInfo(**a) for a in agents]
    )


@router.post("/start", response_model=PlanningChatResponse)
async def start_session(
    request: PlanningStartRequest,
    router_: PlanningRouter = Depends(get_router),
):
    """Start a new planning session.

    Creates a new agent instance, initializes state, and returns the first question.
    """
    agent_type = request.agent.value

    try:
        agent = router_.get_agent(agent_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Initialize with empty profile (will be collected via follow-up)
    state = agent.init_state()

    # Generate session ID
    session_id = str(uuid.uuid4())

    # Start the first follow-up question
    result = agent.chat("开始规划")

    # Store session
    _sessions[session_id] = {
        "agent_type": agent_type,
        "state": state.to_dict(),
        "report": result.get("report"),
    }

    logger.info("Planning session started: {} ({})", session_id, agent_type)

    return PlanningChatResponse(
        session_id=session_id,
        agent=agent_type,
        agent_label=agent.agent_label,
        step=result.get("step", "follow_up"),
        finished=result.get("finished", False),
        message=result.get("message", ""),
        follow_up_round=result.get("follow_up_round", 0),
        max_follow_up_rounds=result.get("max_follow_up_rounds", 7),
        report=_build_report(result.get("report")),
        state=result.get("state"),
    )


@router.post("/chat", response_model=PlanningChatResponse)
async def chat(
    request: PlanningChatRequest,
    router_: PlanningRouter = Depends(get_router),
):
    """Send a message to a planning agent.

    If session_id is None, a new session is auto-created.
    If session_id is provided, the existing session is resumed.
    """
    agent_type = request.agent.value

    # Auto-create session if no session_id
    if request.session_id is None:
        session_id = str(uuid.uuid4())
        try:
            agent = router_.get_agent(agent_type)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        agent.init_state()
    else:
        session_id = request.session_id
        session_data = _sessions.get(session_id)
        if session_data is None:
            raise HTTPException(status_code=404, detail="Session not found")

        try:
            agent = router_.get_agent(agent_type)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # Restore state
        saved_state = PlanningState.from_dict(session_data.get("state", {}))
        agent.restore_state(saved_state)

    # Process message
    result = agent.chat(request.message)

    # Update session store
    _sessions[session_id] = {
        "agent_type": agent_type,
        "state": result.get("state", {}),
        "report": result.get("report"),
    }

    return PlanningChatResponse(
        session_id=session_id,
        agent=agent_type,
        agent_label=agent.agent_label,
        step=result.get("step", "follow_up"),
        finished=result.get("finished", False),
        message=result.get("message", ""),
        follow_up_round=result.get("follow_up_round", 0),
        max_follow_up_rounds=result.get("max_follow_up_rounds", 7),
        report=_build_report(result.get("report")),
        state=result.get("state"),
    )


@router.post("/resume", response_model=PlanningChatResponse)
async def resume_session(
    request: PlanningResumeRequest,
    router_: PlanningRouter = Depends(get_router),
):
    """Resume an existing planning session with saved state."""
    session_data = _sessions.get(request.session_id)
    if session_data is None:
        raise HTTPException(status_code=404, detail="Session not found")

    agent_type = session_data["agent_type"]

    try:
        agent = router_.get_agent(agent_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Restore state
    saved_state = PlanningState.from_dict(session_data.get("state", {}))
    agent.restore_state(saved_state)

    result = agent.chat(request.message)

    # Update session store
    _sessions[request.session_id] = {
        "agent_type": agent_type,
        "state": result.get("state", {}),
        "report": result.get("report"),
    }

    return PlanningChatResponse(
        session_id=request.session_id,
        agent=agent_type,
        agent_label=agent.agent_label,
        step=result.get("step", "follow_up"),
        finished=result.get("finished", False),
        message=result.get("message", ""),
        follow_up_round=result.get("follow_up_round", 0),
        max_follow_up_rounds=result.get("max_follow_up_rounds", 7),
        report=_build_report(result.get("report")),
        state=result.get("state"),
    )


@router.get("/report/{session_id}")
async def get_report(session_id: str):
    """Get the final planning report for a completed session."""
    session_data = _sessions.get(session_id)
    if session_data is None:
        raise HTTPException(status_code=404, detail="Session not found")

    report = session_data.get("report")
    if report is None:
        raise HTTPException(status_code=404, detail="Report not yet generated")

    return {
        "session_id": session_id,
        "agent": session_data["agent_type"],
        "report": report,
    }
