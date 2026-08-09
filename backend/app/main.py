# -*- coding: utf-8 -*-
"""CampusPal - AI Decision Coach for university students.

FastAPI application entry point.
Creates the app, registers lifespan events, exception handlers, and routers.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.v1.users import router as users_router_v1
from app.api.v1.memory import router as memory_router_v1
from app.api.v1.growth import router as growth_router_v1
from app.api.v1.weather import router as weather_router_v1
from app.api.v1.sandbox import router as sandbox_router
from app.api.v1.todos import router as todos_router_v1
from app.api.v1.today.router import router as today_router_v1
from core.config import settings
from core.exceptions import (
    AppException,
    app_exception_handler,
    general_exception_handler,
    validation_exception_handler,
)
from core.logger import setup_logging
from database import init_db
from schemas.response import APIResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: init on startup, cleanup on shutdown."""
    # STARTUP
    setup_logging()
    from loguru import logger

    logger.info("{} v{} starting...".format(settings.app_name, settings.app_version))
    env_label = "debug" if settings.debug else "production"
    logger.info("Environment: {}".format(env_label))

    # Import all models so Base.metadata knows about them, then create tables
    import models  # noqa: F401
    init_db()
    logger.info("Database initialized (all tables created if not exist).")

    yield  # App runs here

    # SHUTDOWN
    logger.info("{} shutting down.".format(settings.app_name))


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI Decision Coach for university students - API v1",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handlers
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)

# Routers
app.include_router(health_router)
app.include_router(users_router_v1, prefix="/api/v1")
app.include_router(memory_router_v1, prefix="/api/v1")
app.include_router(growth_router_v1, prefix="/api/v1")
app.include_router(weather_router_v1, prefix="/api/v1")
app.include_router(todos_router_v1, prefix="/api/v1")
app.include_router(today_router_v1, prefix="/api/v1/today")
app.include_router(sandbox_router, prefix="/api/v1/sandbox")


@app.get("/", response_model=APIResponse[dict], tags=["system"])
async def root():
    """API root - returns welcome info."""
    return APIResponse.ok(
        data={
            "app": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs",
            "redoc": "/redoc",
        }
    )
