"""CRUD operations for categorized, conflict-safe user memory."""

from __future__ import annotations

import json as _json
import re
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from sqlalchemy import or_, select as _select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from crud.base import CRUDBase
from models.memory import Memory


def _serialize_value(value: Any) -> str:
    """Auto-convert list/dict to JSON, while preserving plain strings."""
    if isinstance(value, (list, dict)):
        return _json.dumps(value, ensure_ascii=False)
    if isinstance(value, str):
        return value
    return str(value)


def _build_conflict_history(old_value: str, timestamp: datetime) -> str:
    """Legacy-compatible readable history note."""
    return f"[旧值：{old_value}（更新于 {timestamp.strftime('%Y-%m-%d %H:%M')}）]"


# One canonical key per real-world concept. Chinese keys remain user-readable.
KEY_NORMALIZATION_MAP: dict[str, str] = {
    "专业": "专业", "年级": "年级", "性格": "性格", "性格特质": "性格",
    "兴趣": "兴趣", "爱好": "兴趣", "职业方向": "职业", "职业": "职业",
    "姓名": "姓名", "地域": "地域", "地域偏好": "地域", "城市": "地域",
    "优势": "优势", "劣势": "劣势", "学习能力": "学习能力", "执行力": "执行力",
    "学校": "学校", "大学": "学校", "学院": "学院", "入学年份": "入学年份",
    "目标": "目标", "计划": "目标", "截止日期": "截止日期",
    "考研": "目标详情", "就业": "目标详情", "出国": "目标详情", "考公": "目标详情",
    "任务": "任务", "行动": "行动", "完成": "完成", "反馈": "反馈",
    "学习任务": "学习任务", "当前困惑": "当前困惑", "困惑": "当前困惑",
    "技能": "技能",
    # English keys emitted by the extraction prompt and legacy clients.
    "name": "姓名", "nickname": "姓名", "school": "学校", "college": "学院",
    "major": "专业", "grade": "年级", "enroll_year": "入学年份",
    "personality": "性格", "personality_traits": "性格",
    "interest": "兴趣", "interests": "兴趣", "career": "职业",
    "career_direction": "职业", "target_job": "职业", "location": "地域",
    "city": "地域", "location_preference": "地域", "strength": "优势",
    "strengths": "优势", "weakness": "劣势", "weaknesses": "劣势",
    "skills": "技能", "learning_ability": "学习能力", "execution": "执行力",
    "social_ability": "社交能力", "stress_tolerance": "抗压能力",
    "family_expectation": "家庭期望", "economic_situation": "经济状况",
    "time_window": "时间窗口", "path_preferences": "关注路径",
    "goal": "目标", "plan": "目标", "deadline": "截止日期",
    "current_goal": "目标",
    "task": "任务", "learning_task": "学习任务", "action": "行动",
    "done": "完成", "feedback": "反馈", "core_confusion": "当前困惑",
}

PROFILE_KEYS = {
    "姓名", "学校", "学院", "专业", "年级", "入学年份", "性格", "兴趣",
    "职业", "地域", "优势", "劣势", "技能", "学习能力", "执行力",
    "社交能力", "抗压能力", "家庭期望", "经济状况", "时间窗口",
}
GOAL_KEYS = {"目标", "目标详情", "截止日期", "关注路径"}
ACTION_KEYS = {"任务", "学习任务", "行动", "完成", "反馈"}
VALID_MEMORY_TYPES = {"profile", "goal", "action", "fact", "context"}
AUTHORITATIVE_SOURCE_PREFIXES = (
    "user_edit", "user_registration", "user_profile_update",
    "growth_report", "sandbox_context",
)


def normalize_key(key: str) -> str:
    """Normalize Chinese/English aliases into one canonical key."""
    if not key:
        return key
    stripped = re.sub(r"\s+", " ", key.strip())
    lookup = stripped.lower()
    if lookup in KEY_NORMALIZATION_MAP:
        return KEY_NORMALIZATION_MAP[lookup]
    if stripped in KEY_NORMALIZATION_MAP:
        return KEY_NORMALIZATION_MAP[stripped]
    # Preserve namespaced keys and normalize only known compound prefixes.
    if ":" not in stripped:
        for separator in ("-", "_"):
            if separator in stripped:
                prefix, rest = stripped.split(separator, 1)
                normalized_prefix = KEY_NORMALIZATION_MAP.get(prefix.lower(), KEY_NORMALIZATION_MAP.get(prefix))
                if normalized_prefix:
                    return f"{normalized_prefix}{separator}{rest}"
    return stripped


