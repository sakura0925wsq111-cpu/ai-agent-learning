from __future__ import annotations

import unittest
import uuid
import json
from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models  # noqa: F401 - register all SQLAlchemy models
from app.main import app
from database.base import Base
from database.session import get_db
from models.growth import GrowthReport, GrowthSession


class NonAIAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.Session = sessionmaker(bind=cls.engine, autocommit=False, autoflush=False)
        Base.metadata.create_all(bind=cls.engine)

        def override_get_db():
            db = cls.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        app.dependency_overrides.clear()
        cls.engine.dispose()

    def _register(self, label: str) -> dict:
        unique = uuid.uuid4().hex[:10]
        response = self.client.post(
            "/api/v1/users",
            json={
                "student_id": f"{label}-{unique}",
                "name": label,
                "password": "secure-pass",
                "school": "测试大学",
                "college": "测试学院",
                "major": "测试专业",
                "enroll_year": "2026",
                "grade": "大一",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["data"]

    @staticmethod
    def _headers(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def test_user_profile_requires_owner_token(self):
        first = self._register("用户甲")
        second = self._register("用户乙")
        path = f"/api/v1/users/{first['user_id']}"

        self.assertEqual(self.client.get(path).status_code, 401)
        self.assertEqual(
            self.client.get(path, headers=self._headers(second["token"])).status_code,
            403,
        )
        allowed = self.client.get(path, headers=self._headers(first["token"]))
        self.assertEqual(allowed.status_code, 200, allowed.text)
        self.assertEqual(allowed.json()["data"]["id"], first["user_id"])

        bad_login = self.client.post(
            "/api/v1/users/login",
            json={"student_id": first["user"]["student_id"], "password": "wrong-pass"},
        )
        self.assertEqual(bad_login.status_code, 401)
        self.assertEqual(bad_login.json()["detail"], "学号或密码错误")

    def test_todos_and_today_reject_cross_user_access(self):
        first = self._register("任务用户甲")
        second = self._register("任务用户乙")
        todo_path = f"/api/v1/todos?user_id={first['user_id']}"

        self.assertEqual(
            self.client.post(todo_path, json={"title": "无凭证任务"}).status_code,
            401,
        )
        self.assertEqual(
            self.client.post(
                todo_path,
                headers=self._headers(second["token"]),
                json={"title": "越权任务"},
            ).status_code,
            403,
        )
        created = self.client.post(
            todo_path,
            headers=self._headers(first["token"]),
            json={"title": "本人任务"},
        )
        self.assertEqual(created.status_code, 201, created.text)

        overview_path = f"/api/v1/today/overview?user_id={first['user_id']}"
        self.assertEqual(
            self.client.get(
                overview_path, headers=self._headers(second["token"])
            ).status_code,
            403,
        )

    def test_timeline_only_includes_todos_for_selected_date(self):
        user = self._register("日历用户")
        headers = self._headers(user["token"])
        todo_path = f"/api/v1/todos?user_id={user['user_id']}"
        target = date.today() + timedelta(days=1)

        no_deadline = self.client.post(
            todo_path, headers=headers, json={"title": "无日期任务"}
        )
        scheduled = self.client.post(
            todo_path,
            headers=headers,
            json={
                "title": "明日任务",
                "deadline": target.isoformat() + "T09:30:00",
            },
        )
        self.assertEqual(no_deadline.status_code, 201, no_deadline.text)
        self.assertEqual(scheduled.status_code, 201, scheduled.text)

        timeline = self.client.get(
            f"/api/v1/today/timeline?user_id={user['user_id']}&date={target.isoformat()}",
            headers=headers,
        )
        self.assertEqual(timeline.status_code, 200, timeline.text)
        events = timeline.json()["data"]["events"]
        todo_events = [event for event in events if event["event_type"] == "todo"]
        self.assertEqual([event["title"] for event in todo_events], ["明日任务"])
        self.assertEqual(todo_events[0]["time"], "09:30")

        calendar = self.client.get(
            f"/api/v1/today/calendar?user_id={user['user_id']}"
            f"&year={target.year}&month={target.month}",
            headers=headers,
        )
        self.assertEqual(calendar.status_code, 200, calendar.text)
        scheduled_dates = [
            day["date"]
            for day in calendar.json()["data"]["days"]
            if any(event["title"] == "明日任务" for event in day["events"])
        ]
        self.assertEqual(scheduled_dates, [target.isoformat()])

    def test_semester_start_controls_existing_course_calendar(self):
        user = self._register("学期日历用户")
        headers = self._headers(user["token"])
        user_id = user["user_id"]
        today = date.today()
        courses_path = f"/api/v1/today/courses?user_id={user_id}"

        created = self.client.post(
            courses_path,
            headers=headers,
            json={
                "name": "学期课程",
                "schedule": [{
                    "weekday": today.isoweekday(),
                    "start": 1,
                    "end": 2,
                    "weeks": "1-16周",
                }],
                "source": "pdf_import",
            },
        )
        self.assertEqual(created.status_code, 201, created.text)

        overview_path = f"/api/v1/today/overview?user_id={user_id}"
        no_semester = self.client.get(overview_path, headers=headers)
        self.assertEqual(no_semester.status_code, 200, no_semester.text)
        self.assertEqual(no_semester.json()["data"]["courses_count"], 0)

        settings_path = (
            f"/api/v1/today/courses/semester-settings?user_id={user_id}"
        )
        future_start = self.client.put(
            settings_path,
            headers=headers,
            json={"semester_start": (today + timedelta(days=7)).isoformat()},
        )
        self.assertEqual(future_start.status_code, 200, future_start.text)
        self.assertEqual(future_start.json()["data"]["updated_count"], 1)
        self.assertEqual(
            self.client.get(overview_path, headers=headers).json()["data"]["courses_count"],
            0,
        )

        active_start = self.client.put(
            settings_path,
            headers=headers,
            json={"semester_start": today.isoformat()},
        )
        self.assertEqual(active_start.status_code, 200, active_start.text)
        active_overview = self.client.get(overview_path, headers=headers)
        self.assertEqual(active_overview.json()["data"]["courses_count"], 1)

        calendar = self.client.get(
            f"/api/v1/today/calendar?user_id={user_id}"
            f"&year={today.year}&month={today.month}",
            headers=headers,
        )
        self.assertEqual(calendar.status_code, 200, calendar.text)
        today_events = calendar.json()["data"]["days"][today.day - 1]["events"]
        self.assertEqual(
            [event["title"] for event in today_events if event["event_type"] == "course"],
            ["学期课程"],
        )

    def test_growth_dashboard_reports_and_sync_are_owner_scoped(self):
        owner = self._register("成长闭环用户")
        other = self._register("成长越权用户")
        session_id = str(uuid.uuid4())
        payload = {
            "summary": "完成就业准备",
            "action_plan": [{
                "phase_key": "phase_1",
                "phase": "第1-2周",
                "tasks": ["整理项目经历", "准备自我介绍"],
            }],
        }
        with self.Session() as db:
            growth_session = GrowthSession(
                id=session_id,
                user_id=owner["user_id"],
                agent_type="career",
                status="completed",
                stage="report",
                finished=True,
                report_json=json.dumps(payload, ensure_ascii=False),
                progress=100.0,
            )
            db.add(growth_session)
            db.flush()
            db.add(GrowthReport(
                session_id=session_id,
                user_id=owner["user_id"],
                agent_type="career",
                report_type="career_report",
                plan_json=json.dumps(payload["action_plan"], ensure_ascii=False),
                full_report_json=json.dumps(payload, ensure_ascii=False),
            ))
            db.commit()

        dashboard_path = f"/api/v1/growth/dashboard/{owner['user_id']}"
        self.assertEqual(self.client.get(dashboard_path).status_code, 401)
        self.assertEqual(
            self.client.get(
                dashboard_path, headers=self._headers(other["token"]),
            ).status_code,
            403,
        )
        dashboard = self.client.get(
            dashboard_path, headers=self._headers(owner["token"]),
        )
        self.assertEqual(dashboard.status_code, 200, dashboard.text)
        self.assertEqual(dashboard.json()["data"]["page_state"], "report_ready")

        reports = self.client.get(
            f"/api/v1/growth/reports?user_id={owner['user_id']}",
            headers=self._headers(owner["token"]),
        )
        self.assertEqual(reports.status_code, 200, reports.text)
        self.assertEqual(reports.json()["data"]["total"], 1)

        hidden_report = self.client.get(
            f"/api/v1/growth/report/{session_id}",
            headers=self._headers(other["token"]),
        )
        self.assertEqual(hidden_report.status_code, 404, hidden_report.text)

        synced = self.client.post(
            "/api/v1/today/sync-plan",
            headers=self._headers(owner["token"]),
            json={
                "user_id": owner["user_id"],
                "growth_session_id": session_id,
                "phase": "phase_1",
            },
        )
        self.assertEqual(synced.status_code, 200, synced.text)
        self.assertEqual(synced.json()["data"]["synced_count"], 2)

        executing = self.client.get(
            dashboard_path, headers=self._headers(owner["token"]),
        )
        self.assertEqual(executing.status_code, 200, executing.text)
        self.assertEqual(executing.json()["data"]["page_state"], "executing")


if __name__ == "__main__":
    unittest.main()
