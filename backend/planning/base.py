# -*- coding: utf-8 -*-
"""PlanningAgent — 方案 B: 5 步拆分执行。

原始: _run_full_analysis() = 1 次 LLM 调用，一次生成全部。
方案 B:
  Step 3  ANALYZE          → LLM 分析现状 + 方向评估
  Step 4  IDENTIFY_PROBLEMS → 代码计算技能缺口
  Step 5  SET_GOALS         → LLM 生成目标描述
  Step 6  BUILD_PLAN        → 代码骨架 + LLM 逐阶段填充
  Step 7  GENERATE_OUTPUT   → 100% 代码组装 + 硬校验

新增子类需实现:
  - agent_type, agent_label
  - build_analyze_prompt()   → 分析 Prompt
  - build_goal_prompt()      → 目标描述 Prompt
  - build_task_fill_prompt() → 任务填充 Prompt
  - build_analysis_strategy() → 追问策略（不变）
  - build_system_prompt()    → 保留向后兼容
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
    PLAN_PHASE_TEMPLATE,
    MIN_ADVANTAGES,
    MIN_RISKS,
    MIN_PLAN_PHASES,
)


ADVISORY_ACK_MAX: int = 30
ADVISORY_INSIGHT_MAX: int = 70
ADVISORY_QUESTION_MAX: int = 40


# ── Unified Output JSON Schema ──────────────────────────────────

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
    """方案 B: 5 步拆分的工作流引擎。

    LLM 从"全能"变"文案工"——
    格式、结构由代码保证，内容由 LLM 填充。
    """

    def __init__(self, llm_service: Any) -> None:
        self.llm = llm_service
        self.state: PlanningState
        self._last_asked_question: str = ""

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
        """Legacy: full system prompt. Kept for backward compat."""

    @abstractmethod
    def build_analyze_prompt(self) -> str:
        """方案 B Step 3: 分析 Prompt。LLM 输出 current_status + directions + advantages。"""

    @abstractmethod
    def build_goal_prompt(self) -> str:
        """方案 B Step 5: 目标描述 Prompt。LLM 输出一段纯文本。"""

    @abstractmethod
    def build_task_fill_prompt(self) -> str:
        """方案 B Step 6: 任务填充 Prompt。LLM 为单个阶段输出 N 条任务。
        Must contain {count}, {goal}, {skill_gaps}, {phase}, {previous_tasks} placeholders."""

    @abstractmethod
    def build_analysis_strategy(self) -> dict[str, Any]:
        """追问策略。包含 focus_dimensions, special_rules, question_topics。"""

    @property
    def use_split_workflow(self) -> bool:
        """方案 B 开关: True=5步拆分, False=旧版单次调用。"""
        return True

    # ── Workflow Engine ─────────────────────────────────────────

    def init_state(self, user_profile: dict[str, Any] | None = None) -> PlanningState:
        """Initialize a fresh planning state, optionally with pre-loaded profile."""
        self.state = PlanningState(agent_type=self.agent_type)

        if user_profile:
            self.state.user_profile = user_profile
            self.state.has_profile = True
            logger.info("PlanningAgent[{}]: profile loaded", self.agent_type)

        if self.state.has_profile:
            self.state.advance_step()
        return self.state

    def restore_state(self, saved: PlanningState) -> None:
        """Restore agent from a previously saved state."""
        self.state = saved
        self._last_asked_question = saved.last_asked_question

    def chat(self, message: str) -> dict[str, Any]:
        """Main entry: process one user message and advance the workflow."""
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
            WorkflowStep.FOLLOW_UP: self._handle_follow_up,
            WorkflowStep.AWAIT_TRIGGER: self._handle_await_trigger,
            WorkflowStep.ANALYZE: (
                self._handle_analyze_split if self.use_split_workflow
                else self._handle_analyze_legacy
            ),
            WorkflowStep.IDENTIFY_PROBLEMS: (
                self._handle_identify_problems_split if self.use_split_workflow
                else self._handle_analyze_legacy
            ),
            WorkflowStep.SET_GOALS: (
                self._handle_set_goals_split if self.use_split_workflow
                else self._handle_analyze_legacy
            ),
            WorkflowStep.BUILD_PLAN: (
                self._handle_build_plan_split if self.use_split_workflow
                else self._handle_analyze_legacy
            ),
            WorkflowStep.GENERATE_OUTPUT: (
                self._handle_generate_output_split if self.use_split_workflow
                else self._handle_analyze_legacy
            ),
        }

        handler = handlers.get(step)
        if handler is None:
            return self._build_error("Unknown workflow step")

        return handler(message)

    # ── Step Handlers (original, unchanged) ─────────────────────

    def _handle_read_profile(self, message: str) -> dict[str, Any]:
        """Step 1: Read user profile."""
        profile = self._try_parse_profile(message)
        if profile:
            self.state.user_profile = profile
            self.state.has_profile = True
            self.state.advance_step()
            return self._continue_workflow("")
        else:
            self.state.has_profile = True
            self.state.user_profile = {"raw_input": message}
            self.state.advance_step()
            return self._continue_workflow("")

    def _handle_follow_up(
        self,
        message: str,
        turn_analysis: dict[str, Any] | None = None,
        knowledge_context: str = "",
    ) -> dict[str, Any]:
        """Step 2: Answer first, then ask only a valuable clarification.

        Records user answers and advances the conversation. The LLM-generated
        response can include analysis and domain knowledge before at most one
        high-value personal question.
        """
        from planning.readiness import classify_answer_availability

        turn_analysis = turn_analysis or {}
        readiness = dict(turn_analysis.get("readiness", {}) or {})
        if readiness:
            self.state.advice_readiness = readiness
        is_ambiguous = self.state.is_ambiguous(message)
        availability = str(readiness.get("current_availability", ""))
        if availability not in ("answered", "unknown", "declined", "not_answered"):
            availability = classify_answer_availability(message)
        stop_all_keywords = [
            "开始规划", "开始分析", "直接规划", "不用问了", "别再问", "不再回答",
            "没有其他补充", "没有别的信息", "没有补充", "就是这些", "主要情况",
            "能想到的", "可以了",
        ]
        wants_to_stop_questions = any(kw in message for kw in stop_all_keywords)

        # Store the previous question (the one the user just answered)
        prev_q = (
            self.state.last_asked_question
            or self._last_asked_question
            or f"follow_up_{self.state.follow_up_round + 1}"
        )
        resolved_message = self._resolve_former_latter(prev_q, message)
        current_dimension = (
            self.state.last_asked_dimension
            or str(readiness.get("current_dimension", ""))
        )
        if wants_to_stop_questions and availability == "answered":
            availability = "declined"
        self.state.record_follow_up(
            prev_q,
            resolved_message,
            dimension=current_dimension,
            availability=availability,
        )

        # Respect an explicit request to stop.  Missing information becomes an
        # uncertainty boundary, never a reason to force more answers.
        if wants_to_stop_questions:
            advice_level = (
                "personalized"
                if readiness.get("ready_for_personalized_advice")
                else "conditional"
            )
            readiness.update({"ready": True, "can_ask": False, "advice_level": advice_level})
            self.state.advice_readiness = readiness
            self.state.follow_up_complete = True
            self.state.advance_step()
            advisory = self._generate_dynamic_question(
                is_retry=False,
                last_answer=message,
                turn_analysis={
                    **turn_analysis,
                    "should_ask": False,
                    "ready_for_advice": True,
                    "advice_level": advice_level,
                    "readiness": readiness,
                },
                knowledge_context=knowledge_context,
            )
            if advice_level == "conditional":
                status = "可以先按现有信息做条件式规划，未确认部分会明确列为假设。"
            else:
                status = "现有信息已经可以形成初步判断。"
            self._last_asked_question = ""
            self.state.last_asked_question = ""
            self.state.last_asked_dimension = ""
            return self._build_response(
                step="awaiting",
                finished=False,
                message=f"{advisory}\n\n{status}回复“开始规划”即可。",
                follow_up_round=self.state.follow_up_round,
            )

        # “不知道 / 不清楚 / 不方便回答” means this variable is currently
        # unavailable.  Do not rephrase and pressure the user; move to another
        # useful dimension if one remains.
        if is_ambiguous and availability == "answered":
            self.state.ambiguous_count += 1
            if self.state.retry_count < MAX_RETRIES_PER_QUESTION:
                self.state.retry_count += 1
                next_msg = self._generate_dynamic_question(
                    is_retry=True,
                    last_answer=message,
                    turn_analysis=turn_analysis,
                    knowledge_context=knowledge_context,
                )
                self._last_asked_question = next_msg
                self.state.mark_question_asked(next_msg, current_dimension)
                return self._build_response(
                    step="follow_up", finished=False, message=next_msg,
                    follow_up_round=self.state.follow_up_round,
                )
            self.state.retry_count = 0
        else:
            self.state.retry_count = 0

        analysis_wants_question = (
            bool(turn_analysis.get("should_ask"))
            if isinstance(turn_analysis, dict) and "should_ask" in turn_analysis
            else self.state.should_continue_follow_up()
        )
        should_ask = self.state.should_continue_follow_up() and analysis_wants_question

        if should_ask:
            next_msg = self._generate_dynamic_question(
                is_retry=False,
                last_answer=message,
                turn_analysis=turn_analysis,
                knowledge_context=knowledge_context,
            )
            self._last_asked_question = next_msg
            next_dimension = str(readiness.get("next_dimension", ""))
            self.state.mark_question_asked(next_msg, next_dimension)
            return self._build_response(
                step="follow_up", finished=False, message=next_msg,
                follow_up_round=self.state.follow_up_round,
            )

        ready_for_advice = bool(turn_analysis.get("ready_for_advice", True))
        if not ready_for_advice:
            advisory = self._generate_dynamic_question(
                is_retry=False,
                last_answer=message,
                turn_analysis={**turn_analysis, "should_ask": False, "advice_level": "general_only"},
                knowledge_context=knowledge_context,
            )
            missing_labels = readiness.get("missing_labels", [])
            missing_text = "、".join(missing_labels[:3])
            suffix = (
                f"目前还缺少{missing_text}，暂时只做通用分析。"
                if missing_text else "目前信息还不足，暂时只做通用分析。"
            )
            self._last_asked_question = ""
            self.state.last_asked_question = ""
            self.state.last_asked_dimension = ""
            return self._build_response(
                step="insufficient",
                finished=False,
                message=f"{advisory}{suffix}你之后想补充时，直接告诉我就好。",
                follow_up_round=self.state.follow_up_round,
            )

        self.state.follow_up_complete = True
        self.state.advance_step()
        logger.info("PlanningAgent[{}]: follow-up complete after {} rounds, awaiting trigger",
                    self.agent_type, self.state.follow_up_round)
        advisory = self._generate_dynamic_question(
            is_retry=False,
            last_answer=message,
            turn_analysis={**(turn_analysis or {}), "should_ask": False},
            knowledge_context=knowledge_context,
        )
        advice_level = str(turn_analysis.get("advice_level", "personalized"))
        if advice_level == "conditional":
            readiness_line = "现有信息可以形成条件式判断；未确认部分会作为假设并标明不确定性。"
        else:
            readiness_line = "已有信息足够形成初步判断。"
        trigger_msg = f"{advisory}\n\n{readiness_line}如果你希望生成完整方案，回复“开始规划”即可。"
        self._last_asked_question = ""
        self.state.last_asked_question = ""
        self.state.last_asked_dimension = ""
        return self._build_response(
            step="awaiting",
            finished=False,
            message=trigger_msg,
            follow_up_round=self.state.follow_up_round,
        )

    # ── Await Trigger (between FOLLOW_UP and ANALYZE) ──────────

    def _handle_await_trigger(self, message: str) -> dict[str, Any]:
        """Wait for user to say '开始规划' before starting analysis."""
        trigger_keywords = ["开始规划", "开始", "规划", "好的", "可以", "行", "嗯", "好", "生成", "来吧", "ok", "yes", "go", "开始分析"]
        if any(kw in message for kw in trigger_keywords):
            self.state.advance_step()
            logger.info("PlanningAgent[{}]: trigger confirmed, advancing to ANALYZE", self.agent_type)
            return self._continue_workflow("")
        else:
            return self._build_response(
                step="awaiting",
                finished=False,
                message="准备好了就说\"开始规划\"，我们马上开始！",
            )

    # ── 方案 B: 5-Step Split Handlers ──────────────────────────

    def _handle_analyze_split(self, message: str) -> dict[str, Any]:
        """Step 3: LLM 分析现状 + 方向评估 → 存入 state.analysis。"""
        logger.info("PlanningAgent[{}]: ANALYZE (split)", self.agent_type)

        context = self.state.build_context_for_llm()
        system_prompt = self.build_analyze_prompt()
        system_prompt += (
            "\n\n事实边界：只能使用用户画像和问答记录中明确出现的信息。"
            "不得补写学校层次、成绩、项目、能力、家庭条件、偏好或目标；"
            "标记为‘不知道/未回答’的字段保持未知。推断必须写明是推断，"
            "缺少可靠来源时不得给出精确薪资、概率、名额或政策数字。"
        )
        if self.state.advice_readiness.get("advice_level") == "conditional":
            system_prompt += (
                "\n\n当前只能生成条件式分析：对缺失信息不得擅自补全；"
                "方向判断必须写明适用前提，并降低结论确定性。"
            )

        try:
            raw = self.llm.chat(
                user_message=f"## 用户信息\n{context}\n\n请输出分析 JSON。",
                system_prompt=system_prompt,
                temperature=0.3,
                max_tokens=2048,
            )
            self.state.analysis_raw = raw
            analysis = self._parse_analysis_output(raw)

            if analysis and "current_status" in analysis:
                self.state.analysis = analysis
                # Ensure advantages count
                adv = analysis.get("advantages", [])
                if not isinstance(adv, list) or len(adv) < MIN_ADVANTAGES:
                    analysis["advantages"] = self._pad_advantages(adv)
                self.state.analysis = analysis
                self.state.advance_step()
                return self._continue_workflow("")
        except Exception as exc:
            logger.error("PlanningAgent[{}]: ANALYZE failed: {}", self.agent_type, exc)

        # Fallback: use empty analysis, let identify_problems still work
        self.state.analysis = {
            "current_status": "分析暂时不可用",
            "directions": [],
            "advantages": [{"point": "主动规划", "detail": "你正在积极规划未来"}],
        }
        self.state.advance_step()
        return self._continue_workflow("")

    def _handle_identify_problems_split(self, message: str) -> dict[str, Any]:
        """Step 4: 代码计算技能缺口。对比用户技能 vs 目标方向要求。"""
        logger.info("PlanningAgent[{}]: IDENTIFY_PROBLEMS (split)", self.agent_type)

        gaps = self._compute_skill_gaps()
        self.state.identified_problems = gaps
        self.state.advance_step()
        return self._continue_workflow("")

    def _handle_set_goals_split(self, message: str) -> dict[str, Any]:
        """Step 5: LLM 生成目标描述。只用 LLM 写文案。"""
        logger.info("PlanningAgent[{}]: SET_GOALS (split)", self.agent_type)

        system_prompt = self.build_goal_prompt()
        gaps_text = self._format_gaps()

        try:
            raw = self.llm.chat(
                user_message=(
                    f"用户情况：\n{self.state.build_context_for_llm()}\n\n"
                    f"初步分析：\n{json.dumps(self.state.analysis, ensure_ascii=False)}\n\n"
                    f"能力缺口：\n{gaps_text}"
                ),
                system_prompt=system_prompt,
                temperature=0.5,
                max_tokens=256,
            )
            self.state.long_term_goal = raw.strip()
        except Exception as exc:
            logger.error("PlanningAgent[{}]: SET_GOALS failed: {}", self.agent_type, exc)
            self.state.long_term_goal = f"在 90 天内补齐能力短板，为{self.agent_label}做好准备"

        self.state.advance_step()
        return self._continue_workflow("")

    def _handle_build_plan_split(self, message: str) -> dict[str, Any]:
        """Step 6: 代码骨架 + LLM 逐阶段填充任务。"""
        logger.info("PlanningAgent[{}]: BUILD_PLAN (split)", self.agent_type)

        template_prompt = self.build_task_fill_prompt()
        goal = self.state.long_term_goal
        gaps_text = self._format_gaps()
        previous_summary = "（尚无前序阶段）"

        action_plan: list[dict[str, Any]] = []

        for phase_cfg in PLAN_PHASE_TEMPLATE:
            count = phase_cfg["tasks_count"]
            phase = phase_cfg["phase"]

            user_prompt = template_prompt.format(
                count=count,
                goal=goal,
                skill_gaps=gaps_text,
                phase=phase,
                previous_tasks=previous_summary,
            )

            try:
                raw = self.llm.chat(
                    user_message=user_prompt,
                    temperature=0.5,
                    max_tokens=512,
                )
                tasks = self._parse_task_lines(raw, count)
            except Exception as exc:
                logger.error("PlanningAgent[{}]: BUILD_PLAN phase={} failed: {}",
                           self.agent_type, phase, exc)
                tasks = [f"完成{phase}阶段核心学习任务" for _ in range(count)]

            action_plan.append({
                "phase_key": phase_cfg["key"],
                "phase": phase,
                "tasks": tasks,
                "expected_outcome": f"完成{phase}阶段的{count}项任务，进入下一阶段",
            })

            # Build cumulative summary for next phase
            done = "; ".join(tasks[:2])
            previous_summary = f"已完成：{done}"

        self.state.action_plan = action_plan
        self.state.advance_step()
        return self._continue_workflow("")

    def _handle_generate_output_split(self, message: str) -> dict[str, Any]:
        """Step 7: 100% 代码组装 JSON + 硬校验。"""
        logger.info("PlanningAgent[{}]: GENERATE_OUTPUT (split)", self.agent_type)

        output = self._build_final_output()

        # 硬校验
        errors = self._validate_output(output)
        if errors:
            logger.warning("PlanningAgent[{}]: output validation: {}", self.agent_type, errors)
            output = self._fix_output(output, errors)

        self.state.output = output
        self.state.finished = True

        return self._build_response(
            step="completed",
            finished=True,
            message=self._get_completion_message(),
            report=output,
        )

    # ── Legacy monolithic handler (backward compatibility) ──────

    def _handle_analyze_legacy(self, message: str) -> dict[str, Any]:
        """OLD: 1 LLM call for everything."""
        report = self._run_full_analysis()
        self.state.output = report
        self.state.finished = True
        return self._build_response(
            step="completed", finished=True,
            message=self._get_completion_message(), report=report,
        )

    # ── 方案 B: 核心逻辑 ────────────────────────────────────────

    def _compute_skill_gaps(self) -> list[dict[str, Any]]:
        """对比用户技能 vs 目标方向 → 结构化缺口列表。

        交给子类的 _get_skill_matrix_for_direction 完成映射。
        """
        from planning.rules import find_best_matching_direction, compute_skill_gaps

        # Get top direction from analysis
        directions = self.state.analysis.get("directions", [])
        if not directions:
            return [{"skill": "目标方向未明确", "status": "待定", "priority": "high"}]

        top_direction = directions[0].get("name", "")
        matched_direction = find_best_matching_direction(top_direction)

        if not matched_direction:
            return [{
                "skill": f"方向「{top_direction}」暂未收录",
                "status": "未知", "priority": "medium",
                "detail": "系统中暂无该方向的技能矩阵，请手动评估"
            }]

        # Get user skills
        user_skills = self.state.get_user_skills()

        result = compute_skill_gaps(matched_direction, user_skills)

        gaps: list[dict[str, Any]] = []

        for skill in result["missing_required"]:
            gaps.append({"skill": skill, "status": "缺失", "priority": "high"})

        for skill in result["missing_nice"]:
            gaps.append({"skill": skill, "status": "建议补充", "priority": "medium"})

        if not gaps:
            gaps.append({
                "skill": "必备技能已基本覆盖",
                "status": "合格", "priority": "low",
                "detail": f"覆盖率 {result['completeness']:.0%}"
            })

        return gaps

    def _format_gaps(self) -> str:
        """Format identified_problems as a readable string."""
        if not self.state.identified_problems:
            return "（暂无已知缺口）"
        lines = []
        for g in self.state.identified_problems:
            lines.append(f"- [{g.get('priority', '?')}] {g['skill']}: {g.get('status', '?')}")
        return "\n".join(lines)

    def _build_final_output(self) -> dict[str, Any]:
        """100% 代码组装最终 JSON。"""
        analysis = self.state.analysis
        gaps = self.state.identified_problems
        goal = self.state.long_term_goal
        plan = self.state.action_plan

        # Build risks from gaps
        risks = []
        for g in gaps:
            if g.get("priority") in ("high", "medium"):
                risks.append({
                    "point": g["skill"],
                    "detail": f"该项技能{g.get('status', '缺失')}，需要通过针对性学习补齐",
                    "level": g.get("priority", "medium"),
                })

        if len(risks) < MIN_RISKS:
            risks.append({
                "point": "市场竞争",
                "detail": "当前就业市场竞争激烈，需要持续提升竞争力",
                "level": "medium",
            })

        # Build main_problem from gaps
        high_gaps = [g["skill"] for g in gaps if g.get("priority") == "high"]
        main_problem = "、".join(high_gaps[:3]) if high_gaps else "需进一步明确方向后制定针对性计划"

        readiness = self.state.advice_readiness
        assumptions = []
        if readiness.get("advice_level") == "conditional":
            missing = "、".join(readiness.get("missing_labels", [])) or "部分个人变量"
            assumptions.append(f"{missing}尚未确认，方案按情景假设给出，需在获得新信息后复核")

        return {
            "summary": goal,
            "current_status": analysis.get("current_status", ""),
            "main_problem": main_problem,
            "goal": goal,
            "advantages": analysis.get("advantages", []),
            "risks": risks[:MIN_RISKS + 2],
            "action_plan": plan,
            "next_question": "你想深入了解哪个阶段的计划？或者有什么需要调整的地方？",
            "advice_level": readiness.get("advice_level", "personalized"),
            "information_gaps": readiness.get("missing_labels", []),
            "assumptions": assumptions,
        }

    def _validate_output(self, output: dict[str, Any]) -> list[str]:
        """硬校验输出。返回错误列表（空=通过）。"""
        errors: list[str] = []

        adv = output.get("advantages", [])
        if not isinstance(adv, list) or len(adv) < MIN_ADVANTAGES:
            errors.append(f"advantages: 需要至少 {MIN_ADVANTAGES} 条，当前 {len(adv) if isinstance(adv, list) else 0} 条")

        risks = output.get("risks", [])
        if not isinstance(risks, list) or len(risks) < MIN_RISKS:
            errors.append(f"risks: 需要至少 {MIN_RISKS} 条，当前 {len(risks) if isinstance(risks, list) else 0} 条")

        plan = output.get("action_plan", [])
        if not isinstance(plan, list) or len(plan) < MIN_PLAN_PHASES:
            errors.append(f"action_plan: 需要至少 {MIN_PLAN_PHASES} 个阶段，当前 {len(plan) if isinstance(plan, list) else 0} 个")

        for s_field in ("summary", "current_status", "main_problem", "goal"):
            if not isinstance(output.get(s_field), str) or not output.get(s_field):
                errors.append(f"{s_field}: 不能为空")

        return errors

    def _fix_output(self, output: dict[str, Any], errors: list[str]) -> dict[str, Any]:
        """尝试修复校验失败的字段。"""
        fixed = dict(output)

        if not isinstance(fixed.get("advantages"), list) or len(fixed.get("advantages", [])) < MIN_ADVANTAGES:
            cur = fixed.get("advantages", [])
            if not isinstance(cur, list):
                cur = []
            while len(cur) < MIN_ADVANTAGES:
                cur.append({"point": "主动规划的意愿", "detail": "你正在积极规划未来发展方向"})
            fixed["advantages"] = cur

        if not isinstance(fixed.get("risks"), list) or len(fixed.get("risks", [])) < MIN_RISKS:
            cur = fixed.get("risks", [])
            if not isinstance(cur, list):
                cur = []
            while len(cur) < MIN_RISKS:
                cur.append({
                    "point": "信息有限", "detail": "当前收集的信息有限，后续可补充完善",
                    "level": "medium",
                })
            fixed["risks"] = cur

        for s_field in ("current_status", "main_problem"):
            if not fixed.get(s_field):
                fixed[s_field] = "信息待补充"

        if not fixed.get("goal"):
            fixed["goal"] = self.state.long_term_goal or f"完成{self.agent_label}"

        if not fixed.get("summary"):
            fixed["summary"] = fixed["goal"]

        return fixed

    def _pad_advantages(self, existing: list[dict]) -> list[dict]:
        """Ensure advantages list meets minimum count."""
        result = list(existing) if existing else []
        while len(result) < MIN_ADVANTAGES:
            result.append({"point": "自我驱动力", "detail": "主动使用工具进行成长规划"})
        return result

    # ── Legacy: old monolithic analysis (kept for backward compat) ─

    def _run_full_analysis(self) -> dict[str, Any]:
        """OLD: Single LLM call for full report."""
        system_prompt = self.build_system_prompt()
        user_prompt = self._build_analysis_user_prompt()
        try:
            raw = self.llm.chat(
                user_message=user_prompt, system_prompt=system_prompt,
                temperature=0.3, max_tokens=4096,
            )
            self.state.analysis_raw = raw
            report = self._parse_json_output(raw)
            if report:
                return report
        except Exception as exc:
            logger.error("PlanningAgent[{}]: LLM analysis failed: {}", self.agent_type, exc)
        return self._generate_fallback_output()

    def _build_analysis_user_prompt(self) -> str:
        """OLD: user prompt for monolithic analysis."""
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
        result = dict(UNIFIED_OUTPUT_SCHEMA)
        for key in UNIFIED_OUTPUT_SCHEMA:
            if key in parsed:
                result[key] = parsed[key]
        for list_field in ("advantages", "risks", "action_plan"):
            if not isinstance(result.get(list_field), list):
                result[list_field] = []
        for str_field in ("summary", "current_status", "main_problem", "goal", "next_question"):
            if not isinstance(result.get(str_field), str):
                result[str_field] = str(result.get(str_field, ""))
        return result

    def _parse_analysis_output(self, raw: str) -> dict[str, Any] | None:
        """Parse the preliminary analysis without dropping direction data."""
        from utils.json_parser import safe_json_parse

        parsed = safe_json_parse(raw)
        if not isinstance(parsed, dict):
            logger.warning("PlanningAgent[{}]: failed to parse analysis JSON", self.agent_type)
            return None

        current_status = parsed.get("current_status", "")
        directions = parsed.get("directions", [])
        advantages = parsed.get("advantages", [])
        if not isinstance(current_status, str) or not current_status.strip():
            return None
        if not isinstance(directions, list):
            directions = []
        if not isinstance(advantages, list):
            advantages = []

        normalized_directions: list[dict[str, Any]] = []
        for item in directions[:3]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            try:
                score = max(0, min(100, int(item.get("match_score", 0))))
            except (TypeError, ValueError):
                score = 0
            normalized_directions.append({
                "name": name,
                "match_score": score,
                "reasoning": str(item.get("reasoning", "")).strip(),
            })

        return {
            "current_status": current_status.strip(),
            "directions": normalized_directions,
            "advantages": advantages,
        }

    def _parse_task_lines(self, raw: str, expected_count: int) -> list[str]:
        """Parse LLM output into exactly expected_count task lines."""
        lines = [l.strip() for l in raw.strip().split("\n") if l.strip()]
        # Remove leading numbers like "1. ", "1、", "1) "
        import re
        cleaned = []
        for line in lines:
            line = re.sub(r'^[\d]+[\.\、\)\)\s]+', '', line).strip()
            if line:
                cleaned.append(line)

        # Pad or trim to expected count
        if len(cleaned) < expected_count:
            cleaned += [f"完成{self.agent_label}相关学习任务" for _ in range(expected_count - len(cleaned))]
        return cleaned[:expected_count]

    def _generate_fallback_output(self) -> dict[str, Any]:
        """Graceful fallback when LLM analysis fails."""
        return {
            "summary": f"很抱歉，{self.agent_label}分析暂时无法完成。请稍后重试。",
            "current_status": "分析过程中遇到技术问题",
            "main_problem": "系统暂时无法完成分析",
            "goal": f"完成{self.agent_label}",
            "advantages": [{"point": "你已经迈出了规划的第一步", "detail": "主动寻求成长规划本身就是一种优势"}],
            "risks": [{"point": "信息不足", "detail": "当前收集的信息不足以生成完整分析", "level": "medium"}],
            "action_plan": [{"phase": "近期", "tasks": ["重新尝试分析", "补充更多个人信息"]}],
            "next_question": "是否愿意重新开始一轮规划？",
        }

    # ── Advisory Turn Generation ────────────────────────────────

    @staticmethod
    def _trim_advisory_part(text: str, limit: int, ending: str = "") -> str:
        """Trim one response part without leaving an obviously broken clause."""
        import re

        cleaned = re.sub(r"\s+", "", str(text or "")).strip()
        if not cleaned:
            return ""
        if len(cleaned) > limit:
            candidate = cleaned[:limit]
            # An insight must end at a complete sentence.  Cutting at a comma
            # and then appending "。" turns fragments such as "薪资还会受城市、"
            # into misleading, unfinished statements.
            sentence_cut = max(candidate.rfind(mark) for mark in "。！？")
            if ending == "。" and sentence_cut >= max(12, limit // 3):
                cleaned = candidate[:sentence_cut + 1]
            elif ending == "。":
                cleaned = candidate[: max(1, limit - 1)].rstrip("，；、。！？") + "…"
            else:
                cut = max(candidate.rfind(mark) for mark in "，；、。！？")
                if cut >= max(8, limit // 2):
                    cleaned = candidate[:cut + 1]
                else:
                    cleaned = candidate[: max(1, limit - 1)].rstrip("，；、。！？") + "…"
        if ending and not cleaned.endswith(("。", "！", "？", "…")):
            cleaned = cleaned.rstrip("，；、") + ending
        return cleaned

    @staticmethod
    def _soften_advisory_text(text: str) -> str:
        """Replace common commanding or absolute phrases with calibrated ones."""
        replacements = (
            ("你必须", "可以考虑"),
            ("你应该", "可以先"),
            ("显然", "从目前信息看"),
            ("肯定会", "更可能"),
            ("肯定是", "更可能是"),
            ("绝对不能", "通常不建议"),
            ("绝对", "通常"),
            ("不适合", "目前匹配度可能有限"),
        )
        softened = str(text or "")
        for source, target in replacements:
            softened = softened.replace(source, target)
        return softened

    def _fallback_acknowledgement(self, last_answer: str) -> str:
        from planning.readiness import classify_answer_availability

        answer = str(last_answer or "").strip().strip("。！？?!")
        if not answer:
            return ""
        if any(marker in answer for marker in ("没有其他补充", "没有别的信息", "没有补充", "主要情况", "就是这些", "能想到的")):
            return "现有信息我已经记下了。"
        availability = classify_answer_availability(answer)
        if availability == "unknown":
            # "还没想好冲985还是求稳" contains uncertainty *and* a useful
            # decision signal.  Preserve that signal in the acknowledgement
            # instead of collapsing every unknown-like phrase to a generic
            # sentence.
            residual = answer
            for marker in (
                "我还没想好", "还没想好", "我不知道", "不知道",
                "我不清楚", "不清楚", "我不确定", "不确定",
                "暂时没有想法", "还没考虑", "说不准", "看情况",
                "都行", "都可以", "无所谓", "随便", "再说吧",
            ):
                residual = residual.replace(marker, "")
            residual = residual.strip("，。！？?!、 ")
            if len(residual) >= 3:
                snippet = self._trim_advisory_part(
                    residual.removeprefix("该"), 16,
                ).rstrip("。！？?!…")
                return f"你对“{snippet}”还拿不准，没关系。"
            return "这项暂时不确定也没关系。"
        if availability == "declined":
            return "这项可以先跳过。"
        if "薪资" in answer or "工资" in answer or "收入" in answer:
            if "考研" in answer and "就业" in answer:
                return "你在比较考研和就业的薪资差异。"
            return "你正在关注薪资差异。"
        if "考研" in answer and "就业" in answer:
            return "你正在比较考研和就业。"
        snippet = self._trim_advisory_part(answer, 12).rstrip("。！？?!…")
        return f"你提到“{snippet}”，我先接着这个重点说。"

    @staticmethod
    def _acknowledgement_mentions_answer(acknowledgement: str, last_answer: str) -> bool:
        """Use lightweight phrase overlap to reject generic acknowledgements."""
        import re

        answer = re.sub(r"\s+", "", str(last_answer or ""))
        acknowledgement = re.sub(r"\s+", "", str(acknowledgement or ""))
        ignored = {"我更", "比较", "目前", "大概", "可以", "就是", "这个", "那个", "还是"}
        signals = {
            answer[index:index + 2]
            for index in range(max(0, len(answer) - 1))
            if answer[index:index + 2] not in ignored
        }
        return any(signal in acknowledgement for signal in signals)

    def _safe_personal_question(self) -> str:
        """Fallback when the model accidentally emits a knowledge-test question."""
        return {
            "graduate": "你更看重目标岗位门槛，还是读研的时间成本？",
            "career": "你更看重成长、稳定，还是工作强度？",
            "civil": "你更看重稳定性，还是备考的时间成本？",
            "major": "你更看重目标专业，还是转专业的时间成本？",
        }.get(self.agent_type, "你更看重哪项个人目标或现实约束？")

    def _compose_advisory_turn(
        self,
        payload: dict[str, Any],
        *,
        should_ask: bool,
        last_answer: str,
        advice_level: str = "personalized",
        grounding_context: str = "",
    ) -> str:
        """Assemble a short, gentle response with code-enforced limits."""
        import re

        acknowledgement = self._soften_advisory_text(payload.get("acknowledgement", ""))
        insight = self._soften_advisory_text(payload.get("insight", ""))
        question = self._soften_advisory_text(payload.get("question", ""))

        compact_context = re.sub(r"\s+", "", grounding_context)
        declared_facts = payload.get("user_facts_used", [])
        if not isinstance(declared_facts, list):
            declared_facts = []
        valid_facts = [
            str(fact).strip() for fact in declared_facts
            if len(str(fact).strip()) >= 2
            and re.sub(r"\s+", "", str(fact).strip()) in compact_context
        ]
        unsupported_fact = len(valid_facts) != len(declared_facts)
        knowledge_evidence = str(payload.get("knowledge_evidence", "")).strip()
        unsupported_evidence = bool(
            knowledge_evidence
            and re.sub(r"\s+", "", knowledge_evidence) not in compact_context
        )
        specific_user_claim = any(
            marker in insight
            for marker in (
                "你的专业是", "你目前是", "你已经有", "你已经具备", "你具备",
                "你缺少", "你的基础", "你的成绩", "你的家庭", "你的学校", "你所在",
            )
        )
        unsupported_numbers = any(
            token not in compact_context
            for token in re.findall(r"\d+(?:\.\d+)?(?:%|万|元|k|K|名|分)?", insight)
        )
        if (
            unsupported_fact
            or unsupported_evidence
            or unsupported_numbers
            or (specific_user_claim and not valid_facts)
        ):
            insight = {
                "general_only": "现有信息还不足以支持个性化结论，可以先比较目标门槛、当前基础和时间成本。",
                "conditional": "如果未确认信息与当前判断一致，可以先按目标、基础和时间成本分情形比较。",
            }.get(
                advice_level,
                "基于已确认信息，可以先比较目标门槛、当前基础和时间成本。",
            )

        if advice_level == "general_only":
            # Last-resort lexical guard in addition to the prompt and workflow
            # gate.  Information-collection turns may explain dimensions, but
            # must not sound like a personalized verdict.
            for source, target in (
                ("你更适合", "是否适合仍需结合"),
                ("建议你选择", "可以先比较"),
                ("建议你优先", "可以先了解"),
                ("最适合你", "是否匹配仍需判断"),
                ("直接选择", "先比较"),
            ):
                insight = insight.replace(source, target)
        elif advice_level == "conditional" and not any(
            marker in insight[:18] for marker in ("如果", "前提", "假设", "情形", "取决于")
        ):
            insight = f"如果未确认信息与当前判断一致，{insight}"

        # Acknowledgement is code-grounded in the user's actual answer.  This
        # prevents a fluent model from adding an experience or preference the
        # user never stated.
        if last_answer:
            acknowledgement = self._fallback_acknowledgement(last_answer)

        acknowledgement = self._trim_advisory_part(
            acknowledgement, ADVISORY_ACK_MAX, "。"
        )
        insight = self._trim_advisory_part(
            insight or "可以先结合目标、基础和时间成本做判断",
            ADVISORY_INSIGHT_MAX,
            "。",
        )

        if should_ask:
            if any(
                phrase in question
                for phrase in ("你知道", "你了解", "了解过", "是否了解", "是否知道")
            ):
                question = self._safe_personal_question()
            question = question.replace("?", "？")
            first_question_end = question.find("？")
            if first_question_end >= 0:
                question = question[:first_question_end + 1]
            question = re.sub(r"[？?]+", "？", question)
            if not question.strip():
                question = "你目前更看重哪一项？"
            question = self._trim_advisory_part(
                question, ADVISORY_QUESTION_MAX, "？"
            )
            if question and not question.endswith("？"):
                question = question.rstrip("。！…") + "？"
        else:
            question = ""

        return "".join(part for part in (acknowledgement, insight, question) if part)

    def _parse_advisory_output(
        self,
        raw: str,
        *,
        should_ask: bool,
        last_answer: str,
        advice_level: str = "personalized",
        grounding_context: str = "",
    ) -> str:
        """Parse structured output, with a compatibility fallback for plain text."""
        import re
        from utils.json_parser import safe_json_parse

        parsed = safe_json_parse(raw)
        if isinstance(parsed, dict) and any(
            key in parsed for key in ("acknowledgement", "insight", "question")
        ):
            return self._compose_advisory_turn(
                parsed,
                should_ask=should_ask,
                last_answer=last_answer,
                advice_level=advice_level,
                grounding_context=grounding_context,
            )

        sentences = [
            sentence.strip()
            for sentence in re.findall(r"[^。！？?]+[。！？?]?", str(raw or ""))
            if sentence.strip()
        ]
        question = ""
        if should_ask:
            for index in range(len(sentences) - 1, -1, -1):
                if sentences[index].endswith(("？", "?")):
                    question = sentences.pop(index)
                    break
        acknowledgement = sentences.pop(0) if last_answer and len(sentences) > 1 else ""
        insight = "".join(sentences)
        return self._compose_advisory_turn(
            {
                "acknowledgement": acknowledgement,
                "insight": insight,
                "question": question,
            },
            should_ask=should_ask,
            last_answer=last_answer,
            advice_level=advice_level,
            grounding_context=grounding_context,
        )

    def _generate_dynamic_question(
        self,
        is_retry: bool,
        last_answer: str,
        turn_analysis: dict[str, Any] | None = None,
        knowledge_context: str = "",
    ) -> str:
        """Generate an answer-first advisory response with an optional question.

        The legacy method name is kept for compatibility.  Unlike the old
        questionnaire behavior, the response must first use known information
        and relevant domain knowledge, then ask at most one personal question.
        """
        strategy = self.build_analysis_strategy()
        topics = strategy.get("question_topics", [])
        special_rules = strategy.get("special_rules", [])
        history = self.state.follow_up_history
        turn_analysis = turn_analysis or {}
        should_ask = True if is_retry else bool(turn_analysis.get("should_ask", True))
        advice_level = str(turn_analysis.get("advice_level", "personalized"))

        # Only keep recent 5 rounds to control context length
        recent_history = history[-5:] if len(history) > 5 else history
        history_text = "\n".join(
            f"Q: {h['q']}\nA: {h['a']}" for h in recent_history
        ) if recent_history else "尚无追问记录"
        if len(history) > 5:
            history_text = f"（更早的{len(history)-5}轮对话已省略）\n{history_text}"

        if is_retry:
            instruction = (
                f"用户刚才的回答「{last_answer}」比较简短，"
                "先给出一个简短的判断框架或可选项，再用一个更容易回答的问题帮助用户表达偏好。"
            )
        else:
            critical_variable = str(turn_analysis.get("critical_variable", "")).strip()
            if not should_ask:
                if advice_level == "conditional":
                    instruction = (
                        "当前不再继续追问。请给出条件式判断，明确使用“如果/在……前提下”等表述，"
                        "不要把未确认信息当作事实，也不要在结尾添加问题。"
                    )
                elif advice_level == "general_only":
                    instruction = (
                        "当前信息未达到个性化建议标准。只提供通用框架或客观信息，"
                        "不要给方向性结论，也不要在结尾添加问题。"
                    )
                else:
                    instruction = (
                        "当前不需要继续追问。请直接回答用户并给出基于现有信息的阶段性判断，"
                        "不要在结尾添加问题。"
                    )
            else:
                level_instruction = (
                    "当前尚未达到个性化建议标准，只能提供通用信息，不能提前替用户下结论。"
                    if advice_level == "general_only" else ""
                )
                instruction = level_instruction + (
                    "先回答用户能由AI回答的部分，再指出真正影响建议的变量，最后只问一个问题。"
                    + (f"本轮优先澄清：{critical_variable}。" if critical_variable else "")
                )

        user_context = self.state.build_context_for_llm()
        today = __import__("datetime").date.today().strftime("%Y年%m月%d日")

        # System prompt: answer first; question is optional and must be personal.
        system_prompt = f"""你是专业、耐心的{self.agent_label}顾问。用户来这里是为了获得分析和建议，不是接受知识测验。

