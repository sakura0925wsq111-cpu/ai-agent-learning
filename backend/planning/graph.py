# -*- coding: utf-8 -*-
"""LangGraph-powered Growth Mode orchestration graph.

Provides three key capabilities:
  1. Interrupt/Resume — SQLite-backed checkpointer persists state automatically.
  2. Human-in-the-Loop — interrupt_before=["planning_build_report"] pauses after analysis.
  3. Streaming — each node completion emits a state update, consumed via SSE.

Graph topology:
    router -> planning_follow_up <-> (user answers) -> planning_analyze -> [INTERRUPT] -> planning_build_report -> END
"""

from __future__ import annotations

import json
import os
from typing import Any, TypedDict

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command
from loguru import logger


# ── GrowthState ────────────────────────────────────────────────

class GrowthState(TypedDict, total=False):
    """Shared state across all graph nodes."""

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


# ── Helpers ────────────────────────────────────────────────────

def _noop_continue(self: Any, msg: str) -> dict[str, Any]:
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


# ── Graph builder (async — needs checkpointer) ─────────────────

async def build_growth_graph(
    llm_service: Any,
    planning_router: Any,
) -> StateGraph:
    """Build and compile the Growth Mode LangGraph StateGraph.

    Must be called inside an async context because AsyncSqliteSaver
    requires async connection setup.
    """

    # ── Node: router ───────────────────────────────────────────
    def _router_node(state: GrowthState) -> dict[str, Any]:
        return {"stage": state.get("stage", "questioning")}

    def _route_router(state: GrowthState) -> str:
        return "planning"

    # ── Node: planning_follow_up ────────────────────────────────
    def _planning_follow_up_node(state: GrowthState) -> dict[str, Any]:
        agent_type: str = state.get("agent_type", "career")
        message: str = state.get("user_message", "").strip()
        correction: str = state.get("user_correction", "").strip()
        last_q: str = state.get("last_question", "")

        agent = planning_router.get_agent(agent_type)
        _restore_agent_state(agent, state)

        if correction:
            agent.state.record_follow_up(last_q or "correction", correction)
            agent.state.ambiguous_count = 0
            question = agent._generate_dynamic_question(is_retry=False, last_answer=correction)
            updates = _save_agent_state(agent)
            updates.update({
                "agent_message": question, "last_question": question,
                "stage": "questioning", "user_correction": "",
            })
            return updates

        if not message and agent.state.follow_up_round == 0:
            question = agent._generate_dynamic_question(is_retry=False, last_answer="")
            updates = _save_agent_state(agent)
            updates.update({
                "agent_message": question, "last_question": question,
                "stage": "questioning", "user_correction": "",
            })
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
                updates.update({
                    "stage": "analyzing",
                    "agent_message": "正在分析你的情况，请稍候...",
                })
            else:
                last_answer = message
                is_retry = agent.state.ambiguous_count > 0 and agent.state.retry_count > 0
                question = agent._generate_dynamic_question(
                    is_retry=is_retry, last_answer=last_answer,
                )
                updates.update({
                    "agent_message": question, "last_question": question,
                    "stage": "questioning",
                })
            return updates

        return {}

    def _route_follow_up(state: GrowthState) -> str:
        if state.get("follow_up_complete", False):
            return "analyze"
        return "follow_up"

    # ── Node: planning_analyze ──────────────────────────────────
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
        parts: list[str] = ["📊 **分析结果**", ""]

        status_text: str = analysis.get("current_status", "")
        if status_text:
            parts.append(f"**现状评估：**{status_text}")
            parts.append("")

        directions: list[dict] = analysis.get("directions", [])
        if directions:
            parts.append("**方向评估：**")
            for d in directions:
                name = d.get("name", "")
                score = d.get("match_score", 0)
                reasoning = d.get("reasoning", "")
                parts.append(f"- {name}（匹配度 {score}%）：{reasoning}")
            parts.append("")

        advantages: list[dict] = analysis.get("advantages", [])
        if advantages:
            parts.append("**你的优势：**")
            for a in advantages:
                point = a.get("point", "")
                detail = a.get("detail", "")
                parts.append(f"- {point}：{detail}")
            parts.append("")

        parts.append("---")
        parts.append("如果分析方向正确，请回复「**继续**」生成完整报告。")
        parts.append("如果想调整方向，请告诉我你想往哪个方向发展。")

        updates.update({
            "agent_message": "\n".join(parts),
            "stage": "analyzing", "user_correction": "", "last_question": "",
        })
        return updates

    # ── Node: planning_build_report ─────────────────────────────
    def _planning_build_report_node(state: GrowthState) -> dict[str, Any]:
        agent_type: str = state.get("agent_type", "career")

        agent = planning_router.get_agent(agent_type)
        _restore_agent_state(agent, state)

        original = agent._continue_workflow
        agent._continue_workflow = _noop_continue
        try:
            agent._handle_identify_problems_split("")
            agent._handle_set_goals_split("")
            agent._handle_build_plan_split("")
            agent._handle_generate_output_split("")
        finally:
            agent._continue_workflow = original

        updates = _save_agent_state(agent)

        report = agent.state.output
        completion_msg = f"✅ {agent.agent_label}分析已完成！请查看报告。"

        updates.update({
            "agent_message": completion_msg,
            "stage": "report", "finished": True,
            "report": report, "output": report,
        })
        return updates

    # ── Assemble ────────────────────────────────────────────────
    builder = StateGraph(GrowthState)

    builder.add_node("router", _router_node)
    builder.add_node("planning_follow_up", _planning_follow_up_node)
    builder.add_node("planning_analyze", _planning_analyze_node)
    builder.add_node("planning_build_report", _planning_build_report_node)

    builder.set_entry_point("router")

    builder.add_conditional_edges("router", _route_router, {"planning": "planning_follow_up"})
    builder.add_conditional_edges("planning_follow_up", _route_follow_up, {
        "follow_up": END, "analyze": "planning_analyze",
    })
    builder.add_edge("planning_analyze", "planning_build_report")
    builder.add_edge("planning_build_report", END)

    # ── SQLite checkpointer ─────────────────────────────────────
    import aiosqlite
    db_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "data", "growth_checkpoints.db"
    )
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = await aiosqlite.connect(db_path)
    checkpointer = AsyncSqliteSaver(conn)
    logger.info("GrowthGraph: AsyncSqliteSaver connected at {}", db_path)

    return builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["planning_build_report"],
    )
