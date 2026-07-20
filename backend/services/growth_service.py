# -*- coding: utf-8 -*-
"""Growth Service ? orchestrates the Growth Agent chat flow.

Manages the full agent lifecycle:
    Start -> Chat (QUESTIONING) -> Auto-ANALYZING -> REPORT

Key differences from old flow:
    - Uses BaseGrowthAgent classes (not QuestionFlowEngine)
    - State-driven: ConversationState manages the lifecycle
    - Agents are instantiated via AgentRouter
    - All conversations and reports persisted to DB
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy.orm import Session

from core.exceptions import NotFoundException, AppException
from agent.base import BaseGrowthAgent, ConversationState, AgentStage
from agent.router import AgentRouter
from models.growth import GrowthSession, GrowthConversation, GrowthReport
from schemas.growth import (
    AgentTypeEnum,
    GrowthChatRequest,
    GrowthStartRequest,
    GrowthChatResponse,
    GrowthStateResponse,
    GrowthHistoryResponse,
    GrowthSessionSummary,
    GrowthReportResponse,
    ConversationMessage,
    QuestionCard,
)
from crud.base import CRUDBase


session_crud = CRUDBase[GrowthSession](GrowthSession)
conv_crud = CRUDBase[GrowthConversation](GrowthConversation)
report_crud = CRUDBase[GrowthReport](GrowthReport)


class GrowthService:
    """Orchestrates Growth Agent conversations.

    Each turn:
        1. Load or create session
        2. Load or create agent via AgentRouter
        3. Call agent.chat(message)
        4. Persist conversation + state to DB
        5. Return response with next question or report
    """

    def __init__(self, llm_service: Any) -> None:
        self.llm = llm_service
        self.router = AgentRouter(llm_service)
        # In-memory agent cache: {session_id: BaseGrowthAgent}
        self._agents: dict[str, BaseGrowthAgent] = {}

    # Public API

    def start_session(
        self, db: Session, *, request: GrowthStartRequest
    ) -> GrowthChatResponse:
        """Start a new growth session and return the first question.

        Args:
            db: Database session.
            request: Start request with user_id and agent type.

        Returns:
            GrowthChatResponse with the first question card.
        """
        agent_type = request.agent.value if isinstance(request.agent, AgentTypeEnum) else request.agent

        logger.info("Growth: Starting session for user={}, agent={}", request.user_id, agent_type)

        # Create agent and initialize state
        agent = self.router.get_agent(agent_type)
        state = agent.init_state()

        # Create DB session
        session = session_crud.create(db, obj_in={
            "user_id": request.user_id,
            "agent_type": agent_type,
            "status": "active",
            "stage": state.stage.value,
            "current_step": 0,
            "total_steps": state.total_steps,
            "state_json": json.dumps(state.to_dict(), ensure_ascii=False),
            "progress": 0.0,
        })

        # Cache agent
        self._agents[session.id] = agent

        # Get first question
        first_q = agent.get_next_question()

        # Record initial system message
        conv_crud.create(db, obj_in={
            "session_id": session.id,
            "user_id": request.user_id,
            "role": "system",
            "content": "Growth session started: {}".format(agent_type),
            "step": 0,
            "stage": "questioning",
        })

        logger.info("Growth: Session {} started", session.id)

        return GrowthChatResponse(
            session_id=session.id,
            agent=agent_type,
            stage="questioning",
            finished=False,
            current_step=0,
            total_steps=state.total_steps,
            next_question=QuestionCard(**first_q) if first_q else None,
            report=None,
            message="???????{}????????????".format(agent.agent_label),
        )

    def chat(
        self, db: Session, *, request: GrowthChatRequest
    ) -> GrowthChatResponse:
        """Process a chat message and advance the agent flow.

        If session_id is None, auto-creates a new session and returns the first question.
        If session_id is provided, continues an existing session.

        When questioning completes, returns stage="analyzing" immediately
        (no blocking) and fires a background thread for LLM analysis.

        Args:
            db: Database session.
            request: Chat request with user_id, agent, message, optional session_id.

        Returns:
            GrowthChatResponse with next question, analyzing status, or report.
        """
        agent_type = request.agent.value if isinstance(request.agent, AgentTypeEnum) else request.agent

        # --- session_id is None: auto-create session, return first question ---
        if not request.session_id:
            logger.info("Growth: auto-creating session for user={}, agent={}", request.user_id, agent_type)

            agent = self.router.get_agent(agent_type)
            state = agent.init_state()

            session = session_crud.create(db, obj_in={
                "user_id": request.user_id,
                "agent_type": agent_type,
                "status": "active",
                "stage": state.stage.value,
                "current_step": 0,
                "total_steps": state.total_steps,
                "state_json": json.dumps(state.to_dict(), ensure_ascii=False),
                "progress": 0.0,
            })

            self._agents[session.id] = agent

            first_q = agent.get_next_question()
            conv_crud.create(db, obj_in={
                "session_id": session.id,
                "user_id": request.user_id,
                "role": "system",
                "content": "Growth session started: {}".format(agent_type),
                "step": 0,
                "stage": "questioning",
            })

            logger.info("Growth: Session {} auto-created", session.id)
            return GrowthChatResponse(
                session_id=session.id,
                agent=agent_type,
                stage="questioning",
                finished=False,
                current_step=0,
                total_steps=state.total_steps,
                next_question=QuestionCard(**first_q) if first_q else None,
                report=None,
                message="???????{}????????????".format(agent.agent_label),
            )

        # --- session_id provided: continue existing session ---
        session = session_crud.get(db, id=request.session_id)
        if session is None:
            raise NotFoundException("Session {} not found".format(request.session_id))
        if session.finished:
            raise AppException("This session is already completed.")

        # Load agent
        agent = self._get_or_restore_agent(db, session)

        # Record user message
        conv_crud.create(db, obj_in={
            "session_id": session.id,
            "user_id": request.user_id,
            "role": "user",
            "content": request.message,
            "step": session.current_step + 1,
            "stage": session.stage,
        })

        # Process through agent
        logger.debug("Growth: Processing chat, step={}, stage={}", session.current_step, session.stage)
        result = agent.chat(request.message)

        # Record agent response
        conv_crud.create(db, obj_in={
            "session_id": session.id,
            "user_id": request.user_id,
            "role": "assistant",
            "content": result.get("message", ""),
            "step": agent.state.current_step,
            "stage": result.get("stage", "questioning"),
        })

        # Update session in DB
        state_dict = agent.state.to_dict()
        update_data = {
            "stage": agent.state.stage.value,
            "status": agent.state.status.value,
            "current_step": agent.state.current_step,
            "finished": agent.state.finished,
            "state_json": json.dumps(state_dict, ensure_ascii=False),
            "answers_json": json.dumps(agent.state.answers, ensure_ascii=False),
            "progress": min(1.0, agent.state.current_step / agent.state.total_steps)
            if agent.state.total_steps > 0 else 0.0,
        }

        if agent.state.report_json:
            update_data["report_json"] = json.dumps(agent.state.report_json, ensure_ascii=False)

        session_crud.update(db, db_obj=session, obj_in=update_data)

        # --- Async: if stage is "analyzing", fire background analysis ---
        if result.get("stage") == "analyzing":
            logger.info("Growth: triggering async analysis for session {}", session.id)
            self._run_analysis_async(session.id, request.user_id, agent_type)

        # If report generated (sync or cached), save to GrowthReport table
        if result.get("stage") == "report" and agent.state.report_json:
            self._save_report(db, session, agent.state.report_json)
            logger.info("Growth: Report saved for session {}", session.id)

        # Build response
        next_q_data = result.get("next_question")
        next_question = QuestionCard(**next_q_data) if next_q_data else None

        return GrowthChatResponse(
            session_id=session.id,
            agent=agent_type,
            stage=result.get("stage", "questioning"),
            finished=result.get("finished", False),
            current_step=agent.state.current_step,
            total_steps=agent.state.total_steps,
            next_question=next_question,
            report=result.get("report"),
            message=result.get("message", ""),
        )

    def _run_analysis_async(
        self, session_id: str, user_id: str, agent_type: str
    ) -> None:
        """Run LLM analysis in a background daemon thread.

        Creates a fresh DB session, calls agent._handle_analyzing(),
        and persists the report.
        """
        import threading

        def _do_analyze() -> None:
            from database.session import SessionLocal
            bg_db = SessionLocal()
            try:
                logger.info("Growth: background analysis started for session {}", session_id)
                session = session_crud.get(bg_db, id=session_id)
                if session is None or session.finished:
                    logger.warning("Growth: session {} not found or already finished", session_id)
                    return

                agent = self._get_or_restore_agent(bg_db, session)
                result = agent._handle_analyzing()

                # Update DB
                state_dict = agent.state.to_dict()
                update_data = {
                    "stage": agent.state.stage.value,
                    "status": agent.state.status.value,
                    "finished": agent.state.finished,
                    "state_json": json.dumps(state_dict, ensure_ascii=False),
                }
                if agent.state.report_json:
                    update_data["report_json"] = json.dumps(
                        agent.state.report_json, ensure_ascii=False
                    )

                session_crud.update(bg_db, db_obj=session, obj_in=update_data)

                if agent.state.report_json:
                    self._save_report(bg_db, session, agent.state.report_json)

                logger.info("Growth: background analysis completed for session {}", session_id)
            except Exception as exc:
                logger.error("Growth: background analysis failed for session {}: {}",
                             session_id, exc)
            finally:
                bg_db.close()

        thread = threading.Thread(target=_do_analyze, daemon=True)
        thread.start()
        logger.debug("Growth: analysis thread spawned for session {}", session_id)

    def get_state(self, db: Session, *, user_id: str) -> GrowthStateResponse:
        """Get the current growth state for a user.

        Returns the most recent active session, or None if no active session.

        Args:
            db: Database session.
            user_id: User ID.

        Returns:
            GrowthStateResponse with current session state.
        """
        # Get most recent session (active first, then completed)
        sessions = session_crud.get_multi(
            db, user_id=user_id, finished=False, limit=1
        )
        if not sessions:
            sessions = session_crud.get_multi(
                db, user_id=user_id, limit=1
            )
        if not sessions:
            return GrowthStateResponse()

        session = sessions[0]
        state_dict = {}
        if session.state_json:
            try:
                state_dict = json.loads(session.state_json)
            except json.JSONDecodeError:
                pass

        return GrowthStateResponse(
            session_id=session.id,
            agent=session.agent_type,
            stage=session.stage,
            finished=session.finished,
            current_step=session.current_step,
            total_steps=session.total_steps,
            answers=state_dict.get("answers", {}),
            has_report=session.report_json is not None,
            created_at=session.created_at,
            updated_at=session.updated_at,
        )

    def get_history(
        self, db: Session, *, user_id: str, limit: int = 20
    ) -> GrowthHistoryResponse:
        """Get growth session history for a user.

        Args:
            db: Database session.
            user_id: User ID.
            limit: Max number of sessions to return.

        Returns:
            GrowthHistoryResponse with list of session summaries.
        """
        sessions = session_crud.get_multi(
            db, user_id=user_id, limit=limit
        )

        summaries = []
        for s in sessions:
            msg_count = conv_crud.count(db, session_id=s.id)
            summaries.append(GrowthSessionSummary(
                session_id=s.id,
                agent=s.agent_type,
                status=s.status,
                finished=s.finished,
                created_at=s.created_at,
                message_count=msg_count,
            ))

        return GrowthHistoryResponse(
            user_id=user_id,
            sessions=summaries,
        )

    def get_report(self, db: Session, *, session_id: str) -> GrowthReportResponse:
        """Get the final growth report for a completed session.

        Args:
            db: Database session.
            session_id: Session ID.

        Returns:
            GrowthReportResponse with the full report.
        """
        session = session_crud.get(db, id=session_id)
        if session is None:
            raise NotFoundException("Session {} not found".format(session_id))
        if not session.report_json:
            raise AppException("Report not yet generated for this session.")

        try:
            report = json.loads(session.report_json)
        except json.JSONDecodeError:
            report = {}

        return GrowthReportResponse(
            session_id=session.id,
            agent=session.agent_type,
            report=report,
            created_at=session.updated_at,
        )

    def get_conversation(
        self, db: Session, *, session_id: str
    ) -> list[ConversationMessage]:
        """Get all conversation messages for a session.

        Args:
            db: Database session.
            session_id: Session ID.

        Returns:
            List of GrowthConversation schema objects.
        """
        msgs = conv_crud.get_multi(db, session_id=session_id, limit=200)
        return [
            ConversationMessage.model_validate(m) for m in msgs
        ]

    # Private helpers

    def _get_or_restore_agent(
        self, db: Session, session: GrowthSession
    ) -> BaseGrowthAgent:
        """Get cached agent or restore from DB state."""
        if session.id in self._agents:
            logger.debug("Growth: Using cached agent for session {}", session.id)
            return self._agents[session.id]

        # Restore agent from saved state
        agent = self.router.get_agent(session.agent_type)
        if session.state_json:
            try:
                state_data = json.loads(session.state_json)
                state = ConversationState.from_dict(state_data)
                agent.restore_state(state)
            except (json.JSONDecodeError, Exception) as e:
                logger.warning("Growth: Failed to restore state, reinitializing: {}", e)
                agent.init_state()
        else:
            agent.init_state()

        self._agents[session.id] = agent
        logger.debug("Growth: Agent restored for session {}", session.id)
        return agent

    def _save_report(
        self, db: Session, session: GrowthSession, report: dict[str, Any]
    ) -> None:
        """Save the final report to the GrowthReport table."""
        # Check if report already exists
        existing = report_crud.get_multi(db, session_id=session.id, limit=1)
        if existing:
            report_crud.update(db, db_obj=existing[0], obj_in={
                "full_report_json": json.dumps(report, ensure_ascii=False),
                "profile_json": json.dumps(report.get("profile", {}), ensure_ascii=False),
                "analysis_json": json.dumps(report.get("analysis", {}), ensure_ascii=False),
                "advantages_json": json.dumps(report.get("advantages", []), ensure_ascii=False),
                "risks_json": json.dumps(report.get("risks", []), ensure_ascii=False),
                "recommendations_json": json.dumps(report.get("recommendations", []), ensure_ascii=False),
                "plan_json": json.dumps(report.get("plan", []), ensure_ascii=False),
            })
        else:
            report_crud.create(db, obj_in={
                "session_id": session.id,
                "user_id": session.user_id,
                "agent_type": session.agent_type,
                "report_type": "{}_report".format(session.agent_type),
                "full_report_json": json.dumps(report, ensure_ascii=False),
                "profile_json": json.dumps(report.get("profile", {}), ensure_ascii=False),
                "analysis_json": json.dumps(report.get("analysis", {}), ensure_ascii=False),
                "advantages_json": json.dumps(report.get("advantages", []), ensure_ascii=False),
                "risks_json": json.dumps(report.get("risks", []), ensure_ascii=False),
                "recommendations_json": json.dumps(report.get("recommendations", []), ensure_ascii=False),
                "plan_json": json.dumps(report.get("plan", []), ensure_ascii=False),
            })

        logger.info("Growth: Report persisted for session {}", session.id)


# Singleton
_growth_service: GrowthService | None = None


def get_growth_service(llm_service: Any | None = None) -> GrowthService:
    """Return the singleton GrowthService instance."""
    global _growth_service
    if _growth_service is None:
        if llm_service is None:
            from services.llm_service import get_llm_service
            llm_service = get_llm_service()
        _growth_service = GrowthService(llm_service)
    return _growth_service
