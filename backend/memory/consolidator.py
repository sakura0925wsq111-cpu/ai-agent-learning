# -*- coding: utf-8 -*-
"""Memory Consolidator — offline merging & compression of user memories.

Triggered when memory count exceeds 80% of MEMORY_MAX_PER_USER.
Groups similar memories by key prefix and asks the LLM to summarize
each group into a single consolidated entry.
"""

from __future__ import annotations

import json as _json
import re
from typing import Any

from loguru import logger
from sqlalchemy.orm import Session

from crud.memory import memory as memory_crud
from services.llm_service import get_llm_service

# ── Constants ──────────────────────────────────────────────────────

MEMORY_MAX_PER_USER = 50
CONSOLIDATE_THRESHOLD = int(MEMORY_MAX_PER_USER * 0.8)  # 40
TARGET_COUNT = 30

# ── Consolidation prompt ──────────────────────────────────────────

CONSOLIDATION_SYSTEM_PROMPT = """你是一个信息整合助手。你需要将多条相关的用户记忆合并成一条综合摘要。

## 规则
1. 保留所有关键信息，不要遗漏重要细节
2. 合并相似或重复的信息
3. 生成一个简洁的综合描述
4. confidence 设为 0.7（因为是合并后的推断）
5. 输出纯 JSON，不要 markdown 代码块

## 输出格式
{
  "key": "合并后的key",
  "value": "综合描述",
  "confidence": 0.7
}
"""


def _extract_key_prefix(key: str) -> str:
    """Extract the prefix of a key for grouping.

    Strategy:
    - If key contains '-', use the part before the first '-' (e.g., "技能-Python" → "技能")
    - If key contains '_', use the part before the first '_'
    - Otherwise use the full key
    """
    for sep in ("-", "_"):
        if sep in key:
            return key.split(sep, 1)[0]
    return key


def consolidate_memories(
    db: Session,
    user_id: str,
    target_count: int = TARGET_COUNT,
) -> int:
    """Consolidate user memories to reduce total count.

    Groups memories by key prefix and asks LLM to summarize each group
    with >1 member into a single entry. Deletes originals, inserts consolidated.

    Args:
        db: Database session.
        user_id: Target user ID.
        target_count: Desired maximum number of memories after consolidation.

    Returns:
        Number of memories removed (consolidated).
    """
    all_memories = list(memory_crud.get_by_user(db, user_id=user_id))
    current_count = len(all_memories)

    if current_count < CONSOLIDATE_THRESHOLD:
        logger.debug(
            "consolidate_memories: count={} < threshold={}, skipping",
            current_count, CONSOLIDATE_THRESHOLD,
        )
        return 0

    logger.info(
        "consolidate_memories: user={}, current={}, threshold={}, target={}",
        user_id, current_count, CONSOLIDATE_THRESHOLD, target_count,
    )

    # Group memories by key prefix
    groups: dict[str, list[dict[str, Any]]] = {}
    for mem in all_memories:
        prefix = _extract_key_prefix(mem.key)
        if prefix not in groups:
            groups[prefix] = []
        groups[prefix].append({
            "id": mem.id,
            "key": mem.key,
            "value": mem.value,
            "importance": mem.importance,
        })

    # Only consolidate groups with >1 member
    candidates = {k: v for k, v in groups.items() if len(v) > 1}

    if not candidates:
        logger.info("consolidate_memories: no groups with >1 member to consolidate")
        return 0

    # Sort groups by size (largest first) — consolidate biggest groups first
    sorted_groups = sorted(candidates.items(), key=lambda x: len(x[1]), reverse=True)

    llm = get_llm_service()
    removed_count = 0

    for group_key, group_memories in sorted_groups:
        # Stop if we've reached target
        remaining = current_count - removed_count
        if remaining <= target_count:
            logger.info("consolidate_memories: reached target {} (now {})", target_count, remaining)
            break

        if len(group_memories) < 2:
            continue

        logger.debug(
            "Consolidating group '{}': {} memories", group_key, len(group_memories),
        )

        try:
            consolidated = _llm_consolidate_group(llm, group_key, group_memories)
            if consolidated is None:
                continue

            # Delete original memories in this group
            ids_to_delete = [m["id"] for m in group_memories]
            keys_to_delete = [m["key"] for m in group_memories]
            deleted = memory_crud.delete_many_by_keys(
                db, user_id=user_id, keys=keys_to_delete,
            )
            removed_count += deleted

            # Insert consolidated memory
            memory_crud.upsert(
                db,
                user_id=user_id,
                key=consolidated["key"],
                value=consolidated["value"],
                importance=max(m["importance"] for m in group_memories),
                confidence=0.7,
                source=f"consolidated from {len(group_memories)} memories",
            )

            logger.info(
                "Consolidated group '{}': deleted {} memories, inserted 1 consolidated",
                group_key, deleted,
            )

        except Exception as exc:
            logger.error(
                "Failed to consolidate group '{}' for user={}: {}",
                group_key, user_id, exc,
            )
            continue

    logger.info(
        "consolidate_memories done: user={}, removed={}, remaining≈{}",
        user_id, removed_count, current_count - removed_count + len(candidates),
    )
    return removed_count


def _llm_consolidate_group(
    llm: Any,
    group_key: str,
    memories: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Ask LLM to consolidate a group of related memories into one.

    Args:
        llm: LLMService instance.
        group_key: The key prefix for this group.
        memories: List of memory dicts with key, value, importance.

    Returns:
        Consolidated memory dict {key, value, confidence} or None on failure.
    """
    # Build the user prompt with all memories in the group
    memory_lines = []
    for i, m in enumerate(memories, 1):
        memory_lines.append(f"{i}. {m['key']}: {m['value']}")

    user_prompt = "请合并以下 " + str(len(memories)) + " 条相关记忆（前缀: " + group_key + "）：\n\n" + "\n".join(memory_lines) + "\n\n请输出合并后的综合记忆（JSON 格式）。"

    messages = [
        {"role": "system", "content": CONSOLIDATION_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    try:
        raw = llm.chat_multi_turn(messages=messages, temperature=0.2, max_tokens=512)
    except Exception as exc:
        logger.error("LLM consolidation call failed: {}", exc)
        return None

    # Parse the JSON response
    import re
    fence_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', raw, re.DOTALL)
    json_str = fence_match.group(1).strip() if fence_match else raw.strip()

    # Extract JSON object
    brace_start = json_str.find('{')
    brace_end = json_str.rfind('}')
    if brace_start != -1 and brace_end != -1:
        json_str = json_str[brace_start:brace_end + 1]

    try:
        data = _json.loads(json_str)
    except _json.JSONDecodeError as exc:
        logger.warning("Failed to parse consolidation JSON: {} — raw: {}", exc, raw[:200])
        # Fallback: manual consolidation
        return {
            "key": f"{group_key}概览",
            "value": "；".join([f"{m['key']}: {m['value']}" for m in memories]),
            "confidence": 0.7,
        }

    return {
        "key": str(data.get("key", f"{group_key}概览")),
        "value": str(data.get("value", "综合信息")),
        "confidence": float(data.get("confidence", 0.7)),
    }
