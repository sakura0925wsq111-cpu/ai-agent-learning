# -*- coding: utf-8 -*-
"""ProjectionAgent — independent agent for multi-path comparison and timeline projection.

This agent is NOT a subclass of PlanningAgent. It stands alone, receiving
N completed path reports and producing a structured comparison JSON.

Design principles:
    - Independent identity: own system_prompt, role, analysis rules
    - No subclass relationship with PlanningAgent
    - Input: N path reports + user profile
    - Output: structured comparison JSON (projections, matrix, decision guide)
    - Core constraint: never makes the decision for the user
"""

from __future__ import annotations

import json
from typing import Any

from loguru import logger

from sandbox.prompts.projection import (
    PROJECTION_SYSTEM_PROMPT,
    build_projection_user_prompt,
)
from utils.json_parser import safe_json_parse

# ── Fallback projection templates ────────────────────────────────


def _build_fallback_projection(path_type: str, path_label: str) -> dict[str, Any]:
    """Build a minimal fallback projection when LLM analysis fails for a path."""
    return {
        "path_type": path_type,
        "path_label": path_label,
        "core_insight": f"基于{path_label}报告的分析。由于系统原因，暂无法生成完整推演，以下为报告原始信息的结构化摘要。",
        "time_projection": {
            "short_term": "请参考原始报告的行动计划",
            "mid_term": "请参考原始报告的阶段目标",
            "long_term": "取决于短期和中期执行效果",
            "key_milestones": ["请参考原始报告"],
        },
        "strengths": [],
        "challenges": [],
        "best_for": f"对{path_label}方向有明确兴趣和基础的用户",
        "deal_breakers": "暂无足够信息判断",
    }


def _build_fallback_result(path_reports: dict[str, dict]) -> dict[str, Any]:
    """Build a complete fallback comparison result."""
    labels = {"career": "就业规划", "graduate": "考研规划",
              "civil": "考公考编规划", "major": "转专业规划"}

    projections = [
        _build_fallback_projection(pt, labels.get(pt, pt))
        for pt in path_reports
    ]

    return {
        "projections": projections,
        "comparison_matrix": {
            "dimensions": ["匹配度", "风险", "时间成本"],
            "scores": {},
        },
        "relationship_analysis": {
            "note": "由于系统原因，关系分析暂未完成。请查看各路径报告自行判断。",
        },
        "decision_guide": {
            "questions_to_ask_yourself": [
                "你最看重的是什么？稳定、成长还是兴趣？",
                "你能接受的最长时间投入是多少？",
                "如果第一条路走不通，你的备选方案是什么？",
            ],
            "if_you_value_X_then_Y": [],
            "possible_hybrid_strategies": [],
        },
        "key_uncertainties": [
            {"factor": "系统分析不完整", "impact": "建议重新触发对比分析", "how_to_reduce": "重试或查阅原始报告"}
        ],
        "summary": "对比分析因系统原因未能完整生成。请查看各路径的原始报告进行手动对比。建议重新触发分析。",
    }


# ── ProjectionAgent ──────────────────────────────────────────────


