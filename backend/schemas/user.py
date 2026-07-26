"""User Pydantic schemas — request/response models for User API."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Payload for user login."""

    student_id: str = Field(..., min_length=1, max_length=50, description="Student ID")
    password: str = Field(..., min_length=1, max_length=100, description="Password")


class UserCreate(BaseModel):
    """Payload for creating a new user."""

    student_id: str = Field(..., min_length=1, max_length=50, description="Student ID")
    name: str = Field(..., min_length=1, max_length=100, description="Real name")
    password: str = Field(..., min_length=6, max_length=100, description="Password")
    school: str = Field(default="", max_length=200, description="School name")
    college: str = Field(default="", max_length=200, description="College name")
    major: str = Field(default="", max_length=200, description="Major / field of study")
    enroll_year: str = Field(default="", max_length=10, description="Enrollment year")
    nickname: Optional[str] = Field(default=None, max_length=100, description="Nickname (defaults to name)")
    grade: Optional[str] = Field(default=None, max_length=50, description="Grade / year")


class UserUpdate(BaseModel):
    """Payload for updating an existing user (partial update)."""

    name: Optional[str] = Field(default=None, max_length=100)
    nickname: Optional[str] = Field(default=None, max_length=100)
    student_id: Optional[str] = Field(default=None, max_length=50)
    school: Optional[str] = Field(default=None, max_length=200)
    college: Optional[str] = Field(default=None, max_length=200)
    major: Optional[str] = Field(default=None, max_length=200)
    grade: Optional[str] = Field(default=None, max_length=50)
    enroll_year: Optional[str] = Field(default=None, max_length=10)


class UserResponse(BaseModel):
    """User response model returned by the API."""

    id: str
    student_id: Optional[str] = None
    name: str
    nickname: str
    avatar: Optional[str] = None
    school: Optional[str] = None
    college: Optional[str] = None
    major: Optional[str] = None
    grade: Optional[str] = None
    enroll_year: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LoginResponse(BaseModel):
    """Response for login / register."""

    token: str
    user_id: str
    user: UserResponse
