# -*- coding: utf-8 -*-
"""LangGraph-powered Growth Mode orchestration graph.

Graph topology (FULL):
    router → turn_analysis → [knowledge] → advisory_response → await_trigger
           → analyze → [confirm] → build_report
           └→ sandbox_discovery → sandbox_projection → planning_follow_up

Capabilities:
  1. SQLite persistence (AsyncSqliteSaver) — survives server restart
  2. Human confirmation — preliminary analysis stops before report generation
  3. Intelligent routing — ambiguous → sandbox, clear goal → planning
  4. Sandbox integration — discovery → projection → handoff to planning
"""

from __future__ import annotations

import json
import os
from typing import Any, TypedDict

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from loguru import logger

class GrowthState(TypedDict, total=False):
    user_id: str
    agent_type: str
    session_id: str
    user_message: str
    user_correction: str
    planning_state_json: str
    follow_up_round: int
    questions_asked: int
    follow_up_complete: bool
    analysis: dict[str, Any]
    identified_problems: list[dict[str, Any]]
    long_term_goal: str
    action_plan: list[dict[str, Any]]
    output: dict[str, Any]
    stage: str
    finished: bool
    agent_message: str
    report: dict[str, Any] | None
    error_message: str
    last_question: str
    # Sandbox state (serialised)
    sandbox_state_json: str
    sandbox_phase: str
    chosen_path: str
    # Await trigger (between FOLLOW_UP and ANALYZE)
    awaiting_trigger: bool
    # Explicit confirmation gate between preliminary analysis and final report
    report_requested: bool
    # Per-turn advisory routing
    turn_analysis: dict[str, Any]
    knowledge_context: str
    knowledge_evidence: dict[str, Any]

# ── Helpers ────────────────────────────────────────────────────

def _noop_continue(msg: str) -> dict[str, Any]:
    return {"_noop": True}

def _restore_agent_state(agent: Any, state: GrowthState) -> None:
    ps_json = state.get("planning_state_json", "")
    if ps_json:
        from planning.state import PlanningState
        ps = PlanningState.from_dict(json.loads(ps_json))
        agent.restore_state(ps)
    else:
        agent.init_state()
    last_question = state.get("last_question", "") or agent.state.last_asked_question
    agent._last_asked_question = last_question
    agent.state.last_asked_question = last_question

def _save_agent_state(agent: Any) -> dict[str, Any]:
    return {
        "planning_state_json": json.dumps(agent.state.to_dict(), ensure_ascii=False),
        "follow_up_round": agent.state.follow_up_round,
        "questions_asked": agent.state.questions_asked,
        "follow_up_complete": agent.state.follow_up_complete,
        "analysis": agent.state.analysis,
        "identified_problems": agent.state.identified_problems,
        "long_term_goal": agent.state.long_term_goal,
        "action_plan": agent.state.action_plan,
        "output": agent.state.output,
        "finished": agent.state.finished,
    }

# ── Intent detection for router ────────────────────────────────

# ── Professional Report Formatter ────────────────────────────────────────

