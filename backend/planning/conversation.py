# -*- coding: utf-8 -*-
"""Turn-level analysis for the growth-planning conversation.

This layer separates facts the assistant should answer from personal variables
that only the user can clarify.  It intentionally runs before response
generation so the planning agent does not default to questionnaire mode.
"""

from __future__ import annotations

import json
import re
from typing import Any

from loguru import logger

from utils.json_parser import safe_json_parse


_OBJECTIVE_TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "salary": ("薪资", "工资", "起薪", "收入", "待遇"),
    "comparison": ("区别", "差异", "对比", "就业还是", "考研还是", "本科就业", "读研"),
    "path_overview": (
        "方向", "路径", "选择", "适合什么", "有哪些岗位", "前景",
        "想考研", "想就业", "想考公", "想转专业",
    ),
    "exam": ("考什么", "考试内容", "考试科目", "行测", "申论", "数学几", "专业课"),
    "timeline": ("多久", "多长时间", "时间线", "备考周期", "什么时候开始"),
    "policy": ("政策", "条件", "门槛", "要求", "流程", "报录比", "竞争程度"),
}

_DEFAULT_CRITICAL_VARIABLE: dict[str, str] = {
    "career": "目标岗位偏好，以及你更看重薪资、成长还是稳定",
    "graduate": "目标岗位是否有明显学历门槛，以及你读研的核心动机",
    "civil": "目标地区和岗位类型，以及你对稳定性与备考成本的权衡",
    "major": "转专业的核心原因、目标专业和可接受的时间成本",
}


def _detect_topics(message: str) -> list[str]:
    topics = [
        topic
        for topic, keywords in _OBJECTIVE_TOPIC_KEYWORDS.items()
        if any(keyword in message for keyword in keywords)
    ]
    if not topics and (not message or any(word in message for word in ("了解", "看看", "咨询"))):
        topics.append("path_overview")
    return topics


def _fallback_analysis(
    *,
    agent_type: str,
    message: str,
    follow_up_round: int,
    max_follow_up_rounds: int,
) -> dict[str, Any]:
    topics = _detect_topics(message)
    answerable = bool(topics)
    critical_variable = _DEFAULT_CRITICAL_VARIABLE.get(agent_type, "你的目标、优先级和现实约束")
    return {
        "intent": "information" if answerable else "personal_update",
        "answerable_by_ai": answerable,
        "needs_knowledge": answerable or not message,
        "knowledge_topics": topics or ["path_overview"],
        "known_information": [],
        "missing_variables": [critical_variable],
        "critical_variable": critical_variable,
        "should_ask": follow_up_round < max_follow_up_rounds,
        "reason": "使用本地规则完成单轮判断",
    }


