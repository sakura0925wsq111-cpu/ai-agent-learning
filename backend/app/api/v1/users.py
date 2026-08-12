"""User REST API — CRUD endpoints for /api/v1/users."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from loguru import logger

from database.session import get_db
from schemas.response import APIResponse
from schemas.user import (
    UserCreate, UserUpdate, UserResponse,
    LoginRequest, LoginResponse,
)
from crud.user import user as user_crud
from core.exceptions import NotFoundException
from core.rate_limit import enforce_login_rate_limit
from utils.auth import (
    create_token,
    get_current_user_id,
    hash_password,
    require_user_access,
    verify_password,
)
from services.memory_service import memory_service

router = APIRouter(prefix="/users", tags=["users"])


def _sync_user_to_memory(
    db: Session,
    user_id: str,
    user_data: dict,
    *,
    source: str = "user_profile_sync",
    confidence: float = 0.99,
) -> None:
    """Sync user profile fields into the memory system."""
    memory_items = []
    field_map = {
        "school": "school",
        "college": "college",
        "major": "major",
        "enroll_year": "enroll_year",
        "grade": "grade",
    }
    for mem_key, data_key in field_map.items():
        value = user_data.get(data_key, "")
        if value:
            memory_items.append({
                "key": mem_key,
                "value": str(value),
                "memory_type": "profile",
                "importance": 7,
                "confidence": confidence,
                "source": source,
            })

    if memory_items:
        try:
            memory_service.save_batch(db, user_id=user_id, items=memory_items)
            logger.info(f"Synced {len(memory_items)} profile fields to memory for user {user_id}")
        except Exception as exc:
            logger.warning(f"Memory sync failed (non-fatal): {exc}")


@router.post("/login", response_model=APIResponse[LoginResponse])
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    """Login with student_id and password."""
    enforce_login_rate_limit(request, payload.student_id)
    user_obj = user_crud.get_by_student_id(db, student_id=payload.student_id)
    if user_obj is None:
        raise HTTPException(status_code=401, detail="学号或密码错误")
    if not user_obj.password_hash:
        raise HTTPException(status_code=401, detail="学号或密码错误")
    if not verify_password(payload.password, user_obj.password_hash):
        raise HTTPException(status_code=401, detail="学号或密码错误")

    token = create_token(user_obj.id)
    user_resp = UserResponse.model_validate(user_obj)

    # Sync existing profile data into memory (ensures memory is up to date)
    _sync_user_to_memory(db, user_obj.id, {
        "name": user_obj.name,
        "student_id": user_obj.student_id,
        "school": user_obj.school,
        "college": user_obj.college,
        "major": user_obj.major,
        "enroll_year": user_obj.enroll_year,
        "grade": user_obj.grade,
    })

    logger.info("User login succeeded: user_id={}", user_obj.id)
    return APIResponse.ok(data=LoginResponse(token=token, user_id=user_obj.id, user=user_resp))


@router.post("", response_model=APIResponse[LoginResponse], status_code=201)
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    """Create a new user (register). Returns token + user info."""
    # Check duplicate student_id
    existing = user_crud.get_by_student_id(db, student_id=payload.student_id)
    if existing:
        raise HTTPException(status_code=409, detail="Student ID already registered")

    data = {
        "student_id": payload.student_id,
        "name": payload.name,
        "nickname": payload.nickname or payload.name,
        "password_hash": hash_password(payload.password),
        "school": payload.school,
        "college": payload.college,
        "major": payload.major,
        "enroll_year": payload.enroll_year,
        "grade": payload.grade or "",
    }
    obj = user_crud.create(db, obj_in=data)
    token = create_token(obj.id)
    user_resp = UserResponse.model_validate(obj)

    # Sync profile fields to memory
    _sync_user_to_memory(db, obj.id, {
        "name": obj.name,
        "student_id": obj.student_id,
        "school": obj.school,
        "college": obj.college,
        "major": obj.major,
        "enroll_year": obj.enroll_year,
        "grade": obj.grade,
    }, source="user_registration", confidence=1.0)

    logger.info("User registered: user_id={}", obj.id)
    return APIResponse.ok(data=LoginResponse(token=token, user_id=obj.id, user=user_resp))


@router.get("/{user_id}", response_model=APIResponse[UserResponse])
def get_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """Get a user by ID."""
    require_user_access(user_id, current_user_id)
    obj = user_crud.get(db, id=user_id)
    if obj is None:
        raise NotFoundException(f"User {user_id} not found")
    return APIResponse.ok(data=UserResponse.model_validate(obj))


@router.put("/{user_id}", response_model=APIResponse[UserResponse])
def update_user(
    user_id: str,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """Update a user (partial update)."""
    require_user_access(user_id, current_user_id)
    obj = user_crud.get(db, id=user_id)
    if obj is None:
        raise NotFoundException(f"User {user_id} not found")
    update_data = payload.model_dump(exclude_unset=True)
    obj = user_crud.update(db, db_obj=obj, obj_in=update_data)

    # Sync updated fields to memory
    changed = {k: v for k, v in update_data.items() if v is not None}
    if changed:
        _sync_user_to_memory(
            db, obj.id, changed,
            source="user_profile_update", confidence=1.0,
        )

    return APIResponse.ok(data=UserResponse.model_validate(obj))


@router.delete("/{user_id}", response_model=APIResponse[dict])
def delete_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """Delete a user."""
    require_user_access(user_id, current_user_id)
    obj = user_crud.delete(db, id=user_id)
    if obj is None:
        raise NotFoundException(f"User {user_id} not found")
    return APIResponse.ok(data={"deleted": user_id})