每轮回复按以下顺序组织：
1. 如果用户刚回答了问题，先用一句话具体承接回答，不能只说“好的、明白、感谢分享”。
2. 给出一条简短、有用的判断或领域信息。
3. 仅在确有必要时，最后提出一个高价值澄清问题。

核心规则：
- AI能够回答的客观信息必须直接回答，禁止反问“你知道……吗”“你了解……吗”。
- 只能询问用户本人才能回答的信息：经历、能力现状、目标偏好、价值排序、可投入时间和现实约束。
- 允许本轮零提问；如果单轮分析要求不追问，回复中不能出现问题句。
- 每轮最多一个核心问题，不重复历史问题，不一次索取一整套资料。
- 没有可靠、带时间范围的依据时，不得编造精确薪资、报录比、录取率或政策数字。
- 已知事实与合理推断要区分；信息不足时可以明确假设，但仍应先提供通用分析。
- advice_level=general_only 时，只能给客观信息、判断维度或通用路径，禁止输出个性化推荐结论。
- advice_level=conditional 时，要用情景或假设表达，不得把用户不知道或不愿回答的内容当作事实。
- 用户回答“不知道、不清楚、不方便回答”时，温和接住并换一个信息维度，不追问同一项。
- 语气柔和、克制，不说“你必须、你应该、显然、肯定、绝对、不适合”。
- 多用“可以先、更可能、相对来说、从目前信息看”，但不要堆叠安慰或过度表扬。
- acknowledgement 不超过30字，insight 不超过70字，question 不超过40字。
- 总回复建议80到140字，禁止标题、列表和大段铺垫。