def canonical_memory_type(key: str, requested: str = "fact") -> str:
    """Classify a key deterministically so callers cannot create type conflicts."""
    canonical = normalize_key(key)
    lowered = canonical.lower()
    if lowered.startswith("context:"):
        return "context"
    if lowered.startswith("growth:"):
        suffix = lowered.rsplit(":", 1)[-1]
        if suffix == "goal":
            return "goal"
        if suffix in {"action_plan", "progress", "feedback"}:
            return "action"
        return "fact"
    if canonical in PROFILE_KEYS:
        return "profile"
    if canonical in GOAL_KEYS:
        return "goal"
    if canonical in ACTION_KEYS:
        return "action"
    return requested if requested in VALID_MEMORY_TYPES else "fact"


def _normalize_value_for_compare(value: str) -> str:
    """Ignore whitespace/case/JSON ordering when detecting duplicates."""
    stripped = re.sub(r"\s+", " ", value.strip())
    try:
        parsed = _json.loads(stripped)
        return _json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (_json.JSONDecodeError, TypeError):
        return stripped.casefold()


def _is_authoritative_source(source: str) -> bool:
    return source.startswith(AUTHORITATIVE_SOURCE_PREFIXES)


def _load_conflict_history(raw: str | None) -> list[dict[str, Any]]:
    try:
        parsed = _json.loads(raw or "[]")
        return parsed if isinstance(parsed, list) else []
    except (_json.JSONDecodeError, TypeError):
        return []


def _append_conflict(
    memory: Memory,
    *,
    value: str,
    memory_type: str,
    confidence: float,
    source: str,
    timestamp: datetime,
    status: str,
) -> None:
    history = _load_conflict_history(getattr(memory, "conflict_history", "[]"))
    entry = {
        "value": value,
        "memory_type": memory_type,
        "confidence": round(float(confidence), 4),
        "source": source,
        "timestamp": timestamp.isoformat(),
        "status": status,
    }
    comparable_fields = ("value", "memory_type", "confidence", "source", "status")
    if any(
        all(previous.get(field) == entry[field] for field in comparable_fields)
        for previous in history
    ):
        return
    history.append(entry)
    memory.conflict_history = _json.dumps(history[-20:], ensure_ascii=False)


def history_note_in_source(source: str) -> bool:
    """Compatibility helper for callers that still inspect legacy source notes."""
    return "[旧值：" in source


