# -*- coding: utf-8 -*-
"""LangGraph-powered Growth Mode orchestration graph.

Graph topology (FULL):
    router ──→ ├── planning_follow_up → analyze → [?] → build_report
                └── sandbox_discovery → sandbox_projection → planning_follow_up

Capabilities:
  1. SQLite persistence (AsyncSqliteSaver) — survives server restart
  2. Auto-complete — analysis flows directly into report generation
  3. Intelligent routing — ambiguous → sandbox, clear goal → planning
  4. Sandbox integration — discovery → projection → handoff to planning
"""

from __future__ import annotations

import json
import os
from typing import Any, TypedDict

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command
from loguru import logger

class GrowthState(TypedDict, total=False):
    user_id: str
    agent_type: str
    session_id: str
    user_message: str
    user_correction: str
    planning_state_json: str
    follow_up_round: int
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

def _save_agent_state(agent: Any) -> dict[str, Any]:
    return {
        "planning_state_json": json.dumps(agent.state.to_dict(), ensure_ascii=False),
        "follow_up_round": agent.state.follow_up_round,
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


    return "\n".join(parts)# ── Graph builder ──────────────────────────────────────────────

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

    def _route_router(state: GrowthState) -> str:
        """Always route to planning ? sandbox has its own entry point."""
        return "planning"

    # ── Node: planning_follow_up ────────────────────────────────
    def _planning_follow_up_node(state: GrowthState) -> dict[str, Any]:
        agent_type: str = state.get("agent_type", "career")
        message: str = state.get("user_message", "").strip()
        correction: str = state.get("user_correction", "").strip()
        last_q: str = state.get("last_question", "")
        chosen: str = state.get("chosen_path", "")

        # If coming from sandbox, use chosen path
        if chosen and not agent_type:
            agent_type = chosen

        agent = planning_router.get_agent(agent_type)
        _restore_agent_state(agent, state)

        if correction:
            agent.state.record_follow_up(last_q or "correction", correction)
            agent.state.ambiguous_count = 0
            question = agent._generate_dynamic_question(is_retry=False, last_answer=correction)
            updates = _save_agent_state(agent)
            updates.update({"agent_message": question, "last_question": question,
                            "stage": "questioning", "user_correction": ""})
            return updates

        if not message and agent.state.follow_up_round == 0:
            question = agent._generate_dynamic_question(is_retry=False, last_answer="")
            updates = _save_agent_state(agent)
            updates.update({"agent_message": question, "last_question": question,
                            "stage": "questioning", "user_correction": "", "chosen_path": ""})
            return updates

        if message:
            original = agent._continue_workflow
            agent._continue_workflow = _noop_continue
            try:
                agent._handle_follow_up(message)
            finally:
                agent._continue_workflow = original
            updates = _save_agent_state(agent)
            if agent.state.follow_up_complete:
                updates.update({"stage": "awaiting", "awaiting_trigger": True,
                                "agent_message": "信息收集完毕，可以开始规划了。准备好了就说\"开始规划\"吧！"})
            else:
                is_retry = agent.state.ambiguous_count > 0 and agent.state.retry_count > 0
                question = agent._generate_dynamic_question(is_retry=is_retry, last_answer=message)
                updates.update({"agent_message": question, "last_question": question, "stage": "questioning"})
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

        # —— Guard: if analysis already done and user says "继续", skip to build_report ——
        # Check both LangGraph state and agent state for existing analysis
        state_analysis = state.get("analysis", {})
        agent_analysis = agent.state.analysis if hasattr(agent.state, "analysis") else {}
        existing = state_analysis if state_analysis and state_analysis.get("current_status") else agent_analysis
        has_analysis = existing and existing.get("current_status")
        msg = state.get("user_message", "").strip()
        continue_keywords = ["继续", "生成", "可以", "好的", "行", "ok", "yes", "go", "开始规划", "开始", "继续规划", "下一步"]
        user_wants_continue = msg and any(kw in msg for kw in continue_keywords)
        if has_analysis and user_wants_continue and not correction:
            logger.info("PlanningAgent[{}]: analysis exists, user says continue - skipping to build_report", agent_type)
            return {
                "stage": "report",
                "agent_message": "好的，正在生成完整规划报告...",
                "analysis": existing,
                "follow_up_complete": True,
            }

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
        agent_label = agent.agent_label
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
        parts.append('• 回复「继续」让我生成完整的规划报告')
        parts.append('• 或者告诉我哪里需要调整方向')
        parts.append('')
        parts.append('你觉得这个方向准确吗？')

        message = '\n'.join(parts)
        updates.update({"agent_message": message, "stage": "analyzing",
                        "user_correction": "", "last_question": ""})
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
        message = _format_professional_report(report, agent.agent_label)
        updates.update({"agent_message": message,
                        "stage": "report", "finished": True, "report": report, "output": report,
                        "progress": 100.0})
        logger.info("PlanningAgent[{}]: report complete (100%%)", agent_type)
        return updates

    # ── Node: sandbox_discovery ─────────────────────────────────
    def _sandbox_discovery_node(state: GrowthState) -> dict[str, Any]:
        """Discovery phase: 5-7 rounds of user profiling via sandbox."""
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

        parts = ["?? **Path Comparison Results**", ""]
        for p in projections:
            pt = p.get("path_type", "")
            label = SANDBOX_PATHS.get(pt, pt)
            insight = p.get("core_insight", "")
            parts.append(f"**{label}:** {insight}")
            parts.append("")
        if summary:
            parts.append(f"**Summary:** {summary}")
        parts.append("")
        parts.append("---")
        parts.append("Which path would you like to explore? Reply: career / graduate / civil / major")

        # Determine chosen path from user message
        msg = state.get("user_message", "").strip().lower()
        path_map = {"career": "career", "就业": "career", "工作": "career",
                     "graduate": "graduate", "考研": "graduate", "读研": "graduate",
                     "civil": "civil", "考公": "civil", "考编": "civil",
                     "major": "major", "转专业": "major", "换专业": "major"}
        chosen = ""
        for kw, pt in path_map.items():
            if kw in msg or kw in msg:
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
        """Wait for user confirmation before starting analysis."""
        message: str = state.get("user_message", "").strip()
        trigger_keywords = ["开始规划", "开始", "规划", "好的", "可以", "行", "嗯", "好", "生成", "来吧", "ok", "yes", "go", "开始分析"]
        if any(kw in message for kw in trigger_keywords):
            return {
                "awaiting_trigger": False,
                "stage": "analyzing",
                "agent_message": "好的，正在为你生成规划报告...",
            }
        return {
            "agent_message": "准备好了就说\"开始规划\"，我们马上开始！",
        }

    def _route_await_trigger(state: GrowthState) -> str:
        if state.get("awaiting_trigger", True):
            return "await"
        return "analyze"

    # ── Assemble graph ──────────────────────────────────────────
    builder = StateGraph(GrowthState)

    builder.add_node("router", _router_node)
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
    route_targets = {"planning": "planning_follow_up"}
    if has_sandbox:
        route_targets["sandbox"] = "sandbox_discovery"
    builder.add_conditional_edges("router", _route_router, route_targets)

    # Planning branch
    builder.add_conditional_edges("planning_follow_up", _route_follow_up,
                                  {"follow_up": END, "await": "planning_await_trigger", "analyze": "planning_analyze"})
    builder.add_conditional_edges("planning_await_trigger", _route_await_trigger,
                                  {"await": END, "analyze": "planning_analyze"})
    builder.add_edge("planning_analyze", "planning_build_report")
    builder.add_edge("planning_build_report", END)

    # Sandbox branch
    if has_sandbox:
        builder.add_conditional_edges("sandbox_discovery", _route_sandbox,
                                      {"discovery": END, "projection": "sandbox_projection"})
        builder.add_conditional_edges("sandbox_projection", _route_projection,
                                      {"wait": END, "handoff": "planning_follow_up"})

    # ── SQLite checkpointer ─────────────────────────────────────
    import aiosqlite
    db_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "data", "growth_checkpoints.db"
    )
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = await aiosqlite.connect(db_path)
    checkpointer = AsyncSqliteSaver(conn)
    logger.info("GrowthGraph: AsyncSqliteSaver at {}", db_path)

    return builder.compile(
        checkpointer=checkpointer,
    )
