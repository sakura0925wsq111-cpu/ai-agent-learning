# -*- coding: utf-8 -*-
"""PlanningAgent — extensible base class for all growth planning agents.

Design principle: All agents share the same 8-step workflow engine.
Each agent only swaps three things:
    1. System Prompt     — role definition + analysis rules + output format
    2. Analysis Strategy — what dimensions to focus on
    3. Output Template   — unified JSON structure (same schema, domain-specific content)

To add a new agent (e.g., "留学规划Agent"):
    1. Create prompts/study_abroad.py with STUDY_ABROAD_SYSTEM_PROMPT
    2. Create agents/study_abroad.py inheriting PlanningAgent
    3. Override agent_type, agent_label, build_system_prompt()
    4. Register in router.py
    5. Add route in api/planning.py
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from loguru import logger

from planning.state import (
    PlanningState,
    WorkflowStep,
    WORKFLOW_ORDER,
    MAX_FOLLOW_UP_ROUNDS,
    MAX_RETRIES_PER_QUESTION,
)


# ── Unified Output JSON Schema ──────────────────────────────────
# Every agent MUST produce this exact structure.
# Content varies by agent domain, but the shape is invariant.

UNIFIED_OUTPUT_SCHEMA: dict[str, Any] = {
    "summary": "",
    "current_status": "",
    "main_problem": "",
    "goal": "",
    "advantages": [],
    "risks": [],
    "action_plan": [],
    "next_question": "",
}


class PlanningAgent(ABC):
    """Extensible base for all CampusPal growth planning agents.

    Orchestrates the 8-step workflow:
        READ_PROFILE -> READ_DIAGNOSIS -> FOLLOW_UP (3-7 rounds)
        -> ANALYZE -> IDENTIFY_PROBLEMS -> SET_GOALS
        -> BUILD_PLAN -> GENERATE_OUTPUT

    Subclasses only need to provide:
        - agent_type, agent_label
        - build_system_prompt()
        - build_analysis_strategy()
    """

    def __init__(self, llm_service: Any) -> None:
        self.llm = llm_service
        self.state: PlanningState

    # ── Abstract: subclasses MUST implement ─────────────────────

    @property
    @abstractmethod
    def agent_type(self) -> str:
        """Unique agent identifier, e.g. 'career', 'graduate'."""

    @property
    @abstractmethod
    def agent_label(self) -> str:
        """Human-readable label in Chinese, e.g. '就业规划'."""

    @abstractmethod
    def build_system_prompt(self) -> str:
        """Return the full system prompt for this agent.

        Must include:
            - Role definition
            - Analysis rules
            - The UNIFIED_OUTPUT_SCHEMA as output format instruction
        """

    @abstractmethod
    def build_analysis_strategy(self) -> dict[str, Any]:
        """Return the analysis strategy config for this agent.

        Example for career agent:
            {
                "focus_dimensions": ["岗位定位", "职业方向", "能力缺口"],
                "special_rules": ["不要推荐具体招聘网站"],
                "question_topics": ["专业背景", "求职动机", "工作偏好", ...],
            }
        """

    # ── Workflow Engine ─────────────────────────────────────────

    def init_state(self, user_profile: dict[str, Any] | None = None,
                   diagnosis: dict[str, Any] | None = None) -> PlanningState:
        """Initialize a fresh planning state, optionally with pre-loaded profile/diagnosis."""
        self.state = PlanningState(agent_type=self.agent_type)

        if user_profile:
            self.state.user_profile = user_profile
            self.state.has_profile = True
            logger.info("PlanningAgent[{}]: profile loaded", self.agent_type)

        if diagnosis:
            self.state.diagnosis = diagnosis
            self.state.has_diagnosis = True
            logger.info("PlanningAgent[{}]: diagnosis loaded", self.agent_type)

        # Start at the appropriate step
        if self.state.has_profile:
            self.state.advance_step()  # skip READ_PROFILE
        if self.state.has_diagnosis:
            self.state.advance_step()  # skip READ_DIAGNOSIS

        return self.state

    def restore_state(self, saved: PlanningState) -> None:
        """Restore agent from a previously saved state."""
        self.state = saved

    def chat(self, message: str) -> dict[str, Any]:
        """Main entry: process one user message and advance the workflow.

        Returns a dict the service layer can serialize into API responses.
        """
        if self.state.finished:
            return self._build_response(
                step="completed",
                finished=True,
                message="本次规划已完成。可以查看报告或开始新的规划。",
                report=self.state.output,
            )

        step = self.state.current_step
        logger.debug("PlanningAgent[{}] step={} round={}",
                     self.agent_type, step.value, self.state.follow_up_round)

        handlers = {
            WorkflowStep.READ_PROFILE: self._handle_read_profile,
            WorkflowStep.READ_DIAGNOSIS: self._handle_read_diagnosis,
            WorkflowStep.FOLLOW_UP: self._handle_follow_up,
            WorkflowStep.ANALYZE: self._handle_analyze,
            WorkflowStep.IDENTIFY_PROBLEMS: self._handle_identify_problems,
            WorkflowStep.SET_GOALS: self._handle_set_goals,
            WorkflowStep.BUILD_PLAN: self._handle_build_plan,
            WorkflowStep.GENERATE_OUTPUT: self._handle_generate_output,
        }

        handler = handlers.get(step)
        if handler is None:
            return self._build_error("Unknown workflow step")

        return handler(message)

    # ── Step Handlers ───────────────────────────────────────────

    def _handle_read_profile(self, message: str) -> dict[str, Any]:
        """Step 1: Read user profile.

        If the message contains structured profile data (JSON or key-value),
        parse it. Otherwise, ask the user to provide basic info.
        """
        # Try to parse structured profile from message
        profile = self._try_parse_profile(message)
        if profile:
            self.state.user_profile = profile
            self.state.has_profile = True
            self.state.advance_step()
            logger.info("PlanningAgent[{}]: profile parsed from message", self.agent_type)
            # Proceed to next step
            return self._continue_workflow("")
        else:
            # Ask for profile info
            self.state.has_profile = True  # mark as handled even if empty
            self.state.user_profile = {"raw_input": message}
            self.state.advance_step()
            return self._continue_workflow("")

    def _handle_read_diagnosis(self, message: str) -> dict[str, Any]:
        """Step 2: Read growth diagnosis results if available."""
        diagnosis = self._try_parse_diagnosis(message)
        if diagnosis:
            self.state.diagnosis = diagnosis
            self.state.has_diagnosis = True

        self.state.advance_step()
        return self._continue_workflow("")

    def _handle_follow_up(self, message: str) -> dict[str, Any]:
        """Step 3: Dynamic follow-up questions (3-7 rounds).

        Key behaviors:
        - Questions are generated dynamically by the LLM based on previous answers
        - NOT a fixed script of questions
        - Stop when enough info is gathered (min 3, max 7)
        - Detect ambiguous answers and probe deeper
        """
        is_ambiguous = self.state.is_ambiguous(message)

        # Record this round's answer
        current_q_id = f"follow_up_{self.state.follow_up_round + 1}"
        self.state.record_follow_up(current_q_id, message)

        if is_ambiguous:
            self.state.ambiguous_count += 1
            if self.state.retry_count < MAX_RETRIES_PER_QUESTION:
                self.state.retry_count += 1
                next_q = self._generate_dynamic_question(
                    is_retry=True,
                    last_answer=message,
                )
                return self._build_response(
                    step="follow_up",
                    finished=False,
                    message=next_q,
                    follow_up_round=self.state.follow_up_round,
                )
            # Max retries exceeded, accept ambiguous answer
            self.state.retry_count = 0
        else:
            self.state.retry_count = 0

        # Check if we should continue or stop
        if self.state.should_continue_follow_up():
            next_q = self._generate_dynamic_question(
                is_retry=False,
                last_answer=message,
            )
            return self._build_response(
                step="follow_up",
                finished=False,
                message=next_q,
                follow_up_round=self.state.follow_up_round,
            )

        # Follow-up complete -> advance to analysis
        self.state.follow_up_complete = True
        self.state.advance_step()
        logger.info("PlanningAgent[{}]: follow-up complete after {} rounds",
                    self.agent_type, self.state.follow_up_round)

        # Chain into analysis immediately
        return self._continue_workflow(message)

    def _handle_analyze(self, message: str) -> dict[str, Any]:
        """Steps 4-8: Run LLM analysis and generate full output in one pass.

        Combines analyze, identify problems, set goals, build plan, and
        generate output into a single LLM call for efficiency.
        """
        report = self._run_full_analysis()
        self.state.output = report
        self.state.finished = True

        return self._build_response(
            step="completed",
            finished=True,
            message=self._get_completion_message(),
            report=report,
        )

    def _handle_identify_problems(self, message: str) -> dict[str, Any]:
        """Step 5: Merged into _handle_analyze for efficiency."""
        return self._handle_analyze(message)

    def _handle_set_goals(self, message: str) -> dict[str, Any]:
        """Step 6: Merged into _handle_analyze for efficiency."""
        return self._handle_analyze(message)

    def _handle_build_plan(self, message: str) -> dict[str, Any]:
        """Step 7: Merged into _handle_analyze for efficiency."""
        return self._handle_analyze(message)

    def _handle_generate_output(self, message: str) -> dict[str, Any]:
        """Step 8: Merged into _handle_analyze for efficiency."""
        return self._handle_analyze(message)

    # ── LLM Integration ─────────────────────────────────────────

    def _run_full_analysis(self) -> dict[str, Any]:
        """Send all collected context to the LLM and parse the unified JSON output.

        Returns:
            Dict matching UNIFIED_OUTPUT_SCHEMA.
        """
        system_prompt = self.build_system_prompt()
        user_prompt = self._build_analysis_user_prompt()

        try:
            raw = self.llm.chat(
                user_message=user_prompt,
                system_prompt=system_prompt,
                temperature=0.3,
                max_tokens=4096,
            )
            self.state.analysis_raw = raw
            report = self._parse_json_output(raw)
            if report:
                return report
        except Exception as exc:
            logger.error("PlanningAgent[{}]: LLM analysis failed: {}", self.agent_type, exc)

        return self._generate_fallback_output()

    def _build_analysis_user_prompt(self) -> str:
        """Construct the user prompt for the final analysis LLM call."""
        strategy = self.build_analysis_strategy()
        context = self.state.build_context_for_llm()

        focus_dims = strategy.get("focus_dimensions", [])
        special_rules = strategy.get("special_rules", [])

        dims_text = "\n".join(f"- {d}" for d in focus_dims)
        rules_text = "\n".join(f"- {r}" for r in special_rules)

        return f"""请根据以下信息进行分析并生成规划报告。

