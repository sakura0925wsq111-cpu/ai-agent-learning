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

import asyncio
import json
from typing import Any

import re
from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from sandbox.orchestrator import DecisionSandbox
from sandbox.state import SANDBOX_PATHS
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
from core.rate_limit import enforce_ai_daily_limit
from utils.auth import get_current_user_id, require_user_access
from utils.json_parser import safe_json_parse



def _clean_message(msg: str) -> str:
    """Remove internal fields from sandbox output."""
    if not msg:
        return msg
    msg = re.sub(r'{[^{}]*"(?:next_question|reasoning|analysis|internal)"[^{}]*}\n?', '', msg)
    lines = msg.split(chr(10))
    cleaned = []
    for line in lines:
        s = line.strip()
        if s.startswith("###") and any(kw in s for kw in ["Reason", "Analysis", "Next", "Output"]):
            continue
        if s.startswith("{") and len(s) > 20 and s.endswith("}"):
            continue
        cleaned.append(line)
    return chr(10).join(cleaned).strip()


def _initial_question_for_paths(path_types: list[str]) -> str:
    """Start with a personal fact, never a request to choose a selected path."""
    pair = frozenset(path_types[:2])
    if pair == frozenset(("career", "graduate")):
        return "你现在最能代表自己能力的一项项目、实习或作品是什么？暂时没有也可以直接说“暂无”。"
    if pair == frozenset(("career", "civil")):
        return "你计划毕业后优先在哪个城市或地区发展？暂时没有也可以直接说“暂无”。"
    if pair == frozenset(("graduate", "civil")):
        return "你目前已经开始准备的内容是什么？比如专业课、英语、行测或申论；暂时没有也可以直接说“暂无”。"
    if pair == frozenset(("major", "career")):
        return "你希望转入的专业或对应岗位方向是什么？暂时没有也可以直接说“暂无”。"
    return "你现在最能代表自己能力的一项经历是什么？暂时没有也可以直接说“暂无”。"


_INVALID_FIRST_QUESTION_MARKERS = (
    "更希望", "更愿意", "更看重", "选哪个", "哪条路径", "哪个方向",
    "纠结", "你知道", "你了解", "是否了解", "是否知道",
)


def _valid_initial_question(raw: str) -> str:
    """Accept only one factual, user-answerable LLM question."""
    question = re.sub(r"\s+", "", str(raw or "")).replace("?", "？")
    if question and not question.endswith("？"):
        question = question.rstrip("。！…") + "？"
    if (
        len(question) < 8
        or len(question) > 90
        or question.count("？") != 1
        or any(marker in question for marker in _INVALID_FIRST_QUESTION_MARKERS)
    ):
        return ""
    return question


async def _initial_question_from_llm(sandbox: DecisionSandbox, session) -> str:
    """Generate the first preselected-path question; fall back safely on failure."""
    labels = "、".join(SANDBOX_PATHS.get(path_type, path_type) for path_type in session.path_selections)
    profile = {key: value for key, value in session.user_profile.items() if value}
    system_prompt = """你是大学生成长决策沙盘的首轮提问助手。用户已经固定选择了对比路径。

只输出 JSON：{"question":"..."}。

规则：
1. 只问一个用户本人能确认的事实：项目、实习、作品、课程基础、已开始的准备、目标地区或现实约束。
2. 不能要求用户在已选路径之间做选择，禁止问“更希望/更愿意/更看重/选哪个/哪条路径”。
3. 不问用户是否知道薪资、政策、考试内容等 AI 应回答的信息。
4. 问题必须自然、具体，允许用户回答“暂无”或“不知道”。
5. 不要解释、标题、Markdown 或第二个问题。"""
    user_prompt = (
        f"已选路径：{labels}\n"
        f"已知画像：{json.dumps(profile, ensure_ascii=False) if profile else '暂无'}\n"
        "请生成第一轮问题。"
    )
    try:
        raw = await asyncio.wait_for(
            asyncio.to_thread(
                sandbox.llm.chat,
                user_message=user_prompt,
                system_prompt=system_prompt,
                temperature=0.2,
                max_tokens=160,
                request_timeout=20,
                max_retries=0,
            ),
            timeout=22,
        )
        parsed = safe_json_parse(raw)
        candidate = parsed.get("question", "") if isinstance(parsed, dict) else raw
        question = _valid_initial_question(candidate)
        if question:
            return question
        logger.warning("Sandbox initial question rejected; using deterministic fallback")
    except Exception as exc:
        logger.warning("Sandbox initial question generation failed; using fallback: {}", type(exc).__name__)
    return _initial_question_for_paths(session.path_selections)

