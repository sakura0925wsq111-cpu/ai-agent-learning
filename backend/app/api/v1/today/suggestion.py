# -*- coding: utf-8 -*-
"""AI Today Suggestion API — LLM-powered daily advice."""

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from loguru import logger

from database.session import get_db
from schemas.response import APIResponse
from schemas.today import TodaySuggestionRequest
from services.today import TodayService
from services.llm_service import get_llm_service
from utils.auth import get_current_user_id, require_user_access

router = APIRouter()


@router.post("/suggestion", response_model=APIResponse[dict])
async def get_suggestion(
    payload: TodaySuggestionRequest,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """Generate an AI-powered daily suggestion with weather + growth context."""
    require_user_access(payload.user_id, current_user_id)
    llm = get_llm_service()
    service = TodayService(llm_service=llm)

    # Fetch weather for suggestion context
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
                    "condition": _code_to_condition(cur["weather_code"]),
                    "location": payload.city,
                    "advice": _weather_advice(round(cur["temperature_2m"]), cur["weather_code"]),
                }
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


def _code_to_condition(code: int) -> str:
    mapping = {
        0: "晴", 1: "少云", 2: "局部多云", 3: "多云",
        45: "雾", 51: "小毛毛雨", 53: "中毛毛雨", 55: "大毛毛雨",
        61: "小雨", 63: "中雨", 65: "大雨",
        71: "小雪", 73: "中雪", 75: "大雪",
        80: "阵雨", 95: "雷暴",
    }
    return mapping.get(code, "未知")


def _weather_advice(temp: int, code: int) -> str:
    if code in (95, 96):
        return "今天有雷暴天气，尽量避免户外活动，注意安全哦~"
    if code in (71, 73, 75):
        return "下雪天路滑，出门注意保暖和防滑！"
    if code in (61, 63, 65, 80):
        return "下雨天记得带伞，路面湿滑注意安全~"
    if temp >= 35:
        return "高温预警！注意防暑降温，多喝水。"
    if temp <= 5:
        return "天气较冷，注意保暖，多喝热水~"
    if 15 <= temp <= 25:
        return "天气舒适宜人，适合出门散步或运动！"
    return "天气不错，祝你有愉快的一天~"
