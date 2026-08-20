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
    from sandbox.state import SANDBOX_PATHS
    labels = SANDBOX_PATHS

    projections = [
        _build_fallback_projection(pt, labels.get(pt, pt))
        for pt in path_reports
    ]

    return {
        "projections": projections,
        # A failed model call must not look like a valid 5/5 comparison.
        "comparison_matrix": None,
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


def _normalize_comparison_matrix(
    raw_matrix: Any,
    path_reports: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """Normalize supported matrix shapes without fabricating scores.

    The model has returned both the canonical ``dimensions/scores`` object
    and a row-oriented list in the wild.  Invalid or incomplete data should be
    hidden, not filled with an arbitrary 5.
    """

    if raw_matrix is None:
        return None

    dimensions: list[str] = []
    score_map: dict[str, Any] = {}

    def add_dimension(value: Any) -> str:
        if isinstance(value, dict):
            value = value.get("dimension") or value.get("label") or value.get("name")
        label = str(value or "").strip()
        if label and label not in dimensions:
            dimensions.append(label)
        return label

    if isinstance(raw_matrix, list):
        for row in raw_matrix:
            if not isinstance(row, dict):
                continue
            label = add_dimension(row)
            row_scores = row.get("scores")
            if not label or not isinstance(row_scores, dict):
                continue
            for path_type, value in row_scores.items():
                score_map.setdefault(str(path_type), {})[label] = value
    elif isinstance(raw_matrix, dict):
        for value in raw_matrix.get("dimensions", []):
            add_dimension(value)
        raw_scores = raw_matrix.get("scores")
        if isinstance(raw_scores, dict):
            score_map = {str(key): value for key, value in raw_scores.items()}
        if str(raw_matrix.get("source") or raw_matrix.get("score_source") or "").lower() in {"fallback", "default"}:
            return None

    if not dimensions:
        return None

    normalized_scores: dict[str, list[int]] = {}
    for path_type in path_reports:
        values = score_map.get(path_type)
        if isinstance(values, dict):
            values = [values.get(label) for label in dimensions]
        if not isinstance(values, list) or len(values) != len(dimensions):
            return None
        parsed: list[int] = []
        for value in values:
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                return None
            if not 1 <= numeric <= 10:
                return None
            parsed.append(round(numeric))
        normalized_scores[path_type] = parsed

    if len(normalized_scores) < 2:
        return None
    if all(value == 5 for values in normalized_scores.values() for value in values):
        return None
    return {"dimensions": dimensions, "scores": normalized_scores, "source": "llm"}


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

    PATH_LABELS: dict[str, str] = None  # initialized in __init__ from SANDBOX_PATHS

    def __init__(self, llm_service: Any) -> None:
        """Initialize the projection agent.

        Args:
            llm_service: LLMService instance for API calls.
        """
        from sandbox.state import SANDBOX_PATHS
        self.PATH_LABELS = SANDBOX_PATHS
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
                max_tokens=2048,  # reduced for faster response
                request_timeout=15.0,
                max_retries=0,
            )

            result = safe_json_parse(raw_response)
            if result is None:
                logger.warning("ProjectionAgent: failed to parse LLM output, using fallback")
                logger.debug("Projection output was not valid JSON (length={})", len(raw_response))
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
        # Ensure exactly one schema-safe projection per requested path. Models
        # sometimes omit path_type/path_label even when the content is valid;
        # assign unlabelled items by input order instead of returning a 500.
        incoming = raw.get("projections")
        incoming = incoming if isinstance(incoming, list) else []
        by_path: dict[str, dict[str, Any]] = {}
        unassigned: list[dict[str, Any]] = []
        for item in incoming:
            if not isinstance(item, dict):
                continue
            path_type = str(item.get("path_type", ""))
            if path_type in path_reports and path_type not in by_path:
                by_path[path_type] = item
            else:
                unassigned.append(item)

        normalized_projections: list[dict[str, Any]] = []
        for path_type in path_reports:
            item = by_path.get(path_type)
            if item is None and unassigned:
                item = unassigned.pop(0)
            fallback = _build_fallback_projection(
                path_type, self.PATH_LABELS.get(path_type, path_type),
            )
            if item:
                fallback.update(item)
            fallback["path_type"] = path_type
            fallback["path_label"] = self.PATH_LABELS.get(path_type, path_type)
            for scalar_key in ("core_insight", "best_for", "deal_breakers"):
                fallback[scalar_key] = str(fallback.get(scalar_key) or "")
            if not isinstance(fallback.get("time_projection"), dict):
                fallback["time_projection"] = {}
            time_projection = fallback["time_projection"]
            for time_key in ("short_term", "mid_term", "long_term"):
                time_projection[time_key] = str(time_projection.get(time_key) or "")
            milestones = time_projection.get("key_milestones")
            time_projection["key_milestones"] = [str(item) for item in milestones] if isinstance(milestones, list) else []
            for list_key in ("strengths", "challenges"):
                values = fallback.get(list_key)
                if not isinstance(values, list):
                    values = []
                fallback[list_key] = [
                    ({str(key): str(value) for key, value in value.items()} if isinstance(value, dict) else {"factor": str(value)})
                    for value in values
                ]
            normalized_projections.append(fallback)
        raw["projections"] = normalized_projections

        # Normalize only complete, verifiable scores. Never fabricate a 5.
        raw["comparison_matrix"] = _normalize_comparison_matrix(
            raw.get("comparison_matrix"), path_reports,
        )
        # Ensure relationship_analysis
        if not isinstance(raw.get("relationship_analysis"), dict):
            raw["relationship_analysis"] = {"note": "路径关系分析暂未完成。"}
        relationship = raw["relationship_analysis"]
        relationship["note"] = str(relationship.get("note") or "")
        for key in ("mutually_exclusive", "can_be_sequential", "complementary"):
            if not isinstance(relationship.get(key), list):
                relationship[key] = []

        # Ensure decision_guide
        if not isinstance(raw.get("decision_guide"), dict):
            raw["decision_guide"] = {}
        dg = raw["decision_guide"]
        dg.setdefault("questions_to_ask_yourself", ["你最看重的是什么？", "你能接受的最大风险是什么？"])
        dg.setdefault("if_you_value_X_then_Y", [])
        dg.setdefault("possible_hybrid_strategies", [])
        dg["questions_to_ask_yourself"] = [str(item) for item in dg["questions_to_ask_yourself"]] if isinstance(dg["questions_to_ask_yourself"], list) else []
        for key in ("if_you_value_X_then_Y", "possible_hybrid_strategies"):
            values = dg[key] if isinstance(dg[key], list) else []
            dg[key] = [
                ({str(k): str(v) for k, v in item.items()} if isinstance(item, dict) else {"recommendation": str(item)})
                for item in values
            ]

        # Ensure key_uncertainties
        uncertainties = raw.get("key_uncertainties")
        uncertainties = uncertainties if isinstance(uncertainties, list) else []
        raw["key_uncertainties"] = [
            (
                {
                    "factor": str(item.get("factor") or "待确认因素"),
                    "impact": str(item.get("impact") or ""),
                    "how_to_reduce": str(item.get("how_to_reduce") or ""),
                }
                if isinstance(item, dict)
                else {"factor": str(item), "impact": "", "how_to_reduce": ""}
            )
            for item in uncertainties
        ]

        # Ensure summary
        if "summary" not in raw or not raw.get("summary"):
            raw["summary"] = self._generate_basic_summary(path_reports)
        else:
            raw["summary"] = str(raw["summary"])

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
            "comparison_matrix": None,
            "relationship_analysis": {"note": "没有可对比的路径。"},
            "decision_guide": {
                "questions_to_ask_yourself": [],
                "if_you_value_X_then_Y": [],
                "possible_hybrid_strategies": [],
            },
            "key_uncertainties": [],
            "summary": "暂无可对比的路径分析。",
        }