{context}

## 分析维度
{dims_text}

## 特殊规则
{rules_text}

## 要求
1. 先分析用户情况，后给出建议
2. 不给唯一答案，始终提供多个选项
3. 每个建议都要解释"为什么"
4. 严格按照系统提示中的 JSON 格式输出
5. 所有文字使用中文
6. 不要输出 JSON 之外的任何内容
"""

    def _parse_json_output(self, raw: str) -> dict[str, Any] | None:
        """Parse LLM output into the unified JSON schema."""
        from utils.json_parser import safe_json_parse
        parsed = safe_json_parse(raw)
        if parsed is None:
            logger.warning("PlanningAgent[{}]: failed to parse JSON output", self.agent_type)
            return None

        # Validate against unified schema
        result = dict(UNIFIED_OUTPUT_SCHEMA)
        for key in UNIFIED_OUTPUT_SCHEMA:
            if key in parsed:
                result[key] = parsed[key]

        # Ensure list fields are lists
        for list_field in ("advantages", "risks", "action_plan"):
            if not isinstance(result.get(list_field), list):
                result[list_field] = []

        # Ensure string fields are strings
        for str_field in ("summary", "current_status", "main_problem", "goal", "next_question"):
            if not isinstance(result.get(str_field), str):
                result[str_field] = str(result.get(str_field, ""))

        return result

    def _generate_fallback_output(self) -> dict[str, Any]:
        """Generate a graceful fallback when LLM analysis fails."""
        strategy = self.build_analysis_strategy()
        return {
            "summary": f"很抱歉，{self.agent_label}分析暂时无法完成。请稍后重试。",
            "current_status": "分析过程中遇到技术问题",
            "main_problem": "系统暂时无法完成分析",
            "goal": f"完成{self.agent_label}",
            "advantages": [
                {"point": "你已经迈出了规划的第一步", "detail": "主动寻求成长规划本身就是一种优势"}
            ],
            "risks": [
                {"point": "信息不足", "detail": "当前收集的信息不足以生成完整分析", "level": "medium"}
            ],
            "action_plan": [
                {"phase": "近期", "tasks": ["重新尝试分析", "补充更多个人信息"]}
            ],
            "next_question": "是否愿意重新开始一轮规划？",
        }

    # ── Dynamic Question Generation ─────────────────────────────

    def _generate_dynamic_question(self, is_retry: bool, last_answer: str) -> str:
        """Generate the next dynamic follow-up question via LLM.

        The question is NOT from a fixed script — it adapts based on:
        - Previous answers
        - Missing information dimensions
        - Agent-specific analysis strategy
        """
        strategy = self.build_analysis_strategy()
        topics = strategy.get("question_topics", [])
        history = self.state.follow_up_history

        history_text = "\n".join(
            f"Q: {h['q']}\nA: {h['a']}" for h in history
        ) if history else "（尚无追问记录）"

        if is_retry:
            instruction = f"用户刚才的回答「{last_answer}」比较模糊。请换个角度追问，帮助用户更具体地表达。"
        else:
            covered = len(history)
            remaining = MAX_FOLLOW_UP_ROUNDS - covered
            instruction = (
                f"当前是第{covered}轮追问，还剩{remaining}轮。"
                f"请根据已有信息，提出下一个最有价值的问题。"
                f"如果信息已经足够（至少覆盖了{len(topics) // 2}个维度），"
                f"请生成一个收尾问题准备进入分析阶段。"
            )

        prompt = f"""你是{self.agent_label}领域的专业顾问，正在通过追问了解用户情况。

