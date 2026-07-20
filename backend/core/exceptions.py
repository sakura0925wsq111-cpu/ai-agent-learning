"""Custom exceptions and global exception handlers for FastAPI."""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger

from schemas.response import APIResponse


class AppException(Exception):
    """Base application exception with HTTP status and error code."""

    def __init__(self, message: str, status_code: int = 400, error_code: int = 1):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(message)


class NotFoundException(AppException):
    """Resource not found (404)."""

    def __init__(self, message: str = "Resource not found"):
        super().__init__(message=message, status_code=404, error_code=404)


class ValidationException(AppException):
    """Request validation error (422)."""

    def __init__(self, message: str = "Validation failed"):
        super().__init__(message=message, status_code=422, error_code=422)


# ── Global exception handlers ──


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Convert FastAPI validation errors to unified APIResponse format.

    Extracts the first error message from Pydantic's error list.
    """
    errors = exc.errors()
    message = errors[0]["msg"] if errors else "Validation failed"
    logger.warning(f"Validation error: {message} (path={request.url.path})")

    return JSONResponse(
        status_code=422,
        content=APIResponse.error(code=422, message=f"Validation error: {message}").model_dump(),
    )


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Handle known application exceptions."""
    logger.warning(f"AppException: {exc.message} (status={exc.status_code})")
    return JSONResponse(
        status_code=exc.status_code,
        content=APIResponse.error(code=exc.error_code, message=exc.message).model_dump(),
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unexpected errors."""
    logger.exception(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content=APIResponse.error(code=500, message="Internal server error").model_dump(),
    )
