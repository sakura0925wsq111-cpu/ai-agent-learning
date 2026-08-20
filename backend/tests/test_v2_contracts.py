# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.api.v1.today.overview import get_overview
from app.api.v1.today.suggestion import get_suggestion
from app.api.v1.weather import WeatherResponse, fetch_weather, resolve_city_coords
from schemas.growth import GrowthDashboardResponse, GrowthReportResponse
from schemas.response import APIResponse
from schemas.today import SyncPlanRequest, TodayOverviewResponse, TodaySuggestionRequest
from sandbox.schemas import SandboxResultResponse


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "contracts"


def fixture(name: str) -> dict:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


class V2ContractFixtureTests(unittest.TestCase):
    def test_today_complete_empty_and_weather_failure_are_valid(self) -> None:
        payloads = fixture("today.json")
        for name in ("normal", "empty", "weather_failure"):
            parsed = TodayOverviewResponse.model_validate(payloads[name])
            self.assertEqual(parsed.user_id, "fixture-user")
        self.assertIsNone(payloads["weather_failure"]["weather"])

    def test_dashboard_has_all_four_stable_states_and_ratio_units(self) -> None:
        payloads = fixture("dashboard.json")
        self.assertEqual(set(payloads), {"new", "planning", "report_ready", "executing"})
        parsed = {key: GrowthDashboardResponse.model_validate(value) for key, value in payloads.items()}
        self.assertEqual(parsed["planning"].active_session["current_step"], 2)
        self.assertGreaterEqual(parsed["executing"].active_plan["progress"], 0)
        self.assertLessEqual(parsed["executing"].active_plan["progress"], 1)

    def test_sandbox_is_raw_while_v1_uses_envelope(self) -> None:
        raw = fixture("sandbox.json")["complete"]
        sandbox = SandboxResultResponse.model_validate(raw).model_dump()
        envelope = APIResponse.ok(data={"session_id": "growth-1"}).model_dump()
        self.assertNotIn("code", sandbox)
        self.assertEqual(envelope["code"], 0)
        self.assertIn("data", envelope)

    def test_projection_time_is_text_and_matrix_scores_are_one_to_ten(self) -> None:
        payload = SandboxResultResponse.model_validate(fixture("sandbox.json")["complete"])
        projection = payload.projection_result
        self.assertIsNotNone(projection)
        for path in projection.projections:
            self.assertIsInstance(path.time_projection.short_term, str)
            self.assertIsInstance(path.time_projection.mid_term, str)
            self.assertIsInstance(path.time_projection.long_term, str)
        for scores in projection.comparison_matrix.scores.values():
            self.assertTrue(all(1 <= value <= 10 for value in scores))
        missing = SandboxResultResponse.model_validate(fixture("sandbox.json")["missing_matrix"])
        self.assertIsNone(missing.projection_result.comparison_matrix)

    def test_growth_reports_support_complete_legacy_and_missing_plan(self) -> None:
        payloads = fixture("report.json")
        for value in payloads.values():
            parsed = GrowthReportResponse.model_validate(value)
            self.assertIsInstance(parsed.report, dict)

    def test_progress_ratios_never_become_display_percentages_on_backend(self) -> None:
        for value in fixture("progress.json").values():
            ratio = value["overall_completion"]
            self.assertGreaterEqual(ratio, 0)
            self.assertLessEqual(ratio, 1)

    def test_memory_capacity_and_special_character_keys_are_preserved(self) -> None:
        payloads = fixture("memory.json")
        self.assertEqual(payloads["full"]["total"], payloads["full"]["max_capacity"])
        self.assertEqual(payloads["special_key"]["memories"][0]["key"], "偏好/地点&方向")

    def test_sync_start_date_is_optional_and_backward_compatible(self) -> None:
        legacy = SyncPlanRequest(user_id="fixture-user", growth_session_id="growth-1", phase="phase_1")
        enhanced = SyncPlanRequest(user_id="fixture-user", growth_session_id="growth-1", phase="phase_1", start_date="2026-08-17")
        self.assertIsNone(legacy.start_date)
        self.assertEqual(enhanced.start_date.isoformat(), "2026-08-17")

    def test_exam_import_rows_accept_date_cells(self) -> None:
        from datetime import date

        from app.api.v1.today.import_ import _extract_exams_from_rows

        items = _extract_exams_from_rows([
            ("考试科目", "考试日期", "考试地点"),
            ("数据结构", date(2026, 8, 20), "B202"),
        ])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["subject"], "数据结构")
        self.assertEqual(items[0]["exam_date"].isoformat(), "2026-08-20")


