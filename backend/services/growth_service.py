# -*- coding: utf-8 -*-
"""Growth Service -- LangGraph-powered Growth Agent orchestration. (async-native)

Runs entirely on FastAPI/Uvicorn event loop. No thread-pool bridges needed.
AsyncSqliteSaver for persistent interrupt/resume across server restarts.
"""

from __future__ import annotations

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
MAX_FOLLOW_UP = 5


class GrowthService:
    """Orchestrates Growth Agent conversations via LangGraph (async-native)."""

    def __init__(self, llm_service: Any, sandbox: Any = None) -> None:
        self.llm = llm_service
        self.router = PlanningRouter(llm_service)
        self._sandbox = sandbox
        self._graph = None

    async def _get_graph(self):
        if self._graph is None:
            self._graph = await build_growth_graph(self.llm, self.router, self._sandbox)
        return self._graph

    async def _invoke(self, state, config) -> dict[str, Any]:
        g = await self._get_graph()
        return await g.ainvoke(state, config)

    async def _stream(self, state, config):
        g = await self._get_graph()
        async for event in g.astream(state, config, stream_mode="updates"):
            yield event

    # ── REST API (all async) ──────────────────────────────────

    async def start_session(self, db: Session, *, request: GrowthStartRequest) -> GrowthChatResponse:
        agent_type = _norm(request.agent)
        user = user_crud.get(db, id=request.user_id)
        profile: dict[str, str] = {}
        if user:
            if user.nickname: profile["nickname"] = user.nickname
            if user.major: profile["major"] = user.major
            if user.grade: profile["grade"] = user.grade

        # Load memory DB for cross-session continuity
        # Only profile-type memories (school/college/major/grade/enroll_year).
        # Action/goal memories from previous planning sessions are NOT loaded
        # to avoid the agent referencing old conversations in new sessions.
        try:
            from services.memory_service import memory_service
            memories = memory_service.load_memory(db, user_id=request.user_id, as_dict=True, memory_type="profile")
            if isinstance(memories, dict) and memories:
                # Map memory keys to profile fields (same mapping as sandbox)
                key_mapping = {
                    "school": "school",
                    "college": "college",
                    "enroll_year": "enroll_year",
                }
                for mem_key, field in key_mapping.items():
                    if mem_key in memories and field not in profile:
                        profile[field] = str(memories[mem_key])

                logger.info("Growth: loaded {} profile memories for user {}",
                            len(memories), request.user_id)
        except Exception as exc:
            logger.warning("Growth: failed to load memories: {}", exc)

        # Load sandbox context if provided (gap 1 fix)
        sandbox_profile: dict[str, str] = {}
        sandbox_history: list[dict[str, str]] = []
        if request.sandbox_session_id:
            try:
                from app.api.v1.sandbox import get_sandbox
                sb = get_sandbox()
                sb_sess = sb.get_session(request.sandbox_session_id)
                if sb_sess:
                    # Merge sandbox user_profile
                    for k, v in sb_sess.user_profile.items():
                        if v and k not in profile:
                            profile[k] = str(v)
                    # Capture discovery history for pre-filling
                    sandbox_history = sb_sess.discovery_history
                    logger.info("Growth: loaded sandbox context for user {}, {} profile fields, {} history items",
                                request.user_id, len(profile), len(sandbox_history))
            except Exception as exc:
                logger.warning("Growth: failed to load sandbox context: {}", exc)
        db_sess = session_crud.create(db, obj_in={
            "user_id": request.user_id, "agent_type": agent_type,
            "status": "active", "stage": "questioning",
            "current_step": 0, "total_steps": MAX_FOLLOW_UP,
            "state_json": "{}", "progress": 0.0,
        })
        initial = _make_initial(agent_type, db_sess.id, request.user_id, profile, sandbox_history)
        config = {"configurable": {"thread_id": db_sess.id}}
        result = await self._invoke(initial, config)
        _flush(db_sess, result)
        conv_crud.create(db, obj_in={
            "session_id": db_sess.id, "user_id": request.user_id,
            "role": "system", "content": f"Growth session started: {agent_type}",
            "step": 0, "stage": "questioning",
        })
        db.commit()
        logger.info("Growth: session {} started", db_sess.id)
        return _to_response(db_sess.id, agent_type, result)

    async def chat(self, db: Session, *, request: GrowthChatRequest) -> GrowthChatResponse:
        agent_type = _norm(request.agent)
        if not request.session_id:
            start = await self.start_session(db, request=GrowthStartRequest(
                user_id=request.user_id, agent=request.agent,
            ))
            if not request.message.strip():
                return start
            request.session_id = start.session_id

        db_sess = _get_sess(db, request.session_id)
        state = _state_from_db(db_sess, request)
        config = {"configurable": {"thread_id": db_sess.id}}
        result = await self._invoke(state, config)
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
            self._save_report(db, db_sess, result["report"])
            await self._save_memory(db, db_sess, result["report"])
        db.commit()

        # ── Per-turn async memory extraction ──────────────────
        if request.message.strip():
            try:
                from services.memory_service import memory_service
                memory_service.extract_from_turn_async(
                    user_id=request.user_id,
                    user_message=request.message,
                    assistant_message=msg,
                )
            except Exception:
                pass  # Non-blocking; extraction runs in background thread

        return _to_response(db_sess.id, agent_type, result)

    # ── Human-in-the-loop ─────────────────────────────────────

    async def correct_analysis(self, db: Session, *, session_id: str, user_id: str, correction: str) -> GrowthChatResponse:
        from langgraph.types import Command
        db_sess = _get_sess(db, session_id)
        config = {"configurable": {"thread_id": session_id}}
        result = await self._invoke(
            Command(goto="planning_analyze", update={"user_correction": correction}),
            config,
        )
        _flush(db_sess, result)
        db.commit()
        return _to_response(session_id, db_sess.agent_type, result)

    async def approve_analysis(self, db: Session, *, session_id: str, user_id: str) -> GrowthChatResponse:
        from langgraph.types import Command
        db_sess = _get_sess(db, session_id)
        config = {"configurable": {"thread_id": session_id}}
        result = await self._invoke(Command(resume="continue"), config)
        _flush(db_sess, result)
        if result.get("finished") and result.get("report"):
            self._save_report(db, db_sess, result["report"])
            await self._save_memory(db, db_sess, result["report"])
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
                    "session_id": session_id, "stage": node_data.get("stage", ""),
                    "finished": node_data.get("finished", False),
                    "message": node_data.get("agent_message", ""),
                    "report": node_data.get("report"),
                    "follow_up_round": node_data.get("follow_up_round", 0),
                })
                if node_data:
                    _flush(db_sess, node_data)
                    if node_data.get("finished") and node_data.get("report"):
                        self._save_report(db, db_sess, node_data["report"])
                        await self._save_memory(db, db_sess, node_data["report"])
                db.commit()
        except Exception as exc:
            logger.exception("Growth stream error: {}", exc)
            yield _sse("error", {"message": str(exc)})

    # ── State / History / Report ──────────────────────────────

    def get_state(self, db: Session, *, user_id: str) -> GrowthStateResponse:
        sessions = session_crud.get_multi(db, user_id=user_id)
        sessions = sorted(sessions, key=lambda s: s.updated_at or s.created_at, reverse=True)
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
        sessions = session_crud.get_multi(db, user_id=user_id)
        sessions = sorted(sessions, key=lambda s: s.created_at, reverse=True)[:limit]
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

    # ── Memory integration ────────────────────────────────────


    def get_conversation(self, db: Session, *, session_id: str) -> list[dict[str, Any]]:
        """Get all messages for a growth session."""
        convs = conv_crud.get_multi(db, session_id=session_id)
        convs = sorted(convs, key=lambda c: c.created_at)
        return [
            {
                "role": c.role,
                "content": c.content,
                "step": c.step,
                "stage": c.stage,
                "created_at": c.created_at.isoformat() if c.created_at else "",
            }
            for c in convs
        ]

    async def _save_memory(self, db: Session, session: GrowthSession, report: dict[str, Any]) -> None:
        """Write key findings to Memory system for cross-session continuity."""
        try:
            from services.memory_service import memory_service
            uid = session.user_id

            # Save goal
            goal_text = report.get("goal", "")
            if goal_text:
                memory_service.save_memory(db, data=__import__("schemas.memory", fromlist=["MemoryCreate"]).MemoryCreate(
                    user_id=uid, key="current_goal",
                    value=goal_text[:500], memory_type="goal",
                    importance=5, confidence=0.9,
                    source=f"growth_report:{session.id}",
                ))

            # Save profile snapshot
            summary = report.get("summary", "")
            status = report.get("current_status", "")
            if summary or status:
                profile_text = f"{status}\n{summary}".strip()[:500]
                memory_service.save_memory(db, data=__import__("schemas.memory", fromlist=["MemoryCreate"]).MemoryCreate(
                    user_id=uid, key="latest_analysis",
                    value=profile_text, memory_type="profile",
                    importance=4, confidence=0.85,
                    source=f"growth_report:{session.id}",
                ))

            logger.info("Growth: memory saved for user={}", uid)
        except Exception as exc:
            logger.warning("Growth: failed to save memory: {}", exc)

    # ── Internal ──────────────────────────────────────────────

    def _save_report(self, db: Session, session: GrowthSession, report: dict[str, Any]) -> None:
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