禁止示例：
“你知道考研和就业的薪资区别吗？”
“你是否了解公务员考试内容和竞争程度？”

正确方式：先柔和承接用户的具体回答，再说明差异或规则，最后询问会改变建议的个人偏好或约束。

事实约束：
- 只能使用“已知用户信息、已完成对话、可引用的领域知识”中出现的事实。
- 不得补写用户未提到的学校、成绩、项目、家庭、能力、城市、偏好或目标。
- 用户说不知道或跳过的字段属于未知，不能按常见情况替用户填上。
- user_facts_used 必须逐字摘自输入；knowledge_evidence 必须逐字摘自给定领域知识。没有依据就留空。

只输出合法JSON：
{{"acknowledgement":"对上一条回答的具体、柔和承接；首次对话可为空","insight":"一条简短分析或领域信息","question":"最多一个邀请式问题；无需追问时为空","user_facts_used":["仅列实际使用且能在输入中找到的用户事实原文"],"knowledge_evidence":"实际引用的领域知识原文；没有则为空"}}"""

        # User prompt: current context and specific instruction
        user_prompt = f"""当前日期：{today}

已知用户信息：
{user_context if user_context else "（暂无）"}

本轮需要覆盖的话题方向：
{chr(10).join(f"- {t}" for t in topics)}

