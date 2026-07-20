# -*- coding: utf-8 -*-
"""Sandbox API — FastAPI routes for the DecisionSandbox multi-path comparison system.

Endpoints:
    GET  /sandbox/paths          — list all available comparison paths
    POST /sandbox/start          — start a new sandbox session
    POST /sandbox/chat           — send a message during a sandbox session
    POST /sandbox/resume         — resume a session with saved state
    GET  /sandbox/result/{id}    — get the final projection result
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from sandbox.orchestrator import DecisionSandbox
from sandbox.schemas import (
    SandboxStartRequest,
    SandboxChatRequest,
    SandboxChatResponse,
    SandboxResumeRequest,
    SandboxResultResponse,
    SandboxPathListResponse,
    SandboxPathInfo,
    ProjectionResult,
)
from database.session import get_db
from sqlalchemy.orm import Session

router = APIRouter(prefix="/sandbox", tags=["sandbox"])

# ── Sandbox singleton ──────────────────────────────────────────
_sandbox: DecisionSandbox | None = None


def get_sandbox() -> DecisionSandbox:
    """Dependency: get the DecisionSandbox singleton."""
    global _sandbox
    if _sandbox is None:
        from services.llm_service import get_llm_service
        from planning.router import PlanningRouter
        from services.memory_service import memory_service

        _sandbox = DecisionSandbox(
            llm_service=get_llm_service(),
            planning_router=PlanningRouter(get_llm_service()),
            memory_service=memory_service,
        )
        logger.info("Sandbox singleton initialized")
    return _sandbox


# ── Session store ──────────────────────────────────────────────
# {session_id: serialized_state_dict}
_sandbox_sessions: dict[str, dict[str, Any]] = {}


def _save_session(sandbox: DecisionSandbox, session_id: str) -> None:
    """Persist a session to the session store."""
    session = sandbox.get_session(session_id)
    if session:
        _sandbox_sessions[session_id] = session.to_dict()


def _load_session(sandbox: DecisionSandbox, session_id: str) -> Any:
    """Load a session from the store and restore it in the sandbox."""
    data = _sandbox_sessions.get(session_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return sandbox.restore_session(data)


# ── Helper: build projection result ────────────────────────────

def _build_projection(raw: dict[str, Any] | None) -> ProjectionResult | None:
    """Build a ProjectionResult from raw dict, gracefully handling missing fields."""
    if not raw:
        return None
    try:
        return ProjectionResult(**raw)
    except Exception as exc:
        logger.warning("ProjectionResult validation failed: {}", exc)
        return None


# ── Endpoints ──────────────────────────────────────────────────

@router.get("/paths", response_model=SandboxPathListResponse)
async def list_paths(sandbox: DecisionSandbox = Depends(get_sandbox)):
    """List all available paths for comparison."""
    paths = sandbox.list_available_paths()
    return SandboxPathListResponse(
        paths=[SandboxPathInfo(**p) for p in paths]
    )


@router.post("/start", response_model=SandboxChatResponse)
async def start_session(
    request: SandboxStartRequest,
    sandbox: DecisionSandbox = Depends(get_sandbox),
    db: Session = Depends(get_db),
):
    """Start a new sandbox session.

    Creates a fresh session, loads user memories, and starts the discovery phase.
    If paths are pre-selected, they're set in the session.
    """
    # Start session with memory loading
    session = sandbox.start_session(
        user_id=request.user_id,
        db_session=db,
    )

    # Pre-load memories into profile
    sandbox._load_memory_into_profile(session)

    # Pre-set paths if specified
    if request.paths:
        session.path_selections = [p.value for p in request.paths]
        logger.info(
            "Sandbox[{}]: pre-selected paths: {}",
            session.session_id, session.path_selections,
        )

    # Kick off discovery phase
    result = sandbox.chat(session, "开始", db_session=db)

    # Persist session
    _save_session(sandbox, session.session_id)

    return SandboxChatResponse(
        session_id=session.session_id,
        user_id=session.user_id,
        phase=result["phase"],
        finished=result.get("finished", False),
        message=result["message"],
        discovery_round=result.get("discovery_round", 0),
        max_discovery_rounds=result.get("max_discovery_rounds", 7),
        path_selections=result.get("path_selections", []),
        projection_result=_build_projection(result.get("projection_result")),
        state=result.get("state"),
        error=result.get("error"),
    )


@router.post("/chat", response_model=SandboxChatResponse)
async def chat(
    request: SandboxChatRequest,
    sandbox: DecisionSandbox = Depends(get_sandbox),
    db: Session = Depends(get_db),
):
    """Send a message during a sandbox session.

    The message is processed through the current phase of the workflow.
    """
    session = _load_session(sandbox, request.session_id)

    if session.finished:
        # Session already complete — return cached result
        return SandboxChatResponse(
            session_id=session.session_id,
            user_id=session.user_id,
            phase=session.current_phase.value,
            finished=True,
            message="本次分析已完成。可以查看对比结果。",
            path_selections=session.path_selections,
            path_reports=session.path_reports if session.path_reports else None,
            projection_result=_build_projection(session.projection_result),
            state=session.to_dict(),
        )

    if not request.message.strip():
        # Empty message — return current state without advancing
        last_q = "请继续。"
        if session.discovery_history:
            last_q = session.discovery_history[-1]["q"]
        return SandboxChatResponse(
            session_id=session.session_id,
            user_id=session.user_id,
            phase=session.current_phase.value,
            finished=False,
            message=last_q,
            discovery_round=session.discovery_round,
            max_discovery_rounds=7,
            path_selections=session.path_selections,
            state=session.to_dict(),
        )

    result = sandbox.chat(session, request.message, db_session=db)

    # Persist session
    _save_session(sandbox, session.session_id)

    return SandboxChatResponse(
        session_id=session.session_id,
        user_id=session.user_id,
        phase=result["phase"],
        finished=result.get("finished", False),
        message=result["message"],
        discovery_round=result.get("discovery_round", 0),
        max_discovery_rounds=result.get("max_discovery_rounds", 7),
        path_selections=result.get("path_selections", []),
        path_reports=result.get("path_reports"),
        projection_result=_build_projection(result.get("projection_result")),
        state=result.get("state"),
        error=result.get("error"),
    )


@router.post("/resume", response_model=SandboxChatResponse)
async def resume_session(
    request: SandboxResumeRequest,
    sandbox: DecisionSandbox = Depends(get_sandbox),
    db: Session = Depends(get_db),
):
    """Resume a sandbox session with previously saved state.

    Used when the client has persisted the session state and wants to continue.
    """
    # Restore from the provided state
    from sandbox.state import SandboxSession
    session = SandboxSession.from_dict(request.state)
    sandbox._sessions[session.session_id] = session

    if session.finished:
        return SandboxChatResponse(
            session_id=session.session_id,
            user_id=session.user_id,
            phase=session.current_phase.value,
            finished=True,
            message="本次分析已完成。可以查看对比结果。",
            path_selections=session.path_selections,
            path_reports=session.path_reports if session.path_reports else None,
            projection_result=_build_projection(session.projection_result),
            state=session.to_dict(),
        )

    if not request.message.strip():
        return SandboxChatResponse(
            session_id=session.session_id,
            user_id=session.user_id,
            phase=session.current_phase.value,
            finished=False,
            message="请继续。已恢复上次的会话状态。",
            discovery_round=session.discovery_round,
            max_discovery_rounds=7,
            path_selections=session.path_selections,
            state=session.to_dict(),
        )

    result = sandbox.chat(session, request.message, db_session=db)

    # Persist session
    _save_session(sandbox, session.session_id)

    return SandboxChatResponse(
        session_id=session.session_id,
        user_id=session.user_id,
        phase=result["phase"],
        finished=result.get("finished", False),
        message=result["message"],
        discovery_round=result.get("discovery_round", 0),
        max_discovery_rounds=result.get("max_discovery_rounds", 7),
        path_selections=result.get("path_selections", []),
        path_reports=result.get("path_reports"),
        projection_result=_build_projection(result.get("projection_result")),
        state=result.get("state"),
        error=result.get("error"),
    )


@router.get("/result/{session_id}")
async def get_result(
    session_id: str,
    sandbox: DecisionSandbox = Depends(get_sandbox),
):
    """Get the final projection result for a completed session."""
    data = _sandbox_sessions.get(session_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Session not found")

    from sandbox.state import SandboxSession
    session = SandboxSession.from_dict(data)

    return {
        "session_id": session.session_id,
        "user_id": session.user_id,
        "finished": session.finished,
        "path_selections": session.path_selections,
        "path_reports": session.path_reports if session.path_reports else None,
        "projection_result": session.projection_result if session.projection_result else None,
    }
