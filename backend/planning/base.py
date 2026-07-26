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

    def _handle_follow_up(self, message: str) -> dict[str, Any]:
        """Step 2: Dynamic follow-up questions (3-7 rounds).

        Records user answers and advances the conversation. The LLM-generated
        response (via _generate_dynamic_question) now includes acknowledgment,
        info confirmation, and the next question."""
        is_ambiguous = self.state.is_ambiguous(message)

        # —— Skip detection: user wants to jump to analysis ——
        skip_keywords = ["开始规划", "开始分析", "直接规划", "跳过", "不用问了", "可以了"]
        if any(kw in message for kw in skip_keywords) and self.state.follow_up_round >= 2:
            self.state.follow_up_complete = True
            self.state.advance_step()
            logger.info("PlanningAgent[{}]: user skipped follow-up at round {}", self.agent_type, self.state.follow_up_round)
            trigger_msg = "好的，信息收集得差不多了，可以开始规划了。准备好了就说【开始规划】吧！"
            return self._build_response(
                step="awaiting", finished=False, message=trigger_msg,
                follow_up_round=self.state.follow_up_round,
            )

        # Store the previous question (the one the user just answered)
        prev_q = self._last_asked_question or f"follow_up_{self.state.follow_up_round + 1}"
        self.state.record_follow_up(prev_q, message)

        if is_ambiguous:
            self.state.ambiguous_count += 1
            if self.state.retry_count < MAX_RETRIES_PER_QUESTION:
                self.state.retry_count += 1
                next_msg = self._generate_dynamic_question(is_retry=True, last_answer=message)
                self._last_asked_question = next_msg
                return self._build_response(
                    step="follow_up", finished=False, message=next_msg,
                    follow_up_round=self.state.follow_up_round,
                )
            self.state.retry_count = 0
        else:
            self.state.retry_count = 0

        if self.state.should_continue_follow_up():
            next_msg = self._generate_dynamic_question(is_retry=False, last_answer=message)
            self._last_asked_question = next_msg
            return self._build_response(
                step="follow_up", finished=False, message=next_msg,
                follow_up_round=self.state.follow_up_round,
            )

        self.state.follow_up_complete = True
        self.state.advance_step()
        logger.info("PlanningAgent[{}]: follow-up complete after {} rounds, awaiting trigger",
                    self.agent_type, self.state.follow_up_round)
        trigger_msg = "信息收集完毕，可以开始规划了。准备好了就说\"开始规划\"吧！"
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

        try:
            raw = self.llm.chat(
                user_message=f"## 用户信息\n{context}\n\n请输出分析 JSON。",
                system_prompt=system_prompt,
                temperature=0.3,
                max_tokens=2048,
            )
            self.state.analysis_raw = raw
            analysis = self._parse_json_output(raw)

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
                user_message=f"缺口：\n{gaps_text}",
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

        return {
            "summary": goal,
            "current_status": analysis.get("current_status", ""),
            "main_problem": main_problem,
            "goal": goal,
            "advantages": analysis.get("advantages", []),
            "risks": risks[:MIN_RISKS + 2],
            "action_plan": plan,
            "next_question": "你想深入了解哪个阶段的计划？或者有什么需要调整的地方？",
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

    # ── Dynamic Question Generation (unchanged) ─────────────────

    def _generate_dynamic_question(self, is_retry: bool, last_answer: str) -> str:
        """Generate the next dynamic follow-up question via LLM.

        Uses a clean system prompt (role + style) and a focused user prompt
        (context + instruction) for higher-quality, human-like responses.
        """
        strategy = self.build_analysis_strategy()
        topics = strategy.get("question_topics", [])
        history = self.state.follow_up_history

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
                f"请换一个角度温和地引导用户说得更具体一些。"
            )
        else:
            covered = len(history)
            remaining = MAX_FOLLOW_UP_ROUNDS - covered
            if remaining <= 1:
                instruction = (
                    f"当前已是第{covered}轮追问，接近尾声。"
                    f"请用一个收尾性的问题，为进入分析阶段做准备。"
                )
            else:
                instruction = (
                    f"当前是第{covered}轮追问，还剩{remaining}轮。"
                    f"请根据已有信息和尚未覆盖的话题，提出下一个最有价值的问题。"
                )

        user_context = self.state.build_context_for_llm()
        today = __import__("datetime").date.today().strftime("%Y年%m月%d日")

        # System prompt: stable persona + style rules
        system_prompt = f"""你是{self.agent_label}领域的专业顾问，同时也是一位温暖、善于倾听的学长/学姐。

## 聊天风格
- 先简短回应对方上一句话，让对方感到被认真倾听
- 然后自然地过渡到下一个问题，像朋友聊天一样流畅
- 每次只问一个问题，不要一次抛出多个问题
- 回复长度控制在 80‑200 字，简洁有温度

## 行为准则
- 追问阶段你的工作就是倾听和提问，把分析留给后续的报告生成阶段
- 结合用户已透露的信息来追问，体现你在认真跟进
- 不问用户已经明确回答过的问题
- 如果用户回答模糊，温和地引导对方展开，而不是直接跳到下一个话题"""

        # User prompt: current context and specific instruction
        user_prompt = f"""当前日期：{today}

已知用户信息：
{user_context if user_context else "（暂无）"}

本轮需要覆盖的话题方向：
{chr(10).join(f"- {t}" for t in topics)}

已完成的对话：
{history_text}

本轮任务：
{instruction}

请直接输出你的回复（纯文本，不要 JSON，不要 Markdown）。"""

        try:
            response = self.llm.chat(
                user_message=user_prompt,
                system_prompt=system_prompt,
                temperature=0.65,
                max_tokens=700,
            )
            return response.strip()
        except Exception:
            if is_retry:
                return "我理解你可能还在思考。没关系，我们可以换个角度——你目前最关心的是什么？"
            elif len(history) >= 5:
                return "感谢你的分享，我已经对你的情况有了比较全面的了解。在进入分析之前，还有什么想补充的吗？"
            else:
                return "我明白了。接下来我想更深入地了解你的具体情况，方便的话可以详细说说吗？"
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
