# -*- coding: utf-8 -*-
"""Growth Service — LangGraph-powered Growth Agent orchestration.

SQLite-backed checkpointer → interrupt/resume
interrupt_before → human-in-the-loop
graph.astream() → SSE streaming
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from loguru import logger
from sqlalchemy.orm import Session

from core.exceptions import NotFoundException
from planning.graph import build_growth_graph, GrowthState
from planning.router import PlanningRouter
from models.growth import GrowthSession, GrowthConversation, GrowthReport
from schemas.growth import (
    AgentTypeEnum, GrowthChatRequest, GrowthStartRequest,
    GrowthChatResponse, GrowthStateResponse, GrowthHistoryResponse,
    GrowthSessionSummary, GrowthReportResponse, QuestionCard,
)
from crud.base import CRUDBase
from crud.user import user as user_crud

session_crud = CRUDBase[GrowthSession](GrowthSession)
conv_crud = CRUDBase[GrowthConversation](GrowthConversation)
report_crud = CRUDBase[GrowthReport](GrowthReport)
MAX_FOLLOW_UP = 7


# ── Async bridge ───────────────────────────────────────────────

_RUNNING_LOOP: asyncio.AbstractEventLoop | None = None


def _ensure_loop() -> asyncio.AbstractEventLoop:
    global _RUNNING_LOOP
    if _RUNNING_LOOP is None or _RUNNING_LOOP.is_closed():
        _RUNNING_LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_RUNNING_LOOP)
    return _RUNNING_LOOP


def _run_async(coro, timeout: int = 60) -> Any:
    """Run coroutine safely from sync code."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor() as pool:
        future = pool.submit(asyncio.run, coro)
        return future.result(timeout=timeout)


# ── Service ────────────────────────────────────────────────────