## 需要覆盖的话题
{chr(10).join(f"- {t}" for t in topics)}

## 已完成的问答
{history_text}

## 本轮指令
{instruction}

## 规则
- 只输出一个问题，不要加任何前缀、评论或 JSON
- 问题要具体、有引导性
- 避免"是/否"类封闭式问题
- 根据用户的上一轮回答自然衔接
- 如果这是最后一轮，用一个总结性问题收尾"""

        try:
            response = self.llm.chat(
                user_message=prompt,
                temperature=0.8,  # higher creativity for question generation
                max_tokens=256,
            )
            return response.strip()
        except Exception:
            # Fallback to a generic contextual question
            if is_retry:
                return "可以再具体说说吗？比如有没有特别在意的方向或限制条件？"
            elif len(history) >= MIN_FOLLOW_UP_ROUNDS:
                return "好的，我已经了解了你的基本情况。还有什么特别想补充的吗？"
            else:
                return "接下来我想了解你的具体情况，能详细说说吗？"

    # ── Helpers ─────────────────────────────────────────────────

    def _continue_workflow(self, message: str) -> dict[str, Any]:
        """Continue the workflow by recursing into the next step."""
        return self.chat(message)

    def _try_parse_profile(self, text: str) -> dict[str, Any] | None:
        """Try to extract user profile from structured text."""
        try:
            data = json.loads(text)
            if isinstance(data, dict) and data:
                return data
        except (json.JSONDecodeError, ValueError):
            pass
        return None

    def _try_parse_diagnosis(self, text: str) -> dict[str, Any] | None:
        """Try to extract diagnosis data from structured text."""
        return self._try_parse_profile(text)  # Same logic

    def _get_completion_message(self) -> str:
        return f"✅ {self.agent_label}分析已完成！请查看报告。"

    def _build_response(
        self,
        step: str,
        finished: bool,
        message: str,
        follow_up_round: int = 0,
        report: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "agent_type": self.agent_type,
            "agent_label": self.agent_label,
            "step": step,
            "finished": finished,
            "message": message,
            "follow_up_round": follow_up_round,
            "max_follow_up_rounds": MAX_FOLLOW_UP_ROUNDS,
            "report": report,
            "state": self.state.to_dict(),
        }

    def _build_error(self, message: str) -> dict[str, Any]:
        return self._build_response(
            step="error",
            finished=True,
            message=message,
        )
