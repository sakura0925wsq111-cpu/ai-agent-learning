"""Unified API response envelope.

Every endpoint returns this structure:
{
    "code": 0,           # 0 = success, nonzero = error
    "message": "success",
    "data": { ... }      # payload or null on error
}
"""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    """Standard wrapper for all API responses."""

    code: int = 0
    message: str = "success"
    data: T | None = None

    @classmethod
    def ok(cls, data: T = None, message: str = "success") -> "APIResponse[T]":
        """Success response."""
        return cls(code=0, message=message, data=data)

    @classmethod
    def error(cls, code: int, message: str) -> "APIResponse[None]":
        """Error response."""
        return cls(code=code, message=message, data=None)