def _format_professional_report(report: dict[str, Any], agent_label: str) -> str:
    """Convert internal report dict into a clean, human-readable message (no Markdown syntax)."""
    parts: list[str] = []
    summary = report.get("summary", "")
    current_status = report.get("current_status", "")
    goal = report.get("goal", "")
    main_problem = report.get("main_problem", "")
    advantages = report.get("advantages", [])
    risks = report.get("risks", [])
    action_plan = report.get("action_plan", [])
    next_question = report.get("next_question", "")

    parts.append(f"你的{agent_label}报告")
    parts.append("")
    if summary:
        parts.append(summary)
        parts.append("")
    status_text = current_status or main_problem or ""
    if status_text:
        parts.append("现状分析")
        parts.append(status_text)
        parts.append("")
    if goal:
        parts.append("核心目标")
        parts.append(goal)
        parts.append("")
    if advantages and isinstance(advantages, list) and len(advantages) > 0:
        parts.append("个人优势")
        for a in advantages:
            if isinstance(a, dict):
                point = a.get("point") or a.get("name") or a.get("strength") or ""
                detail = a.get("detail") or a.get("description") or ""
                if point:
                    line = f"  {point}"
                    if detail:
                        line += f"：{detail}"
                    parts.append(line)
            elif isinstance(a, str):
                parts.append(f"  {a}")
        parts.append("")
    if risks and isinstance(risks, list) and len(risks) > 0:
        parts.append("风险提示")
        for r in risks:
            if isinstance(r, dict):
                risk_name = r.get("risk") or r.get("point") or r.get("name") or (next(iter(r.values()), "") if r else "")
                mitigation = r.get("mitigation") or r.get("solution") or r.get("detail") or ""
                if risk_name:
                    line = f"  {risk_name}"
                    if mitigation:
                        line += f" — 建议：{mitigation}"
                    parts.append(line)
            elif isinstance(r, str):
                parts.append(f"  {r}")
        parts.append("")
    if action_plan and isinstance(action_plan, list) and len(action_plan) > 0:
        parts.append("行动路径")
        for i, phase in enumerate(action_plan, 1):
            if isinstance(phase, dict):
                name = phase.get("phase") or phase.get("name") or phase.get("title") or f"阶段{i}"
                duration = phase.get("duration") or phase.get("timeline") or ""
                header = name + (f"（{duration}）" if duration else "")
                parts.append(f"  {header}")
                tasks = phase.get("tasks", [])
                if tasks and isinstance(tasks, list):
                    for t in tasks:
                        if isinstance(t, dict):
                            task_text = t.get("task") or t.get("title") or t.get("name") or (next(iter(t.values()), "") if t else "")
                            if task_text:
                                parts.append(f"    - {task_text}")
                        elif isinstance(t, str):
                            parts.append(f"    - {t}")
                elif phase.get("detail") or phase.get("description"):
                    parts.append(f"    {phase.get('detail') or phase.get('description', '')}")
            elif isinstance(phase, str):
                parts.append(f"  {phase}")
        parts.append("")
    if next_question:
        parts.append(next_question)
        parts.append("")
    parts.append("如对以上规划有任何疑问，随时告诉我。")
    return "\n".join(parts)

# ── Graph builder ──────────────────────────────────────────────

