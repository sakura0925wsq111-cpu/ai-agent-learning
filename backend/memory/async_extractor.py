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

EXTRACTION_SYSTEM_PROMPT = """你是一个信息抽取助手。你的任务是从对话历史中提取用户的个人信息，并分类存储。

## 记忆分类
每条记忆必须标注 memory_type，取值为以下之一：
- "profile": 长期用户画像（专业、年级、性格、兴趣、能力等稳定信息）
- "goal": 成长目标（考研、就业、出国、学习计划等目标性信息）
- "action": 行动记录（用户做了什么、完成了什么任务、反馈如何）
- "fact": 一般事实（其他有价值但不易归类的事实信息）

## 抽取规则
1. 只抽取用户明确陈述或强烈暗示的信息，不要编造
2. 每条信息包含：key、value、confidence（0-1）、source（原文引用）、memory_type、importance（1-5）
3. 如果用户纠正了之前的信息，用新的 value 覆盖
4. 不要把"你好""谢谢"等寒暄存入记忆

## 信息类别示例
- 专业 (major): type=profile
- 年级 (grade): type=profile
- 目标 (goal): type=goal
- 兴趣 (interest): type=profile
- 职业方向 (career): type=profile
- 性格特质 (personality): type=profile
- 学习任务 (learning_task): type=action
- 当前困惑 (core_confusion): type=fact

## 输出格式（纯 JSON，不要 markdown 代码块）
{
  "memories": [
    {
      "key": "major",
      "value": "交通工程",
      "confidence": 1.0,
      "source": "用户说'我学的交通工程'",
      "memory_type": "profile",
      "importance": 5
    }
  ]
}

如果没有提取到任何信息，返回：{"memories": []}
"""


def _normalize_extracted_key(key: str) -> str:
    """Apply the same canonical key mapping used by memory persistence."""
    from crud.memory import normalize_key

    return normalize_key(key)


def extract_profile_from_history(
    messages: list[dict[str, str]],
    max_retries: int = 1,
) -> list[dict[str, Any]]:
    """Extract user profile memories from conversation history via dedicated LLM call.

    Args:
        messages: List of {"role": "...", "content": "..."} dicts.
        max_retries: Number of retries on failure (default 1).

    Returns:
        List of memory dicts with keys: key, value, confidence, source, memory_type, importance.
    """
    if not messages:
        logger.debug("extract_profile_from_history: empty messages, returning []")
        return []

    llm = get_llm_service()

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

    logger.error(
        "extract_profile_from_history: all {} attempts failed, last error: {}",
        max_retries + 1, last_error,
    )
    return []


def _parse_extraction_result(raw: str) -> list[dict[str, Any]]:
    """Parse the LLM extraction response into a list of memory dicts."""
    import re
    fence_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', raw, re.DOTALL)
    json_str = fence_match.group(1).strip() if fence_match else raw.strip()

    brace_start = json_str.find('{')
    brace_end = json_str.rfind('}')
    if brace_start != -1 and brace_end != -1:
        json_str = json_str[brace_start:brace_end + 1]

    try:
        data = _json.loads(json_str)
    except _json.JSONDecodeError as exc:
        logger.warning("Failed to parse extraction JSON: {} (length={})", exc, len(raw))
        return []

    if not isinstance(data, dict) or "memories" not in data:
        logger.warning("Extraction result missing required 'memories' list")
        return []

    memories = data["memories"]
    if not isinstance(memories, list):
        return []

    deduplicated: dict[str, dict[str, Any]] = {}
    for item in memories:
        if not isinstance(item, dict):
            continue
        if "key" not in item or "value" not in item:
            continue

        key = _normalize_extracted_key(str(item["key"]))
        if not key or key.lower().startswith("context:"):
            continue
        value_raw = item["value"]
        if isinstance(value_raw, (dict, list)):
            value = _json.dumps(value_raw, ensure_ascii=False)
        else:
            value = str(value_raw).strip()
        if not value:
            continue
        raw_memory_type = str(item.get("memory_type", "fact"))
        if raw_memory_type not in ("profile", "goal", "action", "fact"):
            raw_memory_type = _infer_memory_type(key)
        from crud.memory import canonical_memory_type
        memory_type = canonical_memory_type(key, raw_memory_type)
        try:
            confidence = max(0.0, min(1.0, float(item.get("confidence", 0.5))))
        except (TypeError, ValueError):
            confidence = 0.5
        try:
            importance = max(1, min(10, int(item.get("importance", 1))))
        except (TypeError, ValueError):
            importance = 1
        candidate = {
            "key": key,
            "value": value,
            "memory_type": memory_type,
            "confidence": confidence,
            "source": str(item.get("source", ""))[:1000],
            "importance": importance,
        }
        existing = deduplicated.get(key)
        if existing is None or confidence >= existing["confidence"]:
            deduplicated[key] = candidate

    result = list(deduplicated.values())
    logger.info("Extracted {} unique memory items from history", len(result))
    return result


def _infer_memory_type(key: str) -> str:
    """Infer memory_type from key name when LLM doesn't provide it."""
    from crud.memory import canonical_memory_type

    classified = canonical_memory_type(key, "fact")
    if classified != "fact":
        return classified
    goal_keys = {"goal", "目标", "plan", "计划", "deadline", "截止日期"}
    action_keys = {"task", "任务", "action", "行动", "完成", "done", "feedback", "反馈"}
    profile_keys = {"major", "专业", "grade", "年级", "personality", "性格",
                    "interest", "兴趣", "career", "职业", "strength", "优势",
                    "weakness", "劣势", "name", "姓名", "location", "地域"}

    key_lower = key.lower()
    if any(gk in key_lower or gk in key for gk in goal_keys):
        return "goal"
    if any(ak in key_lower or ak in key for ak in action_keys):
        return "action"
    if any(pk in key_lower or pk in key for pk in profile_keys):
        return "profile"
    return "fact"
