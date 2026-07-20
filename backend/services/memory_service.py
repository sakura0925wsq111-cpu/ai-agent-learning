"""Memory Service — high-level API for managing user memories.

Used by both REST endpoints and the Chat pipeline (Agent).
Provides save/load/update/delete with validation.
"""

from typing import Optional

from loguru import logger
from sqlalchemy.orm import Session

from crud.memory import memory as memory_crud
from models.memory import Memory
from schemas.memory import MemoryCreate, MemoryUpdate, MemoryResponse
from core.exceptions import NotFoundException


class MemoryService:
    """Service layer for Memory CRUD operations."""

    def save_memory(self, db: Session, *, data: MemoryCreate) -> MemoryResponse:
        """Save a new memory or update an existing one (upsert)."""
        logger.info(f"Saving memory: user={data.user_id}, key={data.key}")

        obj = memory_crud.upsert(
            db,
            user_id=data.user_id,
            key=data.key,
            value=data.value,
            importance=data.importance,
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
        """Batch upsert multiple memory items for a user."""
        results: list[MemoryResponse] = []
        for item in items:
            obj = memory_crud.upsert(
                db,
                user_id=user_id,
                key=item["key"],
                value=item["value"],
                importance=item.get("importance", 1),
            )
            results.append(MemoryResponse.model_validate(obj))
        logger.info(f"Batch saved {len(results)} memories for user={user_id}")
        return results

    def load_memory(
        self,
        db: Session,
        *,
        user_id: str,
        as_dict: bool = False,
    ) -> list[MemoryResponse] | dict[str, str]:
        """Load all memories for a user.

        Args:
            as_dict: If True, return {key: value} dict. Otherwise list of MemoryResponse.
        """
        if as_dict:
            return memory_crud.as_dict(db, user_id=user_id)

        memories = memory_crud.get_by_user(db, user_id=user_id)
        return [MemoryResponse.model_validate(m) for m in memories]

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
        """Format all user memories as a string for system prompt injection."""
        memories = memory_crud.get_by_user(db, user_id=user_id)
        if not memories:
            return ""

        lines = ["## 用户已知信息"]
        for m in memories:
            lines.append(f"- {m.key}: {m.value}")
        return "\n".join(lines)


# Singleton
memory_service = MemoryService()