class ProjectionAgent:
    """Independent agent that compares N growth path reports.

    Produces a structured comparison JSON with:
        - Timeline projections for each path
        - Multi-dimensional comparison matrix
        - Path relationship analysis (exclusive, sequential, complementary)
        - Conditional decision guide (if you value X, then Y fits better)
        - Key uncertainties

    Usage:
        agent = ProjectionAgent(llm_service)
        result = agent.compare(
            user_profile={...},
            path_reports={"career": {...}, "graduate": {...}},
            discovery_context="...",
        )
    """

    # ── Known path labels ───────────────────────────────────────

    PATH_LABELS: dict[str, str] = {
        "career": "就业规划",
        "graduate": "考研规划",
        "civil": "考公考编规划",
        "major": "转专业规划",
    }

    def __init__(self, llm_service: Any) -> None:
        """Initialize the projection agent.

        Args:
            llm_service: LLMService instance for API calls.
        """
        self.llm = llm_service
        logger.info("ProjectionAgent initialized")

    # ── Public API ──────────────────────────────────────────────

    def compare(
        self,
        user_profile: dict[str, Any],
        path_reports: dict[str, dict[str, Any]],
        discovery_context: str = "",
    ) -> dict[str, Any]:
        """Run multi-path comparison analysis.

        Args:
            user_profile: Accumulated user profile from discovery phase.
            path_reports: Dict of {path_type: report_dict} from planning agents.
            discovery_context: Formatted discovery history string.

        Returns:
            Structured comparison JSON dict.
        """
        if not path_reports:
            logger.warning("ProjectionAgent.compare called with empty path_reports")
            return self._empty_result()

        logger.info(
            "ProjectionAgent: comparing {} paths: {}",
            len(path_reports), list(path_reports.keys()),
        )

        user_prompt = build_projection_user_prompt(
            user_profile=user_profile,
            path_reports=path_reports,
            discovery_context=discovery_context,
        )

        try:
            raw_response = self.llm.chat(
                user_message=user_prompt,
                system_prompt=PROJECTION_SYSTEM_PROMPT,
                temperature=0.3,  # low temperature for structured output
                max_tokens=4096,  # large output for full comparison
            )

            result = safe_json_parse(raw_response)
            if result is None:
                logger.warning("ProjectionAgent: failed to parse LLM output, using fallback")
                logger.debug("Raw response (first 500 chars): {}", raw_response[:500])
                return _build_fallback_result(path_reports)

            # Validate and normalize the result
            result = self._normalize_result(result, path_reports)
            logger.info("ProjectionAgent: comparison completed successfully")
            return result

        except Exception as exc:
            logger.exception("ProjectionAgent: comparison failed: {}", exc)
            return _build_fallback_result(path_reports)

    # ── Normalization ───────────────────────────────────────────

    def _normalize_result(
        self,
        raw: dict[str, Any],
        path_reports: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """Normalize and validate the LLM output, filling in missing fields.

        Args:
            raw: Raw dict from LLM JSON parsing.
            path_reports: Original path reports to cross-reference.

        Returns:
            Normalized dict with all required fields.
        """
        # Ensure projections
        if "projections" not in raw or not isinstance(raw["projections"], list):
            raw["projections"] = [
                _build_fallback_projection(pt, self.PATH_LABELS.get(pt, pt))
                for pt in path_reports
            ]

        # Ensure each path in path_reports has a projection entry
        existing_paths = {p.get("path_type", "") for p in raw["projections"]}
        for pt in path_reports:
            if pt not in existing_paths:
                raw["projections"].append(
                    _build_fallback_projection(pt, self.PATH_LABELS.get(pt, pt))
                )

        # Ensure comparison_matrix
        if "comparison_matrix" not in raw or not isinstance(raw["comparison_matrix"], dict):
            raw["comparison_matrix"] = {
                "dimensions": ["匹配度", "风险", "时间成本"],
                "scores": {},
            }

        # Ensure relationship_analysis
        if "relationship_analysis" not in raw or not isinstance(raw["relationship_analysis"], dict):
            raw["relationship_analysis"] = {
                "note": "路径关系分析暂未完成。",
            }

        # Ensure decision_guide
        if "decision_guide" not in raw or not isinstance(raw["decision_guide"], dict):
            raw["decision_guide"] = {
                "questions_to_ask_yourself": [
                    "你最看重的是什么？",
                    "你能接受的最大风险是什么？",
                ],
                "if_you_value_X_then_Y": [],
                "possible_hybrid_strategies": [],
            }

        dg = raw["decision_guide"]
        if "questions_to_ask_yourself" not in dg:
            dg["questions_to_ask_yourself"] = []
        if "if_you_value_X_then_Y" not in dg:
            dg["if_you_value_X_then_Y"] = []
        if "possible_hybrid_strategies" not in dg:
            dg["possible_hybrid_strategies"] = []

        # Ensure key_uncertainties
        if "key_uncertainties" not in raw or not isinstance(raw["key_uncertainties"], list):
            raw["key_uncertainties"] = []

        # Ensure summary
        if "summary" not in raw or not raw.get("summary"):
            raw["summary"] = self._generate_basic_summary(path_reports)

        return raw

    def _generate_basic_summary(self, path_reports: dict[str, dict[str, Any]]) -> str:
        """Generate a basic summary when LLM doesn't provide one."""
        paths = list(path_reports.keys())
        labels = [self.PATH_LABELS.get(p, p) for p in paths]
        return (
            f"已完成对{'、'.join(labels)}的对比分析。"
            f"各路径在时间成本、风险和成长空间上存在显著差异，"
            f"建议根据你最看重的价值观因素来选择最匹配的方向。"
        )

    def _empty_result(self) -> dict[str, Any]:
        """Return an empty comparison result."""
        return {
            "projections": [],
            "comparison_matrix": {"dimensions": [], "scores": {}},
            "relationship_analysis": {"note": "没有可对比的路径。"},
            "decision_guide": {
                "questions_to_ask_yourself": [],
                "if_you_value_X_then_Y": [],
                "possible_hybrid_strategies": [],
            },
            "key_uncertainties": [],
            "summary": "暂无可对比的路径分析。",
        }
