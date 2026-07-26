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

        # Also load user registration info (nickname, major, grade)
        if db_session:
            try:
                from crud.user import user as user_crud
                user = user_crud.get(db_session, id=user_id)
                if user:
                    if user.nickname and "nickname" not in session.user_profile:
                        session.user_profile["nickname"] = user.nickname
                    if user.major and "major" not in session.user_profile:
                        session.user_profile["major"] = user.major
                    if user.grade and "grade" not in session.user_profile:
                        session.user_profile["grade"] = user.grade
                    logger.info("Sandbox: loaded user registration info for {}", user_id)
            except Exception as exc:
                logger.warning("Sandbox: failed to load user info: {}", exc)

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
            elif session.current_phase == SandboxPhase.COMPLETED:
                result = self._build_response(
                    session, "",
                    extra={"finished": True, "projection_result": session.projection_result},
                )
            else:
                result = self._build_response(
                    session, "?????????????",
                    extra={"error": True},
                )

            # Persist memory after each interaction
            if self.memory and db_session:
                self._persist_memory(session, db_session)

            # Fire async LLM-based memory extraction from this turn
            if message.strip():
                try:
                    from services.memory_service import memory_service
                    memory_service.extract_from_turn_async(
                        user_id=session.user_id,
                        user_message=message,
                        assistant_message=result.get("message", ""),
                    )
                except Exception:
                    pass  # Non-blocking

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
                # Re-show path selection cards
                path_cards = []
                icons = {"career": "/images/icon-job.png", "graduate": "/images/icon-postgrad.png", "civil": "/images/icon-civil.png", "major": "/images/icon-transfer.png"}
                colors = {"career": "#4A90D9", "graduate": "#7B68EE", "civil": "#E8913A", "major": "#50C878"}
                bg_colors = {"career": "#EBF3FB", "graduate": "#F0EDFC", "civil": "#FDF3E8", "major": "#E8F8EF"}
                time_labels = {"career": "3-6个月准备", "graduate": "6-12个月备考", "civil": "6-12个月备考", "major": "1-2个学期"}
                risk_labels = {"career": "竞争激烈", "graduate": "录取率不确定", "civil": "上岸难度大", "major": "学分转换风险"}
                for pt, label in SANDBOX_PATHS.items():
                    path_cards.append({
                        "type": pt, "name": label, "icon": icons.get(pt, "default"),
                        "color": colors.get(pt, "#333"), "bgColor": bg_colors.get(pt, "#F5F5F5"),
                        "match_score": 0, "insight": f"探索{label}方向的可能性",
                        "time_label": time_labels.get(pt, ""), "risk_label": risk_labels.get(pt, ""),
                        "recommended": False,
                    })
                resp = self._build_response(
                    session, "请点击上方卡片选择你想对比的方向（可多选），然后说【开始比对】。",
                    extra={"selecting_paths": True},
                )
                resp["show_cards"] = True
                resp["cards"] = path_cards
                resp["report_text"] = "请选择对比方向"
                return resp
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
        """Run comparison analysis for one path via direct LLM call.

        Strategy:
            - Use a comparison-only prompt (NOT PlanningAgent workflow)
            - Only produce fit/risk/projection, no action plans

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

        # Build comparison-only analysis via LLM (NOT full planning agent workflow).
        # The sandbox only needs: strengths, challenges, fit, projection, risks.
        # Action plans and daily tasks belong to the planning agent after handoff.
        comparison_prompt = f"""你是一位{SANDBOX_PATHS.get(path_type, path_type)}领域的专业顾问。请基于以下用户信息，生成一份**对比分析摘要**（不是完整的成长规划）。

## 用户信息
{context}

## 输出要求
请以JSON格式输出，只包含以下字段，不要生成行动计划或学习路线：

{{
  "strengths": [
    {{"point": "该路径对用户的优势", "detail": "具体说明"}}
  ],
  "challenges": [
    {{"point": "该路径对用户的挑战", "detail": "具体说明", "level": "high|medium|low"}}
  ],
  "best_for": "这条路径最适合什么样的人",
  "deal_breakers": "什么样的人应该避开这条路径",
  "time_projection": {{
    "short_term": "选择这条路3个月后的可能状态（1-2句话）",
    "mid_term": "1年后的可能状态",
    "long_term": "2-3年后的可能状态"
  }},
  "key_requirements": ["成功走这条路需要具备的条件1", "条件2"],
  "risk_summary": "一句话概括最大的风险"
}}