class GrowthService:

    def __init__(self, llm_service: Any) -> None:
        self.llm = llm_service
        self.router = PlanningRouter(llm_service)
        self._graph = None

    async def _get_graph(self):
        if self._graph is None:
            self._graph = await build_growth_graph(self.llm, self.router)
        return self._graph

    async def _invoke(self, state, config) -> dict[str, Any]:
        g = await self._get_graph()
        return await g.ainvoke(state, config)

    async def _stream(self, state, config):
        g = await self._get_graph()
        async for event in g.astream(state, config, stream_mode="updates"):
            yield event

    # ── REST API ──────────────────────────────────────────────

    def start_session(self, db: Session, *, request: GrowthStartRequest) -> GrowthChatResponse:
        agent_type = _norm(request.agent)
        user = user_crud.get(db, id=request.user_id)
        profile: dict[str, str] = {}
        if user:
            if user.nickname: profile["nickname"] = user.nickname
            if user.major: profile["major"] = user.major
            if user.grade: profile["grade"] = user.grade

        db_sess = session_crud.create(db, obj_in={
            "user_id": request.user_id, "agent_type": agent_type,
            "status": "active", "stage": "questioning",
            "current_step": 0, "total_steps": MAX_FOLLOW_UP,
            "state_json": "{}", "progress": 0.0,
        })
        initial = _make_initial(agent_type, db_sess.id, request.user_id, profile)
        config = {"configurable": {"thread_id": db_sess.id}}

        result = _run_async(self._invoke(initial, config))
        _flush(db_sess, result)
        conv_crud.create(db, obj_in={
            "session_id": db_sess.id, "user_id": request.user_id,
            "role": "system",
            "content": f"Growth session started: {agent_type}",
            "step": 0, "stage": "questioning",
        })
        db.commit()
        logger.info("Growth: session {} started", db_sess.id)
        return _to_response(db_sess.id, agent_type, result)

    def chat(self, db: Session, *, request: GrowthChatRequest) -> GrowthChatResponse:
        agent_type = _norm(request.agent)
        if not request.session_id:
            start = self.start_session(db, request=GrowthStartRequest(
                user_id=request.user_id, agent=request.agent,
            ))
            if not request.message.strip():
                return start
            request.session_id = start.session_id

        db_sess = _get_sess(db, request.session_id)
        state = _state_from_db(db_sess, request)
        config = {"configurable": {"thread_id": db_sess.id}}

        result = _run_async(self._invoke(state, config))
        _flush(db_sess, result)

        if request.message.strip():
            conv_crud.create(db, obj_in={
                "session_id": db_sess.id, "user_id": request.user_id,
                "role": "user", "content": request.message,
                "step": result.get("follow_up_round", 0),
                "stage": result.get("stage", "questioning"),
            })
        msg = result.get("agent_message", "")
        if msg:
            conv_crud.create(db, obj_in={
                "session_id": db_sess.id, "user_id": request.user_id,
                "role": "assistant", "content": msg,
                "step": result.get("follow_up_round", 0),
                "stage": result.get("stage", "questioning"),
            })
        if result.get("finished") and result.get("report"):
            _save_rpt(db, db_sess, result["report"])
        db.commit()
        return _to_response(db_sess.id, agent_type, result)

    # ── Human-in-the-loop ─────────────────────────────────────

    def correct_analysis(self, db: Session, *, session_id: str, user_id: str, correction: str) -> GrowthChatResponse:
        from langgraph.types import Command
        db_sess = _get_sess(db, session_id)
        config = {"configurable": {"thread_id": session_id}}
        cmd = Command(goto="planning_analyze", update={"user_correction": correction})
        result = _run_async(self._invoke(cmd, config))
        _flush(db_sess, result)
        db.commit()
        return _to_response(session_id, db_sess.agent_type, result)

    def approve_analysis(self, db: Session, *, session_id: str, user_id: str) -> GrowthChatResponse:
        from langgraph.types import Command
        db_sess = _get_sess(db, session_id)
        config = {"configurable": {"thread_id": session_id}}
        result = _run_async(self._invoke(Command(resume="continue"), config))
        _flush(db_sess, result)
        if result.get("finished") and result.get("report"):
            _save_rpt(db, db_sess, result["report"])
        db.commit()
        return _to_response(session_id, db_sess.agent_type, result)

    # ── SSE Streaming ─────────────────────────────────────────

    async def chat_stream(self, db: Session, *, session_id: str, user_id: str,
                          message: str = "", agent_type: str = "career") -> AsyncIterator[str]:
        agent_type = _norm(agent_type)
        if session_id:
            db_sess = session_crud.get(db, id=session_id)
            if db_sess is None:
                yield _sse("error", {"message": "Session not found"})
                return
            state = _state_from_db(db_sess, GrowthChatRequest(
                user_id=user_id, agent=AgentTypeEnum(agent_type),
                message=message, session_id=session_id,
            ))
        else:
            user = user_crud.get(db, id=user_id)
            profile: dict[str, str] = {}
            if user:
                if user.nickname: profile["nickname"] = user.nickname
                if user.major: profile["major"] = user.major
                if user.grade: profile["grade"] = user.grade
            db_sess = session_crud.create(db, obj_in={
                "user_id": user_id, "agent_type": agent_type,
                "status": "active", "stage": "questioning",
                "current_step": 0, "total_steps": MAX_FOLLOW_UP,
                "state_json": "{}", "progress": 0.0,
            })
            session_id = db_sess.id
            state = _make_initial(agent_type, session_id, user_id, profile)
            state["user_message"] = message

        config = {"configurable": {"thread_id": session_id}}
        try:
            async for event in self._stream(state, config):
                node_name = list(event.keys())[0] if event else "unknown"
                node_data = event.get(node_name, {})
                yield _sse(node_name, {
                    "session_id": session_id,
                    "stage": node_data.get("stage", ""),
                    "finished": node_data.get("finished", False),
                    "message": node_data.get("agent_message", ""),
                    "report": node_data.get("report"),
                    "follow_up_round": node_data.get("follow_up_round", 0),
                })
                if node_data:
                    _flush(db_sess, node_data)
                    if node_data.get("finished") and node_data.get("report"):
                        _save_rpt(db, db_sess, node_data["report"])
                db.commit()
        except Exception as exc:
            logger.exception("Growth stream error: {}", exc)
            yield _sse("error", {"message": str(exc)})

    # ── State / History / Report ──────────────────────────────

    def get_state(self, db: Session, *, user_id: str) -> GrowthStateResponse:
        sessions = session_crud.get_multi(
            db, user_id=user_id, order_by=GrowthSession.updated_at.desc(), limit=1,
        )
        if not sessions:
            return GrowthStateResponse()
        s = sessions[0]
        answers: dict[str, str] = {}
        try:
            answers = json.loads(s.state_json or "{}").get("follow_up_answers", {})
        except (json.JSONDecodeError, TypeError):
            pass
        return GrowthStateResponse(
            session_id=s.id, agent=s.agent_type, stage=s.stage,
            finished=s.finished, current_step=s.current_step,
            total_steps=s.total_steps or MAX_FOLLOW_UP, answers=answers,
            has_report=bool(s.report_json and len(s.report_json or "") > 0),
            created_at=s.created_at, updated_at=s.updated_at,
        )

    def get_history(self, db: Session, *, user_id: str, limit: int = 20) -> GrowthHistoryResponse:
        sessions = session_crud.get_multi(
            db, user_id=user_id, order_by=GrowthSession.created_at.desc(), limit=limit,
        )
        return GrowthHistoryResponse(user_id=user_id, sessions=[
            GrowthSessionSummary(
                session_id=s.id, agent=s.agent_type, status=s.status,
                finished=s.finished, created_at=s.created_at,
                message_count=len(s.conversations) if s.conversations else 0,
            ) for s in sessions
        ])

    def get_report(self, db: Session, *, session_id: str) -> GrowthReportResponse:
        reports = report_crud.get_multi(db, session_id=session_id, limit=1)
        if not reports:
            raise NotFoundException(f"Report for session {session_id} not found")
        r = reports[0]
        data: dict[str, Any] = {}
        if r.full_report_json:
            try:
                data = json.loads(r.full_report_json)
            except json.JSONDecodeError:
                pass
        return GrowthReportResponse(
            session_id=session_id, agent=r.agent_type,
            report=data, created_at=r.created_at,
        )


