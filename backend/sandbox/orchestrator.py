# -*- coding: utf-8 -*-
"""DecisionSandbox — orchestrator for the multi-path comparison system.

Phases:
    1. DISCOVERY      — Analyze known context + collect critical personal variables
    2. PATH_PROBE     — At most 1 path-specific clarification per selected path
    3. PARALLEL_SIM   — Inject context into planning agents, generate reports
    4. PROJECTION     — ProjectionAgent compares N reports

Integrates with:
    - PlanningRouter: to create and orchestrate domain-specific agents
    - MemoryService: to read/write user memories across sessions
    - ProjectionAgent: to generate the final comparison JSON
"""

from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
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
from planning.conversation import normalize_advisory_text
from planning.knowledge import get_knowledge_context
from utils.json_parser import safe_json_parse



def _safe_json(raw):
    """Try to parse JSON from LLM output, handling markdown fences."""
    import json, re
    if not raw:
        return None
    m = re.search(r'\{.*\}', raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except:
            pass
    return None


def _matrix_match_score(matrix: dict[str, Any], path_type: str) -> int:
    """Return a safe 0-100 fit score without assuming a fixed column index."""
    dimensions = matrix.get("dimensions", []) if isinstance(matrix, dict) else []
    scores = matrix.get("scores", {}) if isinstance(matrix, dict) else {}
    match_index = next(
        (
            index for index, dimension in enumerate(dimensions)
            if any(keyword in str(dimension) for keyword in ("匹配", "适配", "契合"))
        ),
        0 if dimensions else None,
    )
    values = scores.get(path_type, []) if isinstance(scores, dict) else []
    if match_index is None or not isinstance(values, list) or match_index >= len(values):
        return 0
    try:
        value = float(values[match_index])
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, round(value if value > 10 else value * 10)))


def _is_decision_pushback(message: str) -> bool:
    """Detect an explicit objection to the assistant handing the choice back."""
    normalized = re.sub(r"\s+", "", str(message or ""))
    return any(
        marker in normalized
        for marker in (
            "不知道才问你", "不清楚才问你", "就是不知道", "你帮我判断",
            "帮我选", "直接告诉我", "直接给建议", "给个方向", "先给结论",
            "到底选什么", "你觉得选什么", "别再问", "不要再问",
        )
    )


def _is_decision_request(message: str) -> bool:
    """Detect when the user wants a direction, not another preference prompt."""
    normalized = re.sub(r"\s+", "", str(message or ""))
    explicit = _is_decision_pushback(normalized)
    undecided_choice = any(marker in normalized for marker in ("不知道", "不清楚", "没想好")) and any(
        marker in normalized for marker in ("还是", "怎么选", "选哪个", "方向")
    )
    return explicit or undecided_choice


def _extract_visible_question(text: str) -> str:
    """Return the single question that is actually present in visible text."""
    normalized = str(text or "").replace("?", "？")
    matches = re.findall(r"[^。！；\n]*？", normalized)
    return matches[-1].strip() if matches else ""


def _without_question(text: str) -> str:
    normalized = str(text or "").replace("?", "？")
    index = normalized.find("？")
    if index < 0:
        return normalized.strip()
    sentence_start = max(
        normalized.rfind("。", 0, index),
        normalized.rfind("！", 0, index),
        normalized.rfind("；", 0, index),
    )
    return normalized[: sentence_start + 1].strip()


_KNOWLEDGE_TEST_MARKERS = (
    "你知道", "你了解", "了解过", "是否了解", "是否知道", "知不知道",
)

_LOCKED_PATH_CHOICE_MARKERS = (
    "更倾向", "更希望", "更愿意", "更看重", "选哪个", "哪条路径",
    "哪个方向", "直接就业还是读研", "读研还是就业", "适合读研",
)

_DISCOVERY_DIMENSION_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("target", ("目标", "方向", "岗位", "院校", "专业")),
    ("values", ("更看重", "薪资", "收入", "稳定", "成长", "兴趣", "价值")),
    ("ability", ("基础", "项目", "实习", "数学", "英语", "成绩", "能力", "技能")),
    ("constraints", ("时间", "家庭", "城市", "地域", "经济", "投入", "成本")),
)