router = APIRouter(tags=["sandbox"])

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
# Session helpers — sessions live in DecisionSandbox._sessions only.
# The API layer accesses them through sandbox methods with auth checks.


def _load_session(sandbox, session_id, user_id="", db=None):
    session = sandbox.get_session(session_id)
    if session is None and user_id and db is not None:
        # Process-local sessions may disappear after a restart. Restore the
        # latest serialized context owned by this user before returning 404.
        try:
            from services.memory_service import memory_service
            memory_service.wait_for_pending(user_id, timeout=5.0)
            state = memory_service.load_context(
                db, user_id=user_id, context_kind="sandbox", context_id=session_id,
            )
            if state:
                restored = sandbox.restore_session(state)
                if restored.user_id == user_id and restored.session_id == session_id:
                    session = restored
                else:
                    sandbox._sessions.pop(restored.session_id, None)
        except Exception as exc:
            logger.warning("Sandbox context restore failed: {}", exc)
    if session is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Session not found")
    if user_id and session.user_id != user_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Access denied")
    return session


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
async def list_paths(
    sandbox: DecisionSandbox = Depends(get_sandbox),
    current_user_id: str = Depends(get_current_user_id),
):
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
    current_user_id: str = Depends(enforce_ai_daily_limit),
):
    """Start a new sandbox session.

    Creates a fresh session, loads user memories, and starts the discovery phase.
    If paths are pre-selected, they're set in the session.
    """
    require_user_access(request.user_id, current_user_id)
    # Start session with memory loading
    session = sandbox.start_session(
        user_id=request.user_id,
        db_session=db,
    )


    # Pre-set paths if specified
    if request.paths:
        session.path_selections = [p.value for p in request.paths]
        session.path_selection_source = "preset"
        session.path_selection_locked = True
        logger.info(
            "Sandbox[{}]: pre-selected paths: {}",
            session.session_id, session.path_selections,
        )

    # Do not send a hidden synthetic "开始" turn through the LLM.  That turn
    # used to consume one of the three discovery rounds and was incorrectly
    # stored as if the user had answered a question.  The client displays this
    # same greeting before the user's first real message.
    if session.path_selections:
        labels = "、".join(
            SANDBOX_PATHS.get(path_type, path_type)
            for path_type in session.path_selections
        )
        first_question = await _initial_question_from_llm(sandbox, session)
        greeting = f"已记录你选择的{labels}。\n\n第一轮：{first_question}"
        session.last_discovery_question = first_question
        session.mark_question_asked(first_question)
    else:
        greeting = "你好，我是你的决策教练。你可以直接告诉我现在最纠结的选择，我会先给分析，再和你补齐关键信息。"
        session.last_discovery_question = "你现在最纠结的选择是什么？"
    session.last_discovery_response = greeting
    sandbox._persist_memory(
        session,
        db,
        user_message="",
        assistant_message=greeting,
    )

    return SandboxChatResponse(
        session_id=session.session_id,
        user_id=session.user_id,
        phase=session.current_phase.value,
        finished=False,
        message=greeting,
        discovery_round=0,
        max_discovery_rounds=3,
        path_selections=session.path_selections,
        path_selection_source=session.path_selection_source,
        path_selection_locked=session.path_selection_locked,
        state=session.to_dict(),
    )


