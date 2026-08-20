# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models  # noqa: F401 - register metadata
from database.base import Base
from models.growth import GrowthReport, GrowthSession
from models.today import PlanTask
from models.todo import Todo
from models.user import User
from schemas.growth import AgentTypeEnum, GrowthChatRequest
from services.growth_service import GrowthService
from services.today import TodayService


class _CoachLLM:
    def __init__(self) -> None:
        self.system_prompt = ""
        self.kwargs = {}

    def chat(self, *, user_message: str, system_prompt: str = "", **kwargs) -> str:
        self.system_prompt = system_prompt
        self.kwargs = kwargs
        return "你已经完成一项任务，建议今天只保留下一项重点。"


class GrowthTodayLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.Session = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)
        Base.metadata.create_all(bind=self.engine)
        self.db = self.Session()
        self.user = User(id="growth-loop-user", name="测试用户", nickname="测试用户")
        self.session = GrowthSession(
            id="growth-loop-session",
            user_id=self.user.id,
            agent_type="career",
            status="completed",
            stage="report",
            finished=True,
            report_json="{}",
            progress=100.0,
        )
        report_payload = {
            "summary": "围绕产品方向建立求职准备计划",
            "goal": "完成产品实习准备",
            "action_plan": [
                {
                    "phase_key": "phase_1",
                    "phase": "第1-2周",
                    "tasks": [
                        "完成一版项目复盘",
                        {"title": "整理目标岗位要求", "deadline": "2026-08-15T20:00:00"},
                    ],
                },
                {
                    "phase_key": "phase_2",
                    "phase": "第3-4周",
                    "tasks": ["投递第一批岗位"],
                },
            ],
        }
        self.report = GrowthReport(
            id="growth-loop-report",
            session_id=self.session.id,
            user_id=self.user.id,
            agent_type="career",
            report_type="career_report",
            plan_json=json.dumps(report_payload["action_plan"], ensure_ascii=False),
            full_report_json=json.dumps(report_payload, ensure_ascii=False),
        )
        self.db.add_all([self.user, self.session, self.report])
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_sync_is_idempotent_and_progress_uses_todo_status(self) -> None:
        service = TodayService()
        first = service.sync_growth_plan(
            self.db,
            user_id=self.user.id,
            growth_session_id=self.session.id,
            phase="phase_1",
        )
        second = service.sync_growth_plan(
            self.db,
            user_id=self.user.id,
            growth_session_id=self.session.id,
            phase="phase_1",
        )

        self.assertEqual(first["synced_count"], 2)
        self.assertFalse(first["already_synced"])
        self.assertEqual(second["synced_count"], 0)
        self.assertTrue(second["already_synced"])
        self.assertEqual(self.db.query(Todo).count(), 2)
        self.assertEqual(self.db.query(PlanTask).count(), 2)
        self.assertIsNone(first["todos"][0]["deadline"])

        todo = self.db.query(Todo).order_by(Todo.created_at.asc()).first()
        todo.status = "done"
        self.db.commit()
        progress = service.get_plan_progress(
            self.db,
            user_id=self.user.id,
            growth_session_id=self.session.id,
        )
        self.assertEqual(progress["total"], 2)
        self.assertEqual(progress["completed"], 1)
        self.assertEqual(progress["overall_completion"], 0.5)
        self.assertEqual(progress["current_phase"]["phase_key"], "phase_1")

    def test_sync_optional_start_date_distributes_only_missing_deadlines(self) -> None:
        from datetime import date

        result = TodayService().sync_growth_plan(
            self.db,
            user_id=self.user.id,
            growth_session_id=self.session.id,
            phase="phase_1",
            start_date=date(2026, 8, 17),
        )

        self.assertEqual(result["synced_count"], 2)
        self.assertEqual(result["todos"][0]["deadline"], "2026-08-23")
        self.assertEqual(result["todos"][1]["deadline"], "2026-08-15T20:00:00")

    def test_dashboard_switches_from_report_ready_to_executing(self) -> None:
        growth = GrowthService(_CoachLLM())
        before = growth.get_dashboard(self.db, user_id=self.user.id)
        self.assertEqual(before.page_state, "report_ready")
        self.assertEqual(before.report_count, 1)
        self.assertEqual(before.latest_report["session_id"], self.session.id)

        TodayService().sync_growth_plan(
            self.db,
            user_id=self.user.id,
            growth_session_id=self.session.id,
            phase="phase_1",
        )
        after = growth.get_dashboard(self.db, user_id=self.user.id)
        self.assertEqual(after.page_state, "executing")
        self.assertEqual(after.active_plan["total"], 2)
        self.assertEqual(after.active_plan["title"], "就业指导报告")

    def test_today_suggestion_uses_a_bounded_llm_timeout(self) -> None:
        llm = _CoachLLM()

        result = TodayService(llm).generate_suggestion(
            self.db,
            user_id=self.user.id,
        )

        self.assertTrue(result["suggestion"])
        self.assertEqual(llm.kwargs["request_timeout"], 10)
        self.assertEqual(llm.kwargs["max_retries"], 0)

    def test_growth_coach_receives_report_progress_and_memory_context(self) -> None:
        TodayService().sync_growth_plan(
            self.db,
            user_id=self.user.id,
            growth_session_id=self.session.id,
            phase="phase_1",
        )
        todo = self.db.query(Todo).first()
        todo.status = "done"
        self.db.commit()

        llm = _CoachLLM()
        growth = GrowthService(llm)
        with patch("services.memory_service.memory_service.extract_from_turn_async"):
            result = growth.free_qa(
                self.db,
                request=GrowthChatRequest(
                    user_id=self.user.id,
                    agent=AgentTypeEnum.CAREER,
                    session_id=self.session.id,
                    message="帮我复盘一下本周",
                ),
            )
        self.assertIn("完成一项任务", result["message"])
        self.assertIn("真实执行进度", llm.system_prompt)
        self.assertIn('"completed": 1', llm.system_prompt)
        self.assertIn("调整建议", llm.system_prompt)


if __name__ == "__main__":
    unittest.main()
