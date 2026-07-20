"""CRUD operations for User model."""

from typing import Optional, Sequence

from sqlalchemy.orm import Session

from crud.base import CRUDBase
from models.user import User


class CRUDUser(CRUDBase[User]):
    """User CRUD with domain-specific methods."""

    def __init__(self) -> None:
        super().__init__(User)

    def get_by_nickname(self, db: Session, *, nickname: str) -> Optional[User]:
        """Find a user by nickname (case-sensitive)."""
        return db.scalars(
            __import__("sqlalchemy").select(User).where(User.nickname == nickname)
        ).first()

    def get_multi_by_ids(self, db: Session, *, ids: list[str]) -> Sequence[User]:
        """Get multiple users by their IDs."""
        from sqlalchemy import select as _select

        return db.scalars(_select(User).where(User.id.in_(ids))).all()


user = CRUDUser()
