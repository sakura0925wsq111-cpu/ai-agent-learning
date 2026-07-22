# -*- coding: utf-8 -*-
"""LangGraph-powered Growth Mode orchestration graph.

Graph topology:
    router -> planning_follow_up <-> (user answers) -> planning_analyze -> [INTERRUPT] -> planning_build_report -> END

Capabilities:
  1. Interrupt/Resume — InMemorySaver checkpointer (migrate to SQLite for persistence)
  2. Human-in-the-Loop — interrupt_before=["planning_build_report"]
  3. Streaming — graph.astream(stream_mode="updates") for SSE
"""

from __future__ import annotations

import json
import os
from typing import Any, TypedDict

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import InMemorySaver
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


async def build_growth_graph(llm_service: Any, planning_router: Any) -> StateGraph:
    """Build and compile the Growth Mode LangGraph StateGraph."""

    def _router_node(state: GrowthState) -> dict[str, Any]:
        return {"stage": state.get("stage", "questioning")}

    def _route_router(state: GrowthState) -> str:
        return "planning"

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
            updates.update({"agent_message": question, "last_question": question,
                            "stage": "questioning", "user_correction": ""})
            return updates

        if not message and agent.state.follow_up_round == 0:
            question = agent._generate_dynamic_question(is_retry=False, last_answer="")
            updates = _save_agent_state(agent)
            updates.update({"agent_message": question, "last_question": question,
                            "stage": "questioning", "user_correction": ""})
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
                updates.update({"stage": "analyzing", "agent_message": "Analyzing..."})
            else:
                is_retry = agent.state.ambiguous_count > 0 and agent.state.retry_count > 0
                question = agent._generate_dynamic_question(is_retry=is_retry, last_answer=message)
                updates.update({"agent_message": question, "last_question": question, "stage": "questioning"})
            return updates
        return {}

    def _route_follow_up(state: GrowthState) -> str:
        return "analyze" if state.get("follow_up_complete", False) else "follow_up"

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
        parts = ["📊 **Analysis Results**", ""]
        st = analysis.get("current_status", "")
        if st:
            parts.append(f"**Status:** {st}")
            parts.append("")
        dirs = analysis.get("directions", [])
        if dirs:
            parts.append("**Directions:**")
            for d in dirs:
                parts.append(f"- {d.get('name','')} (match {d.get('match_score',0)}%): {d.get('reasoning','')}")
            parts.append("")
        advs = analysis.get("advantages", [])
        if advs:
            parts.append("**Advantages:**")
            for a in advs:
                parts.append(f"- {a.get('point','')}: {a.get('detail','')}")
            parts.append("")
        parts.append("---")
        parts.append('Reply "continue" to generate full report, or tell me to adjust direction.')
        updates.update({"agent_message": "\n".join(parts), "stage": "analyzing",
                        "user_correction": "", "last_question": ""})
        return updates

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
        updates.update({"agent_message": f"Done! {agent.agent_label} report ready.",
                        "stage": "report", "finished": True, "report": report, "output": report})
        return updates

    builder = StateGraph(GrowthState)
    builder.add_node("router", _router_node)
    builder.add_node("planning_follow_up", _planning_follow_up_node)
    builder.add_node("planning_analyze", _planning_analyze_node)
    builder.add_node("planning_build_report", _planning_build_report_node)
    builder.set_entry_point("router")
    builder.add_conditional_edges("router", _route_router, {"planning": "planning_follow_up"})
    builder.add_conditional_edges("planning_follow_up", _route_follow_up, {"follow_up": END, "analyze": "planning_analyze"})
    builder.add_edge("planning_analyze", "planning_build_report")
    builder.add_edge("planning_build_report", END)

    checkpointer = InMemorySaver()
    logger.info("GrowthGraph: InMemorySaver ready")

    return builder.compile(checkpointer=checkpointer, interrupt_before=["planning_build_report"])
