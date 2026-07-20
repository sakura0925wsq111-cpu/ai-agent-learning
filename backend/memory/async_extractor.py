# -*- coding: utf-8 -*-
"""Async memory extractor — extracts user profile from conversation history.

Unlike the inline extractor (which parses JSON from LLM chat replies),
this module sends the full conversation history to the LLM in a dedicated
structured-extraction call with low temperature, independent of the chat reply.
"""

from __future__ import annotations

import json as _json
from typing import Any

from loguru import logger

from services.llm_service import get_llm_service

# ── Extraction prompt ──────────────────────────────────────────────

EXTRACTION_SYSTEM_PROMPT = """你是一个信息抽取助手。你的任务是从对话历史中提取用户的个人信息。

## 抽取规则
1. 只抽取用户明确陈述或强烈暗示的信息，不要编造
2. 每条信息包含：key（信息类别）、value（具体内容）、confidence（置信度 0-1）、source（原文引用）
3. 如果用户纠正了之前的信息，用新的 value 覆盖

## 信息类别示例
- 专业 (major)：交通工程、计算机科学
- 年级 (grade)：大一、研二
- 目标 (goal)：考研、出国、就业
- 兴趣 (interest)：AI、摄影、篮球
- 职业方向 (career)：算法工程师、公务员
- 性格特质 (personality)：内向、外向、细心
- 学习能力 (learning_ability)：强、中等
- 执行力 (execution)：高、一般
- 地域偏好 (location_preference)：北京、上海
- 当前困惑 (core_confusion)：不知道该考研还是就业
- 其他有价值的个人信息

## 输出格式（纯 JSON，不要 markdown 代码块）
{
  "memories": [
    {
      "key": "专业",
      "value": "交通工程",
      "confidence": 1.0,
      "source": "用户说'我学的交通工程'"
    }
  ]
}

如果没有提取到任何信息，返回：{"memories": []}
"""


def extract_profile_from_history(
    messages: list[dict[str, str]],
    max_retries: int = 1,
) -> list[dict[str, Any]]:
    """Extract user profile memories from conversation history via dedicated LLM call.

    Args:
        messages: List of {"role": "...", "content": "..."} dicts representing
                  the conversation history (both user and assistant messages).
        max_retries: Number of retries on failure (default 1).

    Returns:
        List of memory dicts with keys: key, value, confidence, source.
        Returns empty list if no memories extracted or on persistent failure.
    """
    if not messages:
        logger.debug("extract_profile_from_history: empty messages, returning []")
        return []

    llm = get_llm_service()

    # Build extraction messages: system prompt + full history
    extraction_messages: list[dict[str, str]] = [
        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
    ]
    extraction_messages.extend(messages)

    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            raw = llm.chat_multi_turn(
                messages=extraction_messages,
                temperature=0.1,
                max_tokens=1024,
            )
            return _parse_extraction_result(raw)

        except Exception as exc:
            last_error = exc
            logger.warning(
                "extract_profile_from_history attempt {}/{} failed: {}",
                attempt + 1, max_retries + 1, exc,
            )

    # All retries exhausted
    logger.error(
        "extract_profile_from_history: all {} attempts failed, last error: {}",
        max_retries + 1, last_error,
    )
    return []


def _parse_extraction_result(raw: str) -> list[dict[str, Any]]:
    """Parse the LLM extraction response into a list of memory dicts.

    Handles both raw JSON and JSON inside markdown code fences.
    """
    # Try to find JSON inside code fences first
    import re
    fence_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', raw, re.DOTALL)
    json_str = fence_match.group(1).strip() if fence_match else raw.strip()

    # Remove any leading/trailing non-JSON noise
    # Find the outermost { ... }
    brace_start = json_str.find('{')
    brace_end = json_str.rfind('}')
    if brace_start != -1 and brace_end != -1:
        json_str = json_str[brace_start:brace_end + 1]

    try:
        data = _json.loads(json_str)
    except _json.JSONDecodeError as exc:
        logger.warning("Failed to parse extraction JSON: {} — raw: {}", exc, raw[:300])
        return []

    if not isinstance(data, dict) or "memories" not in data:
        logger.warning("Extraction result missing 'memories' key: {}", data)
        return []

    memories = data["memories"]
    if not isinstance(memories, list):
        return []

    result: list[dict[str, Any]] = []
    for item in memories:
        if not isinstance(item, dict):
            continue
        if "key" not in item or "value" not in item:
            continue
        result.append({
            "key": str(item["key"]),
            "value": str(item["value"]),
            "confidence": float(item.get("confidence", 0.5)),
            "source": str(item.get("source", "")),
            "importance": int(item.get("importance", 1)),
        })

    logger.info("Extracted {} memory items from history", len(result))
    return result
