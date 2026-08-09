# -*- coding: utf-8 -*-
"""Growth → Today Sync API — plan sync + progress feedback."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from loguru import logger

from database.session import get_db
from schemas.response import APIResponse
from schemas.today import SyncPlanRequest, PlanProgressResponse
from services.today import TodayService
from services.llm_service import get_llm_service
from utils.auth import get_current_user_id, require_user_access

router = APIRouter()


@router.post("/sync-plan", response_model=APIResponse[dict])
def sync_plan(
    payload: SyncPlanRequest,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """Sync a Growth plan phase into daily Todo items.

    Idempotent: calling twice for the same phase returns 0 synced_count.
    """
    require_user_access(payload.user_id, current_user_id)
    service = TodayService()
    try:
        result = service.sync_growth_plan(
            db,
            user_id=payload.user_id,
            growth_session_id=payload.growth_session_id,
            phase=payload.phase,
        )
        return APIResponse.ok(data=result)
    except ValueError as exc:
        logger.warning("Sync plan failed: {}", exc)
        return APIResponse.error(code=400, message=str(exc))


@router.get("/progress", response_model=APIResponse[dict])
def get_progress(
    user_id: str = Query(..., description="User ID"),
    growth_session_id: str = Query(..., description="Growth session ID"),
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """Query completion progress of a synced growth plan.

    Used by Growth Agent to perceive daily task completion status
    and adjust subsequent planning recommendations.
    """
    require_user_access(user_id, current_user_id)
    service = TodayService()
    result = service.get_plan_progress(
        db,
        user_id=user_id,
        growth_session_id=growth_session_id,
    )
    return APIResponse.ok(data=result)
