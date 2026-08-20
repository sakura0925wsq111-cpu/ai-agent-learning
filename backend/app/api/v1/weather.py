# -*- coding: utf-8 -*-
"""Weather API - Open-Meteo (free, no key required)."""

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from loguru import logger

from schemas.response import APIResponse

router = APIRouter(prefix="/weather", tags=["weather"])

# Chinese city coordinates (lat, lon)
CITY_COORDS = {
    # 直辖市 / 省会
    (39.90, 116.40): ["北京"],
    (31.23, 121.47): ["上海"],
    (23.13, 113.26): ["广州"],
    (22.54, 114.06): ["深圳"],
    (30.27, 120.15): ["杭州"],
    (32.06, 118.80): ["南京"],
    (30.58, 114.30): ["武汉"],
    (30.57, 104.07): ["成都"],
    (29.57, 106.55): ["重庆"],
    (34.26, 108.94): ["西安"],
    (36.07, 120.38): ["青岛"],
    (36.67, 116.98): ["济南"],
    (38.91, 121.61): ["大连"],
    (39.13, 117.18): ["天津"],
    (28.23, 112.94): ["长沙"],
    (31.30, 120.58): ["苏州"],
    (34.76, 113.65): ["郑州"],
    (31.82, 117.23): ["合肥"],
    (24.48, 118.08): ["厦门"],
    (26.07, 119.30): ["福州"],
    (25.04, 102.68): ["昆明"],
    (22.82, 108.37): ["南宁"],
    (41.80, 123.43): ["沈阳"],
    (43.88, 125.32): ["长春"],
    (45.80, 126.53): ["哈尔滨"],
    (43.83, 87.62): ["乌鲁木齐"],
    (36.06, 103.83): ["兰州"],
    (37.87, 112.55): ["太原"],
    (20.02, 110.35): ["海口"],
    (18.25, 109.51): ["三亚"],
    (26.65, 106.63): ["贵阳"],
    # 地级市
    (28.00, 120.70): ["温州"],
    (29.87, 121.55): ["宁波"],
    (31.57, 120.29): ["无锡"],
    (23.05, 113.75): ["东莞"],
    (23.02, 113.12): ["佛山"],
    (22.52, 113.38): ["中山"],
    (22.27, 113.58): ["珠海"],
    (23.11, 114.42): ["惠州"],
    (37.46, 121.45): ["烟台"],
    (36.71, 119.16): ["潍坊"],
    (36.81, 118.05): ["淄博"],
    (36.20, 117.13): ["泰安"],
    (37.52, 122.12): ["威海"],
    (35.43, 119.53): ["日照"],
    (35.10, 118.36): ["临沂"],
    (37.45, 116.31): ["德州"],
}

# Build a reverse lookup: city name -> (lat, lon)
_CITY_LOOKUP = {}
for coords, names in CITY_COORDS.items():
    for name in names:
        _CITY_LOOKUP[name] = coords


class WeatherResponse(BaseModel):
    temp: int = Field(0)
    condition: str = Field("")
    icon: str = Field("")
    humidity: int = Field(0)
    wind: str = Field("")
    location: str = Field("")
    advice: str = Field("")


# WMO weather codes to Chinese
WMO_CODES = {
    0: "晴",
    1: "少云",
    2: "局部多云",
    3: "多云",
    45: "雾",
    48: "冻雾",
    51: "小毛毛雨",
    53: "中毛毛雨",
    55: "大毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    80: "阵雨",
    81: "中阵雨",
    82: "大阵雨",
    95: "雷暴",
    96: "冰雹雷暴",
}


def resolve_city_coords(city: str) -> tuple[float, float] | None:
    """Resolve a city name without substituting a different city on failure."""
    city = str(city or "").strip()
    if not city:
        return None
    if city in _CITY_LOOKUP:
        return _CITY_LOOKUP[city]
    try:
        r = httpx.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "zh", "format": "json"},
            timeout=5,
        )
        data = r.json()
        if data.get("results"):
            loc = data["results"][0]
            return (loc["latitude"], loc["longitude"])
    except Exception as e:
        logger.warning("Geocoding failed: {}", e)
    return None


# Backward-compatible private name for callers that imported the old helper.
_resolve_coords = resolve_city_coords


def _condition_icon(cond):
    """Map weather condition to a platform-independent emoji."""
    if "雷" in cond:
        return "⛈️"
    if "雪" in cond:
        return "❄️"
    if "雨" in cond:
        return "🌧️"
    if "晴" in cond:
        return "☀️"
    if "雾" in cond:
        return "🌫️"
    return "☁️"


def _build_advice(temp, cond):
    """Build weather advice based on temperature and condition."""
    if "雷" in cond:
        return "今天有雷暴天气，尽量避免户外活动，注意安全哦~"
    if "雪" in cond:
        return "下雪天路滑，出门注意保暖和防滑！"
    if "雨" in cond:
        return "下雨天记得带伞，路面湿滑注意安全~"
    if temp >= 35:
        return "高温预警！注意防暑降温，多喝水，避免长时间户外活动。"
    if temp <= -5:
        return "天气严寒，出门一定穿厚点，围巾帽子都安排上！"
    if temp <= 5:
        return "天气较冷，注意保暖，多喝热水~"
    if temp >= 30:
        return "天气炎热，出门注意防晒，多补充水分~"
    if 15 <= temp <= 25:
        return "天气舒适宜人，适合出门散步或运动！"
    return "天气不错，祝你有愉快的一天~"


_WIND_DIRS = ["北", "东北", "东", "东南", "南", "西南", "西", "西北"]


async def fetch_weather(city: str, *, timeout: float = 8) -> WeatherResponse | None:
    """Fetch normalized current weather for reuse by weather and Today APIs."""
    coords = resolve_city_coords(city)
    if coords is None:
        logger.warning("Weather city could not be resolved: {}", city)
        return None
    lat, lon = coords
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m,wind_direction_10m",
                    "timezone": "Asia/Shanghai",
                },
                timeout=timeout,
            )
            response.raise_for_status()
            current = response.json()["current"]
        code = current["weather_code"]
        temp = round(current["temperature_2m"])
        humidity = current["relative_humidity_2m"]
        wind_speed = current.get("wind_speed_10m", 0)
        wind_direction = current.get("wind_direction_10m", 0)
        condition = WMO_CODES.get(code, "未知")
        direction_index = round(wind_direction / 45) % 8
        wind = (
            _WIND_DIRS[direction_index] + "风 " + str(round(wind_speed)) + "级"
            if wind_speed > 0 else "无风"
        )
        return WeatherResponse(
            temp=temp,
            condition=condition,
            icon=_condition_icon(condition),
            humidity=humidity,
            wind=wind,
            location=city,
            advice=_build_advice(temp, condition),
        )
    except Exception as exc:
        logger.warning("Weather fetch failed for {}: {}", city, exc)
        return None


@router.get("", response_model=APIResponse[WeatherResponse])
async def get_weather(city: str = Query("北京", description="city name")):
    """Get current weather for a city."""
    weather = await fetch_weather(city)
    if weather is None:
        raise HTTPException(status_code=503, detail="天气数据暂时获取不到，请稍后重试")
    logger.info(
        "Weather: {} {}C {} {}% {}",
        city, weather.temp, weather.condition, weather.humidity, weather.wind,
    )
    return APIResponse.ok(data=weather)
