"""CRUD operations for Conversation model."""

from typing import Sequence

from sqlalchemy import select as _select
from sqlalchemy.orm import Session

from crud.base import CRUDBase
from models.conversation import Conversation


class CRUDConversation(CRUDBase[Conversation]):
    """Conversation CRUD with domain-specific methods."""

    def __init__(self) -> None:
        super().__init__(Conversation)

    def get_by_user(
        self,
        db: Session,
        *,
        user_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[Conversation]:
        """Get conversation messages for a user, ordered by creation time."""
        stmt = (
            _select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.created_at.asc())
            .offset(skip)
            .limit(limit)
        )
        return db.scalars(stmt).all()

    def get_recent(
        self,
        db: Session,
        *,
        user_id: str,
        n: int = 20,
    ) -> Sequence[Conversation]:
        """Get the most recent N messages for a user."""
        stmt = (
            _select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.created_at.desc())
            .limit(n)
        )
        return list(reversed(db.scalars(stmt).all()))

    def delete_by_user(self, db: Session, *, user_id: str) -> int:
        """Delete all messages for a user. Returns count deleted."""
        from sqlalchemy import delete as _delete

        result = db.execute(_delete(Conversation).where(Conversation.user_id == user_id))
        db.commit()
        return result.rowcount


conversation = CRUDConversation()
