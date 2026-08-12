# -*- coding: utf-8 -*-
"""Memory Service — high-level API for managing user memories.

Used by both REST endpoints and the Chat pipeline (Agent).
Provides save/load/update/delete with validation,
async extraction, relevant-memory retrieval, and consolidation triggers.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from loguru import logger
from sqlalchemy.orm import Session

from crud.memory import memory as memory_crud, normalize_key
from models.memory import Memory
from schemas.memory import MemoryCreate, MemoryUpdate, MemoryResponse
from core.exceptions import NotFoundException

# ── Constants ──────────────────────────────────────────────────────

MEMORY_MAX_PER_USER = 50
MEMORY_CONSOLIDATE_THRESHOLD = int(MEMORY_MAX_PER_USER * 0.8)  # 40
SANDBOX_CONTEXT_TTL_HOURS = 24 * 30

# Display labels for memory types
MEMORY_TYPE_LABELS = {
    "profile": "用户画像",
    "goal": "成长目标",
    "action": "行动记录",
    "fact": "其他信息",
    "context": "会话上下文",
}


class MemoryService:
    """Service layer for Memory CRUD operations."""

    def __init__(self) -> None:
        self._registry_lock = threading.Lock()
        self._user_locks: dict[str, threading.RLock] = {}
        self._pending_by_user: dict[str, list[threading.Thread]] = {}

    def _lock_for_user(self, user_id: str) -> threading.RLock:
        with self._registry_lock:
            return self._user_locks.setdefault(user_id, threading.RLock())

    def _start_user_worker(
        self, user_id: str, target, args: tuple[Any, ...], *, name: str,
    ) -> threading.Thread:
        # Preserve turn order.  Parallel requests may finish extraction in a
        # different order; serialising per user keeps the newest turn as the
        # eventual winner for equal-confidence memories.
        with self._registry_lock:
            predecessors = [
                item for item in self._pending_by_user.get(user_id, [])
                if item.is_alive()
            ]

        def runner() -> None:
            try:
                for predecessor in predecessors:
                    predecessor.join()
                target(*args)
            finally:
                current = threading.current_thread()
                with self._registry_lock:
                    pending = self._pending_by_user.get(user_id, [])
                    self._pending_by_user[user_id] = [item for item in pending if item is not current and item.is_alive()]

        thread = threading.Thread(target=runner, daemon=True, name=name)
        with self._registry_lock:
            self._pending_by_user.setdefault(user_id, []).append(thread)
        thread.start()
        return thread

    def wait_for_pending(self, user_id: str, timeout: float = 5.0) -> bool:
        """Wait for pending context/extraction writes before starting a new session."""
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            with self._registry_lock:
                pending = [item for item in self._pending_by_user.get(user_id, []) if item.is_alive()]
                self._pending_by_user[user_id] = pending
            if not pending:
                return True
            for thread in pending:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                thread.join(remaining)

    def save_memory(self, db: Session, *, data: MemoryCreate) -> MemoryResponse:
        """Save a new memory or update an existing one (upsert)."""
        logger.info(f"Saving memory: user={data.user_id}, key={data.key}, type={data.memory_type}")

        with self._lock_for_user(data.user_id):
            memory_crud.reconcile_user_memories(db, user_id=data.user_id)
            obj = memory_crud.upsert(
                db, user_id=data.user_id, key=data.key, value=data.value,
                memory_type=data.memory_type, importance=data.importance,
                confidence=data.confidence, source=data.source,
                expires_at=data.expires_at,
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
        # Remove exact duplicates within the same extraction result. Conflicting
        # values remain and are processed from low to high confidence so the
        # winning value is deterministic and the alternatives stay in history.
        unique: dict[tuple[str, str], dict[str, Any]] = {}
        for item in items:
            key = normalize_key(str(item.get("key", "")))
            value = str(item.get("value", "")).strip()
            if key and value:
                unique[(key, value.casefold())] = {**item, "key": key, "value": value}
        ordered = sorted(unique.values(), key=lambda item: (item["key"], float(item.get("confidence", 1.0))))

        results_by_key: dict[str, MemoryResponse] = {}
        with self._lock_for_user(user_id):
            memory_crud.reconcile_user_memories(db, user_id=user_id)
            for item in ordered:
                obj = memory_crud.upsert(
                    db, user_id=user_id, key=item["key"], value=item["value"],
                    memory_type=item.get("memory_type", "fact"),
                    importance=item.get("importance", 1),
                    confidence=item.get("confidence", 1.0),
                    source=item.get("source", ""),
                    expires_at=item.get("expires_at"),
                )
                results_by_key[obj.key] = MemoryResponse.model_validate(obj)
        results = list(results_by_key.values())
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
        with self._lock_for_user(user_id):
            memory_crud.reconcile_user_memories(db, user_id=user_id)
        if as_dict:
            return memory_crud.as_dict(db, user_id=user_id, include_context=False)

        memories = memory_crud.get_by_user(db, user_id=user_id, memory_type=memory_type)
        if memory_type is None or memory_type == "all":
            memories = [item for item in memories if item.memory_type != "context"]
        return [MemoryResponse.model_validate(m) for m in memories]

    def load_memory_by_type(
        self,
        db: Session,
        *,
        user_id: str,
        memory_type: str,
    ) -> list[MemoryResponse]:
        """Load memories of a specific type for a user."""
        with self._lock_for_user(user_id):
            memory_crud.reconcile_user_memories(db, user_id=user_id)
        memories = memory_crud.get_by_type(db, user_id=user_id, memory_type=memory_type)
        return [MemoryResponse.model_validate(m) for m in memories]

    def load_growth_context(
        self, db: Session, *, user_id: str, agent_type: str,
    ) -> dict[str, Any]:
        """Load categorized long-term memories relevant to one growth agent."""
        with self._lock_for_user(user_id):
            memory_crud.reconcile_user_memories(db, user_id=user_id)
        memories = list(memory_crud.get_by_user(db, user_id=user_id, limit=200))
        profile_field_map = {
            "姓名": "nickname", "学校": "school", "学院": "college",
            "专业": "major", "年级": "grade", "入学年份": "enroll_year",
            "性格": "personality", "兴趣": "interests", "职业": "career_preference",
            "地域": "location_preference", "优势": "strengths", "劣势": "weaknesses",
            "技能": "skills", "学习能力": "learning_ability", "执行力": "execution",
            "当前困惑": "core_confusion",
        }
        result: dict[str, Any] = {
            "profile": {}, "goal": "", "action_plan": "", "analysis": "",
            "memory_ids": [],
        }
        generic_goal = ""
        target_keys = {
            f"growth:{agent_type}:goal": "goal",
            f"growth:{agent_type}:action_plan": "action_plan",
            f"growth:{agent_type}:analysis": "analysis",
        }
        for memory in memories:
            if memory.memory_type == "context":
                continue
            is_growth_profile = memory.memory_type == "profile" or memory.key == "当前困惑"
            if is_growth_profile and memory.key in profile_field_map and memory.confidence >= 0.6:
                result["profile"][profile_field_map[memory.key]] = memory.value
                result["memory_ids"].append(memory.id)
            if memory.key in {"目标", "current_goal"} and memory.memory_type == "goal":
                generic_goal = memory.value
            target = target_keys.get(memory.key)
            if target:
                result[target] = memory.value
                result["memory_ids"].append(memory.id)
        if not result["goal"]:
            result["goal"] = generic_goal
        if not result["analysis"]:
            legacy_analysis = next(
                (item.value for item in memories if item.key == "latest_analysis"), "",
            )
            result["analysis"] = legacy_analysis
        return result

    def save_context(
        self,
        db: Session,
        *,
        user_id: str,
        context_kind: str,
        context_id: str,
        payload: dict[str, Any],
        ttl_hours: int = 168,
        source: str = "session_context",
    ) -> MemoryResponse:
        """Persist resumable context separately from long-term facts."""
        key = f"context:{context_kind}:{context_id}"
        expires_at = datetime.now(timezone.utc) + timedelta(hours=max(1, ttl_hours))
        with self._lock_for_user(user_id):
            memory_crud.reconcile_user_memories(db, user_id=user_id)
            obj = memory_crud.upsert(
                db, user_id=user_id, key=key,
                value=json.dumps(payload, ensure_ascii=False), memory_type="context",
                importance=1, confidence=1.0, source=source, expires_at=expires_at,
            )
        return MemoryResponse.model_validate(obj)

    def load_context(
        self,
        db: Session,
        *,
        user_id: str,
        context_kind: str,
        context_id: str,
    ) -> dict[str, Any] | None:
        """Load an unexpired context payload, enforcing ownership and type."""
        key = f"context:{context_kind}:{context_id}"
        memory = memory_crud.get_by_key(db, user_id=user_id, key=key)
        if memory is None or memory.memory_type != "context":
            return None
        expires_at = memory.expires_at
        if expires_at is not None:
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at <= datetime.now(timezone.utc):
                memory_crud.delete_by_key(db, user_id=user_id, key=key)
                return None
        try:
            parsed = json.loads(memory.value)
            return parsed if isinstance(parsed, dict) else None
        except (json.JSONDecodeError, TypeError):
            return None

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
        all_memories = [
            item for item in memory_crud.get_by_user(db, user_id=user_id)
            if item.memory_type != "context"
        ]
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
        source_context: str = "conversation",
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
            self._start_user_worker(
                user_id,
                self._run_per_turn_extraction,
                (user_id, list(messages), source_context),
                name=f"memory-extract-{user_id[:8]}",
            )
            logger.debug(
                "Started async memory extraction for user={}, {} messages",
                user_id, len(messages),
            )
            return None
        return self._extract_and_save_in_db(
            db, user_id=user_id, messages=messages, source_context=source_context,
        )

    def _extract_and_save_in_db(
        self,
        db: Session,
        *,
        user_id: str,
        messages: list[dict[str, str]],
        source_context: str,
    ) -> list[MemoryResponse]:
        """Extract and save with the caller-owned session."""
        from memory.async_extractor import extract_profile_from_history
        from services.llm_service import reset_llm_context, set_llm_context

        context_token = set_llm_context(user_id=user_id, feature="memory.extraction")
        try:
            memories = extract_profile_from_history(messages, max_retries=1)
        except Exception as exc:
            logger.error(
                "extract_and_save: extraction failed for user={}: {}",
                user_id, exc,
            )
            return []
        finally:
            reset_llm_context(context_token)

        if not memories:
            logger.debug("extract_and_save: no memories extracted for user={}", user_id)
            return []
        try:
            tagged_memories = []
            for item in memories:
                evidence = str(item.get("source", "")).strip()
                tagged_memories.append({
                    **item,
                    "source": f"{source_context} | {evidence}" if evidence else source_context,
                })
            results = self.save_batch(db, user_id=user_id, items=tagged_memories)
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

    # ── Consolidation trigger (P2) ──────────────────────────────

    def _maybe_consolidate_async(self, db: Session, user_id: str) -> None:
        """Check and trigger consolidation if memory count exceeds threshold."""
        count = self.load_memory_count(db, user_id=user_id)
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
        source_detail = str(update_data.get("source") or "").strip()
        source = f"user_edit | {source_detail}" if source_detail else "user_edit"
        with self._lock_for_user(user_id):
            obj = memory_crud.upsert(
                db,
                user_id=user_id,
                key=key,
                value=update_data.get("value", obj.value),
                memory_type=update_data.get("memory_type", obj.memory_type),
                importance=update_data.get("importance", obj.importance),
                confidence=update_data.get("confidence", 1.0),
                source=source,
                expires_at=update_data.get("expires_at", obj.expires_at),
            )
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
            if mtype == "context":
                continue
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
        """Return the number of user-visible long-term memories."""
        return len([
            item for item in memory_crud.get_by_user(db, user_id=user_id, limit=1000)
            if item.memory_type != "context"
        ])

    def load_context_metadata(self, db: Session, *, user_id: str) -> list[dict[str, Any]]:
        """Return safe context summaries without exposing serialized chat payloads."""
        contexts = memory_crud.get_by_user(
            db, user_id=user_id, memory_type="context", limit=100,
        )
        result: list[dict[str, Any]] = []
        for item in contexts:
            parts = item.key.split(":", 2)
            kind = parts[1] if len(parts) > 1 else "session"
            context_id = parts[2] if len(parts) > 2 else ""
            result.append({
                "kind": kind,
                "context_id": context_id,
                "updated_at": item.updated_at.isoformat() if item.updated_at else None,
                "expires_at": item.expires_at.isoformat() if item.expires_at else None,
            })
        return result



    # ── Per-message async extraction (for growth + sandbox modes) ─────────

    def extract_from_turn_async(
        self,
        user_id: str,
        user_message: str,
        assistant_message: str = "",
        source_context: str = "conversation_turn",
    ) -> threading.Thread | None:
        """Fire a background thread to extract memories from the latest turn.

        Called after each user message in growth mode and sandbox mode.
        The extraction runs asynchronously so it never blocks the chat response.

        Args:
            user_id: The user's ID.
            user_message: The user's latest message text.
            assistant_message: The assistant's response (optional, for context).
        """
        if not user_message.strip():
            return None

        # Build minimal message list for extraction
        messages: list[dict[str, str]] = [
            {"role": "user", "content": user_message[:2000]},
        ]
        if assistant_message.strip():
            messages.append({"role": "assistant", "content": assistant_message[:2000]})

        thread = self._start_user_worker(
            user_id,
            self._run_per_turn_extraction,
            (user_id, messages, source_context),
            name=f"mem-extract-{user_id[:8]}",
        )
        logger.debug("Memory: fired async extraction for user={}", user_id)
        return thread

    def _run_per_turn_extraction(
        self,
        user_id: str,
        messages: list[dict[str, str]],
        source_context: str,
    ) -> None:
        """Background thread: extract memories and save to DB."""
        from database.session import SessionLocal
        db = SessionLocal()
        try:
            result = self._extract_and_save_in_db(
                db, user_id=user_id, messages=messages,
                source_context=source_context,
            )
            logger.info(
                "Memory: async extraction saved {} items for user={}",
                len(result), user_id,
            )
        except Exception as exc:
            logger.warning("Memory: async extraction failed for user={}: {}", user_id, exc)
        finally:
            db.close()

    def persist_sandbox_state(
        self,
        db: Session,
        *,
        user_id: str,
        session_id: str,
        session_state: dict[str, Any],
        profile_items: list[dict[str, Any]],
    ) -> MemoryResponse:
        """Synchronously persist handoff-critical sandbox state.

        Only the optional LLM extraction remains asynchronous; this state is
        committed before the sandbox response returns so a process restart
        cannot break handoff to Growth mode.
        """
        if profile_items:
            tagged = [
                {
                    **item,
                    "source": f"sandbox_profile:{session_id}",
                }
                for item in profile_items
            ]
            self.save_batch(db, user_id=user_id, items=tagged)
        return self.save_context(
            db,
            user_id=user_id,
            context_kind="sandbox",
            context_id=session_id,
            payload=session_state,
            ttl_hours=SANDBOX_CONTEXT_TTL_HOURS,
            source=f"sandbox_context:{session_id}",
        )


# Singleton
memory_service = MemoryService()
