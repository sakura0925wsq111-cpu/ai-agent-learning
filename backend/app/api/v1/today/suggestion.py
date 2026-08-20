# -*- coding: utf-8 -*-
"""AI Today Suggestion API — LLM-powered daily advice."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from loguru import logger

from database.session import get_db
from schemas.response import APIResponse
from schemas.today import TodaySuggestionRequest
from services.today import TodayService
from services.llm_service import get_llm_service
from utils.auth import get_current_user_id, require_user_access
from core.rate_limit import enforce_ai_daily_limit
from app.api.v1.weather import fetch_weather

router = APIRouter()


@router.post("/suggestion", response_model=APIResponse[dict])
async def get_suggestion(
    payload: TodaySuggestionRequest,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(enforce_ai_daily_limit),
):
    """Generate an AI-powered daily suggestion with weather + growth context."""
    require_user_access(payload.user_id, current_user_id)
    llm = get_llm_service()
    service = TodayService(llm_service=llm)

    # Fetch weather for suggestion context
    weather = None
    try:
        resolved = await fetch_weather(payload.city, timeout=5)
        weather = resolved.model_dump() if resolved is not None else None
    except Exception as exc:
        logger.warning("Suggestion weather fetch failed: {}", exc)

    # Try loading growth progress
    growth_progress = None
    try:
        from services.today.today_service import PlanTask
        from models.today import PlanTask as PT
        from models.todo import Todo
        pt = db.query(PT).filter(
            PT.user_id == payload.user_id,
        ).order_by(PT.synced_at.desc()).first()
        if pt:
            todos_all = db.query(PT).filter(
                PT.user_id == payload.user_id,
                PT.growth_session_id == pt.growth_session_id,
            ).all()
            total = len(todos_all)
            completed = 0
            for t in todos_all:
                todo = db.query(Todo).filter(Todo.id == t.todo_id).first()
                if todo and todo.status in ("done", "archived"):
                    completed += 1
            growth_progress = {
                "agent_type": "成长规划",
                "current_phase": {"phase_1": "第1-2周", "phase_2": "第3-4周",
                                  "phase_3": "第5-8周", "phase_4": "第9-12周"}.get(
                    pt.phase_key, pt.phase_key),
                "overall_completion": completed / total if total > 0 else 0,
            }
    except Exception as exc:
        logger.debug("Growth progress lookup skipped: {}", exc)

    result = service.generate_suggestion(
        db,
        user_id=payload.user_id,
        weather=weather,
        growth_progress=growth_progress,
    )
    return APIResponse.ok(data=result)