class CRUDMemory(CRUDBase[Memory]):
    """Memory CRUD with normalization, expiry, deduplication and conflicts."""

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
        include_expired: bool = False,
    ) -> Sequence[Memory]:
        stmt = _select(Memory).where(Memory.user_id == user_id)
        if not include_expired:
            now = datetime.now(timezone.utc)
            stmt = stmt.where(or_(Memory.expires_at.is_(None), Memory.expires_at > now))
        if memory_type and memory_type != "all":
            stmt = stmt.where(Memory.memory_type == memory_type)
        stmt = stmt.order_by(Memory.importance.desc(), Memory.updated_at.desc(), Memory.created_at.desc())
        return db.scalars(stmt.offset(skip).limit(limit)).all()

    def get_by_key(self, db: Session, *, user_id: str, key: str) -> Optional[Memory]:
        canonical = normalize_key(key)
        direct = db.scalars(_select(Memory).where(
            Memory.user_id == user_id, Memory.key == canonical,
        )).first()
        if direct is not None:
            return direct
        # Resolve a legacy alias without creating another row.
        rows = db.scalars(_select(Memory).where(Memory.user_id == user_id)).all()
        return next((row for row in rows if normalize_key(row.key) == canonical), None)

    def count_by_user(self, db: Session, *, user_id: str) -> int:
        return len(self.get_by_user(db, user_id=user_id, limit=1000))

    def get_by_type(
        self, db: Session, *, user_id: str, memory_type: str,
    ) -> Sequence[Memory]:
        return self.get_by_user(db, user_id=user_id, memory_type=memory_type)

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
        expires_at: datetime | None = None,
    ) -> Memory:
        """Upsert one canonical row and preserve rejected/replaced conflicts."""
        serialized_value = _serialize_value(value).strip()
        if not serialized_value:
            raise ValueError("Memory value cannot be empty")
        key = normalize_key(key)
        memory_type = canonical_memory_type(key, memory_type)
        if memory_type != "context":
            expires_at = None
        incoming_confidence = max(0.0, min(1.0, float(confidence)))
        existing = self.get_by_key(db, user_id=user_id, key=key)
        now = datetime.now(timezone.utc)

        if existing is not None:
            same_value = _normalize_value_for_compare(existing.value) == _normalize_value_for_compare(serialized_value)
            authoritative = _is_authoritative_source(source)
            existing_authoritative = _is_authoritative_source(existing.source)
            should_replace = authoritative or (
                not existing_authoritative
                and incoming_confidence >= float(existing.confidence)
            )
            if same_value:
                # Idempotent duplicate: keep the strongest evidence and refresh
                # expiring context without creating a conflict entry.
                if authoritative or (
                    not existing_authoritative
                    and incoming_confidence >= float(existing.confidence)
                ):
                    if source:
                        existing.source = source
                    existing.memory_type = memory_type
                existing.confidence = max(float(existing.confidence), incoming_confidence)
                if memory_type == "context" and expires_at is not None:
                    existing.expires_at = expires_at
            elif should_replace:
                _append_conflict(
                    existing, value=existing.value, memory_type=existing.memory_type,
                    confidence=existing.confidence, source=existing.source,
                    timestamp=now, status="replaced",
                )
                existing.value = serialized_value
                existing.memory_type = memory_type
                existing.confidence = incoming_confidence
                existing.expires_at = expires_at
                if source:
                    existing.source = source
            else:
                _append_conflict(
                    existing, value=serialized_value, memory_type=memory_type,
                    confidence=incoming_confidence, source=source,
                    timestamp=now, status="rejected_lower_confidence",
                )
            existing.importance = max(existing.importance, importance)
            existing.updated_at = now
            existing.key = key
            db.add(existing)
            db.commit()
            db.refresh(existing)
            return existing

        obj = Memory(
            user_id=user_id, key=key, value=serialized_value,
            memory_type=memory_type, importance=importance,
            confidence=incoming_confidence, source=source,
            conflict_history="[]", expires_at=expires_at,
            created_at=now, updated_at=now,
        )
        db.add(obj)
        try:
            db.commit()
            db.refresh(obj)
            return obj
        except IntegrityError:
            # A concurrent worker won the unique-key race.
            db.rollback()
            if self.get_by_key(db, user_id=user_id, key=key) is None:
                raise
            return self.upsert(
                db, user_id=user_id, key=key, value=serialized_value,
                memory_type=memory_type, importance=importance,
                confidence=incoming_confidence, source=source, expires_at=expires_at,
            )

    def reconcile_user_memories(self, db: Session, *, user_id: str) -> int:
        """Merge legacy aliases and remove expired contexts for one user."""
        rows = list(db.scalars(_select(Memory).where(Memory.user_id == user_id)).all())
        now = datetime.now(timezone.utc)
        removed = 0
        changed = False
        groups: dict[str, list[Memory]] = {}
        for row in rows:
            expires_at = row.expires_at
            if expires_at is not None:
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                if expires_at <= now:
                    db.delete(row)
                    removed += 1
                    changed = True
                    continue
            groups.setdefault(normalize_key(row.key), []).append(row)

        def rank(item: Memory) -> tuple[float, float, int]:
            changed_at = item.updated_at or item.created_at or now
            if changed_at.tzinfo is None:
                changed_at = changed_at.replace(tzinfo=timezone.utc)
            return (float(item.confidence), changed_at.timestamp(), int(item.key == normalize_key(item.key)))

        for canonical, group in groups.items():
            winner = max(group, key=rank)
            losers = [item for item in group if item is not winner]
            for loser in losers:
                if _normalize_value_for_compare(loser.value) != _normalize_value_for_compare(winner.value):
                    _append_conflict(
                        winner, value=loser.value, memory_type=loser.memory_type,
                        confidence=loser.confidence, source=loser.source,
                        timestamp=now, status="merged_legacy_duplicate",
                    )
                winner.importance = max(winner.importance, loser.importance)
                db.delete(loser)
                removed += 1
                changed = True
            if losers:
                db.flush()
            if winner.key != canonical:
                winner.key = canonical
                changed = True
            expected_type = canonical_memory_type(canonical, winner.memory_type)
            if winner.memory_type != expected_type:
                winner.memory_type = expected_type
                changed = True
            db.add(winner)
        if changed:
            db.commit()
        return removed

    def delete_by_key(self, db: Session, *, user_id: str, key: str) -> bool:
        obj = self.get_by_key(db, user_id=user_id, key=key)
        if obj is None:
            return False
        db.delete(obj)
        db.commit()
        return True

    def delete_many_by_keys(self, db: Session, *, user_id: str, keys: list[str]) -> int:
        from sqlalchemy import delete as _delete
        candidates = set(keys) | {normalize_key(key) for key in keys}
        result = db.execute(_delete(Memory).where(
            Memory.user_id == user_id, Memory.key.in_(candidates),
        ))
        db.commit()
        return result.rowcount

    def as_dict(
        self, db: Session, *, user_id: str, include_context: bool = False,
    ) -> dict[str, str]:
        memories = self.get_by_user(db, user_id=user_id)
        return {
            item.key: item.value for item in memories
            if include_context or item.memory_type != "context"
        }


memory = CRUDMemory()