@router.post("/chat", response_model=SandboxChatResponse)
async def chat(
    request: SandboxChatRequest,
    sandbox: DecisionSandbox = Depends(get_sandbox),
    db: Session = Depends(get_db),
    current_user_id: str = Depends(enforce_ai_daily_limit),
):
    """Send a message during a sandbox session.

    The message is processed through the current phase of the workflow.
    """
    require_user_access(request.user_id, current_user_id)
    session = _load_session(sandbox, request.session_id, current_user_id, db)

    if session.finished:
        # Session already complete — return cached result
        return SandboxChatResponse(
            session_id=session.session_id,
            user_id=session.user_id,
            phase=session.current_phase.value,
            finished=True,
            message="本次分析已完成。可以查看对比结果。",
            path_selections=session.path_selections,
            path_selection_source=session.path_selection_source,
            path_selection_locked=session.path_selection_locked,
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
            path_selection_source=session.path_selection_source,
            path_selection_locked=session.path_selection_locked,
            state=session.to_dict(),
        )

    result = sandbox.chat(session, request.message, db_session=db)

    # Persist session

    return SandboxChatResponse(
        session_id=session.session_id,
        user_id=session.user_id,
        phase=result["phase"],
        finished=result.get("finished", False),
        message=result["message"],
        discovery_round=result.get("discovery_round", 0),
        max_discovery_rounds=result.get("max_discovery_rounds", 7),
        path_selections=result.get("path_selections", []),
        path_selection_source=result.get("path_selection_source", session.path_selection_source),
        path_selection_locked=result.get("path_selection_locked", session.path_selection_locked),
        path_reports=result.get("path_reports"),
        projection_result=_build_projection(result.get("projection_result")),
        show_cards=result.get("show_cards", False),
        cards=result.get("cards", []),
        report_text=result.get("report_text", ""),
        state=result.get("state"),
        error=result.get("error"),
    )


@router.post("/resume", response_model=SandboxChatResponse)
async def resume_session(
    request: SandboxResumeRequest,
    sandbox: DecisionSandbox = Depends(get_sandbox),
    db: Session = Depends(get_db),
    current_user_id: str = Depends(enforce_ai_daily_limit),
):
    """Resume a sandbox session with previously saved state.

    Used when the client has persisted the session state and wants to continue.
    """
    # Restore from the provided state
    from sandbox.state import SandboxSession
    session = SandboxSession.from_dict(request.state)
    require_user_access(session.user_id, current_user_id)
    sandbox._sessions[session.session_id] = session

    if session.finished:
        return SandboxChatResponse(
            session_id=session.session_id,
            user_id=session.user_id,
            phase=session.current_phase.value,
            finished=True,
            message="本次分析已完成。可以查看对比结果。",
            path_selections=session.path_selections,
            path_selection_source=session.path_selection_source,
            path_selection_locked=session.path_selection_locked,
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
            path_selection_source=session.path_selection_source,
            path_selection_locked=session.path_selection_locked,
            state=session.to_dict(),
        )

    result = sandbox.chat(session, request.message, db_session=db)

    # Persist session

    return SandboxChatResponse(
        session_id=session.session_id,
        user_id=session.user_id,
        phase=result["phase"],
        finished=result.get("finished", False),
        message=result["message"],
        discovery_round=result.get("discovery_round", 0),
        max_discovery_rounds=result.get("max_discovery_rounds", 7),
        path_selections=result.get("path_selections", []),
        path_selection_source=result.get("path_selection_source", session.path_selection_source),
        path_selection_locked=result.get("path_selection_locked", session.path_selection_locked),
        path_reports=result.get("path_reports"),
        projection_result=_build_projection(result.get("projection_result")),
        show_cards=result.get("show_cards", False),
        cards=result.get("cards", []),
        report_text=result.get("report_text", ""),
        state=result.get("state"),
        error=result.get("error"),
    )




from fastapi.responses import StreamingResponse

