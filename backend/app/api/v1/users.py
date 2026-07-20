"""User REST API — CRUD endpoints for /api/v1/users."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database.session import get_db
from schemas.response import APIResponse
from schemas.user import UserCreate, UserUpdate, UserResponse
from crud.user import user as user_crud
from core.exceptions import NotFoundException

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=APIResponse[UserResponse], status_code=201)
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    """Create a new user."""
    data = payload.model_dump(exclude_unset=True)
    obj = user_crud.create(db, obj_in=data)
    return APIResponse.ok(data=UserResponse.model_validate(obj))


@router.get("/{user_id}", response_model=APIResponse[UserResponse])
def get_user(user_id: str, db: Session = Depends(get_db)):
    """Get a user by ID."""
    obj = user_crud.get(db, id=user_id)
    if obj is None:
        raise NotFoundException(f"User {user_id} not found")
    return APIResponse.ok(data=UserResponse.model_validate(obj))


@router.put("/{user_id}", response_model=APIResponse[UserResponse])
def update_user(user_id: str, payload: UserUpdate, db: Session = Depends(get_db)):
    """Update a user (partial update)."""
    obj = user_crud.get(db, id=user_id)
    if obj is None:
        raise NotFoundException(f"User {user_id} not found")
    update_data = payload.model_dump(exclude_unset=True)
    obj = user_crud.update(db, db_obj=obj, obj_in=update_data)
    return APIResponse.ok(data=UserResponse.model_validate(obj))


@router.delete("/{user_id}", response_model=APIResponse[dict])
def delete_user(user_id: str, db: Session = Depends(get_db)):
    """Delete a user."""
    obj = user_crud.delete(db, id=user_id)
    if obj is None:
        raise NotFoundException(f"User {user_id} not found")
    return APIResponse.ok(data={"deleted": user_id})