def analyze_turn(
    llm: Any,
    *,
    agent_type: str,
    agent_label: str,
    message: str,
    user_context: str,
    follow_up_round: int,
    max_follow_up_rounds: int,
    readiness: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify the turn before composing a user-facing response.

    The LLM provides semantic judgment; deterministic detection is merged in so
    obvious knowledge questions are never accidentally treated as profile
    questions.  Failures fall back to the deterministic result.
    """

    fallback = _fallback_analysis(
        agent_type=agent_type,
        message=message,
        follow_up_round=follow_up_round,
        max_follow_up_rounds=max_follow_up_rounds,
    )

    system_prompt = f"""你是{agent_label}对话的单轮分析器，只做判断，不直接回复用户。

你的核心任务是区分两类信息：
1. AI应主动回答：行业与路径差异、考试科目、常见时间线、岗位门槛、一般政策和薪资影响因素。
2. 只能询问用户：个人经历、能力现状、目标偏好、价值排序、可投入时间和现实约束。

规则：
- 用户询问第一类信息时，answerable_by_ai 必须为 true，不能把问题原样反问用户。
- 只有某个缺失变量会显著改变建议时，should_ask 才为 true。
- 已有信息足够，或已达到追问上限时，should_ask 必须为 false。
- 建议充分度由代码门控：general_only 时禁止给个性化结论；conditional 时只能给带假设的条件式建议。
- critical_variable 只能是用户自身信息，不能是“是否了解某行业/政策/薪资”。
- 只输出合法 JSON，不要输出其他文字。

输出格式：
{{"intent":"information|decision|personal_update","answerable_by_ai":true,"needs_knowledge":true,"knowledge_topics":["salary|comparison|path_overview|exam|timeline|policy"],"known_information":["..."],"missing_variables":["..."],"critical_variable":"...","should_ask":true,"reason":"..."}}"""

    user_prompt = f"""已知用户信息：
{user_context or "（暂无）"}

用户本轮输入：
{message or "（会话刚开始，尚无新输入）"}

当前已经完成 {follow_up_round} 轮高价值澄清，最多允许 {max_follow_up_rounds} 轮。
代码计算的建议充分度：
{json.dumps(readiness, ensure_ascii=False) if readiness else "（未提供）"}

请判断本轮应该先回答什么，以及是否真的需要再问一个问题。"""

    try:
        if callable(getattr(type(llm), "chat_json", None)):
            parsed = llm.chat_json(
                user_message=user_prompt,
                system_prompt=system_prompt,
                temperature=0.1,
                max_tokens=700,
                validator=lambda value: isinstance(value.get("should_ask"), bool),
            )
        else:
            raw = llm.chat(
                user_message=user_prompt,
                system_prompt=system_prompt,
                temperature=0.1,
                max_tokens=700,
            )
            parsed = safe_json_parse(raw)
        if not isinstance(parsed, dict):
            raise ValueError("turn analysis is not a JSON object")
    except Exception as exc:
        logger.warning("Planning turn analysis failed, using fallback: {}", exc)
        return fallback

    result = dict(fallback)
    for key in (
        "intent", "answerable_by_ai", "needs_knowledge", "knowledge_topics",
        "known_information", "missing_variables", "critical_variable",
        "should_ask", "reason",
    ):
        if key in parsed:
            result[key] = parsed[key]

    for bool_key in ("answerable_by_ai", "needs_knowledge", "should_ask"):
        if not isinstance(result.get(bool_key), bool):
            result[bool_key] = fallback[bool_key]

    detected_topics = _detect_topics(message)
    if detected_topics:
        result["answerable_by_ai"] = True
        result["needs_knowledge"] = True
        supplied_topics = result.get("knowledge_topics", [])
        if not isinstance(supplied_topics, list):
            supplied_topics = []
        result["knowledge_topics"] = list(dict.fromkeys(detected_topics + supplied_topics))

    result["should_ask"] = bool(result.get("should_ask")) and follow_up_round < max_follow_up_rounds

    if readiness:
        result["readiness"] = readiness
        result["ready_for_advice"] = bool(readiness.get("ready"))
        result["ready_for_personalized_advice"] = bool(
            readiness.get("ready_for_personalized_advice")
        )
        result["advice_level"] = readiness.get("advice_level", "general_only")
        # The deterministic gate has final authority over whether another
        # clarification is needed.  The LLM only decides how to phrase it.
        result["should_ask"] = bool(readiness.get("can_ask"))
        next_label = str(readiness.get("next_dimension_label", "")).strip()
        if next_label:
            result["critical_variable"] = next_label
            result["missing_variables"] = readiness.get("missing_labels", [next_label])

    supplied_topics = result.get("knowledge_topics", [])
    if not isinstance(supplied_topics, list):
        supplied_topics = []
    allowed_topics = set(_OBJECTIVE_TOPIC_KEYWORDS)
    result["knowledge_topics"] = [
        topic for topic in dict.fromkeys(supplied_topics) if topic in allowed_topics
    ] or fallback["knowledge_topics"]

    critical_variable = result.get("critical_variable")
    invalid_question_targets = ("是否了解", "知不知道", "是否知道", "薪资区别", "考试内容", "竞争程度", "政策")
    if (
        not isinstance(critical_variable, str)
        or not critical_variable.strip()
        or any(target in critical_variable for target in invalid_question_targets)
    ):
        result["critical_variable"] = fallback["critical_variable"]
    return result


def serialize_turn_analysis(analysis: dict[str, Any]) -> str:
    """Compact JSON representation for prompt injection and logs."""
    return json.dumps(analysis, ensure_ascii=False, separators=(",", ":"))


def normalize_advisory_text(text: str, max_chars: int = 160) -> str:
    """Normalize user-visible advisory text from structured sandbox phases."""
    cleaned = re.sub(r"\s+", "", str(text or "")).strip()
    replacements = (
        ("你必须", "可以考虑"),
        ("你应该", "可以先"),
        ("显然", "从目前信息看"),
        ("肯定会", "更可能"),
        ("绝对不能", "通常不建议"),
        ("不适合", "目前匹配度可能有限"),
    )
    for source, target in replacements:
        cleaned = cleaned.replace(source, target)
    cleaned = cleaned.replace("?", "？")
    first_question = cleaned.find("？")
    if first_question >= 0:
        cleaned = cleaned[:first_question + 1]
    if len(cleaned) <= max_chars:
        return cleaned

    question = ""
    if cleaned.endswith("？"):
        question_start = max(
            cleaned.rfind("。", 0, len(cleaned) - 1),
            cleaned.rfind("！", 0, len(cleaned) - 1),
        )
        if question_start >= 0:
            question = cleaned[question_start + 1:]
            cleaned = cleaned[:question_start + 1]
    body_limit = max_chars - len(question)
    body = cleaned[: max(1, body_limit - 1)].rstrip("，；、。！？") + "…"
    return body + question