@router.post("/chat/stream")
async def sandbox_chat_stream(
    request: SandboxChatRequest,
    sandbox: DecisionSandbox = Depends(get_sandbox),
    db: Session = Depends(get_db),
    current_user_id: str = Depends(enforce_ai_daily_limit),
):
    """Stream sandbox chat response via SSE."""
    require_user_access(request.user_id, current_user_id)
    session = _load_session(sandbox, request.session_id, current_user_id, db)

    async def event_stream():
        async for event, data in sandbox.chat_stream(session, request.message, db_session=db):
            yield f"event: {event}\ndata: {data}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.get("/handoff")
async def handoff_to_agent(
    session_id: str = __import__("fastapi").Query(..., description="Sandbox session ID"),
    path_type: str = __import__("fastapi").Query(..., description="Chosen path type (career/graduate/civil/major)"),
    user_id: str = __import__("fastapi").Query("", description="Session owner for persisted-context restore"),
    sandbox: DecisionSandbox = Depends(get_sandbox),
    db: Session = Depends(get_db),
    current_user_id: str = Depends(enforce_ai_daily_limit),
):
    """Hand off sandbox context to a planning agent.

    After the user sees the sandbox comparison and picks a direction,
    this endpoint packages all discovery context and returns the first
    planning agent question. The frontend should then switch to the
    growth/chat flow with the returned agent_state.

    Returns:
        - agent_type: the chosen planning agent type
        - agent_label: Chinese label
        - initial_question: first follow-up question from the agent
        - handoff_context: all discovery data for the frontend to pass to growth/start
        - agent_state: initial PlanningState for growth/chat
    """
    require_user_access(user_id, current_user_id)
    try:
        if sandbox.get_session(session_id) is None and user_id:
            _load_session(sandbox, session_id, user_id, db)
        result = sandbox.handoff_to_agent(
            session_id=session_id,
            path_type=path_type,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception("Sandbox handoff failed: {}", exc)
        raise HTTPException(status_code=500, detail="路径衔接失败，请稍后重试")

@router.get("/result/{session_id}")
async def get_result(
    session_id: str,
    user_id: str = __import__("fastapi").Query("", description="Session owner for persisted-context restore"),
    sandbox: DecisionSandbox = Depends(get_sandbox),
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """Get the final projection result for a completed session."""
    require_user_access(user_id, current_user_id)
    session = _load_session(sandbox, session_id, current_user_id, db)

    # Extract match scores from projection_result
    matches = []
    proj = session.projection_result or {}
    projections = proj.get("projections", [])
    matrix = proj.get("comparison_matrix", {})
    matrix_scores = matrix.get("scores", {})
    
    # Try to find the user-fit dimension index.
    match_dim_idx = None
    dims = matrix.get("dimensions", [])
    for i, d in enumerate(dims):
        if "匹配" in str(d) or "适配" in str(d) or "契合" in str(d):
            match_dim_idx = i
            break
    
    for p in projections:
        pt = p.get("path_type", "")
        score = None
        
        # First: use explicit match_score from projection
        if "match_score" in p and isinstance(p["match_score"], (int, float)):
            score = p["match_score"]
        # Fallback: extract from comparison_matrix scores
        elif match_dim_idx is not None and pt in matrix_scores:
            dim_scores = matrix_scores[pt]
            if isinstance(dim_scores, list) and match_dim_idx < len(dim_scores):
                score = dim_scores[match_dim_idx] * 10  # convert 1-10 to percentage
        
        if score is not None:
            matches.append({
                "type": pt,
                "score": score / 100.0 if score > 1 else score,
                "recommended": score >= 80,
            })
    
    # Sort by score descending
    matches.sort(key=lambda m: m["score"], reverse=True)

    return {
        "session_id": session.session_id,
        "user_id": session.user_id,
        "finished": session.finished,
        "path_selections": session.path_selections,
        "path_reports": session.path_reports if session.path_reports else None,
        "projection_result": session.projection_result if session.projection_result else None,
        "matches": matches,
        "summary": proj.get("summary", ""),
    }