class V2WeatherContractTests(unittest.IsolatedAsyncioTestCase):
    def test_known_city_resolution_is_not_beijing(self) -> None:
        self.assertEqual(resolve_city_coords("青岛"), (36.07, 120.38))

    def test_unknown_city_failure_does_not_fall_back_to_beijing(self) -> None:
        with patch("app.api.v1.weather.httpx.get", side_effect=RuntimeError("offline")):
            self.assertIsNone(resolve_city_coords("不存在的城市"))

    async def test_fetch_weather_uses_resolved_coordinates(self) -> None:
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"current": {"temperature_2m": 26.6, "relative_humidity_2m": 70, "weather_code": 2, "wind_speed_10m": 2.2, "wind_direction_10m": 90}}
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.get = AsyncMock(return_value=response)
        with patch("app.api.v1.weather.httpx.AsyncClient", return_value=client):
            weather = await fetch_weather("青岛")
        self.assertEqual(weather.location, "青岛")
        params = client.get.await_args.kwargs["params"]
        self.assertEqual((params["latitude"], params["longitude"]), (36.07, 120.38))

    async def test_today_overview_uses_shared_weather_and_keeps_null_on_failure(self) -> None:
        service = MagicMock()
        service.get_overview.return_value = {"user_id": "fixture-user", "date": "2026-08-13", "greeting": "下午好", "weather": None, "courses_count": 0, "todos_count": 0, "nearest_exam": None, "courses_today": [], "pending_todos": []}
        weather = WeatherResponse(temp=27, condition="多云", icon="☁️", humidity=68, wind="东风 2级", location="青岛", advice="正常出行")
        with patch("app.api.v1.today.overview._get_today_service", return_value=service), patch("app.api.v1.today.overview.fetch_weather", new=AsyncMock(return_value=weather)):
            response = await get_overview(user_id="fixture-user", city="青岛", db=MagicMock(), current_user_id="fixture-user")
        self.assertEqual(response.data["weather"]["location"], "青岛")
        with patch("app.api.v1.today.overview._get_today_service", return_value=service), patch("app.api.v1.today.overview.fetch_weather", new=AsyncMock(return_value=None)):
            response = await get_overview(user_id="fixture-user", city="未知", db=MagicMock(), current_user_id="fixture-user")
        self.assertIsNone(response.data["weather"])

    async def test_today_suggestion_uses_the_same_resolved_city_weather(self) -> None:
        weather = WeatherResponse(temp=27, condition="多云", icon="☁️", humidity=68, wind="东风 2级", location="青岛", advice="正常出行")
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        service = MagicMock()
        service.generate_suggestion.return_value = {"user_id": "fixture-user", "date": "2026-08-13", "suggestion": "正常安排", "context_summary": {}}
        with patch("app.api.v1.today.suggestion.TodayService", return_value=service), patch("app.api.v1.today.suggestion.get_llm_service", return_value=MagicMock()), patch("app.api.v1.today.suggestion.fetch_weather", new=AsyncMock(return_value=weather)):
            await get_suggestion(TodaySuggestionRequest(user_id="fixture-user", city="青岛"), db=db, current_user_id="fixture-user")
        self.assertEqual(service.generate_suggestion.call_args.kwargs["weather"]["location"], "青岛")


if __name__ == "__main__":
    unittest.main()