## 规则
- 不要生成行动计划、每日任务、学习路线——这些由后续的深度规划Agent负责
- 聚焦在「这条路适不适合这个用户」的判断依据
- 信息不足的维度可以合理推测，但标注为推测"""

        try:
            raw = self.llm.chat(
                user_message=comparison_prompt,
                temperature=0.7,
                max_tokens=2048,
            )
            report = safe_json_parse(raw)
            if report and isinstance(report, dict):
                report["path_type"] = path_type
                report["path_label"] = SANDBOX_PATHS.get(path_type, path_type)
                return report
        except Exception as exc:
            logger.error("Sandbox: comparison analysis failed for {}: {}", path_type, exc)

        # Fallback
        return self._build_fallback_report(path_type)

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

        # Build rich report and card data
        report_text = self._format_rich_report(result, session)
        cards = self._build_card_data(result, session)

        return self._build_response(
            session,
            report_text,
            extra={
                "finished": True,
                "projection_result": result,
                "show_cards": True,
                "cards": cards,
                "report_text": report_text,
            },
        )


    def _format_rich_report(
        self,
        projection: dict,
        session: "SandboxSession",
    ) -> str:
        """Build a rich, human-readable comparison report from projection data."""
        from sandbox.state import SANDBOX_PATHS

        projections = projection.get("projections", [])
        summary = projection.get("summary", "")
        decision_guide = projection.get("decision_guide", {})
        questions = decision_guide.get("questions_to_ask_yourself", [])
        if_then = decision_guide.get("if_you_value_X_then_Y", [])
        matrix = projection.get("comparison_matrix", {})

        lines_out = []

        # Header
        lines_out.append("========================================\n")
        lines_out.append("      MULTI-PATH COMPARISON REPORT       \n")
        lines_out.append("========================================\n")
        lines_out.append("\n")

        # Summary
        if summary:
            lines_out.append("--- OVERVIEW ---\n")
            lines_out.append(summary + "\n\n")

        # Per-path detail
        path_labels = SANDBOX_PATHS
        scores = matrix.get("scores", {})
        match_idx = 5  # match degree in comparison_matrix dimensions

        for idx, proj in enumerate(projections):
            pt = proj.get("path_type", "")
            label = path_labels.get(pt, pt)
            insight = proj.get("core_insight", "")
            time_proj = proj.get("time_projection", {})
            strengths = proj.get("strengths", [])
            challenges = proj.get("challenges", [])
            best_for = proj.get("best_for", "")
            deal_breakers = proj.get("deal_breakers", "")

            # Match score
            match_pct = ""
            if pt in scores:
                score_list = scores[pt]
                if isinstance(score_list, list) and len(score_list) > match_idx:
                    match_pct = str(int(score_list[match_idx] * 10)) + "%"

            # Divider
            if idx > 0:
                lines_out.append("----------------------------------------\n\n")

            # Title
            title = ">>> " + label
            if match_pct:
                title += " (Match: " + match_pct + ")"
            lines_out.append(title + "\n")
            lines_out.append("\n")

            # Core insight
            if insight:
                lines_out.append(insight + "\n\n")

            # Time projection
            if time_proj:
                short = time_proj.get("short_term", "")
                mid_term = time_proj.get("mid_term", "")
                long_term = time_proj.get("long_term", "")
                milestones = time_proj.get("key_milestones", [])
                lines_out.append("Timeline:\n")
                if short:
                    lines_out.append("  Short (3mo):  " + short + "\n")
                if mid_term:
                    lines_out.append("  Mid  (1yr):   " + mid_term + "\n")
                if long_term:
                    lines_out.append("  Long (2-3yr): " + long_term + "\n")
                if milestones:
                    lines_out.append("  Milestones: " + ", ".join(milestones) + "\n")
                lines_out.append("\n")

            # Strengths
            if strengths:
                lines_out.append("Your Strengths:\n")
                for s in strengths[:3]:
                    factor = s.get("factor", "") if isinstance(s, dict) else str(s)
                    detail = s.get("detail", "") if isinstance(s, dict) else ""
                    if detail:
                        lines_out.append("  + " + factor + ": " + detail + "\n")
                    else:
                        lines_out.append("  + " + factor + "\n")
                lines_out.append("\n")

            # Challenges
            if challenges:
                lines_out.append("Challenges:\n")
                for c in challenges[:3]:
                    factor = c.get("factor", "") if isinstance(c, dict) else str(c)
                    severity = c.get("severity", "") if isinstance(c, dict) else ""
                    detail = c.get("detail", "") if isinstance(c, dict) else ""
                    sev_tag = " [" + severity.upper() + "]" if severity else ""
                    line = "  - " + factor + sev_tag
                    if detail:
                        line += ": " + detail
                    lines_out.append(line + "\n")
                lines_out.append("\n")

            # Best for / Deal breakers
            if best_for:
                lines_out.append("Best For: " + best_for + "\n")
            if deal_breakers:
                lines_out.append("Think Twice If: " + deal_breakers + "\n")
            lines_out.append("\n")

        # Decision guide
        lines_out.append("========================================\n")
        lines_out.append("           DECISION GUIDE               \n")
        lines_out.append("========================================\n\n")

        if if_then:
            lines_out.append("Conditional Recommendations:\n")
            for item in if_then[:5]:
                cond = item.get("condition", "") if isinstance(item, dict) else ""
                rec = item.get("recommendation", "") if isinstance(item, dict) else str(item)
                reason = item.get("reason", "") if isinstance(item, dict) else ""
                lines_out.append("  * If you value [" + cond + "]: " + rec + "\n")
                if reason:
                    lines_out.append("    (" + reason + ")\n")
            lines_out.append("\n")

        if questions:
            lines_out.append("Questions to Reflect On:\n")
            for i, q in enumerate(questions[:5], 1):
                lines_out.append("  " + str(i) + ". " + q + "\n")
            lines_out.append("\n")

        lines_out.append("----------------------------------------\n")
        lines_out.append("Which direction would you like to explore in depth?\n")
        lines_out.append("Tap one of the cards below to start your personalized planning journey.\n")
        lines_out.append("\n")

        return "".join(lines_out)

    def _build_card_data(
        self,
        projection: dict,
        session: "SandboxSession",
    ) -> list:
        """Build structured card data for inline UI rendering from projection result."""
        from sandbox.state import SANDBOX_PATHS

        projections = projection.get("projections", [])
        matrix = projection.get("comparison_matrix", {})
        scores = matrix.get("scores", {})

        card_icons = {
            "career": "/images/icon-job.png", "graduate": "/images/icon-postgrad.png",
            "civil": "/images/icon-civil.png", "major": "/images/icon-transfer.png",
        }
        card_colors = {
            "career": "#52C41A", "graduate": "#4A90D9",
            "civil": "#FA8C16", "major": "#722ED1",
        }
        card_bgs = {
            "career": "#E6F9ED", "graduate": "#E6F2FF",
            "civil": "#FFF3E6", "major": "#F0E6FF",
        }

        cards = []
        high_score = -1
        for proj in projections:
            pt = proj.get("path_type", "")
            score_list = scores.get(pt, [])
            match_score = 0
            if isinstance(score_list, list) and len(score_list) > 5:
                match_score = int(score_list[5] * 10)
            if match_score > high_score:
                high_score = match_score

        for proj in projections:
            pt = proj.get("path_type", "")
            label = SANDBOX_PATHS.get(pt, pt)
            insight = proj.get("core_insight", "")
            time_proj = proj.get("time_projection", {})
            challenges = proj.get("challenges", [])

            score_list = scores.get(pt, [])
            match_score = 0
            if isinstance(score_list, list) and len(score_list) > 5:
                match_score = int(score_list[5] * 10)

            time_label = time_proj.get("short_term", "") if time_proj else ""
            risk_label = ""
            if challenges and isinstance(challenges, list) and len(challenges) > 0:
                c = challenges[0]
                risk_label = c.get("factor", "") if isinstance(c, dict) else str(c)

            cards.append({
                "type": pt,
                "name": label,
                "icon": card_icons.get(pt, "/images/icon-postgrad.png"),
                "color": card_colors.get(pt, "#4A90D9"),
                "bgColor": card_bgs.get(pt, "#E6F2FF"),
                "match_score": match_score,
                "recommended": (match_score == high_score and high_score > 0),
                "insight": insight[:80] if insight else "",
                "time_label": time_label[:50] if time_label else "See full report",
                "risk_label": risk_label[:30] if risk_label else "See full report",
            })

        # Sort: recommended first, then by score desc
        cards.sort(key=lambda c: (not c["recommended"], -c["match_score"]))
        return cards
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

        # ── Also fire async LLM extraction from conversation ─────
        # The orchestrator.chat() passes the user message through
        # but _persist_memory doesn't receive it directly.
        # We extract the last user message from session.discovery_history
        # or from the most recent interaction.
        last_user_msg = ""
        if session.discovery_history:
            last_user_msg = session.discovery_history[-1].get("user", "")
        if not last_user_msg and session.path_probe_history:
            for msgs in session.path_probe_history.values():
                if msgs:
                    last_user_msg = msgs[-1].get("user", "")
                    if last_user_msg:
                        break
        if last_user_msg:
            try:
                from services.memory_service import memory_service
                memory_service.extract_from_turn_async(
                    user_id=session.user_id,
                    user_message=last_user_msg,
                )
            except Exception:
                pass  # Non-blocking

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


    # ── Handoff to Planning Agent ──────────────────────────────

    def handoff_to_agent(
        self,
        session_id: str,
        path_type: str,
    ) -> dict[str, Any]:
        """Hand off sandbox context to a planning agent for deep planning.

        After the user sees the sandbox comparison and picks a direction,
        this method packages all discovery context and hands it to the
        corresponding planning agent for full follow-up and plan generation.

        Args:
            session_id: The sandbox session ID.
            path_type: The chosen path type (e.g. "career", "graduate").

        Returns:
            Dict with agent_type, initial_question, and handoff_context.
        """
        session = self._sessions.get(session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")

        if path_type not in SANDBOX_PATHS:
            raise ValueError(f"Unknown path type: {path_type}. Valid: {list(SANDBOX_PATHS.keys())}")

        # Build handoff context from sandbox discovery + path probe
        handoff_context: dict[str, Any] = {
            "source": "sandbox",
            "sandbox_session_id": session_id,
            "chosen_path": path_type,
            "chosen_path_label": SANDBOX_PATHS[path_type],
        }

        # Include user profile from discovery
        if session.user_profile:
            handoff_context["discovery_profile"] = dict(session.user_profile)

        # Include discovery conversation history
        if session.discovery_history:
            handoff_context["discovery_qa"] = session.discovery_history

        # Include path-specific probe answers
        probe = session.path_probe_history.get(path_type, [])
        if probe:
            handoff_context["path_probe_qa"] = probe

        # Include sandbox comparison result if available
        if session.path_reports and path_type in session.path_reports:
            handoff_context["sandbox_comparison"] = session.path_reports[path_type]

        # Get the planning agent to generate the first contextual question
        try:
            agent = self.router.get_agent(path_type)
            # Build user profile from discovery data
            user_profile = dict(session.user_profile) if session.user_profile else {}
            agent.init_state(user_profile=user_profile)

            # Generate the first follow-up question using the agent engine
            from planning.state import WorkflowStep
            first_result = agent.chat("")
            first_question = first_result.get("message", "")
            agent_state = first_result.get("state", {})
        except Exception as exc:
            logger.warning("Sandbox handoff: agent init failed: {}", exc)
            first_question = f"基于之前的分析，让我们深入规划你的{SANDBOX_PATHS.get(path_type, path_type)}方向。能先跟我说说你的具体情况吗？"
            agent_state = {}

        logger.info(
            "Sandbox[{}]: handed off to {} agent",
            session_id, path_type,
        )

        AGENT_GREETINGS = {
            "career": "准备好开始规划你的职业道路了吗？",
            "graduate": "准备好一起制定你的考研计划了吗？",
            "civil": "准备好规划你的考公之路了吗？",
            "major": "准备好探索新的专业方向了吗？",
        }
        greeting = AGENT_GREETINGS.get(path_type, "准备好开始规划了吗？")

        return {
            "agent_type": path_type,
            "agent_label": SANDBOX_PATHS.get(path_type, path_type),
            "greeting": greeting,
            "initial_question": first_question,
            "handoff_context": handoff_context,
            "agent_state": agent_state,
        }

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
