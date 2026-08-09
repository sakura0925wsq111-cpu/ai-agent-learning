# -*- coding: utf-8 -*-
"""Today Overview API — aggregated daily snapshot."""

import httpx
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from loguru import logger

from database.session import get_db
from schemas.response import APIResponse
from services.today import TodayService
from utils.auth import get_current_user_id, require_user_access

router = APIRouter()


def _get_today_service() -> TodayService:
    return TodayService()


CITY_COORDS_CACHE: dict[str, tuple[float, float]] = {}


@router.get("/overview", response_model=APIResponse[dict])
async def get_overview(
    user_id: str = Query(..., description="User ID"),
    city: str = Query("北京", description="City for weather"),
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """Get today's overview: greeting, weather, courses, todos, nearest exam."""
    require_user_access(user_id, current_user_id)
    service = _get_today_service()
    overview = service.get_overview(db, user_id=user_id)

    # Fetch weather (reuse logic from weather API)
    weather = None
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": 39.90,
                    "longitude": 116.40,
                    "current": "temperature_2m,relative_humidity_2m,weather_code",
                    "timezone": "Asia/Shanghai",
                },
                timeout=5,
            )
            if r.status_code == 200:
                data = r.json()
                cur = data["current"]
                weather = {
                    "temp": round(cur["temperature_2m"]),
                    "humidity": cur["relative_humidity_2m"],
                    "code": cur["weather_code"],
                    "location": city,
                }
    except Exception as exc:
        logger.warning("Overview weather fetch failed: {}", exc)

    overview["weather"] = weather
    return APIResponse.ok(data=overview)


@router.get("/timeline", response_model=APIResponse[dict])
def get_timeline(
    user_id: str = Query(..., description="User ID"),
    date: str | None = Query(None, description="Date in YYYY-MM-DD format, defaults to today"),
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """Get a merged timeline of courses + exams + todos for a given date."""
    require_user_access(user_id, current_user_id)
    from datetime import date as date_type
    target = None
    if date:
        try:
            target = date_type.fromisoformat(date)
        except ValueError:
            return APIResponse.error(code=400, message="Invalid date format, use YYYY-MM-DD")

    service = TodayService()
    result = service.get_timeline(db, user_id=user_id, target_date=target)
    return APIResponse.ok(data=result)


@router.get("/calendar", response_model=APIResponse[dict])
def get_calendar(
    user_id: str = Query(..., description="User ID"),
    year: int = Query(..., ge=2020, le=2100, description="Year"),
    month: int = Query(..., ge=1, le=12, description="Month"),
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """Get a full month calendar with daily events.

    Returns all events for every day of the month, grouped by date.
    Frontend can crop this into week/month views without extra requests.
    """
    require_user_access(user_id, current_user_id)
    service = TodayService()
    result = service.get_calendar(db, user_id=user_id, year=year, month=month)
    return APIResponse.ok(data=result)

