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

from core.exceptions import NotFoundException, ValidationException
from planning.graph import build_growth_graph, GrowthState
from planning.router import PlanningRouter
from planning.state import MAX_FOLLOW_UP_ROUNDS
from models.growth import GrowthSession, GrowthConversation, GrowthReport
from schemas.growth import (
    AgentTypeEnum, GrowthChatRequest, GrowthStartRequest,
    GrowthChatResponse, GrowthStateResponse, GrowthHistoryResponse,
    GrowthSessionSummary, GrowthReportResponse, QuestionCard,
    GrowthDashboardResponse, GrowthReportListResponse, GrowthReportSummary,
)
from crud.base import CRUDBase
from crud.user import user as user_crud

session_crud = CRUDBase[GrowthSession](GrowthSession)
conv_crud = CRUDBase[GrowthConversation](GrowthConversation)
report_crud = CRUDBase[GrowthReport](GrowthReport)
MAX_FOLLOW_UP = MAX_FOLLOW_UP_ROUNDS


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
        if user is None:
            raise NotFoundException(f"User {request.user_id} not found")
        profile: dict[str, str] = {}
        if user.nickname: profile["nickname"] = user.nickname
        if user.major: profile["major"] = user.major
        if user.grade: profile["grade"] = user.grade

        # Wait for the preceding sandbox/growth turn to finish persisting, then
        # load categorized long-term memory relevant to this planning agent.
        growth_memory: dict[str, Any] = {}
        try:
            from services.memory_service import memory_service
            if not memory_service.wait_for_pending(request.user_id, timeout=5.0):
                logger.warning(
                    "Growth: memory writes still pending after timeout for user {}",
                    request.user_id,
                )
            growth_memory = memory_service.load_growth_context(
                db, user_id=request.user_id, agent_type=agent_type,
            )
            for field, value in growth_memory.get("profile", {}).items():
                if value:
                    profile[field] = str(value)
            if growth_memory.get("goal"):
                profile["previous_goal"] = str(growth_memory["goal"])
            if growth_memory.get("action_plan"):
                profile["previous_action_plan"] = str(growth_memory["action_plan"])
            if growth_memory.get("analysis"):
                profile["previous_analysis"] = str(growth_memory["analysis"])
            logger.info(
                "Growth: loaded {} categorized memories for user {} agent {}",
                len(growth_memory.get("memory_ids", [])), request.user_id, agent_type,
            )
        except Exception as exc:
            logger.warning("Growth: failed to load memories: {}", exc)

        # Load sandbox context if provided (gap 1 fix)
        sandbox_history: list[dict[str, str]] = []
        sandbox_question_count = 0
        if request.sandbox_session_id:
            try:
                from sandbox.state import SandboxSession
                from services.memory_service import memory_service
                sb = self._sandbox
                if sb is None:
                    from app.api.v1.sandbox import get_sandbox
                    sb = get_sandbox()
                sb_sess = sb.get_session(request.sandbox_session_id)
                if sb_sess is not None and sb_sess.user_id != request.user_id:
                    logger.warning(
                        "Growth: ignored sandbox context owned by another user: {}",
                        request.sandbox_session_id,
                    )
                    sb_sess = None
                if sb_sess is None:
                    persisted = memory_service.load_context(
                        db,
                        user_id=request.user_id,
                        context_kind="sandbox",
                        context_id=request.sandbox_session_id,
                    )
                    if persisted:
                        restored = SandboxSession.from_dict(persisted)
                        if (
                            restored.user_id == request.user_id
                            and restored.session_id == request.sandbox_session_id
                        ):
                            sb_sess = restored
                            logger.info(
                                "Growth: restored persisted sandbox context {}",
                                request.sandbox_session_id,
                            )
                if sb_sess:
                    # Merge sandbox user_profile
                    for k, v in sb_sess.user_profile.items():
                        if v and k not in profile:
                            profile[k] = str(v)
                    # Carry the complete question budget into the selected
                    # planning direction: shared discovery plus this path's
                    # probe.  This prevents sandbox + planning from silently
                    # exceeding five user-facing clarifications.
                    sandbox_history = list(sb_sess.discovery_history)
                    sandbox_history.extend(sb_sess.path_probe_history.get(agent_type, []))
                    sandbox_history = sandbox_history[:MAX_FOLLOW_UP]
                    sandbox_question_count = len(sb_sess.discovery_history) + sum(
                        len(history) for history in sb_sess.path_probe_history.values()
                    )
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
        initial = _make_initial(
            agent_type,
            db_sess.id,
            request.user_id,
            profile,
            sandbox_history,
            prior_questions_asked=sandbox_question_count,
        )
        config = {"configurable": {"thread_id": db_sess.id}}
        result = await self._invoke(initial, config)
        _flush(db_sess, result)
        first_message = result.get("agent_message", "")
        if first_message:
            conv_crud.create(db, obj_in={
                "session_id": db_sess.id, "user_id": request.user_id,
                "role": "assistant", "content": first_message,
                "step": result.get("questions_asked", result.get("follow_up_round", 0)),
                "stage": result.get("stage", "questioning"),
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

        db_sess = _get_owned_sess(db, request.session_id, request.user_id)
        agent_type = db_sess.agent_type
        if db_sess.finished:
            report = _load_report_dict(db_sess)
            return GrowthChatResponse(
                progress=100,
                session_id=db_sess.id,
                agent=db_sess.agent_type,
                stage="report",
                finished=True,
                current_step=db_sess.current_step,
                total_steps=db_sess.total_steps or MAX_FOLLOW_UP,
                report=report or None,
                message="本次规划已完成，你可以查看报告或继续咨询。",
            )
        state = _state_from_db(db_sess, request)
        if db_sess.stage == "analyzing" and state.get("analysis"):
            # Text input remains a valid alternative to the two confirmation buttons.
            if _is_analysis_approval(request.message):
                state.update({"user_message": "", "report_requested": True})
            else:
                state.update({"user_message": "", "user_correction": request.message.strip()})
        config = {"configurable": {"thread_id": db_sess.id}}
        result = await self._invoke(state, config)
        _flush(db_sess, result)

        if request.message.strip():
            conv_crud.create(db, obj_in={
                "session_id": db_sess.id, "user_id": request.user_id,
                "role": "user", "content": request.message,
                "step": result.get("questions_asked", result.get("follow_up_round", 0)),
                "stage": result.get("stage", "questioning"),
            })
        msg = result.get("agent_message", "")
        if msg:
            conv_crud.create(db, obj_in={
                "session_id": db_sess.id, "user_id": request.user_id,
                "role": "assistant", "content": msg,
                "step": result.get("questions_asked", result.get("follow_up_round", 0)),
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
                    source_context=f"growth_turn:{db_sess.id}",
                )
            except Exception:
                pass  # Non-blocking; extraction runs in background thread

        return _to_response(db_sess.id, agent_type, result)

    # ── Human-in-the-loop ─────────────────────────────────────

    async def correct_analysis(self, db: Session, *, session_id: str, user_id: str, correction: str) -> GrowthChatResponse:
        db_sess = _get_owned_sess(db, session_id, user_id)
        if db_sess.finished:
            raise ValidationException("报告已完成，如需调整请新建一份规划。")
        if not correction.strip():
            raise ValidationException("请填写需要修正的方向。")
        config = {"configurable": {"thread_id": session_id}}
        state = _state_from_db(db_sess, GrowthChatRequest(
            user_id=user_id,
            agent=AgentTypeEnum(db_sess.agent_type),
            message="",
            session_id=session_id,
        ))
        state.update({
            "user_correction": correction.strip(),
            "report_requested": False,
            "stage": "analyzing",
        })
        result = await self._invoke(state, config)
        _flush(db_sess, result)
        conv_crud.create(db, obj_in={
            "session_id": session_id, "user_id": user_id,
            "role": "user", "content": f"修正分析：{correction.strip()}",
            "step": db_sess.current_step, "stage": "analyzing",
        })
        if result.get("agent_message"):
            conv_crud.create(db, obj_in={
                "session_id": session_id, "user_id": user_id,
                "role": "assistant", "content": result["agent_message"],
                "step": db_sess.current_step, "stage": result.get("stage", "analyzing"),
            })
        db.commit()
        try:
            from services.memory_service import memory_service
            memory_service.extract_from_turn_async(
                user_id=user_id,
                user_message=correction.strip(),
                assistant_message=result.get("agent_message", ""),
                source_context=f"growth_correction:{session_id}",
            )
        except Exception:
            pass
        return _to_response(session_id, db_sess.agent_type, result)

    async def approve_analysis(self, db: Session, *, session_id: str, user_id: str) -> GrowthChatResponse:
        db_sess = _get_owned_sess(db, session_id, user_id)
        if db_sess.finished:
            report = _load_report_dict(db_sess)
            return GrowthChatResponse(
                progress=100, session_id=session_id, agent=db_sess.agent_type,
                stage="report", finished=True,
                current_step=db_sess.current_step,
                total_steps=db_sess.total_steps or MAX_FOLLOW_UP,
                report=report or None,
                message="报告已经生成，可以直接查看。",
            )
        if db_sess.stage != "analyzing":
            raise ValidationException("初步分析尚未完成，请先继续回答问题。")
        config = {"configurable": {"thread_id": session_id}}
        state = _state_from_db(db_sess, GrowthChatRequest(
            user_id=user_id,
            agent=AgentTypeEnum(db_sess.agent_type),
            message="",
            session_id=session_id,
        ))
        state.update({"report_requested": True, "user_correction": ""})
        result = await self._invoke(state, config)
        _flush(db_sess, result)
        if result.get("finished") and result.get("report"):
            self._save_report(db, db_sess, result["report"])
            await self._save_memory(db, db_sess, result["report"])
        if result.get("agent_message"):
            conv_crud.create(db, obj_in={
                "session_id": session_id, "user_id": user_id,
                "role": "assistant", "content": result["agent_message"],
                "step": db_sess.current_step, "stage": result.get("stage", "report"),
            })
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
        last_agent_message = ""
        try:
            async for event in self._stream(state, config):
                node_name = list(event.keys())[0] if event else "unknown"
                node_data = event.get(node_name, {})
                if node_data.get("agent_message"):
                    last_agent_message = node_data["agent_message"]
                yield _sse(node_name, {
                    "session_id": session_id, "stage": node_data.get("stage", ""),
                    "finished": node_data.get("finished", False),
                    "message": node_data.get("agent_message", ""),
                    "report": node_data.get("report"),
                    "follow_up_round": node_data.get("follow_up_round", 0),
                    "questions_asked": node_data.get("questions_asked", 0),
                })
                if node_data:
                    _flush(db_sess, node_data)
                    if node_data.get("finished") and node_data.get("report"):
                        self._save_report(db, db_sess, node_data["report"])
                        await self._save_memory(db, db_sess, node_data["report"])
                db.commit()
            if message.strip():
                try:
                    from services.memory_service import memory_service
                    memory_service.extract_from_turn_async(
                        user_id=user_id,
                        user_message=message,
                        assistant_message=last_agent_message,
                        source_context=f"growth_stream:{session_id}",
                    )
                except Exception:
                    pass
        except Exception as exc:
            logger.exception("Growth stream error: {}", exc)
            yield _sse("error", {"message": str(exc)})

    # ── State / History / Report ──────────────────────────────

    def get_state(self, db: Session, *, user_id: str) -> GrowthStateResponse:
        sessions = session_crud.get_multi(db, user_id=user_id)
        sessions = sorted(sessions, key=lambda s: s.updated_at or s.created_at, reverse=True)
        if not sessions:
            return GrowthStateResponse()
        return _session_to_state(sessions[0])

    def get_session_state(self, db: Session, *, session_id: str) -> GrowthStateResponse:
        """Return resumable state for one specific growth session."""
        return _session_to_state(_get_sess(db, session_id))

    def get_history(self, db: Session, *, user_id: str, limit: int = 20) -> GrowthHistoryResponse:
        sessions = session_crud.get_multi(db, user_id=user_id)
        sessions = sorted(sessions, key=lambda s: s.updated_at or s.created_at, reverse=True)[:limit]
        return GrowthHistoryResponse(user_id=user_id, sessions=[
            GrowthSessionSummary(
                session_id=s.id, agent=s.agent_type, status=s.status,
                stage=s.stage, finished=s.finished,
                has_report=bool(s.report_json or s.report),
                created_at=s.created_at, updated_at=s.updated_at,
                message_count=len([
                    c for c in (s.conversations or []) if c.role in ("user", "assistant")
                ]),
            ) for s in sessions
        ])

    def get_reports(
        self, db: Session, *, user_id: str, limit: int = 50,
    ) -> GrowthReportListResponse:
        """List persisted reports directly instead of inferring from sessions."""
        from services.today import TodayService

        reports = db.query(GrowthReport).filter(
            GrowthReport.user_id == user_id,
        ).order_by(GrowthReport.created_at.desc()).limit(limit).all()
        items: list[GrowthReportSummary] = []
        today_service = TodayService()
        for report in reports:
            payload = _report_payload(report)
            try:
                progress = today_service.get_plan_progress(
                    db, user_id=user_id, growth_session_id=report.session_id,
                )
            except Exception as exc:
                logger.warning("Growth reports: progress lookup failed: {}", exc)
                progress = {"total": 0, "overall_completion": 0.0}
            items.append(GrowthReportSummary(
                report_id=report.id,
                session_id=report.session_id,
                agent=report.agent_type,
                title=_agent_report_title(report.agent_type),
                summary=str(
                    payload.get("summary") or payload.get("goal")
                    or payload.get("current_status") or "完整规划报告已生成"
                )[:160],
                created_at=report.created_at,
                is_executing=bool(progress.get("total", 0)),
                progress=float(progress.get("overall_completion", 0.0)),
            ))
        return GrowthReportListResponse(
            user_id=user_id, total=len(items), reports=items,
        )

    def get_dashboard(self, db: Session, *, user_id: str) -> GrowthDashboardResponse:
        """Build the single state snapshot used by the Growth home page."""
        from models.today import PlanTask
        from services.today import TodayService

        sessions = session_crud.get_multi(db, user_id=user_id)
        sessions = sorted(
            sessions, key=lambda item: item.updated_at or item.created_at,
            reverse=True,
        )
        active = next((item for item in sessions if not item.finished), None)
        reports_response = self.get_reports(db, user_id=user_id, limit=50)
        latest_report = reports_response.reports[0] if reports_response.reports else None

        active_plan: dict[str, Any] | None = None
        latest_link = db.query(PlanTask).filter(
            PlanTask.user_id == user_id,
        ).order_by(PlanTask.synced_at.desc()).first()
        if latest_link is not None and latest_link.growth_session_id:
            progress = TodayService().get_plan_progress(
                db,
                user_id=user_id,
                growth_session_id=latest_link.growth_session_id,
            )
            source_report = db.query(GrowthReport).filter(
                GrowthReport.user_id == user_id,
                GrowthReport.session_id == latest_link.growth_session_id,
            ).first()
            current = progress.get("current_phase") or {}
            phase_key = current.get("phase_key") or latest_link.phase_key
            phase_number = _phase_number(phase_key)
            active_plan = {
                "session_id": latest_link.growth_session_id,
                "report_id": source_report.id if source_report else None,
                "agent": source_report.agent_type if source_report else "career",
                "title": _agent_report_title(source_report.agent_type if source_report else "career"),
                "phase_key": phase_key,
                "phase_label": f"第{phase_number}阶段",
                "phase_range": current.get("label", ""),
                "completed": int(progress.get("completed", 0)),
                "total": int(progress.get("total", 0)),
                "cancelled": int(progress.get("cancelled", 0)),
                "progress": float(progress.get("overall_completion", 0.0)),
            }

        if active is not None:
            page_state = "planning"
        elif active_plan is not None:
            page_state = "executing"
        elif latest_report is not None:
            page_state = "report_ready"
        else:
            page_state = "new"

        recent_coach = db.query(GrowthConversation).filter(
            GrowthConversation.user_id == user_id,
            GrowthConversation.role == "assistant",
            GrowthConversation.stage == "qa",
        ).order_by(GrowthConversation.created_at.desc()).first()
        return GrowthDashboardResponse(
            user_id=user_id,
            page_state=page_state,
            report_count=reports_response.total,
            active_session=(
                {
                    "session_id": active.id,
                    "agent": active.agent_type,
                    "stage": active.stage,
                    "current_step": active.current_step,
                    "total_steps": active.total_steps or MAX_FOLLOW_UP,
                    "updated_at": active.updated_at,
                }
                if active is not None else None
            ),
            latest_report=latest_report.model_dump() if latest_report else None,
            active_plan=active_plan,
            coach={
                "available": latest_report is not None,
                "session_id": latest_report.session_id if latest_report else None,
                "agent": latest_report.agent if latest_report else None,
                "last_summary": recent_coach.content[:120] if recent_coach else "",
                "quick_actions": ["汇报进展", "遇到困难", "复盘本周"],
            },
        )

    def get_report(
        self, db: Session, *, session_id: str, user_id: str | None = None,
    ) -> GrowthReportResponse:
        reports = report_crud.get_multi(db, session_id=session_id, limit=1)
        if not reports:
            raise NotFoundException(f"Report for session {session_id} not found")
        r = reports[0]
        if user_id is not None and r.user_id != user_id:
            raise NotFoundException(f"Report for session {session_id} not found")
        data = _report_payload(r)
        return GrowthReportResponse(
            session_id=session_id, agent=r.agent_type,
            report=data, created_at=r.created_at,
        )

    # ── Memory integration ────────────────────────────────────


    def _coach_context(
        self, db: Session, *, user_id: str, session_id: str, agent_type: str,
    ) -> tuple[str, str]:
        """Load real execution progress and stable memory for coach turns."""
        execution_context = "尚未把规划同步到今日任务。"
        memory_context = "暂无额外长期记忆。"
        try:
            from services.today import TodayService
            progress = TodayService().get_plan_progress(
                db, user_id=user_id, growth_session_id=session_id,
            )
            if progress.get("total", 0):
                execution_context = json.dumps(progress, ensure_ascii=False)[:2500]
        except Exception as exc:
            logger.warning("Growth coach: progress context unavailable: {}", exc)
        try:
            from services.memory_service import memory_service
            memory = memory_service.load_growth_context(
                db, user_id=user_id, agent_type=agent_type,
            )
            compact = {
                "profile": memory.get("profile", {}),
                "goal": memory.get("goal", ""),
                "action_plan": memory.get("action_plan", ""),
                "analysis": memory.get("analysis", ""),
            }
            memory_context = json.dumps(compact, ensure_ascii=False)[:2500]
        except Exception as exc:
            logger.warning("Growth coach: memory context unavailable: {}", exc)
        return execution_context, memory_context

    def free_qa(self, db: Session, *, request: GrowthChatRequest) -> dict[str, Any]:
        """Ongoing Growth Coach conversation after the first report exists."""
        if not request.session_id:
            raise ValidationException("缺少规划会话，无法继续咨询。")
        db_sess = _get_owned_sess(db, request.session_id, request.user_id)
        if not db_sess.finished or not db_sess.report_json:
            raise ValidationException("请先完成成长规划报告，再继续咨询。")
        agent_type = db_sess.agent_type

        # Load conversations
        convs = conv_crud.get_multi(db, session_id=request.session_id)
        convs = sorted(convs, key=lambda c: c.created_at)
        qa_history = "\n".join([
            f"{'User' if c.role == 'user' else 'Assistant'}: {c.content}"
            for c in convs[-20:] if c.role in ("user", "assistant")
        ])

        # Load report
        report_text = ""
        try:
            reports = report_crud.get_multi(db, session_id=request.session_id, limit=1)
            if reports and reports[0].full_report_json:
                report_text = reports[0].full_report_json
        except Exception:
            pass

        execution_context, memory_context = self._coach_context(
            db,
            user_id=request.user_id,
            session_id=request.session_id,
            agent_type=agent_type,
        )

        system_prompt = (
            f"你是用户长期使用的成长教练，当前主要跟进{agent_type}方向。"
            "你负责日常沟通、执行复盘和规划调整建议，而不是重新跑一套固定问卷。\n\n"
            f"用户已经确认的规划报告：\n"
            f"{report_text[:2000]}\n\n"
            f"今日任务与真实执行进度：\n{execution_context}\n\n"
            f"相关长期记忆：\n{memory_context}\n\n"
            f"最近对话：\n{qa_history[:2000]}\n\n"
            "请先回应用户当前感受或问题，再结合真实进度给出一个最值得执行的下一步。"
            "如果用户想调整规划，请清楚列出建议保留、延期、删除或新增的内容，"
            "并明确说明这只是调整建议、需要用户确认；不要声称已经修改任务。"
            "不要重复收集已知基础资料。信息确实不足时最多追问一个关键问题。"
            "语气自然、克制，像持续了解用户的教练，不使用Markdown标题。"
        )

        msg = request.message.strip()
        try:
            response = self.llm.chat(
                user_message=msg,
                system_prompt=system_prompt,
            )
        except Exception as e:
            logger.error("Free QA LLM error: {}", e)
            response = "抱歉，我暂时无法回答这个问题，请稍后重试。"

        # Save conversation
        conv_crud.create(db, obj_in={
            "session_id": db_sess.id, "user_id": request.user_id,
            "role": "user", "content": msg,
            "step": 999, "stage": "qa",
        })
        conv_crud.create(db, obj_in={
            "session_id": db_sess.id, "user_id": request.user_id,
            "role": "assistant", "content": response,
            "step": 999, "stage": "qa",
        })
        db.commit()
        try:
            from services.memory_service import memory_service
            memory_service.extract_from_turn_async(
                user_id=request.user_id,
                user_message=msg,
                assistant_message=response,
                source_context=f"growth_qa:{db_sess.id}",
            )
        except Exception:
            pass
        return {"message": response, "session_id": db_sess.id}


    def free_qa_stream(self, db: Session, *, request: GrowthChatRequest):
        """Stream free-form Q&A response token by token using real LLM streaming."""
        if not request.session_id:
            raise ValidationException("缺少规划会话，无法继续咨询。")
        db_sess = _get_owned_sess(db, request.session_id, request.user_id)
        if not db_sess.finished or not db_sess.report_json:
            raise ValidationException("请先完成成长规划报告，再继续咨询。")
        agent_type = db_sess.agent_type

        # Load conversations
        convs = conv_crud.get_multi(db, session_id=request.session_id)
        convs = sorted(convs, key=lambda c: c.created_at)
        qa_history = "\n".join([
            f"{'User' if c.role == 'user' else 'Assistant'}: {c.content}"
            for c in convs[-20:] if c.role in ("user", "assistant")
        ])

        report_text = ""
        try:
            reports = report_crud.get_multi(db, session_id=request.session_id, limit=1)
            if reports and reports[0].full_report_json:
                report_text = reports[0].full_report_json
        except Exception:
            pass

        execution_context, memory_context = self._coach_context(
            db,
            user_id=request.user_id,
            session_id=request.session_id,
            agent_type=agent_type,
        )

        system_prompt = (
            f"你是用户长期使用的成长教练，当前主要跟进{agent_type}方向。\n"
            f"用户已经确认的规划报告：\n"
            f"{report_text[:2000]}\n\n"
            f"今日任务与真实执行进度：\n{execution_context}\n\n"
            f"相关长期记忆：\n{memory_context}\n\n"
            f"以下是最近的对话历史：\n{qa_history[:2000]}\n\n"
            "请基于报告、执行进度和记忆直接回答。先回应当前问题，再给一个具体下一步。"
            "涉及调整时列出变更建议并等待用户确认，不要声称已经修改任务。"
            "不要重复收集基础资料；信息不足时最多追问一个关键问题，不要编造。"
        )

        msg = request.message.strip()
        full_response = ""

        try:
            for chunk in self.llm.chat_stream(
                user_message=msg,
                system_prompt=system_prompt,
                temperature=0.7,
                max_tokens=1024,
            ):
                full_response += chunk
                yield ("token", chunk)
        except Exception as e:
            logger.error("Free QA stream error: {}", e)
            full_response = "抱歉，我暂时无法回答这个问题，请稍后重试。"
            yield ("token", full_response)

        conv_crud.create(db, obj_in={
            "session_id": db_sess.id, "user_id": request.user_id,
            "role": "user", "content": msg,
            "step": 999, "stage": "qa",
        })
        conv_crud.create(db, obj_in={
            "session_id": db_sess.id, "user_id": request.user_id,
            "role": "assistant", "content": full_response,
            "step": 999, "stage": "qa",
        })
        db.commit()

        try:
            from services.memory_service import memory_service
            memory_service.extract_from_turn_async(
                user_id=request.user_id,
                user_message=msg,
                assistant_message=full_response,
                source_context=f"growth_qa:{db_sess.id}",
            )
        except Exception:
            pass

        yield ("done", json.dumps({"message": full_response, "session_id": db_sess.id}, ensure_ascii=False))


    def get_conversation(self, db: Session, *, session_id: str) -> list[dict[str, Any]]:
        """Get all user-visible messages for a growth session."""
        convs = conv_crud.get_multi(db, session_id=session_id)
        convs = sorted(convs, key=lambda c: c.created_at)
        return [
            {
                "id": c.id,
                "role": c.role,
                "content": c.content,
                "step": c.step,
                "stage": c.stage,
                "created_at": c.created_at.isoformat() if c.created_at else "",
            }
            for c in convs if c.role in ("user", "assistant")
        ]

    async def _save_memory(self, db: Session, session: GrowthSession, report: dict[str, Any]) -> None:
        """Write key findings to Memory system for cross-session continuity."""
        try:
            from services.memory_service import memory_service
            uid = session.user_id
            items: list[dict[str, Any]] = []
            goal_text = report.get("goal", "")
            if goal_text:
                items.append({
                    "key": f"growth:{session.agent_type}:goal",
                    "value": str(goal_text)[:1000],
                    "memory_type": "goal", "importance": 5, "confidence": 0.95,
                    "source": f"growth_report:{session.id}",
                })

            summary = report.get("summary", "")
            status = report.get("current_status", "")
            if summary or status:
                items.append({
                    "key": f"growth:{session.agent_type}:analysis",
                    "value": f"{status}\n{summary}".strip()[:1500],
                    "memory_type": "fact", "importance": 4, "confidence": 0.9,
                    "source": f"growth_report:{session.id}",
                })

            action_plan = report.get("action_plan", [])
            if action_plan:
                items.append({
                    "key": f"growth:{session.agent_type}:action_plan",
                    "value": json.dumps(action_plan, ensure_ascii=False)[:5000],
                    "memory_type": "action", "importance": 5, "confidence": 0.95,
                    "source": f"growth_report:{session.id}",
                })

            if items:
                memory_service.save_batch(db, user_id=uid, items=items)
            logger.info("Growth: saved {} categorized memories for user={}", len(items), uid)
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


def _agent_report_title(agent_type: str) -> str:
    return {
        "graduate": "考研规划报告",
        "career": "就业指导报告",
        "employment": "就业指导报告",
        "civil": "考公评估报告",
        "major": "转专业分析报告",
    }.get(agent_type, "个人发展规划报告")


def _report_payload(report: GrowthReport) -> dict[str, Any]:
    try:
        payload = json.loads(report.full_report_json or "{}")
        return payload if isinstance(payload, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _phase_number(phase_key: str) -> int:
    try:
        return max(1, int(str(phase_key).rsplit("_", 1)[-1]))
    except (TypeError, ValueError):
        return 1


def _get_sess(db: Session, sid: str) -> GrowthSession:
    s = session_crud.get(db, id=sid)
    if s is None:
        raise NotFoundException(f"Session {sid} not found")
    return s


def _get_owned_sess(db: Session, sid: str, user_id: str) -> GrowthSession:
    session = _get_sess(db, sid)
    if session.user_id != user_id:
        raise NotFoundException(f"Growth session {sid} not found")
    return session


def _load_report_dict(session: GrowthSession) -> dict[str, Any]:
    try:
        return json.loads(session.report_json or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}


def _session_to_state(session: GrowthSession) -> GrowthStateResponse:
    answers: dict[str, str] = {}
    try:
        saved = json.loads(session.state_json or "{}")
        planning_state = json.loads(saved.get("planning_state_json", "{}"))
        answers = planning_state.get("follow_up_answers", {})
    except (json.JSONDecodeError, TypeError, AttributeError):
        answers = {}
    return GrowthStateResponse(
        session_id=session.id,
        agent=session.agent_type,
        status=session.status,
        stage=session.stage,
        finished=session.finished,
        current_step=session.current_step,
        total_steps=session.total_steps or MAX_FOLLOW_UP,
        answers=answers,
        has_report=bool(session.report_json or session.report),
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


def _make_initial(agent_type: str, session_id: str, user_id: str,
                  profile: dict[str, str], sandbox_history: list | None = None,
                  prior_questions_asked: int = 0) -> GrowthState:
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
        ps.questions_asked = min(
            MAX_FOLLOW_UP,
            max(len(sandbox_history), prior_questions_asked),
        )
        # Sandbox answers count toward the shared five-question budget, but
        # completion is decided by the domain readiness gate, not by raw count.
    return {
        "user_id": user_id, "agent_type": agent_type, "session_id": session_id,
        "user_message": "", "user_correction": "",
        "planning_state_json": json.dumps(ps.to_dict(), ensure_ascii=False),
        "follow_up_round": ps.follow_up_round,
        "questions_asked": ps.questions_asked,
        "follow_up_complete": ps.follow_up_complete,
        "analysis": {}, "identified_problems": [], "long_term_goal": "",
        "action_plan": [], "output": {},
        "stage": "questioning", "finished": False,
        "agent_message": "", "report": None, "error_message": "", "last_question": "",
        "awaiting_trigger": ps.follow_up_complete, "report_requested": False,
        "turn_analysis": {}, "knowledge_context": "", "knowledge_evidence": {},
    }


def _state_from_db(db_sess: GrowthSession, req: GrowthChatRequest) -> GrowthState:
    try:
        saved = json.loads(db_sess.state_json or "{}")
    except (json.JSONDecodeError, TypeError):
        saved = {}
    return {
        "user_id": req.user_id, "agent_type": db_sess.agent_type,
        "session_id": db_sess.id, "user_message": req.message,
        "user_correction": "",
        "planning_state_json": saved.get("planning_state_json", "{}"),
        "follow_up_round": saved.get("follow_up_round", 0),
        "questions_asked": saved.get("questions_asked", 0),
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
        "awaiting_trigger": saved.get("awaiting_trigger", False),
        "report_requested": False,
        "turn_analysis": saved.get("turn_analysis", {}),
        "knowledge_context": saved.get("knowledge_context", ""),
        "knowledge_evidence": saved.get("knowledge_evidence", {}),
    }


def _is_analysis_approval(message: str) -> bool:
    normalized = message.strip().lower()
    if not normalized:
        return False
    keywords = ("继续", "确认", "生成报告", "可以", "好的", "没问题", "ok", "yes")
    return any(keyword in normalized for keyword in keywords)


def _flush(db_sess: GrowthSession, result: dict[str, Any]) -> None:
    now = datetime.now(timezone.utc)
    if result.get("stage"):
        db_sess.stage = result["stage"]
        if result["stage"] == "analyzing" and not result.get("finished"):
            db_sess.status = "analyzing"
    if result.get("finished"):
        db_sess.finished = True
        db_sess.status = "completed"
    asked = result.get("questions_asked", result.get("follow_up_round", 0))
    if asked > 0:
        db_sess.current_step = asked
    state_blob = {
        "planning_state_json": result.get("planning_state_json", "{}"),
        "follow_up_round": result.get("follow_up_round", 0),
        "questions_asked": result.get("questions_asked", 0),
        "follow_up_complete": result.get("follow_up_complete", False),
        "analysis": result.get("analysis", {}),
        "identified_problems": result.get("identified_problems", []),
        "long_term_goal": result.get("long_term_goal", ""),
        "action_plan": result.get("action_plan", []),
        "output": result.get("output", {}),
        "last_question": result.get("last_question", ""),
        "stage": result.get("stage", "questioning"),
        "finished": result.get("finished", False),
        "awaiting_trigger": result.get("awaiting_trigger", False),
        "turn_analysis": result.get("turn_analysis", {}),
        "knowledge_context": result.get("knowledge_context", ""),
        "knowledge_evidence": result.get("knowledge_evidence", {}),
    }
    db_sess.state_json = json.dumps(state_blob, ensure_ascii=False)
    if result.get("report"):
        db_sess.report_json = json.dumps(result["report"], ensure_ascii=False)
        db_sess.progress = 100.0
    elif result.get("stage") == "analyzing":
        db_sess.progress = 40.0
    elif result.get("stage") == "report":
        db_sess.progress = 90.0
    elif result.get("questions_asked", result.get("follow_up_round", 0)) > 0:
        asked = result.get("questions_asked", result.get("follow_up_round", 0))
        db_sess.progress = min(35.0, (asked / MAX_FOLLOW_UP) * 35.0)
    db_sess.updated_at = now


def _to_response(session_id: str, agent_type: str, result: dict[str, Any]) -> GrowthChatResponse:
    stage = result.get("stage", "questioning")
    finished = result.get("finished", False)
    fu = result.get("follow_up_round", 0)
    questions_asked = result.get("questions_asked", fu)
    message = result.get("agent_message", "")
    nq = None
    if not finished and message and stage in ("questioning", "awaiting"):
        nq = QuestionCard(
            id=f"follow_up_{questions_asked + 1}", title=message, options=[],
            required=False, index=min(questions_asked + 1, MAX_FOLLOW_UP), total=MAX_FOLLOW_UP,
        )
    return GrowthChatResponse(
        progress=result.get("progress", 0),
        session_id=session_id, agent=agent_type,
        stage="report" if finished else stage,
        finished=finished, current_step=questions_asked,
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

