# -*- coding: utf-8 -*-
"""DecisionSandbox — orchestrator for the multi-path comparison system.

Phases:
    1. DISCOVERY      — Collect universal user profile (5-7 rounds)
    2. PATH_PROBE     — 1-2 path-specific questions per selected path
    3. PARALLEL_SIM   — Inject context into planning agents, generate reports
    4. PROJECTION     — ProjectionAgent compares N reports

Integrates with:
    - PlanningRouter: to create and orchestrate domain-specific agents
    - MemoryService: to read/write user memories across sessions
    - ProjectionAgent: to generate the final comparison JSON
"""

from __future__ import annotations

import uuid
from typing import Any

from loguru import logger

from sandbox.state import (
    SandboxSession,
    SandboxPhase,
    SANDBOX_PATHS,
    SANDBOX_PATH_LIST_STR,
    PATH_KEYWORDS,
    MAX_DISCOVERY_ROUNDS,
    MAX_PATH_PROBE_ROUNDS,
)
from sandbox.prompts.discovery import (
    build_discovery_system_prompt,
    build_discovery_user_prompt,
)
from sandbox.prompts.path_probe import build_path_probe_prompt
from sandbox.projection import ProjectionAgent
from planning.base import PlanningAgent, UNIFIED_OUTPUT_SCHEMA
from utils.json_parser import safe_json_parse


