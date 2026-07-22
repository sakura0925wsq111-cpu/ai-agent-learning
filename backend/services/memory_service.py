# -*- coding: utf-8 -*-
"""Memory Service — high-level API for managing user memories.

Used by both REST endpoints and the Chat pipeline (Agent).
Provides save/load/update/delete with validation,
async extraction, relevant-memory retrieval, and consolidation triggers.
"""

from __future__ import annotations

import threading
from typing import Any, Optional

from loguru import logger
from sqlalchemy.orm import Session

from crud.memory import memory as memory_crud
from models.memory import Memory
from schemas.memory import MemoryCreate, MemoryUpdate, MemoryResponse
from core.exceptions import NotFoundException

# ── Constants ──────────────────────────────────────────────────────

MEMORY_MAX_PER_USER = 50
MEMORY_CONSOLIDATE_THRESHOLD = int(MEMORY_MAX_PER_USER * 0.8)  # 40

# Display labels for memory types
MEMORY_TYPE_LABELS = {
    "profile": "用户画像",
    "goal": "成长目标",
    "action": "行动记录",
    "fact": "其他信息",
}


class MemoryService:
    """Service layer for Memory CRUD operations."""

    def save_memory(self, db: Session, *, data: MemoryCreate) -> MemoryResponse:
        """Save a new memory or update an existing one (upsert)."""
        logger.info(f"Saving memory: user={data.user_id}, key={data.key}, type={data.memory_type}")

        obj = memory_crud.upsert(
            db,
            user_id=data.user_id,
            key=data.key,
            value=data.value,
            memory_type=data.memory_type,
            importance=data.importance,
            confidence=data.confidence,
            source=data.source,
        )
        logger.debug(f"Memory saved: id={obj.id}")
        return MemoryResponse.model_validate(obj)

    def save_batch(
        self,
        db: Session,
        *,
        user_id: str,
        items: list[dict],
    ) -> list[MemoryResponse]:
        """Batch upsert multiple memory items for a user.

        Triggers consolidation check asynchronously after saving.
        """
        results: list[MemoryResponse] = []
        for item in items:
            obj = memory_crud.upsert(
                db,
                user_id=user_id,
                key=item["key"],
                value=item["value"],
                memory_type=item.get("memory_type", "fact"),
                importance=item.get("importance", 1),
                confidence=item.get("confidence", 1.0),
                source=item.get("source", ""),
            )
            results.append(MemoryResponse.model_validate(obj))
        logger.info(f"Batch saved {len(results)} memories for user={user_id}")

        self._maybe_consolidate_async(db, user_id)
        return results

    def load_memory(
        self,
        db: Session,
        *,
        user_id: str,
        as_dict: bool = False,
        memory_type: str | None = None,
    ) -> list[MemoryResponse] | dict[str, str]:
        """Load all memories for a user, optionally filtered by type.

        Args:
            as_dict: If True, return {key: value} dict.
            memory_type: Optional filter (profile/goal/action/fact).
        """
        if as_dict:
            return memory_crud.as_dict(db, user_id=user_id)

        memories = memory_crud.get_by_user(db, user_id=user_id, memory_type=memory_type)
        return [MemoryResponse.model_validate(m) for m in memories]

    def load_memory_by_type(
        self,
        db: Session,
        *,
        user_id: str,
        memory_type: str,
    ) -> list[MemoryResponse]:
        """Load memories of a specific type for a user."""
        memories = memory_crud.get_by_type(db, user_id=user_id, memory_type=memory_type)
        return [MemoryResponse.model_validate(m) for m in memories]

    # ── Relevant memory retrieval (P1) ──────────────────────────

    def load_relevant_memory(
        self,
        db: Session,
        *,
        user_id: str,
        query: str = "",
        top_k: int = 10,
    ) -> list[MemoryResponse]:
        """Load memories relevant to the current conversation context.

        Uses jieba + Jaccard similarity. Profile memories get a 1.5x boost.
        Falls back to top by importance if jieba unavailable or query empty.
        """
        all_memories = memory_crud.get_by_user(db, user_id=user_id)
        if not all_memories:
            return []

        if not query.strip():
            return [
                MemoryResponse.model_validate(m)
                for m in all_memories[:top_k]
            ]

        try:
            import jieba
        except ImportError:
            logger.warning("jieba not installed, falling back to substring match")
            return self._fallback_relevance(all_memories, query, top_k)

        query_words = list(jieba.cut(query))
        keywords = [w for w in query_words if len(w) >= 2]
        seen: set[str] = set()
        unique_keywords: list[str] = []
        for w in keywords:
            if w not in seen:
                seen.add(w)
                unique_keywords.append(w)
        keywords = unique_keywords[:5]

        if not keywords:
            return [
                MemoryResponse.model_validate(m)
                for m in all_memories[:top_k]
            ]

        keyword_set = set(keywords)
        scored: list[tuple[Memory, float]] = []

        for mem in all_memories:
            mem_text = f"{mem.key} {mem.value}"
            mem_words = set(jieba.lcut(mem_text))

            intersection = len(keyword_set & mem_words)
            union = len(keyword_set | mem_words)
            score = intersection / union if union > 0 else 0.0

            # Boost by importance and memory_type
            score *= (1.0 + mem.importance * 0.1)
            if getattr(mem, "memory_type", "fact") == "profile":
                score *= 1.5  # Profile memories are always relevant

            scored.append((mem, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        top_memories = [m for m, _ in scored[:top_k] if _ > 0]

        if not top_memories:
            all_memories_sorted = sorted(
                all_memories, key=lambda m: m.importance, reverse=True,
            )
            top_memories = all_memories_sorted[:top_k]

        logger.info(
            "load_relevant_memory: {} total, {} relevant for user={}",
            len(all_memories), len(top_memories), user_id,
        )
        return [MemoryResponse.model_validate(m) for m in top_memories]

    def _fallback_relevance(
        self,
        all_memories: list[Memory],
        query: str,
        top_k: int,
    ) -> list[MemoryResponse]:
        """Fallback: substring match when jieba is unavailable."""
        scored: list[tuple[Memory, float]] = []
        for mem in all_memories:
            mem_text = f"{mem.key} {mem.value}"
            score = 1.0 if query.lower() in mem_text.lower() else 0.0
            score *= (1.0 + mem.importance * 0.1)
            scored.append((mem, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        top = [m for m, s in scored[:top_k] if s > 0]
        if not top:
            top = sorted(all_memories, key=lambda m: m.importance, reverse=True)[:top_k]
        return [MemoryResponse.model_validate(m) for m in top]

    # ── Async extraction (P0) ────────────────────────────────────

    def extract_and_save(
        self,
        db: Session,
        *,
        user_id: str,
        messages: list[dict[str, str]],
        run_async: bool = True,
    ) -> Optional[list[MemoryResponse]]:
        """Extract user profile from conversation history and save to DB.

        Args:
            db: Database session (used synchronously when run_async=False).
            user_id: Target user ID.
            messages: Conversation history (role/content dicts).
            run_async: If True (default), runs in a background thread.

        Returns:
            List of saved MemoryResponse when run_async=False, None otherwise.
        """
        if run_async:
            thread = threading.Thread(
                target=self._extract_and_save_sync,
                args=(user_id, messages),
                daemon=True,
                name=f"memory-extract-{user_id[:8]}",
            )
            thread.start()
            logger.debug(
                "Started async memory extraction for user={}, {} messages",
                user_id, len(messages),
            )
            return None
        else:
            return self._extract_and_save_sync(user_id, messages)

    def _extract_and_save_sync(
        self,
        user_id: str,
        messages: list[dict[str, str]],
    ) -> list[MemoryResponse]:
        """Synchronous extraction + save."""
        from memory.async_extractor import extract_profile_from_history

        try:
            memories = extract_profile_from_history(messages, max_retries=1)
        except Exception as exc:
            logger.error(
                "extract_and_save: extraction failed for user={}: {}",
                user_id, exc,
            )
            return []

        if not memories:
            logger.debug("extract_and_save: no memories extracted for user={}", user_id)
            return []

        from database.session import SessionLocal
        db = SessionLocal()
        try:
            results = self.save_batch(db, user_id=user_id, items=memories)
            logger.info(
                "extract_and_save: saved {} memories for user={}",
                len(results), user_id,
            )
            return results
        except Exception as exc:
            logger.error(
                "extract_and_save: failed to save memories for user={}: {}",
                user_id, exc,
            )
            return []
        finally:
            db.close()

    # ── Consolidation trigger (P2) ──────────────────────────────

    def _maybe_consolidate_async(self, db: Session, user_id: str) -> None:
        """Check and trigger consolidation if memory count exceeds threshold."""
        count = memory_crud.count_by_user(db, user_id=user_id)
        if count >= MEMORY_CONSOLIDATE_THRESHOLD:
            logger.info(
                "Memory count {} >= threshold {} for user={}, triggering consolidation",
                count, MEMORY_CONSOLIDATE_THRESHOLD, user_id,
            )
            thread = threading.Thread(
                target=self._run_consolidation,
                args=(user_id,),
                daemon=True,
                name=f"memory-consolidate-{user_id[:8]}",
            )
            thread.start()

    def _run_consolidation(self, user_id: str) -> None:
        """Run consolidation in a background thread."""
        from database.session import SessionLocal
        db = SessionLocal()
        try:
            from memory.consolidator import consolidate_memories
            consolidate_memories(db, user_id)
        except Exception as exc:
            logger.error("Consolidation failed for user={}: {}", user_id, exc)
        finally:
            db.close()

    # ── Single-entry operations ─────────────────────────────────

    def get_memory(self, db: Session, *, user_id: str, key: str) -> Optional[MemoryResponse]:
        """Get a single memory entry by key."""
        obj = memory_crud.get_by_key(db, user_id=user_id, key=key)
        if obj is None:
            return None
        return MemoryResponse.model_validate(obj)

    def update_memory(
        self,
        db: Session,
        *,
        user_id: str,
        key: str,
        data: MemoryUpdate,
    ) -> MemoryResponse:
        """Update a specific memory entry."""
        obj = memory_crud.get_by_key(db, user_id=user_id, key=key)
        if obj is None:
            raise NotFoundException(f"Memory key '{key}' not found for user {user_id}")

        update_data = data.model_dump(exclude_unset=True)
        obj = memory_crud.update(db, db_obj=obj, obj_in=update_data)
        logger.info(f"Memory updated: user={user_id}, key={key}")
        return MemoryResponse.model_validate(obj)

    def delete_memory(self, db: Session, *, user_id: str, key: str) -> bool:
        """Delete a memory entry. Returns True if deleted."""
        deleted = memory_crud.delete_by_key(db, user_id=user_id, key=key)
        if not deleted:
            raise NotFoundException(f"Memory key '{key}' not found for user {user_id}")
        logger.info(f"Memory deleted: user={user_id}, key={key}")
        return True

    def format_for_prompt(self, db: Session, *, user_id: str) -> str:
        """Format user memories grouped by type for system prompt injection.

        Profile memories come first, then goals, then actions, then facts.
        """
        all_memories = list(memory_crud.get_by_user(db, user_id=user_id))
        if not all_memories:
            return ""

        # Group by memory_type
        grouped: dict[str, list[Memory]] = {"profile": [], "goal": [], "action": [], "fact": []}
        for m in all_memories:
            mtype = getattr(m, "memory_type", "fact")
            if mtype not in grouped:
                mtype = "fact"
            grouped[mtype].append(m)

        sections: list[str] = []
        type_order = ["profile", "goal", "action", "fact"]
        for mtype in type_order:
            mems = grouped.get(mtype, [])
            if not mems:
                continue
            label = MEMORY_TYPE_LABELS.get(mtype, mtype)
            section_lines = [f"## {label}"]
            for m in mems:
                section_lines.append(f"- {m.key}: {m.value}")
            sections.append("\n".join(section_lines))

        return "\n\n".join(sections) if sections else ""

    def load_memory_count(self, db: Session, *, user_id: str) -> int:
        """Return the total number of memories for a user."""
        return memory_crud.count_by_user(db, user_id=user_id)


# Singleton
memory_service = MemoryService()