# ── Module helpers ─────────────────────────────────────────────

def _norm(a: Any) -> str:
    return a.value if isinstance(a, AgentTypeEnum) else str(a)


def _get_sess(db: Session, sid: str) -> GrowthSession:
    s = session_crud.get(db, id=sid)
    if s is None:
        raise NotFoundException(f"Session {sid} not found")
    return s


def _make_initial(agent_type: str, session_id: str, user_id: str,
                  profile: dict[str, str]) -> GrowthState:
    from planning.state import PlanningState
    ps = PlanningState(agent_type=agent_type)
    if profile:
        ps.user_profile = profile
        ps.has_profile = True
        ps.advance_step()
    return {
        "user_id": user_id, "agent_type": agent_type, "session_id": session_id,
        "user_message": "", "user_correction": "",
        "planning_state_json": json.dumps(ps.to_dict(), ensure_ascii=False),
        "follow_up_round": 0, "follow_up_complete": False,
        "analysis": {}, "identified_problems": [], "long_term_goal": "",
        "action_plan": [], "output": {},
        "stage": "questioning", "finished": False,
        "agent_message": "", "report": None, "error_message": "", "last_question": "",
    }


def _state_from_db(db_sess: GrowthSession, req: GrowthChatRequest) -> GrowthState:
    try:
        saved = json.loads(db_sess.state_json or "{}")
    except (json.JSONDecodeError, TypeError):
        saved = {}
    return {
        "user_id": req.user_id, "agent_type": _norm(req.agent),
        "session_id": db_sess.id, "user_message": req.message,
        "user_correction": "",
        "planning_state_json": saved.get("planning_state_json", "{}"),
        "follow_up_round": saved.get("follow_up_round", 0),
        "follow_up_complete": saved.get("follow_up_complete", False),
        "analysis": saved.get("analysis", {}),
        "identified_problems": saved.get("identified_problems", []),
        "long_term_goal": saved.get("long_term_goal", ""),
        "action_plan": saved.get("action_plan", []),
        "output": saved.get("output", {}),
        "stage": db_sess.stage or "questioning",
        "finished": db_sess.finished,
        "agent_message": "", "report": None, "error_message": "",
        "last_question": saved.get("last_question", ""),
    }