def _question_key(text: str) -> str:
    """Build a small stable key for repeated-question checks."""
    return re.sub(r"[\s，。！？?、：:]+", "", str(text or "")).strip()


def _question_dimension(text: str) -> str:
    """Map a question to one coarse personal-information dimension."""
    normalized = _question_key(text)
    for dimension, keywords in _DISCOVERY_DIMENSION_KEYWORDS:
        if any(keyword in normalized for keyword in keywords):
            return dimension
    return ""


def _replace_visible_question(text: str, old_question: str, new_question: str) -> str:
    """Replace the one question shown to the user without touching the insight."""
    index = text.rfind(old_question)
    if index < 0:
        return text
    return f"{text[:index]}{new_question}"


def _has_personal_decision_signal(profile: dict[str, Any]) -> bool:
    """Require at least one personal variable beyond background/confusion."""
    keys = (
        "values", "personality", "learning_ability", "execution",
        "social_ability", "stress_tolerance", "family_expectation",
        "economic_situation", "location_preference", "interested_fields",
        "time_window",
    )
    return any(profile.get(key) not in (None, "", [], {}) for key in keys)

def _build_disco_sys(session, mem_ctx=""):
    """Build discovery system prompt with profile context."""
    import json
    from sandbox.prompts.discovery import DISCOVERY_SYSTEM_PROMPT
    prompt = DISCOVERY_SYSTEM_PROMPT
    if mem_ctx:
        prompt += "\n\n## 已知长期记忆\n" + mem_ctx
    if session.user_profile:
        filled = {k: v for k, v in session.user_profile.items() if v}
        if filled:
            prompt += "\n\n## 当前用户画像\n" + json.dumps(filled, ensure_ascii=False, indent=2) + "\n请避免重复询问已知信息。"
    return prompt


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
                self.memory.wait_for_pending(user_id, timeout=5.0)
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
                    session, "抱歉，出了点问题，请重试",
                    extra={"error": True},
                )

            # The memory service owns its DB session and serial worker. Never
            # pass this request-scoped session into a background thread.
            if self.memory:
                self._persist_memory(
                    session, db_session, message, result.get("message", ""),
                )

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


    async def chat_stream(self, session, message, db_session=None):
        """Primary SSE transport for sandbox turns.

        State transitions deliberately reuse :meth:`chat`.  The previous
        streaming implementation duplicated the state machine and drifted from
        the normal endpoint: it forgot selected paths, failed to record the
        first path-probe answer, and skipped persistence.  SSE remains the
        preferred client transport; the non-stream endpoint is only a network
        fallback in the mini-program.
        """
        import json as _json

        if not message.strip():
            yield ("done", _json.dumps({
                "phase": session.current_phase.value,
                "finished": False,
                "message": "请输入内容",
                "path_selections": session.path_selections,
                "path_selection_source": session.path_selection_source,
                "path_selection_locked": session.path_selection_locked,
                "state": session.to_dict(),
            }, ensure_ascii=False))
            return

        status = "analyzing" if session.current_phase in (
            SandboxPhase.PARALLEL_SIM, SandboxPhase.PROJECTION,
        ) else "thinking"
        yield ("status", _json.dumps({
            "phase": session.current_phase.value,
            "status": status,
        }, ensure_ascii=False))

        result = self.chat(session, message, db_session)
        visible = str(result.get("report_text") or result.get("message") or "")
        for index in range(0, len(visible), 30):
            yield ("token", visible[index:index + 30])
        yield ("done", _json.dumps(result, ensure_ascii=False, default=str))

    # ── Phase 1: Discovery ──────────────────────────────────────

    def _discovery_knowledge_context(
        self,
        session: SandboxSession,
        message: str,
    ) -> str:
        """Provide stable path facts to the discovery prompt.

        This is a conservative baseline until the external evidence tools are
        wired in.  It still prevents the discovery model from answering from
        prompt style alone.
        """
        paths = list(session.path_selections)
        for path in self._parse_path_selections(message):
            if path not in paths:
                paths.append(path)
        facts: list[str] = []
        for path in paths[:2]:
            evidence = get_knowledge_context(path, ["path_overview", "comparison"])
            text = str(evidence.get("text", "")).strip()
            if text:
                facts.append(f"{SANDBOX_PATHS.get(path, path)}：\n{text}")
        return "\n".join(facts)

    def _decision_first_fallback(
        self,
        session: SandboxSession,
        message: str,
        *,
        allow_question: bool,
    ) -> str:
        """Concrete, conditional fallback for explicit 'you tell me' turns."""
        paths = list(session.path_selections)
        for path in self._parse_path_selections(message):
            if path not in paths:
                paths.append(path)
        pair = frozenset(paths[:2])
        if pair == frozenset(("career", "graduate")):
            body = (
                "你说得对，这一轮应该先由我给方向。仅按现有信息，我更建议先把就业准备作为验证主线，"
                "同时保留考研窗口：项目和投递能较快检验岗位匹配，数学英语摸底能判断读研成本。"
            )
            question = "你目前项目实践和数学英语，哪一边基础更扎实？"
        elif pair == frozenset(("career", "civil")):
            body = (
                "你说得对，我先给初步方向。现阶段可以先用岗位资格和真实招聘要求做双向筛选："
                "若更重稳定与地域确定性，优先验证考公；若更看重岗位成长和选择面，先验证就业。"
            )
            question = "你目前更受地域限制，还是更在意岗位成长空间？"
        elif pair == frozenset(("major", "career")):
            body = (
                "你说得对，我先给初步方向。可以先验证目标岗位是否真的要求转专业；"
                "如果项目、辅修或实习也能建立能力证据，就业准备通常比直接转专业成本更低。"
            )
            question = "你想转入的方向，已经有明确目标岗位了吗？"
        else:
            body = (
                "你说得对，我先给初步方向。现阶段不必凭感觉定终局，可以先把验证成本更低、"
                "能更快获得真实反馈的路径作为主线，另一条保留窗口，再根据结果调整。"
            )
            question = "哪条路径能在两周内完成一次真实任务或摸底？"
        return normalize_advisory_text(body + (question if allow_question else ""), 160)

    def _safe_sandbox_personal_question(
        self,
        session: SandboxSession,
        path_type: str | None = None,
    ) -> str:
        """Return an answerable fallback when a model asks a knowledge-test question."""
        by_path = {
            "career": [
                ("target", "你更想先验证哪类目标岗位？"),
                ("ability", "你目前有哪些项目、实习或作品可以作为能力证据？"),
                ("constraints", "你对城市、收入或工作强度有什么现实限制？"),
            ],
            "graduate": [
                ("target", "你希望读研后进入哪类岗位或研究方向？"),
                ("ability", "数学、英语或专业课里，哪一项最需要补基础？"),
                ("constraints", "你能为读研投入多久的准备周期？"),
            ],
            "civil": [
                ("target", "你更关注哪个地区或哪类公职岗位？"),
                ("ability", "行测和申论中，哪一项目前更缺少练习？"),
                ("constraints", "你能接受多长的备考周期，并准备什么备选方案？"),
            ],
            "major": [
                ("target", "你希望转入哪个专业或对应方向？"),
                ("ability", "目标专业相关课程或技能里，你已有哪部分基础？"),
                ("constraints", "你能接受的补修或毕业时间成本大概是多少？"),
            ],
        }
        candidates = by_path.get(path_type or "", [])
        if not candidates:
            pair = frozenset(session.path_selections[:2])
            if pair == frozenset(("career", "graduate")):
                candidates = [
                    ("target", "你希望未来进入哪类岗位或方向？"),
                    ("ability", "项目实践和数学英语里，哪一边基础更扎实？"),
                    ("constraints", "你目前最受时间、家庭还是地域哪项限制？"),
                ]
            elif pair == frozenset(("career", "civil")):
                candidates = [
                    ("target", "你更关注哪类岗位或哪个地区？"),
                    ("ability", "你目前有哪些项目、实习或考试基础？"),
                    ("constraints", "你能接受多长的备考或求职周期？"),
                ]
            else:
                candidates = [
                    ("target", "你目前最想优先验证哪类方向？"),
                    ("ability", "你已有哪项基础或经历可以作为判断依据？"),
                    ("constraints", "你目前最受时间、家庭还是地域哪项限制？"),
                ]
        for dimension, question in candidates:
            if dimension not in session.unavailable_discovery_dimensions:
                return question
        return candidates[-1][1]

    def _sanitize_sandbox_question(
        self,
        session: SandboxSession,
        question: str,
        *,
        path_type: str | None = None,
        latest_answer: str = "",
    ) -> str:
        """Keep sandbox questions personal, singular, and non-repetitive."""
        candidate = str(question or "").strip().replace("?", "？")
        if candidate and not candidate.endswith("？"):
            candidate = candidate.rstrip("。！…") + "？"
        candidate_key = _question_key(candidate)
        candidate_dimension = _question_dimension(candidate)
        repeated_after_unknown = candidate_key in session.unavailable_discovery_questions
        dimension_was_skipped = (
            bool(candidate_dimension)
            and candidate_dimension in session.unavailable_discovery_dimensions
        )
        if (
            not candidate
            or any(marker in candidate for marker in _KNOWLEDGE_TEST_MARKERS)
            or (session.path_selection_locked and any(
                marker in candidate for marker in _LOCKED_PATH_CHOICE_MARKERS
            ))
            or repeated_after_unknown
            or dimension_was_skipped
        ):
            return self._safe_sandbox_personal_question(session, path_type)
        return candidate

    def _sanitize_sandbox_advisory(
        self,
        session: SandboxSession,
        text: str,
        *,
        path_type: str | None = None,
        latest_answer: str = "",
        max_chars: int = 160,
    ) -> str:
        """Replace an invalid displayed question while preserving its insight."""
        visible = normalize_advisory_text(text, max_chars)
        shown_question = _extract_visible_question(visible)
        if not shown_question:
            return visible
        safe_question = self._sanitize_sandbox_question(
            session,
            shown_question,
            path_type=path_type,
            latest_answer=latest_answer,
        )
        if safe_question != shown_question:
            visible = _replace_visible_question(visible, shown_question, safe_question)
        return normalize_advisory_text(visible, max_chars)

    def _compose_discovery_response(
        self,
        parsed: dict[str, Any] | None,
        raw: str,
        *,
        decision_request: bool,
        session: SandboxSession,
        message: str,
        allow_question: bool,
    ) -> tuple[str, str]:
        """Make the displayed reply and stored question share one source."""
        if parsed:
            response = str(parsed.get("response", "") or "").strip()
            proposed_question = str(parsed.get("next_question", "") or "").strip()
        else:
            response = str(raw or "").strip()
            proposed_question = ""

        if _is_decision_pushback(message) or (decision_request and not any(
            marker in response
            for marker in ("更建议", "建议先", "优先", "主线", "初步方向", "初步判断", "验证")
        )):
            response = self._decision_first_fallback(
                session, message, allow_question=allow_question,
            )
            return response, _extract_visible_question(response)

        visible = self._sanitize_sandbox_advisory(
            session,
            response or "我先基于现有信息帮你梳理。",
            latest_answer=message,
        )
        if not allow_question:
            visible = normalize_advisory_text(_without_question(visible), 150)
            return visible, ""

        actual_question = _extract_visible_question(visible)
        if not actual_question and proposed_question:
            proposed_question = self._sanitize_sandbox_question(
                session,
                proposed_question,
                latest_answer=message,
            )
            visible = self._sanitize_sandbox_advisory(
                session,
                f"{visible}{proposed_question}",
                latest_answer=message,
            )
            actual_question = _extract_visible_question(visible)
        return visible, actual_question

    @staticmethod
    def _merge_transition_response(analysis: str, transition: str) -> str:
        """Keep a transition to one short insight plus one visible question."""
        question = _extract_visible_question(transition)
        body = _without_question(analysis)
        if question:
            return normalize_advisory_text(f"{body}{question}", 160)
        return normalize_advisory_text(f"{body}{transition}", 160)

    def _handle_discovery(
        self,
        session: SandboxSession,
        message: str,
    ) -> dict[str, Any]:
        """Handle discovery phase: collect universal user profile.

        Uses LLM-driven dynamic questioning, NOT a fixed script.
        Reuses the _generate_dynamic_question pattern from PlanningAgent.
        """
        is_first = session.discovery_round == 0
        decision_request = _is_decision_request(message)
        will_reach_cap = session.discovery_round + 1 >= MAX_DISCOVERY_ROUNDS
        allow_discovery_question = not will_reach_cap and session.can_ask_more()

        # Remember paths already named by the user.  The old flow asked the
        # user to select "就业和考研" again even after they had said exactly
        # that, which made the interaction feel inattentive.
        inferred_paths = self._parse_path_selections(message)
        if not session.path_selection_locked and len(inferred_paths) >= 2:
            for path in inferred_paths:
                if path not in session.path_selections:
                    session.path_selections.append(path)

        # Build prompts
        system_prompt = build_discovery_system_prompt(
            known_profile=session.user_profile if session.user_profile else None,
            memory_context=self._format_memory(session),
            knowledge_context=self._discovery_knowledge_context(session, message),
        )

        history_text = session.build_discovery_context()
        user_prompt = build_discovery_user_prompt(
            history_text=history_text,
            latest_message=message,
            is_first_turn=is_first,
            decision_request=decision_request,
            allow_question=allow_discovery_question,
            paths_locked=session.path_selection_locked,
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
            if decision_request:
                fallback_q = self._decision_first_fallback(
                    session, message, allow_question=allow_discovery_question,
                )
            else:
                fallback_q = "可以先从路径门槛、时间成本和能力证据做初步比较。"
                if allow_discovery_question:
                    fallback_q += "你目前最想先解决哪一个现实顾虑？"
                fallback_q = normalize_advisory_text(fallback_q, 160)
            previous_question = session.last_discovery_question or "用户主动说明"
            if session.is_ambiguous(message):
                session.mark_discovery_unavailable(
                    _question_key(previous_question),
                    _question_dimension(previous_question),
                )
            session.record_discovery(
                previous_question,
                message,
                previous_response=session.last_discovery_response,
            )
            session.last_discovery_response = fallback_q
            session.last_discovery_question = _extract_visible_question(fallback_q)
            if session.last_discovery_question:
                session.mark_question_asked(session.last_discovery_question)
            if not session.should_continue_discovery():
                session.discovery_complete = True
                transition = self._transition_to_path_probe(session)
                transition["message"] = self._merge_transition_response(
                    fallback_q, transition.get("message", ""),
                )
                return transition
            return self._build_response(
                session, fallback_q,
                extra={"discovery_round": session.discovery_round},
            )

        # Parse LLM response
        parsed = safe_json_parse(raw)
        if parsed is None:
            logger.warning("Discovery: failed to parse LLM JSON, using raw text")

        previous_question = session.last_discovery_question or "用户主动说明"
        previous_response = session.last_discovery_response
        if session.is_ambiguous(message):
            session.mark_discovery_unavailable(
                _question_key(previous_question),
                _question_dimension(previous_question),
            )

        if parsed:
            # Update cumulative profile before evaluating whether discovery is
            # genuinely ready to finish.
            updated = parsed.get("updated_profile", {})
            if isinstance(updated, dict):
                for key, value in updated.items():
                    if value:
                        session.user_profile[key] = value
                        session._profile_dirty = True

        model_wants_finish = bool(parsed and parsed.get("finish", False))
        deterministic_finish = model_wants_finish and _has_personal_decision_signal(
            session.user_profile
        )
        will_transition = deterministic_finish or will_reach_cap
        visible_response, actual_question = self._compose_discovery_response(
            parsed,
            raw,
            decision_request=decision_request,
            session=session,
            message=message,
            allow_question=not will_transition and session.can_ask_more(),
        )
        session.record_discovery(
            previous_question,
            message,
            previous_response=previous_response,
        )
        session.last_discovery_response = visible_response
        session.last_discovery_question = actual_question
        if actual_question:
            session.mark_question_asked(actual_question)

        # Check if we should advance
        if deterministic_finish:
            logger.info("Discovery: readiness gate accepted model finish")
            session.discovery_complete = True
            # Transition to PATH_PROBE
            transition = self._transition_to_path_probe(session)
            transition["message"] = self._merge_transition_response(
                visible_response, transition.get("message", ""),
            )
            return transition
        if model_wants_finish:
            logger.info("Discovery: ignored premature model finish; personal signal missing")

        if not session.should_continue_discovery():
            logger.info("Discovery: max rounds reached, transitioning to path probe")
            session.discovery_complete = True
            transition = self._transition_to_path_probe(session)
            transition["message"] = self._merge_transition_response(
                visible_response, transition.get("message", ""),
            )
            return transition

        return self._build_response(
            session, visible_response,
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
            if not session.can_ask_more():
                session.path_probe_done.update(session.path_selections)
                return self._advance_to_parallel_sim(session)
            first_path = session.path_selections[0]
            question = self._generate_path_probe_question(session, first_path)
            session.path_probe_pending_questions[first_path] = question
            session.mark_question_asked(question)
            return self._build_response(
                session, question,
                extra={"phase": "path_probe", "current_path": first_path},
            )
        if not session.can_ask_more():
            # No personal question budget remains.  Compare every supported
            # route conditionally instead of forcing a sixth answer.
            session.path_selections = list(SANDBOX_PATHS)
            session.path_probe_done.update(session.path_selections)
            return self._advance_to_parallel_sim(session)
        # Ask which paths to compare
        path_list = SANDBOX_PATH_LIST_STR
        question = (
            f"我先根据已有信息做路径对比。\n\n"
            f"目前可分析：{path_list}。\n"
            f"你想对比哪些方向？（可以说多个，比如\"就业和考研\"）"
        )
        session.mark_question_asked(question)
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
                if not session.can_ask_more():
                    session.path_selections = list(SANDBOX_PATHS)
                    session.path_probe_done.update(session.path_selections)
                    return self._advance_to_parallel_sim(session)
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
                session.mark_question_asked(resp["message"])
                return resp
            session.path_selections = selections
            logger.info("Sandbox[{}]: selected paths: {}", session.session_id, selections)

            # Initialize path_probe_history for each selection
            for pt in selections:
                session.path_probe_history.setdefault(pt, [])

            # Generate first path's probe question immediately
            if not session.can_ask_more():
                session.path_probe_done.update(selections)
                return self._advance_to_parallel_sim(session)
            first_path = selections[0]
            question = self._generate_path_probe_question(session, first_path)
            session.path_probe_pending_questions[first_path] = question
            session.mark_question_asked(question)
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
        pending_question = session.path_probe_pending_questions.pop(current_path, "")
        session.record_path_probe(current_path, pending_question, message)

        if not session.can_ask_more():
            session.path_probe_done.update(session.path_selections)
            return self._advance_to_parallel_sim(session)

        # Check if we need more questions for this path
        rounds = session.path_probe_rounds(current_path)
        if rounds < MAX_PATH_PROBE_ROUNDS:
            question = self._generate_path_probe_question(session, current_path)
            # Avoid generating redundant questions if LLM fails
            if not question:
                logger.warning("Path probe: empty question for {}, skipping", current_path)
                session.path_probe_done.add(current_path)
                return self._maybe_advance_from_probe(session)
            session.path_probe_pending_questions[current_path] = question
            session.mark_question_asked(question)
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
            if not session.can_ask_more():
                session.path_probe_done.update(session.path_selections)
                return self._advance_to_parallel_sim(session)
            question = self._generate_path_probe_question(session, next_path)
            session.path_probe_pending_questions[next_path] = question
            session.mark_question_asked(question)
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
        latest_answer = str(current_answers[-1].get("a", "")) if current_answers else ""

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
                insight = str(parsed.get("insight", "")).strip()
                question = str(questions[0]).strip() if questions else ""
                if insight and question:
                    return self._sanitize_sandbox_advisory(
                        session,
                        f"{insight}{question}",
                        path_type=path_type,
                        latest_answer=latest_answer,
                        max_chars=140,
                    )
                if insight or question:
                    return self._sanitize_sandbox_advisory(
                        session,
                        insight or question,
                        path_type=path_type,
                        latest_answer=latest_answer,
                        max_chars=140,
                    )
            return self._sanitize_sandbox_advisory(
                session,
                raw or "关于这条路，你还有什么想补充的吗？",
                path_type=path_type,
                latest_answer=latest_answer,
                max_chars=140,
            )
        except Exception as exc:
            logger.warning("Path probe question generation failed: {}", exc)
            label = SANDBOX_PATHS.get(path_type, path_type)
            return self._sanitize_sandbox_advisory(
                session,
                f"关于{label}这条路，你最大的顾虑是什么？",
                path_type=path_type,
                latest_answer=latest_answer,
                max_chars=140,
            )

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
        message_text = str(message or "")
        normalized = message_text.lower()

        for path_type, words in PATH_KEYWORDS.items():
            if path_type in normalized or any(w in message_text for w in words):
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

        All agents now run in parallel via ThreadPoolExecutor.
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
        session_id = session.session_id

        def run_one(path_type):
            try:
                report = self._run_single_agent_simulation(path_type, context, session)
                if report:
                    logger.info("Sandbox[{}]: {} report generated", session_id, path_type)
                    return (path_type, report)
                else:
                    logger.warning("Sandbox[{}]: {} simulation returned empty report", session_id, path_type)
                    return (path_type, self._build_fallback_report(path_type))
            except Exception as exc:
                logger.exception("Sandbox[{}]: {} simulation failed: {}", session_id, path_type, exc)
                return (path_type, self._build_fallback_report(path_type))

        with ThreadPoolExecutor(max_workers=len(session.path_selections)) as executor:
            futures = {executor.submit(run_one, pt): pt for pt in session.path_selections}
            for future in as_completed(futures):
                pt, report = future.result()
                reports[pt] = report

        # Workers finish in nondeterministic order; preserve the user's path
        # selection order for projection cards, scores, and downstream UI.
        reports = {
            path_type: reports[path_type]
            for path_type in session.path_selections
            if path_type in reports
        }

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
                request_timeout=18.0,
                max_retries=0,
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
            match_score = _matrix_match_score(matrix, pt)
            match_pct = f"{match_score}%" if match_score else ""

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
            match_score = _matrix_match_score(matrix, pt)
            if match_score > high_score:
                high_score = match_score

        for proj in projections:
            pt = proj.get("path_type", "")
            label = SANDBOX_PATHS.get(pt, pt)
            insight = proj.get("core_insight", "")
            time_proj = proj.get("time_projection", {})
            challenges = proj.get("challenges", [])

            match_score = _matrix_match_score(matrix, pt)

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
        user_message: str = "",
        assistant_message: str = "",
    ) -> None:
        """Write accumulated user profile data to the Memory DB.

        Context is saved after every turn; canonical upsert makes unchanged
        profile fields idempotent.
        """
        if not self.memory:
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
                    "memory_type": "profile",
                    "importance": 2,
                    "confidence": 0.9,
                })

        # Also save path preferences
        if session.path_selections:
            path_labels = [SANDBOX_PATHS.get(p, p) for p in session.path_selections]
            items.append({
                "key": "关注路径",
                "value": "、".join(path_labels),
                "memory_type": "goal",
                "importance": 3,
                "confidence": 0.95,
            })

        if db_session is None:
            logger.warning("Sandbox: skipped context persistence without a DB session")
            return
        try:
            self.memory.persist_sandbox_state(
                db_session,
                user_id=session.user_id,
                session_id=session.session_id,
                session_state=copy.deepcopy(session.to_dict()),
                profile_items=items,
            )
            if user_message.strip() and user_message.strip() not in {"开始", "继续"}:
                self.memory.extract_from_turn_async(
                    user_id=session.user_id,
                    user_message=user_message,
                    assistant_message=assistant_message,
                    source_context=f"sandbox_turn:{session.session_id}",
                )
            session._profile_dirty = False
            logger.info(
                "Sandbox: persisted context and {} categorized memories for user {}",
                len(items), session.user_id,
            )
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
            "major": "major",
            "专业": "major",
            "grade": "grade",
            "年级": "grade",
            "goal": "goal",
            "目标": "goal",
            "school": "school",
            "学校": "school",
            "college": "college",
            "学院": "college",
            "enroll_year": "enroll_year",
            "入学年份": "enroll_year",
            "career_direction": "career_direction",
            "职业": "career_direction",
            "core_confusion": "core_confusion",
            "当前困惑": "core_confusion",
            "personality": "personality",
            "性格": "personality",
            "learning_ability": "learning_ability",
            "学习能力": "learning_ability",
            "execution": "execution",
            "执行力": "execution",
            "location_preference": "location_preference",
            "地域": "location_preference",
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
            "path_selections": session.path_selections,
            "path_selection_source": session.path_selection_source,
            "path_selection_locked": session.path_selection_locked,
        }

        if extra:
            response.update(extra)

        # Include relevant session metadata
        if session.current_phase == SandboxPhase.DISCOVERY:
            response["discovery_round"] = session.discovery_round
            response["max_discovery_rounds"] = MAX_DISCOVERY_ROUNDS

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
