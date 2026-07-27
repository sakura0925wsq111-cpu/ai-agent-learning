"""CRUD operations for Memory model."""

import json as _json
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from sqlalchemy import select as _select
from sqlalchemy.orm import Session

from crud.base import CRUDBase
from models.memory import Memory


def _serialize_value(value: Any) -> str:
    """Auto-convert list/dict to JSON string, keep plain strings as-is."""
    if isinstance(value, (list, dict)):
        return _json.dumps(value, ensure_ascii=False)
    if isinstance(value, str):
        return value
    return str(value)


def _build_conflict_history(old_value: str, timestamp: datetime) -> str:
    """Build a history note when a memory value changes."""
    ts_str = timestamp.strftime("%Y-%m-%d %H:%M")
    return f"[鏃у€? {old_value} (鏇存柊浜?{ts_str})]"



# ── Key normalization: Chinese↔English synonym dedup ──────────────

# Maps common key synonyms to a canonical form.
# Canonical keys use English short names for compactness and unambiguity.
KEY_NORMALIZATION_MAP: dict[str, str] = {
    # Normalize Chinese synonyms to canonical form
    "专业": "专业",
    "年级": "年级",
    "性格": "性格",
    "性格特质": "性格",
    "兴趣": "兴趣",
    "爱好": "兴趣",
    "职业方向": "职业",
    "职业": "职业",
    "姓名": "姓名",
    "地域": "地域",
    "地域偏好": "地域",
    "城市": "地域",
    "优势": "优势",
    "劣势": "劣势",
    "学习能力": "学习能力",
    "执行力": "执行力",
    "学校": "学校",
    "大学": "学校",
    # Goal
    "目标": "目标",
    "计划": "目标",
    "截止日期": "截止日期",
    "考研": "目标详情",
    "就业": "目标详情",
    "出国": "目标详情",
    "考公": "目标详情",
    # Action
    "任务": "任务",
    "行动": "行动",
    "完成": "完成",
    "反馈": "反馈",
    "学习任务": "学习任务",
    # General
    "当前困惑": "当前困惑",
    "困惑": "当前困惑",
    "技能": "技能",
}


def normalize_key(key: str) -> str:
    """Normalize a memory key to its canonical Chinese form.

    Maps synonyms like "职业方向" → "职业", "性格特质" → "性格".
    Keys not in the map pass through unchanged.
    Handles compound keys like "技能-Python".
    """
    if not key:
        return key
    stripped = key.strip()
    if stripped in KEY_NORMALIZATION_MAP:
        return KEY_NORMALIZATION_MAP[stripped]
    for sep in ("-", "_"):
        if sep in stripped:
            prefix, rest = stripped.split(sep, 1)
            if prefix in KEY_NORMALIZATION_MAP:
                return f"{KEY_NORMALIZATION_MAP[prefix]}{sep}{rest}"
    return stripped


def history_note_in_source(source: str) -> bool:
    """Check if source already contains a conflict history note."""
    return "[鏃у€?" in source


class CRUDMemory(CRUDBase[Memory]):
    """Memory CRUD with domain-specific methods."""

    def __init__(self) -> None:
        super().__init__(Memory)

    def get_by_user(
        self,
        db: Session,
        *,
        user_id: str,
        skip: int = 0,
        limit: int = 100,
        memory_type: str | None = None,
    ) -> Sequence[Memory]:
        """Get all memory entries for a user, ordered by importance desc.

        Optionally filter by memory_type.
        """
        stmt = (
            _select(Memory)
            .where(Memory.user_id == user_id)
        )
        if memory_type and memory_type != "all":
            stmt = stmt.where(Memory.memory_type == memory_type)
        stmt = stmt.order_by(Memory.importance.desc(), Memory.created_at.desc())
        stmt = stmt.offset(skip).limit(limit)
        return db.scalars(stmt).all()

    def get_by_key(self, db: Session, *, user_id: str, key: str) -> Optional[Memory]:
        """Get a specific memory entry by user_id and key."""
        stmt = _select(Memory).where(
            Memory.user_id == user_id, Memory.key == key
        )
        return db.scalars(stmt).first()

    def count_by_user(self, db: Session, *, user_id: str) -> int:
        """Count total memories for a user."""
        return self.count(db, user_id=user_id)

    def get_by_type(
        self,
        db: Session,
        *,
        user_id: str,
        memory_type: str,
    ) -> Sequence[Memory]:
        """Get all memories of a specific type for a user."""
        stmt = (
            _select(Memory)
            .where(Memory.user_id == user_id, Memory.memory_type == memory_type)
            .order_by(Memory.importance.desc())
        )
        return db.scalars(stmt).all()

    def upsert(
        self,
        db: Session,
        *,
        user_id: str,
        key: str,
        value: Any,
        memory_type: str = "fact",
        importance: int = 1,
        confidence: float = 1.0,
        source: str = "",
    ) -> Memory:
        """Insert or update a memory entry.

        If a record with the same (user_id, key) exists, update it.
        On value change, appends conflict history to source field.
        Otherwise, create a new one.
        Auto-serializes list/dict values to JSON strings.
        """
        serialized_value = _serialize_value(value)
        # Normalize key to prevent Chinese/English synonym duplicates
        key = normalize_key(key)
        existing = self.get_by_key(db, user_id=user_id, key=key)
        now = datetime.now(timezone.utc)

        if existing:
            # ---- Conflict history: if value changed, preserve old value in source ----
            if existing.value != serialized_value:
                history_note = _build_conflict_history(existing.value, now)
                if existing.source:
                    existing.source = f"{existing.source} {history_note}"
                else:
                    existing.source = history_note

            existing.value = serialized_value
            existing.memory_type = memory_type
            if importance is not None:
                existing.importance = importance
            if confidence is not None:
                existing.confidence = confidence
            if source:
                # If caller provides explicit source, use it (appending to history)
                if existing.source and history_note_in_source(existing.source):
                    existing.source = f"{source} {existing.source}"
                else:
                    existing.source = source
            existing.updated_at = now
            db.add(existing)
            db.commit()
            db.refresh(existing)
            return existing
        else:
            return self.create(
                db,
                obj_in={
                    "user_id": user_id,
                    "key": key,
                    "value": serialized_value,
                    "memory_type": memory_type,
                    "importance": importance,
                    "confidence": confidence,
                    "source": source,
                    "created_at": now,
                    "updated_at": now,
                },
            )

    def delete_by_key(self, db: Session, *, user_id: str, key: str) -> bool:
        """Delete a memory entry by user_id and key. Returns True if deleted."""
        obj = self.get_by_key(db, user_id=user_id, key=key)
        if obj:
            db.delete(obj)
            db.commit()
            return True
        return False

    def delete_many_by_keys(self, db: Session, *, user_id: str, keys: list[str]) -> int:
        """Delete multiple memories by keys. Returns count of deleted."""
        from sqlalchemy import delete as _delete
        stmt = _delete(Memory).where(
            Memory.user_id == user_id,
            Memory.key.in_(keys),
        )
        result = db.execute(stmt)
        db.commit()
        return result.rowcount

    def as_dict(self, db: Session, *, user_id: str) -> dict[str, str]:
        """Return all memories for a user as a {key: value} dictionary."""
        memories = self.get_by_user(db, user_id=user_id)
        return {m.key: m.value for m in memories}


memory = CRUDMemory()