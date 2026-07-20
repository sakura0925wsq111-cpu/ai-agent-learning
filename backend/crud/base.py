"""Base CRUD class with common SQLAlchemy 2.0 patterns."""

from typing import Any, Generic, Optional, Sequence, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from database.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class CRUDBase(Generic[ModelType]):
    """Generic CRUD operations for any SQLAlchemy model.

    Usage:
        user_crud = CRUDBase[User](User)
    """

    def __init__(self, model: type[ModelType]) -> None:
        self.model = model

    def get(self, db: Session, id: Any) -> Optional[ModelType]:
        """Get a single record by primary key."""
        return db.get(self.model, id)

    def get_multi(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 100,
        **filters: Any,
    ) -> Sequence[ModelType]:
        """Get multiple records with optional filters."""
        stmt: Select = select(self.model)
        for field, value in filters.items():
            if value is not None:
                stmt = stmt.where(getattr(self.model, field) == value)
        stmt = stmt.offset(skip).limit(limit)
        return db.scalars(stmt).all()

    def count(self, db: Session, **filters: Any) -> int:
        """Count records with optional filters."""
        stmt = select(func.count()).select_from(self.model)
        for field, value in filters.items():
            if value is not None:
                stmt = stmt.where(getattr(self.model, field) == value)
        return db.scalar(stmt) or 0

    def create(self, db: Session, *, obj_in: dict[str, Any]) -> ModelType:
        """Create a new record."""
        db_obj = self.model(**obj_in)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(
        self,
        db: Session,
        *,
        db_obj: ModelType,
        obj_in: dict[str, Any],
    ) -> ModelType:
        """Update an existing record."""
        for field, value in obj_in.items():
            if value is not None:
                setattr(db_obj, field, value)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def delete(self, db: Session, *, id: Any) -> Optional[ModelType]:
        """Delete a record by primary key."""
        obj = db.get(self.model, id)
        if obj:
            db.delete(obj)
            db.commit()
        return obj

    def exists(self, db: Session, **filters: Any) -> bool:
        """Check if any record matches the filters."""
        return self.count(db, **filters) > 0