def _flush(db_sess: GrowthSession, result: dict[str, Any]) -> None:
    now = datetime.now(timezone.utc)
    if result.get("stage"):
        db_sess.stage = result["stage"]
    if result.get("finished"):
        db_sess.finished = True
        db_sess.status = "completed"
    if result.get("follow_up_round", 0) > 0:
        db_sess.current_step = result["follow_up_round"]
    state_blob = {
        "planning_state_json": result.get("planning_state_json", "{}"),
        "follow_up_round": result.get("follow_up_round", 0),
        "follow_up_complete": result.get("follow_up_complete", False),
        "analysis": result.get("analysis", {}),
        "identified_problems": result.get("identified_problems", []),
        "long_term_goal": result.get("long_term_goal", ""),
        "action_plan": result.get("action_plan", []),
        "output": result.get("output", {}),
        "last_question": result.get("last_question", ""),
        "stage": result.get("stage", "questioning"),
        "finished": result.get("finished", False),
    }
    db_sess.state_json = json.dumps(state_blob, ensure_ascii=False)
    if result.get("report"):
        db_sess.report_json = json.dumps(result["report"], ensure_ascii=False)
        db_sess.progress = 100.0
    elif result.get("stage") == "analyzing":
        db_sess.progress = 50.0
    elif result.get("follow_up_round", 0) > 0:
        db_sess.progress = min(45.0, (result["follow_up_round"] / MAX_FOLLOW_UP) * 45.0)
    db_sess.updated_at = now


def _to_response(session_id: str, agent_type: str, result: dict[str, Any]) -> GrowthChatResponse:
    stage = result.get("stage", "questioning")
    finished = result.get("finished", False)
    fu = result.get("follow_up_round", 0)
    message = result.get("agent_message", "")
    nq = None
    if not finished and message:
        nq = QuestionCard(
            id=f"follow_up_{fu + 1}", title=message, options=[],
            required=True, index=fu + 1, total=MAX_FOLLOW_UP,
        )
    return GrowthChatResponse(
        session_id=session_id, agent=agent_type,
        stage="report" if finished else stage,
        finished=finished, current_step=fu,
        total_steps=MAX_FOLLOW_UP, next_question=nq,
        report=result.get("report"), message=message,
    )


def _save_rpt(db: Session, session: GrowthSession, report: dict[str, Any]) -> None:
    existing = report_crud.get_multi(db, session_id=session.id, limit=1)
    rj = json.dumps(report, ensure_ascii=False)
    obj_in = {
        "full_report_json": rj,
        "profile_json": json.dumps({"current_status": report.get("current_status", "")}, ensure_ascii=False),
        "analysis_json": json.dumps({"summary": report.get("summary", ""), "main_problem": report.get("main_problem", ""), "goal": report.get("goal", "")}, ensure_ascii=False),
        "advantages_json": json.dumps(report.get("advantages", []), ensure_ascii=False),
        "risks_json": json.dumps(report.get("risks", []), ensure_ascii=False),
        "recommendations_json": json.dumps(report.get("action_plan", []), ensure_ascii=False),
        "plan_json": json.dumps(report.get("action_plan", []), ensure_ascii=False),
    }
    if existing:
        report_crud.update(db, db_obj=existing[0], obj_in=obj_in)
    else:
        report_crud.create(db, obj_in={
            "session_id": session.id, "user_id": session.user_id,
            "agent_type": session.agent_type,
            "report_type": f"{session.agent_type}_report",
            **obj_in,
        })


def _sse(event: str, data: dict[str, Any]) -> str:
    return "data: {}\n\n".format(
        json.dumps({"step": event, "status": "done", "data": data}, ensure_ascii=False)
    )


# ── Singleton ──────────────────────────────────────────────────

_growth_service: GrowthService | None = None


def get_growth_service(llm_service: Any | None = None) -> GrowthService:
    global _growth_service
    if _growth_service is None:
        if llm_service is None:
            from services.llm_service import get_llm_service
            llm_service = get_llm_service()
        _growth_service = GrowthService(llm_service)
    return _growth_service
