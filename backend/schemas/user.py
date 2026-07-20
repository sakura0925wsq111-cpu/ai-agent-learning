"""User Pydantic schemas — request/response models for User API."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    """Payload for creating a new user."""

    nickname: str = Field(default="", max_length=100, description="User nickname")
    avatar: Optional[str] = Field(default=None, max_length=500, description="Avatar URL")
    major: Optional[str] = Field(default=None, max_length=200, description="Major / field of study")
    grade: Optional[str] = Field(default=None, max_length=50, description="Grade / year")
    target: Optional[str] = Field(default=None, description="Academic / career target")


class UserUpdate(BaseModel):
    """Payload for updating an existing user (partial update)."""

    nickname: Optional[str] = Field(default=None, max_length=100)
    avatar: Optional[str] = Field(default=None, max_length=500)
    major: Optional[str] = Field(default=None, max_length=200)
    grade: Optional[str] = Field(default=None, max_length=50)
    target: Optional[str] = Field(default=None)


class UserResponse(BaseModel):
    """User response model returned by the API."""

    id: str
    nickname: str
    avatar: Optional[str] = None
    major: Optional[str] = None
    grade: Optional[str] = None
    target: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