本领域特别规则：
{chr(10).join(f"- {rule}" for rule in special_rules) or "（无）"}

单轮分析结果：
{json.dumps(turn_analysis, ensure_ascii=False) if turn_analysis else "（未提供，按通用策略判断）"}

可引用的领域知识：
{knowledge_context or "（没有额外知识材料；避免给出未经验证的精确数据）"}

已完成的对话：
{history_text}

本轮任务：
{instruction}

请只输出约定的 JSON，不要 Markdown 或其他文字。"""

        try:
            response = self.llm.chat(
                user_message=user_prompt,
                system_prompt=system_prompt,
                temperature=0.5,
                max_tokens=400,
            )
            return self._parse_advisory_output(
                response,
                should_ask=should_ask,
                last_answer=last_answer,
                advice_level=advice_level,
                grounding_context=f"{user_context}\n{last_answer}\n{knowledge_context}",
            )
        except Exception:
            if is_retry:
                fallback = {
                    "acknowledgement": "暂时没想清楚也没关系。",
                    "insight": "可以先从岗位范围、时间成本和发展节奏反推。",
                    "question": "你现在最不愿意承担哪一种成本？",
                }
            elif turn_analysis.get("should_ask") is False:
                fallback = {
                    "acknowledgement": "",
                    "insight": "从现有信息看，可以先比较岗位门槛、能力积累和时间成本；具体数据以对应年份的可靠来源为准。",
                    "question": "",
                }
            else:
                fallback = {
                    "acknowledgement": "",
                    "insight": "可以先从目标门槛、当前基础和机会成本判断。",
                    "question": "你更看重短期确定性还是长期发展空间？",
                }
            return self._compose_advisory_turn(
                fallback,
                should_ask=should_ask,
                last_answer=last_answer,
                advice_level=advice_level,
                grounding_context=f"{user_context}\n{last_answer}\n{knowledge_context}",
            )

    def free_chat(self, message: str) -> str:
        """Generate a natural conversational response during await_trigger phase.

        Unlike _generate_dynamic_question, this:
        - Records the message in history WITHOUT incrementing follow_up_round
        - Uses a lightweight chat prompt instead of the structured question prompt
        - Returns a warm conversational response, nudging toward analysis naturally
        """
        # Record message without incrementing follow_up_round
        prev_q = self._last_asked_question or ""
        self.state.follow_up_history.append({"q": prev_q, "a": message})

        user_context = self.state.build_context_for_llm()

        system_prompt = (
            f"你是{self.agent_label}领域的专业顾问。用户已完成信息收集，"
            f"正在等待合适的时机开始生成规划报告。\n\n"
            f"## 规则\n"
            f"- 用温暖、简洁的语气回应用户（<=80字）\n"
            f"- 如果用户想继续聊，就自然陪着聊，不要催促\n"
            f"- 在回复末尾可以轻描淡写地提一句“准备好了随时开始”\n"
            f"- 不要重复之前问过的问题\n"
            f"- 不要主动推进到分析阶段"
        )

        try:
            response = self.llm.chat(
                user_message=message,
                system_prompt=system_prompt,
                temperature=0.7,
                max_tokens=300,
            )
            return response.strip()
        except Exception:
            return "我在这里呢！有什么想聊的随时说～准备好了就告诉我。"

    def _build_confirmed_summary(self) -> str:
        """Build a summary of confirmed information from follow-up history."""
        items: list[str] = []
        history = self.state.follow_up_history
        # Extract key information from each Q&A pair
        for entry in history:
            answer = entry.get("a", "").strip()
            if answer and len(answer) < 50:
                items.append(answer)
        if items:
            return "\n".join(f"✓ {item}" for item in items)
        return ""


    @staticmethod
    def _resolve_former_latter(question: str, answer: str) -> str:
        """Resolve ‘前者’/‘后者’ in the answer by extracting options from the question.

        When a user answers “后者” to “你倾向A还是B？”, expand it to “后者（B方向）”
        so the LLM downstream has explicit context.
        """
        if not answer or not question:
            return answer

        answer_clean = answer.strip()
        import re

        # Detect shorthand references
        former_keywords = ["前者", "第一个", "前面的", "第一种", "前一种"]
        latter_keywords = ["后者", "第二个", "后面的", "第二种", "后一种"]

        is_former = any(kw in answer_clean for kw in former_keywords)
        is_latter = any(kw in answer_clean for kw in latter_keywords)

        if not (is_former or is_latter):
            return answer

        # Try to split the question into two options
        for sep in ["还是", "或者", "或是"]:
            parts = re.split(sep, question, maxsplit=1)
            if len(parts) != 2:
                continue
            option_a = parts[0].strip().rstrip("，,.?!？！")
            option_b = parts[1].strip().rstrip("，,.?!？！？")

            # Take only the last clause of option_a (the actual option text)
            if "，" in option_a:
                option_a = option_a.split("，")[-1].strip()
            if "," in option_a:
                option_a = option_a.split(",")[-1].strip()

            if is_latter:
                expanded = f"后者（{option_b}）"
                return answer_clean.replace(
                    next(kw for kw in latter_keywords if kw in answer_clean),
                    expanded
                )
            else:
                expanded = f"前者（{option_a}）"
                return answer_clean.replace(
                    next(kw for kw in former_keywords if kw in answer_clean),
                    expanded
                )

        return answer  # could not split, return as-is

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
        }

    def _build_error(self, message: str) -> dict[str, Any]:
        return self._build_response(step="error", finished=True, message=message)
