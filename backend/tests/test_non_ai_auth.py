from __future__ import annotations

import unittest
import uuid
from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models  # noqa: F401 - register all SQLAlchemy models
from app.main import app
from database.base import Base
from database.session import get_db


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


if __name__ == "__main__":
    unittest.main()