# ── Module helpers ─────────────────────────────────────────────

def _norm(a: Any) -> str:
    return a.value if isinstance(a, AgentTypeEnum) else str(a)


def _get_sess(db: Session, sid: str) -> GrowthSession:
    s = session_crud.get(db, id=sid)
    if s is None:
        raise NotFoundException(f"Session {sid} not found")
    return s


def _make_initial(agent_type: str, session_id: str, user_id: str,
                  profile: dict[str, str], sandbox_history: list | None = None) -> GrowthState:
    from planning.state import PlanningState
    ps = PlanningState(agent_type=agent_type)
    if profile:
        ps.user_profile = profile
        ps.has_profile = True
        ps.advance_step()
    if sandbox_history:
        for qa in sandbox_history:
            q = qa.get("q", "")
            a = qa.get("a", "")
            if q and a:
                ps.record_follow_up(q, a)
        # Mark follow-up as complete if we have enough context from sandbox
        if len(sandbox_history) >= 3:
            ps.follow_up_complete = True
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
    if result.get("stage"): db_sess.stage = result["stage"]
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
        # Record growth memory
        try:
            from services.memory_service import memory_service
            agent_label = {"career": "就业规划", "graduate": "考研规划", "civil": "考公规划", "major": "转专业规划"}.get(db_sess.agent_type, db_sess.agent_type)
            goal = result.get("long_term_goal", "") or result.get("output", {}).get("goal", "")
            action_plan = result.get("action_plan", []) or result.get("output", {}).get("action_plan", [])
            memories = [
                {"key": f"last_{db_sess.agent_type}_plan", "value": f"于{now.strftime('%Y-%m-%d')}完成{agent_label}", "memory_type": "action", "importance": 8, "confidence": 1.0, "source": "growth_session"},
            ]
            if goal:
                memories.append({"key": f"{db_sess.agent_type}_goal", "value": goal, "memory_type": "goal", "importance": 9, "confidence": 0.9, "source": "growth_session"})
            if action_plan and len(action_plan) > 0:
                plan_summary = "; ".join([p.get("phase", "") or p.get("title", "") for p in action_plan[:4] if p.get("phase") or p.get("title")])
                if plan_summary:
                    memories.append({"key": f"{db_sess.agent_type}_action_plan", "value": plan_summary, "memory_type": "action", "importance": 7, "confidence": 0.9, "source": "growth_session"})
            memory_service.save_batch(db_sess, user_id=db_sess.user_id, items=memories)
        except Exception:
            pass  # Memory recording is non-critical
    elif result.get("stage") == "analyzing":
        db_sess.progress = 40.0
    elif result.get("stage") == "report":
        db_sess.progress = 90.0
    elif result.get("follow_up_round", 0) > 0:
        db_sess.progress = min(35.0, (result["follow_up_round"] / MAX_FOLLOW_UP) * 35.0)
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


def _sse(event: str, data: dict[str, Any]) -> str:
    return "data: {}\n\n".format(
        json.dumps({"step": event, "status": "done", "data": data}, ensure_ascii=False)
    )


# ── Singleton ──────────────────────────────────────────────────

_growth_service: GrowthService | None = None


def get_growth_service(llm_service: Any | None = None, sandbox: Any = None) -> GrowthService:
    global _growth_service
    if _growth_service is None:
        if llm_service is None:
            from services.llm_service import get_llm_service
            llm_service = get_llm_service()
        if sandbox is None:
            try:
                from app.api.v1.sandbox import get_sandbox
                sandbox = get_sandbox()
            except Exception:
                pass
        _growth_service = GrowthService(llm_service, sandbox)
    return _growth_service