async def build_growth_graph(
    llm_service: Any,
    planning_router: Any,
    sandbox_orchestrator: Any = None,
) -> StateGraph:
    """Build and compile the Growth Mode LangGraph StateGraph."""

    # ── Node: router ───────────────────────────────────────────
    def _router_node(state: GrowthState) -> dict[str, Any]:
        """Pass-through: sandbox and planning have separate entry points."""
        return {"stage": state.get("stage", "questioning")}

    def _is_planning_trigger(message: str) -> bool:
        trigger_keywords = (
            "开始规划", "开始分析", "生成报告", "开始吧", "来吧",
            "继续规划", "下一步", "可以开始了",
        )
        return any(keyword in message for keyword in trigger_keywords)

    def _route_router(state: GrowthState) -> str:
        """Route explicit correction/approval requests to their target step."""
        if state.get("report_requested", False):
            return "report"
        if state.get("user_correction", "").strip():
            return "analyze"
        if state.get("awaiting_trigger", False):
            message = state.get("user_message", "").strip()
            # Questions asked while waiting still deserve a direct answer. Only
            # an actual workflow trigger should bypass turn analysis.
            return "await" if not message or _is_planning_trigger(message) else "planning"
        return "planning"

    # ── Node: turn analysis + optional knowledge grounding ─────
    def _planning_turn_analysis_node(state: GrowthState) -> dict[str, Any]:
        from planning.conversation import analyze_turn
        from planning.readiness import evaluate_advice_readiness
        from planning.state import MAX_FOLLOW_UP_ROUNDS

        agent_type = state.get("agent_type", "career")
        agent = planning_router.get_agent(agent_type)
        _restore_agent_state(agent, state)
        message = state.get("user_message", "").strip()
        readiness = evaluate_advice_readiness(
            agent_type,
            user_profile=agent.state.user_profile,
            follow_up_history=agent.state.follow_up_history,
            unavailable_dimensions=agent.state.unavailable_dimensions,
            questions_asked=agent.state.questions_asked,
            max_questions=MAX_FOLLOW_UP_ROUNDS,
            current_question=agent.state.last_asked_question,
            current_dimension=agent.state.last_asked_dimension,
            current_answer=message,
        )
        analysis = analyze_turn(
            llm_service,
            agent_type=agent_type,
            agent_label=agent.agent_label,
            message=message,
            user_context=agent.state.build_context_for_llm(),
            follow_up_round=agent.state.questions_asked,
            max_follow_up_rounds=MAX_FOLLOW_UP_ROUNDS,
            readiness=readiness,
        )
        return {
            "turn_analysis": analysis,
            "knowledge_context": "",
            "knowledge_evidence": {},
            "stage": "questioning",
        }

    def _route_turn_analysis(state: GrowthState) -> str:
        analysis = state.get("turn_analysis", {})
        return "knowledge" if analysis.get("needs_knowledge", False) else "respond"

    def _planning_knowledge_node(state: GrowthState) -> dict[str, Any]:
        from planning.knowledge import get_knowledge_context

        analysis = state.get("turn_analysis", {})
        evidence = get_knowledge_context(
            state.get("agent_type", "career"),
            analysis.get("knowledge_topics", []),
        )
        return {
            "knowledge_context": evidence.get("text", ""),
            "knowledge_evidence": evidence,
        }

    # ── Node: planning_follow_up ────────────────────────────────
    def _planning_follow_up_node(state: GrowthState) -> dict[str, Any]:
        agent_type: str = state.get("agent_type", "career")
        message: str = state.get("user_message", "").strip()
        correction: str = state.get("user_correction", "").strip()
        last_q: str = state.get("last_question", "")
        chosen: str = state.get("chosen_path", "")
        turn_analysis = state.get("turn_analysis", {})
        knowledge_context = state.get("knowledge_context", "")

        # If coming from sandbox, use chosen path
        if chosen and not agent_type:
            agent_type = chosen

        agent = planning_router.get_agent(agent_type)
        _restore_agent_state(agent, state)
        if turn_analysis.get("readiness"):
            agent.state.advice_readiness = dict(turn_analysis["readiness"])

        if correction:
            agent.state.record_follow_up(last_q or "correction", correction)
            agent.state.ambiguous_count = 0
            question = agent._generate_dynamic_question(is_retry=False, last_answer=correction)
            agent.state.mark_question_asked(question)
            updates = _save_agent_state(agent)
            updates.update({"agent_message": question, "last_question": question,
                            "stage": "questioning", "user_correction": ""})
            return updates

        if not message and not agent.state.follow_up_complete:
            question = agent._generate_dynamic_question(
                is_retry=False,
                last_answer="",
                turn_analysis=turn_analysis,
                knowledge_context=knowledge_context,
            )
            if (
                turn_analysis.get("should_ask") is False
                and turn_analysis.get("ready_for_advice", True)
            ):
                agent.state.follow_up_complete = True
                agent.state.advance_step()
                agent._last_asked_question = ""
                agent.state.last_asked_question = ""
                updates = _save_agent_state(agent)
                updates.update({
                    "agent_message": (
                        f"{question}\n\n已有信息足够形成初步判断。"
                        "如果你希望生成完整方案，回复“开始规划”即可。"
                    ),
                    "last_question": "",
                    "stage": "awaiting",
                    "awaiting_trigger": True,
                    "user_correction": "",
                    "chosen_path": "",
                })
                return updates
            dimension = turn_analysis.get("readiness", {}).get("next_dimension", "")
            agent.state.mark_question_asked(question, dimension)
            agent._last_asked_question = question
            updates = _save_agent_state(agent)
            updates.update({"agent_message": question, "last_question": question,
                            "stage": "questioning", "user_correction": "", "chosen_path": ""})
            return updates

        if not message and agent.state.follow_up_complete:
            updates = _save_agent_state(agent)
            updates.update({
                "stage": "awaiting",
                "awaiting_trigger": True,
                "agent_message": "已带入你在多路径对比中提供的信息。确认无误后，回复“开始规划”即可进入分析。",
            })
            return updates

        if message and agent.state.follow_up_complete:
            response = agent._generate_dynamic_question(
                is_retry=False,
                last_answer=message,
                turn_analysis={**turn_analysis, "should_ask": False},
                knowledge_context=knowledge_context,
            )
            agent.state.follow_up_history.append({"q": "补充咨询", "a": message})
            updates = _save_agent_state(agent)
            updates.update({
                "stage": "awaiting",
                "awaiting_trigger": True,
                "agent_message": (
                    f"{response}\n\n如果你希望生成完整方案，回复“开始规划”即可。"
                ),
                "last_question": "",
            })
            return updates

        if message:
            original = agent._continue_workflow
            agent._continue_workflow = _noop_continue
            try:
                response = agent._handle_follow_up(
                    message,
                    turn_analysis=turn_analysis,
                    knowledge_context=knowledge_context,
                )
            finally:
                agent._continue_workflow = original
            updates = _save_agent_state(agent)
            if agent.state.follow_up_complete:
                updates.update({"stage": "awaiting", "awaiting_trigger": True,
                                "agent_message": response.get("message", ""),
                                "last_question": ""})
            else:
                reply = response.get("message", "")
                has_question = response.get("step") == "follow_up"
                updates.update({
                    "agent_message": reply,
                    "last_question": reply if has_question else "",
                    "stage": "questioning",
                })
            return updates
        return {}

    def _route_follow_up(state: GrowthState) -> str:
        if state.get("awaiting_trigger", False):
            return "await"
        if state.get("follow_up_complete", False):
            return "analyze"
        return "follow_up"

    # ── Node: planning_analyze ───────────────────────────────────
    def _planning_analyze_node(state: GrowthState) -> dict[str, Any]:
        agent_type: str = state.get("agent_type", "career")
        correction: str = state.get("user_correction", "").strip()
        agent = planning_router.get_agent(agent_type)
        _restore_agent_state(agent, state)
        from planning.state import WorkflowStep

        agent.state.set_step(WorkflowStep.ANALYZE)
        if correction:
            agent.state.user_profile["_correction"] = correction
        original = agent._continue_workflow
        agent._continue_workflow = _noop_continue
        try:
            agent._handle_analyze_split("")
        finally:
            agent._continue_workflow = original
        updates = _save_agent_state(agent)
        analysis = agent.state.analysis

        # ── Build natural-language preliminary assessment ─────────────
        st = analysis.get("current_status", "")
        dirs = analysis.get("directions", [])
        advs = analysis.get("advantages", [])

        parts = []

        # 1) Summary of what's been gathered
        if st:
            parts.append('根据我们刚才的交流，我对你的情况有了初步了解。')
            parts.append('')
            parts.append(st)
            parts.append('')

        # 2) Directions analysis — conversational, not Markdown table
        if dirs:
            parts.append('基于你的背景，我梳理了以下几个方向：')
            parts.append('')
            for i, d in enumerate(dirs, 1):
                name = d.get('name', '')
                score = d.get('match_score', 0)
                reasoning = d.get('reasoning', '')
                level = '非常适合' if score >= 80 else '比较适合' if score >= 60 else '可以考虑'
                parts.append(f'{i}. {name} — {level}（{reasoning}）')
            parts.append('')

        # 3) Advantages — reframed as "your strengths"
        if advs:
            parts.append('同时我也注意到你的几个优势：')
            parts.append('')
            for a in advs:
                point = a.get('point', '')
                detail = a.get('detail', '')
                parts.append(f'✓ {point}：{detail}')
            parts.append('')

        # 4) Next step prompt
        parts.append('---')
        parts.append('')
        parts.append('以上是我的初步判断。你可以：')
        parts.append('')
        parts.append('• 点击「确认并生成报告」生成完整规划')
        parts.append('• 或者告诉我哪里需要调整方向')
        parts.append('')
        parts.append('你觉得这个方向准确吗？')

        message = '\n'.join(parts)
        updates.update({"agent_message": message, "stage": "analyzing",
                        "user_correction": "", "last_question": "", "progress": 40.0})
        return updates
    # ── Node: planning_build_report ─────────────────────────────
    def _planning_build_report_node(state: GrowthState) -> dict[str, Any]:
        agent_type: str = state.get("agent_type", "career")
        agent = planning_router.get_agent(agent_type)
        _restore_agent_state(agent, state)
        logger.info("PlanningAgent[{}]: building report... phase=identify_problems", agent_type)
        original = agent._continue_workflow
        agent._continue_workflow = _noop_continue
        try:
            logger.info("PlanningAgent[{}]: phase=identify_problems (20%%)", agent_type)
            agent._handle_identify_problems_split("")
            logger.info("PlanningAgent[{}]: phase=set_goals (40%%)", agent_type)
            agent._handle_set_goals_split("")
            logger.info("PlanningAgent[{}]: phase=build_plan (60%%)", agent_type)
            agent._handle_build_plan_split("")
            logger.info("PlanningAgent[{}]: phase=generate_output (80%%)", agent_type)
            agent._handle_generate_output_split("")
        finally:
            agent._continue_workflow = original
        updates = _save_agent_state(agent)
        report = agent.state.output
        message = "完整规划报告已生成。你可以查看报告，也可以继续咨询具体细节。"
        updates.update({"agent_message": message,
                        "stage": "report", "finished": True, "report": report, "output": report,
                        "progress": 100.0})
        logger.info("PlanningAgent[{}]: report complete (100%%)", agent_type)
        return updates

    # ── Node: sandbox_discovery ─────────────────────────────────
    def _sandbox_discovery_node(state: GrowthState) -> dict[str, Any]:
        """Discovery phase: advice plus up to 3 high-value clarifications."""
        if sandbox_orchestrator is None:
            return {"error_message": "Sandbox not available", "stage": "error"}

        msg = state.get("user_message", "").strip()
        uid = state.get("user_id", "")
        sid = state.get("session_id", "")

        # Restore or create sandbox session
        sb_state_json = state.get("sandbox_state_json", "")
        if sb_state_json:
            from sandbox.state import SandboxSession
            sb_sess = SandboxSession.from_dict(json.loads(sb_state_json))
            sandbox_orchestrator._sessions[sb_sess.session_id] = sb_sess
        else:
            sb_sess = sandbox_orchestrator.start_session(user_id=uid, session_id=f"sb_{sid}")

        try:
            result = sandbox_orchestrator.chat(sb_sess, msg or "Start discovery")
        except Exception as exc:
            logger.error("Sandbox discovery error: {}", exc)
            return {"error_message": str(exc), "stage": "error"}

        return {
            "sandbox_state_json": json.dumps(sb_sess.to_dict(), ensure_ascii=False),
            "sandbox_phase": result.get("phase", "discovery"),
            "agent_message": result.get("message", ""),
            "stage": "questioning",
        }

    def _route_sandbox(state: GrowthState) -> str:
        sb_state_json = state.get("sandbox_state_json", "")
        if sb_state_json:
            from sandbox.state import SandboxSession, SandboxPhase
            sb_sess = SandboxSession.from_dict(json.loads(sb_state_json))
            if sb_sess.finished or sb_sess.current_phase == SandboxPhase.COMPLETED:
                return "projection"
        return "discovery"

    # ── Node: sandbox_projection ────────────────────────────────
    def _sandbox_projection_node(state: GrowthState) -> dict[str, Any]:
        """Projection: compare paths, let user pick, handoff to planning."""
        if sandbox_orchestrator is None:
            return {"error_message": "Sandbox not available", "stage": "error"}

        sb_state_json = state.get("sandbox_state_json", "")
        if not sb_state_json:
            return {"error_message": "No sandbox state", "stage": "error"}

        from sandbox.state import SandboxSession, SANDBOX_PATHS
        sb_sess = SandboxSession.from_dict(json.loads(sb_state_json))
        sandbox_orchestrator._sessions[sb_sess.session_id] = sb_sess

        # Run projection if not done
        if not sb_sess.projection_result:
            try:
                result = sandbox_orchestrator.chat(sb_sess, "compare all paths")
            except Exception as exc:
                logger.error("Sandbox projection error: {}", exc)
                return {"error_message": str(exc), "stage": "error"}
        else:
            result = sandbox_orchestrator._build_response(sb_sess, "")

        proj = sb_sess.projection_result or {}
        projections = proj.get("projections", [])
        summary = proj.get("summary", "")

        parts = ["多路径对比结果", ""]
        for p in projections:
            pt = p.get("path_type", "")
            label = SANDBOX_PATHS.get(pt, pt)
            insight = p.get("core_insight", "")
            parts.append(f"{label}：{insight}")
            parts.append("")
        if summary:
            parts.append(f"综合建议：{summary}")
        parts.append("")
        parts.append("---")
        parts.append("你想继续深入哪个方向？请回复“就业 / 考研 / 考公 / 转专业”。")

        # Determine chosen path from user message
        msg = state.get("user_message", "").strip().lower()
        path_map = {"career": "career", "就业": "career", "工作": "career",
                     "graduate": "graduate", "考研": "graduate", "读研": "graduate",
                     "civil": "civil", "考公": "civil", "考编": "civil",
                     "major": "major", "转专业": "major", "换专业": "major"}
        chosen = ""
        for kw, pt in path_map.items():
            if kw in msg:
                chosen = pt
                break

        return {
            "sandbox_state_json": json.dumps(sb_sess.to_dict(), ensure_ascii=False),
            "sandbox_phase": "completed",
            "agent_message": "\n".join(parts),
            "stage": "questioning",
            "chosen_path": chosen if chosen else "",
        }

    def _route_projection(state: GrowthState) -> str:
        chosen = state.get("chosen_path", "")
        if chosen:
            return "handoff"
        return "wait"

    # Node: planning_await_trigger (awaits user confirmation before analysis)
    def _planning_await_trigger_node(state: GrowthState) -> dict[str, Any]:
        """Wait for user confirmation, with free-form chat in between."""
        message: str = state.get("user_message", "").strip()

        if not message:
            return {
                "awaiting_trigger": True,
                "stage": "awaiting",
                "agent_message": state.get("agent_message", "") or "信息已收集完成，回复“开始规划”进入分析。",
            }

        if _is_planning_trigger(message):
            return {
                "awaiting_trigger": False,
                "stage": "analyzing",
                "agent_message": "好的，正在为你生成规划报告...",
            }

        # Free chat: delegate to agent, keep graph layer LLM-free
        agent_type = state.get("agent_type", "career")
        agent = planning_router.get_agent(agent_type)
        _restore_agent_state(agent, state)

        response = agent.free_chat(message)
        updates = _save_agent_state(agent)
        updates["agent_message"] = response
        return updates

    def _route_await_trigger(state: GrowthState) -> str:
        if state.get("awaiting_trigger", True):
            return "await"
        return "analyze"

    # ── Assemble graph ──────────────────────────────────────────
    builder = StateGraph(GrowthState)

    builder.add_node("router", _router_node)
    builder.add_node("planning_turn_analysis", _planning_turn_analysis_node)
    builder.add_node("planning_knowledge", _planning_knowledge_node)
    builder.add_node("planning_follow_up", _planning_follow_up_node)
    builder.add_node("planning_await_trigger", _planning_await_trigger_node)
    builder.add_node("planning_analyze", _planning_analyze_node)
    builder.add_node("planning_build_report", _planning_build_report_node)

    has_sandbox = sandbox_orchestrator is not None
    if has_sandbox:
        builder.add_node("sandbox_discovery", _sandbox_discovery_node)
        builder.add_node("sandbox_projection", _sandbox_projection_node)

    builder.set_entry_point("router")

    # Router edges
    route_targets = {
        "planning": "planning_turn_analysis",
        "await": "planning_await_trigger",
        "analyze": "planning_analyze",
        "report": "planning_build_report",
    }
    if has_sandbox:
        route_targets["sandbox"] = "sandbox_discovery"
    builder.add_conditional_edges("router", _route_router, route_targets)

    builder.add_conditional_edges(
        "planning_turn_analysis",
        _route_turn_analysis,
        {"knowledge": "planning_knowledge", "respond": "planning_follow_up"},
    )
    builder.add_edge("planning_knowledge", "planning_follow_up")

    # Planning branch
    builder.add_conditional_edges("planning_follow_up", _route_follow_up,
                                  {"follow_up": END, "await": END, "analyze": "planning_analyze"})
    builder.add_conditional_edges("planning_await_trigger", _route_await_trigger,
                                  {"await": END, "analyze": "planning_analyze"})
    # Stop after preliminary analysis; final report requires explicit approval.
    builder.add_edge("planning_analyze", END)
    builder.add_edge("planning_build_report", END)

    # Sandbox branch
    if has_sandbox:
        builder.add_conditional_edges("sandbox_discovery", _route_sandbox,
                                      {"discovery": END, "projection": "sandbox_projection"})
        builder.add_conditional_edges("sandbox_projection", _route_projection,
                                      {"wait": END, "handoff": "planning_follow_up"})

    # ── SQLite checkpointer ─────────────────────────────────────
    import aiosqlite
    db_path = os.getenv("GROWTH_CHECKPOINT_DB") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "data", "growth_checkpoints.db"
    )
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = await aiosqlite.connect(db_path)
    checkpointer = AsyncSqliteSaver(conn)
    logger.info("GrowthGraph: AsyncSqliteSaver at {}", db_path)

    return builder.compile(
        checkpointer=checkpointer,
    )