class DecisionSandbox:
    """Orchestrator for the decision sandbox multi-path comparison workflow.

    Usage:
        sandbox = DecisionSandbox(
            llm_service=llm,
            planning_router=router,
            memory_service=memory,
        )
        session = sandbox.start_session(user_id="user_123")
        result = sandbox.chat(session, message="我很迷茫...")
    """

    def __init__(
        self,
        llm_service: Any,
        planning_router: Any,
        memory_service: Any | None = None,
    ) -> None:
        """Initialize the sandbox orchestrator.

        Args:
            llm_service: LLMService instance for LLM calls.
            planning_router: PlanningRouter instance for creating planning agents.
            memory_service: Optional MemoryService for reading/writing user memories.
        """
        self.llm = llm_service
        self.router = planning_router
        self.memory = memory_service
        self._projection_agent: ProjectionAgent | None = None
        self._sessions: dict[str, SandboxSession] = {}
        logger.info("DecisionSandbox initialized")

    @property
    def projection_agent(self) -> ProjectionAgent:
        """Lazy-init the projection agent."""
        if self._projection_agent is None:
            self._projection_agent = ProjectionAgent(self.llm)
        return self._projection_agent

    # ── Session Management ──────────────────────────────────────

    def start_session(
        self,
        user_id: str,
        session_id: str | None = None,
        db_session: Any | None = None,
    ) -> SandboxSession:
        """Start a new sandbox session.

        Loads existing user memories at session start for context.

        Args:
            user_id: Unique user identifier.
            session_id: Optional session ID (auto-generated if None).
            db_session: Optional SQLAlchemy db session for memory loading.

        Returns:
            A fresh SandboxSession in DISCOVERY phase.
        """
        session_id = session_id or str(uuid.uuid4())

        session = SandboxSession(
            session_id=session_id,
            user_id=user_id,
        )

        # Load memory snapshot from DB
        if self.memory and db_session:
            try:
                memories = self.memory.load_memory(
                    db_session, user_id=user_id, as_dict=True
                )
                if isinstance(memories, dict):
                    session.memory_snapshot = memories
                    logger.info(
                        "Sandbox: loaded {} memory entries for user {}",
                        len(memories), user_id,
                    )
            except Exception as exc:
                logger.warning("Sandbox: failed to load memories: {}", exc)

        # Pre-populate profile from memory so discovery skips known info
        self.load_memory_into_profile(session)

        self._sessions[session_id] = session
        logger.info("Sandbox session started: {} (user={})", session_id, user_id)
        return session

    def restore_session(self, session_data: dict[str, Any]) -> SandboxSession:
        """Restore a session from serialized dict.

        Args:
            session_data: Serialized session dict from SandboxSession.to_dict().

        Returns:
            Restored SandboxSession instance.
        """
        session = SandboxSession.from_dict(session_data)
        self._sessions[session.session_id] = session
        return session

    def get_session(self, session_id: str) -> SandboxSession | None:
        """Get an active session by ID."""
        return self._sessions.get(session_id)

    # ── Main Entry: chat ────────────────────────────────────────

    def chat(
        self,
        session: SandboxSession,
        message: str,
        db_session: Any | None = None,
    ) -> dict[str, Any]:
        """Main entry: process one user message through the current phase.

        Dispatches to the appropriate phase handler based on session state.

        Args:
            session: The active SandboxSession.
            message: User's latest message.
            db_session: Optional DB session for memory persistence.

        Returns:
            Response dict with phase, message, and contextual metadata.
        """
        if session.finished:
            return self._build_response(
                session, "已完成分析。可以查看对比结果。",
                extra={"finished": True},
            )

        logger.info(
            "Sandbox[{}]: phase={}, round={}",
            session.session_id, session.current_phase.value, session.discovery_round,
        )

        try:
            if session.current_phase == SandboxPhase.DISCOVERY:
                result = self._handle_discovery(session, message)
            elif session.current_phase == SandboxPhase.PATH_PROBE:
                result = self._handle_path_probe(session, message)
            elif session.current_phase == SandboxPhase.PARALLEL_SIM:
                result = self._handle_parallel_sim(session)
            elif session.current_phase == SandboxPhase.PROJECTION:
                result = self._handle_projection(session)
            else:
                result = self._build_response(
                    session, "系统状态异常，请重新开始。",
                    extra={"error": True},
                )

            # Persist memory after each interaction
            if self.memory and db_session:
                self._persist_memory(session, db_session)

            return result

        except Exception as exc:
            logger.exception("Sandbox[{}]: error in phase {}: {}",
                             session.session_id, session.current_phase.value, exc)
            session.current_phase = SandboxPhase.ERROR
            session.error_message = str(exc)
            return self._build_response(
                session, f"处理过程中出现错误: {exc}。请稍后重试。",
                extra={"error": True},
            )
        finally:
            # Evict completed/errored sessions to prevent memory leaks
            self._evict_stale_sessions()

    # ── Phase 1: Discovery ──────────────────────────────────────

    def _handle_discovery(
        self,
        session: SandboxSession,
        message: str,
    ) -> dict[str, Any]:
        """Handle discovery phase: collect universal user profile.

        Uses LLM-driven dynamic questioning, NOT a fixed script.
        Reuses the _generate_dynamic_question pattern from PlanningAgent.
        """
        is_first = (session.discovery_round == 0)

        # Build prompts
        system_prompt = build_discovery_system_prompt(
            known_profile=session.user_profile if session.user_profile else None,
            memory_context=self._format_memory(session),
        )

        history_text = session.build_discovery_context()
        user_prompt = build_discovery_user_prompt(
            history_text=history_text,
            latest_message=message,
            is_first_turn=is_first,
        )

        # Call LLM
        try:
            raw = self.llm.chat(
                user_message=user_prompt,
                system_prompt=system_prompt,
                temperature=0.7,
                max_tokens=1024,
            )
        except Exception as exc:
            logger.error("Discovery LLM call failed: {}", exc)
            # Fallback: ask a generic question
            fallback_q = "接下来我想更了解你的情况——你觉得目前最大的困惑是什么？"
            if is_first:
                fallback_q = (
                    "你好！我是你的成长规划助手。你现在对未来的方向有什么困惑吗？"
                    "可以和我聊聊你目前的情况和想法。"
                )
            session.record_discovery(fallback_q, message)
            return self._build_response(
                session, fallback_q,
                extra={"discovery_round": session.discovery_round},
            )

        # Parse LLM response
        parsed = safe_json_parse(raw)
        if parsed is None:
            logger.warning("Discovery: failed to parse LLM JSON, using raw text")
            if is_first:
                next_q = "你好！我是你的成长规划助手。你现在对未来的方向有什么困惑吗？可以和我聊聊你目前的情况和想法。"
            elif raw and raw.strip():
                next_q = raw.strip()[:200]
            else:
                next_q = "接下来我想更了解你的情况——你觉得目前最大的困惑是什么？"
            session.record_discovery(next_q, message)
        else:
            next_q = parsed.get("next_question", "请详细说说你的想法？")
            # Update cumulative profile
            updated = parsed.get("updated_profile", {})
            if isinstance(updated, dict):
                for k, v in updated.items():
                    if v:  # Only store non-empty values
                        session.user_profile[k] = v
                        session._profile_dirty = True
            session.record_discovery(next_q, message)

        # Check if we should advance
        if parsed and parsed.get("finish", False):
            logger.info("Discovery: LLM signaled finish")
            session.discovery_complete = True
            # Transition to PATH_PROBE
            return self._transition_to_path_probe(session)

        if not session.should_continue_discovery():
            logger.info("Discovery: max rounds reached, transitioning to path probe")
            session.discovery_complete = True
            return self._transition_to_path_probe(session)

        return self._build_response(
            session, next_q,
            extra={
                "discovery_round": session.discovery_round,
                "max_discovery_rounds": MAX_DISCOVERY_ROUNDS,
                "user_profile": session.user_profile,
            },
        )

    def _transition_to_path_probe(self, session: SandboxSession) -> dict[str, Any]:
        """Transition from discovery to path probe phase.

        Asks the user which paths they want to compare.
        """
        session.advance_phase()
        logger.info("Sandbox[{}]: entering PATH_PROBE phase", session.session_id)

        # If user already specified paths (e.g., via API), skip the selection question
        if session.path_selections:
            first_path = session.path_selections[0]
            path_label = SANDBOX_PATHS.get(first_path, first_path)
            question = self._generate_path_probe_question(session, first_path)
            return self._build_response(
                session, question,
                extra={"phase": "path_probe", "current_path": first_path},
            )
        # Ask which paths to compare
        path_list = SANDBOX_PATH_LIST_STR
        question = (
            f"好的，我已经对你的情况有了基本了解。接下来我们来做路径对比。\\n\\n"
            f"目前有以下方向可以分析：{path_list}。\\n"
            f"你想对比哪些方向？（可以说多个，比如\"就业和考研\"）"
        )
        return self._build_response(
            session, question,
            extra={"phase": "path_probe", "selecting_paths": True},
        )

    # ── Phase 2: Path Probe ─────────────────────────────────────

    def _handle_path_probe(
        self,
        session: SandboxSession,
        message: str,
    ) -> dict[str, Any]:
        """Handle path probe phase: ask 1-2 path-specific questions.

        State machine within path_probe:
            1. Parse path selections from user message (if not yet done)
            2. For each path, ask 1-2 questions
            3. When all paths have been probed, advance to PARALLEL_SIM
        """
        # Step 1: Parse path selections if not yet done
        if not session.path_selections:
            selections = self._parse_path_selections(message)
            if not selections:
                path_list = SANDBOX_PATH_LIST_STR
                return self._build_response(
                    session, f"我没能识别出你想对比的方向。请从以下选择：{path_list}。可以说多个。",
                    extra={"selecting_paths": True},
                )
            session.path_selections = selections
            logger.info("Sandbox[{}]: selected paths: {}", session.session_id, selections)

            # Initialize path_probe_history for each selection
            for pt in selections:
                session.path_probe_history.setdefault(pt, [])

            # Generate first path's probe question immediately
            first_path = selections[0]
            question = self._generate_path_probe_question(session, first_path)
            return self._build_response(
                session, question,
                extra={"phase": "path_probe", "current_path": first_path},
            )

        # Step 2: Record answer and determine next action
        # Find which path we're currently probing
        current_path = self._find_current_probe_path(session)
        if current_path is None:
            logger.warning("Path probe: no current path found, advancing to simulation")
            return self._advance_to_parallel_sim(session)

        # Record the answer
        session.record_path_probe(current_path, "", message)

        # Check if we need more questions for this path
        rounds = session.path_probe_rounds(current_path)
        if rounds < MAX_PATH_PROBE_ROUNDS:
            question = self._generate_path_probe_question(session, current_path)
            # Avoid generating redundant questions if LLM fails
            if not question:
                logger.warning("Path probe: empty question for {}, skipping", current_path)
                session.path_probe_done.add(current_path)
                return self._maybe_advance_from_probe(session)
            return self._build_response(
                session, question,
                extra={"phase": "path_probe", "current_path": current_path, "probe_round": rounds},
            )

        # This path is done
        session.path_probe_done.add(current_path)
        logger.info("Sandbox[{}]: path probe done for {}", session.session_id, current_path)
        return self._maybe_advance_from_probe(session)

    def _find_current_probe_path(self, session: SandboxSession) -> str | None:
        """Find the next path that still needs probing."""
        for pt in session.path_selections:
            if pt not in session.path_probe_done:
                return pt
        return None

    def _maybe_advance_from_probe(self, session: SandboxSession) -> dict[str, Any]:
        """Check if all paths have been probed, then advance."""
        next_path = self._find_current_probe_path(session)
        if next_path:
            question = self._generate_path_probe_question(session, next_path)
            return self._build_response(
                session, question,
                extra={"phase": "path_probe", "current_path": next_path},
            )

        # All paths probed — advance to parallel simulation
        return self._advance_to_parallel_sim(session)

    def _advance_to_parallel_sim(self, session: SandboxSession) -> dict[str, Any]:
        """Advance to parallel simulation phase."""
        session.advance_phase()
        logger.info(
            "Sandbox[{}]: entering PARALLEL_SIM for paths: {}",
            session.session_id, session.path_selections,
        )
        return self._handle_parallel_sim(session)

    def _generate_path_probe_question(
        self,
        session: SandboxSession,
        path_type: str,
    ) -> str:
        """Generate a path-specific probe question via LLM.

        Args:
            session: The active session.
            path_type: The path type to probe.

        Returns:
            A question string.
        """
        system_prompt = build_path_probe_prompt(
            path_type=path_type,
            discovery_context=session.build_discovery_context(),
        )

        current_answers = session.path_probe_history.get(path_type, [])
        if current_answers:
            history_text = "已回答:\n" + "\n".join(
                f"- {qa['a']}" for qa in current_answers
            )
        else:
            history_text = "尚无补充问题。"

        user_prompt = f"""## 需要补充的路径信息
路径类型: {SANDBOX_PATHS.get(path_type, path_type)}
{history_text}

请生成下一个补充问题。"""

        try:
            raw = self.llm.chat(
                user_message=user_prompt,
                system_prompt=system_prompt,
                temperature=0.7,
                max_tokens=512,
            )
            parsed = safe_json_parse(raw)
            if parsed and "questions" in parsed:
                questions = parsed["questions"]
                if questions:
                    return questions[0]
            return raw.strip()[:300] if raw else "关于这条路，你还有什么想补充的吗？"
        except Exception as exc:
            logger.warning("Path probe question generation failed: {}", exc)
            label = SANDBOX_PATHS.get(path_type, path_type)
            return f"关于{label}这条路，你最大的顾虑是什么？"

    def _parse_path_selections(self, message: str) -> list[str]:
        """Parse user message to determine which paths they want to compare.

        Uses keyword matching against Chinese path names, with the
        centralized PATH_KEYWORDS registry for richer matching.

        Args:
            message: User text message.

        Returns:
            List of matching path type keys.
        """
        selected: list[str] = []

        for path_type, words in PATH_KEYWORDS.items():
            if any(w in message for w in words):
                selected.append(path_type)

        # If nothing matched, try globals like "all" / "对比"
        if not selected:
            if any(w in message for w in ["都", "全部", "所有", "all", "对比"]):
                selected = list(SANDBOX_PATHS.keys())

        return selected

    # ── Phase 3: Parallel Simulation ────────────────────────────

    def _handle_parallel_sim(self, session: SandboxSession) -> dict[str, Any]:
        """Handle parallel simulation: inject context into each planning agent.

        For each selected path:
            1. Create the corresponding PlanningAgent
            2. Initialize with user context (skip follow-up phase)
            3. Jump directly to analysis and generate report

        All agents run in serial but could be parallelized with asyncio.
        """
        if not session.path_selections:
            return self._build_response(
                session, "没有选择任何路径，无法进行分析。",
                extra={"error": True},
            )

        logger.info(
            "Sandbox[{}]: running parallel simulation for {} paths",
            session.session_id, len(session.path_selections),
        )

        reports: dict[str, dict[str, Any]] = {}
        context = session.build_user_context_for_agent()

        for path_type in session.path_selections:
            try:
                report = self._run_single_agent_simulation(path_type, context, session)
                if report:
                    reports[path_type] = report
                    logger.info("Sandbox[{}]: {} report generated", session.session_id, path_type)
                else:
                    logger.warning("Sandbox[{}]: {} simulation returned empty report", session.session_id, path_type)
                    reports[path_type] = self._build_fallback_report(path_type)
            except Exception as exc:
                logger.exception("Sandbox[{}]: {} simulation failed: {}", session.session_id, path_type, exc)
                reports[path_type] = self._build_fallback_report(path_type)

        session.path_reports = reports
        session.parallel_sim_complete = True

        # Advance to projection
        session.advance_phase()
        return self._handle_projection(session)

    def _run_single_agent_simulation(
        self,
        path_type: str,
        context: str,
        session: SandboxSession,
    ) -> dict[str, Any] | None:
        """Run a single planning agent simulation for one path.

        Strategy:
            - Create the agent
            - Initialize with user_profile and skip follow-up
            - Inject a "please skip to analysis" message
            - Parse the report from the agent's output

        Args:
            path_type: Agent type key.
            context: Pre-built user context string.
            session: Active session for additional context.

        Returns:
            Report dict or None.
        """
        try:
            agent = self.router.get_agent(path_type)
        except ValueError as exc:
            logger.error("Sandbox: unknown agent type {}: {}", path_type, exc)
            return None

        # Build a rich user profile from discovery data
        user_profile = dict(session.user_profile)

        # Add path-specific probe answers
        probe_history = session.path_probe_history.get(path_type, [])
        if probe_history:
            user_profile["path_specific_context"] = "\n".join(
                f"Q: {qa.get('q', '')}\nA: {qa.get('a', '')}"
                for qa in probe_history
            )

        # Initialize agent with profile, then force-skip to report generation.
        # This bypasses the normal follow-up engine entirely.
        agent.init_state(user_profile=user_profile)
        from planning.state import WorkflowStep
        agent.state.set_step(WorkflowStep.GENERATE_OUTPUT)
        agent.state.follow_up_complete = True

        # Build the simulation prompt: inject context and ask for direct analysis
        simulation_message = f"""请基于以下信息直接进行分析，跳过追问阶段。

## 背景信息
路径类型: {SANDBOX_PATHS.get(path_type, path_type)}
{context}

## 要求
请直接生成完整的分析报告（JSON格式）。
如果某些维度信息不足，请基于一般情况和合理假设进行分析，并在对应部分标注。"""

        try:
            result = agent.chat(simulation_message)
        except Exception as exc:
            logger.error("Sandbox: agent chat failed for {}: {}", path_type, exc)
            return None

        # Extract report from result
        report = result.get("report")
        if report:
            return report

        # Try to parse from output
        output = result.get("state", {}).get("output", {})
        if output:
            return output

        logger.warning("Sandbox: no report in agent output for {}", path_type)
        return None

    def _build_fallback_report(self, path_type: str) -> dict[str, Any]:
        """Build a minimal fallback report when agent simulation fails."""
        label = SANDBOX_PATHS.get(path_type, path_type)
        return {
            "summary": f"{label}路径分析因系统原因未能完整生成。请在后续对话中重新触发分析。",
            "current_status": "信息不足",
            "main_problem": "系统分析未完成",
            "goal": "",
            "advantages": [{"point": "暂未分析", "detail": "请重新触发分析"}],
            "risks": [{"point": "分析未完成", "detail": "系统错误导致分析中断", "level": "high"}],
            "action_plan": [],
            "next_question": "",
        }

    # ── Phase 4: Projection ─────────────────────────────────────

    def _handle_projection(self, session: SandboxSession) -> dict[str, Any]:
        """Handle projection phase: run the ProjectionAgent to compare results."""
        logger.info("Sandbox[{}]: running projection comparison", session.session_id)

        try:
            result = self.projection_agent.compare(
                user_profile=session.user_profile,
                path_reports=session.path_reports,
                discovery_context=session.build_discovery_context(),
            )
        except Exception as exc:
            logger.exception("Sandbox: projection failed: {}", exc)
            result = self._build_fallback_projection(session)

        session.projection_result = result
        session.advance_phase()  # -> COMPLETED

        # Save session state
        self._sessions[session.session_id] = session

        return self._build_response(
            session,
            "🎉 多路径对比分析已完成！以下是分析结果：",
            extra={
                "finished": True,
                "projection_result": result,
            },
        )

    def _build_fallback_projection(self, session: SandboxSession) -> dict[str, Any]:
        """Build a minimal fallback projection when LLM analysis fails."""
        from sandbox.projection import _build_fallback_result
        return _build_fallback_result(session.path_reports)

    # ── Memory Integration ──────────────────────────────────────

    def _persist_memory(
        self,
        session: SandboxSession,
        db_session: Any,
    ) -> None:
        """Write accumulated user profile data to the Memory DB.

        Only persists when profile has meaningful changes (dirty flag),
        avoiding redundant database writes on every chat turn.
        """
        if not self.memory:
            return
        if not getattr(session, "_profile_dirty", True):
            return

        items: list[dict] = []

        # Map session profile fields to memory keys
        field_mapping = {
            "major": "专业",
            "grade": "年级",
            "core_confusion": "当前困惑",
            "personality": "性格特质",
            "learning_ability": "学习能力",
            "execution": "执行力",
            "social_ability": "社交能力",
            "stress_tolerance": "抗压能力",
            "family_expectation": "家庭期望",
            "economic_situation": "经济状况",
            "location_preference": "地域偏好",
            "time_window": "时间窗口",
        }

        for field, label in field_mapping.items():
            val = session.user_profile.get(field)
            if val:
                items.append({
                    "key": label,
                    "value": str(val),
                    "importance": 2,
                })

        # Also save path preferences
        if session.path_selections:
            path_labels = [SANDBOX_PATHS.get(p, p) for p in session.path_selections]
            items.append({
                "key": "关注路径",
                "value": "、".join(path_labels),
                "importance": 3,
            })

        if items:
            try:
                self.memory.save_batch(
                    db_session,
                    user_id=session.user_id,
                    items=items,
                )
                logger.info("Sandbox: persisted {} memory items for user {}",
                            len(items), session.user_id)
            except Exception as exc:
                logger.warning("Sandbox: failed to persist memory: {}", exc)

    def _format_memory(self, session: SandboxSession) -> str:
        """Format memory snapshot as a string for prompt injection."""
        if not session.memory_snapshot:
            return ""
        lines = []
        for k, v in session.memory_snapshot.items():
            lines.append(f"- {k}: {v}")
        return "已知信息:\n" + "\n".join(lines) if lines else ""

    def load_memory_into_profile(self, session: SandboxSession) -> None:
        """Pre-populate user_profile from memory snapshot.

        Called at session start so discovery phase doesn't re-ask known info.
        """
        key_mapping = {
            "专业": "major",
            "年级": "grade",
            "目标": "goal",
            "兴趣": "interested_fields",
            "职业方向": "career_direction",
            "当前困惑": "core_confusion",
            "性格特质": "personality",
            "学习能力": "learning_ability",
            "执行力": "execution",
            "地域偏好": "location_preference",
        }

        for mem_key, field in key_mapping.items():
            if mem_key in session.memory_snapshot:
                session.user_profile[field] = session.memory_snapshot[mem_key]

    # ── Session Cleanup ────────────────────────────────────────

    def _evict_stale_sessions(self) -> None:
        """Remove completed or errored sessions from memory.

        Prevents the in-memory session store from growing unboundedly.
        Completed sessions remain accessible via the API session store.
        """
        stale_ids = [
            sid for sid, s in self._sessions.items()
            if s.finished or s.current_phase == SandboxPhase.ERROR
        ]
        for sid in stale_ids:
            del self._sessions[sid]
        if stale_ids:
            logger.debug("Sandbox: evicted {} stale sessions", len(stale_ids))

    # ── Response Builder ────────────────────────────────────────

    def _build_response(
        self,
        session: SandboxSession,
        message: str,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build a standardized response dict for the API layer.

        Args:
            session: Active session.
            message: Primary response message (shown to user).
            extra: Additional fields to include in the response.

        Returns:
            Response dict.
        """
        response: dict[str, Any] = {
            "session_id": session.session_id,
            "user_id": session.user_id,
            "phase": session.current_phase.value,
            "finished": session.finished,
            "message": message,
        }

        if extra:
            response.update(extra)

        # Include relevant session metadata
        if session.current_phase == SandboxPhase.DISCOVERY:
            response["discovery_round"] = session.discovery_round
            response["max_discovery_rounds"] = MAX_DISCOVERY_ROUNDS

        if session.current_phase == SandboxPhase.PATH_PROBE:
            response["path_selections"] = session.path_selections

        if session.current_phase in (SandboxPhase.PROJECTION, SandboxPhase.COMPLETED):
            response["path_reports"] = session.path_reports

        if session.projection_result:
            response["projection_result"] = session.projection_result

        if session.error_message:
            response["error"] = session.error_message

        # Always include full session state for client-side persistence
        response["state"] = session.to_dict()

        return response

    # ── Direct API Helpers ──────────────────────────────────────

    def list_available_paths(self) -> list[dict[str, str]]:
        """List all paths available for comparison in the sandbox."""
        return [
            {"type": k, "label": v} for k, v in SANDBOX_PATHS.items()
        ]

    def get_result(self, session: SandboxSession) -> dict[str, Any] | None:
        """Get the final projection result for a completed session.

        Args:
            session: A sandbox session (should be COMPLETED).

        Returns:
            Projection result dict or None.
        """
        if not session.finished:
            return None
        return session.projection_result
