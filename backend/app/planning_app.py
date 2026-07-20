# -*- coding: utf-8 -*-
"""CampusPal Planning API — standalone FastAPI application.

Run:
    cd backend
    python -m app.planning_app

Or with uvicorn:
    uvicorn app.planning_app:app --reload --port 8001

This is a self-contained app for the PlanningAgent framework.
It can also be integrated into the main CampusPal app by importing its router.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.planning import router as planning_router
from core.config import settings
from core.logger import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    from loguru import logger
    logger.info(
        "CampusPal Planning API v{} starting (port 8001)...",
        settings.app_version,
    )
    logger.info("Available agents: career, graduate, civil, major")
    logger.info("Docs at http://localhost:8001/docs")
    yield
    logger.info("CampusPal Planning API shutting down.")


app = FastAPI(
    title="CampusPal Planning API",
    version=settings.app_version,
    description="Multi-agent growth planning framework for Chinese university students",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register planning routes
app.include_router(planning_router)


@app.get("/", tags=["system"])
async def root():
    return {
        "app": "CampusPal Planning API",
        "version": settings.app_version,
        "docs": "/docs",
        "agents": [
            {"type": "career", "label": "就业规划"},
            {"type": "graduate", "label": "考研规划"},
            {"type": "civil", "label": "考公考编规划"},
            {"type": "major", "label": "转专业规划"},
        ],
    }


# ── Integration helper: include in main CampusPal app ──────────
# In app/main.py, add:
#   from api.planning import router as planning_router
#   app.include_router(planning_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.planning_app:app", host="0.0.0.0", port=8001, reload=True)
