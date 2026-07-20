"""CRUD operations for Memory model."""

from typing import Optional, Sequence

from sqlalchemy import select as _select
from sqlalchemy.orm import Session

from crud.base import CRUDBase
from models.memory import Memory


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
    ) -> Sequence[Memory]:
        """Get all memory entries for a user, ordered by importance desc."""
        stmt = (
            _select(Memory)
            .where(Memory.user_id == user_id)
            .order_by(Memory.importance.desc(), Memory.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return db.scalars(stmt).all()

    def get_by_key(self, db: Session, *, user_id: str, key: str) -> Optional[Memory]:
        """Get a specific memory entry by user_id and key."""
        stmt = _select(Memory).where(
            Memory.user_id == user_id, Memory.key == key
        )
        return db.scalars(stmt).first()

    def upsert(
        self,
        db: Session,
        *,
        user_id: str,
        key: str,
        value: str,
        importance: int = 1,
    ) -> Memory:
        """Insert or update a memory entry.

        If a record with the same (user_id, key) exists, update it.
        Otherwise, create a new one.
        """
        existing = self.get_by_key(db, user_id=user_id, key=key)
        if existing:
            existing.value = value
            if importance is not None:
                existing.importance = importance
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
                    "value": value,
                    "importance": importance,
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

    def as_dict(self, db: Session, *, user_id: str) -> dict[str, str]:
        """Return all memories for a user as a {key: value} dictionary."""
        memories = self.get_by_user(db, user_id=user_id)
        return {m.key: m.value for m in memories}


memory = CRUDMemory()
