# -*- coding: utf-8 -*-
"""Today Service — daily suggestion, Growth sync, progress tracking."""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone, timedelta
from typing import Any

from loguru import logger
from sqlalchemy.orm import Session

from models.today import Course, Exam, PlanTask
from models.todo import Todo
from models.growth import GrowthReport
from crud.base import CRUDBase

course_crud = CRUDBase[Course](Course)
exam_crud = CRUDBase[Exam](Exam)
todo_crud = CRUDBase[Todo](Todo)


# ── Greeting helper ─────────────────────────────────────────────

def _greeting() -> str:
    hour = datetime.now().hour
    if hour < 12:
        return "早上好"
    if hour < 18:
        return "下午好"
    return "晚上好"


def _today_str() -> str:
    return date.today().isoformat()


def _weekday_today() -> int:
    return date.today().isoweekday()  # 1=Mon, 7=Sun


# ── Plan sync helper ────────────────────────────────────────────

PHASE_LABELS = {
    "phase_1": "第1-2周",
    "phase_2": "第3-4周",
    "phase_3": "第5-8周",
    "phase_4": "第9-12周",
}


class TodayService:
    """Orchestrates Today Mode business logic."""

    def __init__(self, llm_service: Any = None) -> None:
        self.llm = llm_service

    # ── Overview ────────────────────────────────────────────────

    def get_overview(self, db: Session, *, user_id: str) -> dict[str, Any]:
        """Aggregate today's snapshot: courses, todos, nearest exam."""
        weekday = _weekday_today()
        today = date.today()

        # Courses today: filter client-side by schedule_json weekday
        all_courses = db.query(Course).filter(Course.user_id == user_id).all()
        courses_today: list[dict[str, Any]] = []
        for c in all_courses:
            try:
                schedule = json.loads(c.schedule_json or "[]")
            except (json.JSONDecodeError, TypeError):
                schedule = []
            for slot in schedule:
                if slot.get("weekday") == weekday:
                    courses_today.append({
                        "id": c.id, "name": c.name,
                        "teacher": c.teacher, "location": c.location,
                        "start": slot.get("start"), "end": slot.get("end"),
                        "weeks": slot.get("weeks", ""),
                        "color": c.color, "source": c.source,
                    })

        # Pending todos
        todos = db.query(Todo).filter(
            Todo.user_id == user_id,
            Todo.status == "pending",
        ).order_by(Todo.created_at.desc()).all()

        pending_todos = [{
            "id": t.id, "title": t.title, "deadline": t.deadline,
            "source": t.source, "status": t.status,
        } for t in todos]

        # Nearest exam (within 14 days)
        two_weeks = today + timedelta(days=14)
        nearest = db.query(Exam).filter(
            Exam.user_id == user_id,
            Exam.exam_date >= today,
            Exam.exam_date <= two_weeks,
        ).order_by(Exam.exam_date.asc()).first()

        nearest_exam = None
        if nearest:
            nearest_exam = {
                "id": nearest.id, "subject": nearest.subject,
                "exam_date": nearest.exam_date.isoformat(),
                "start_time": nearest.start_time,
                "location": nearest.location,
            }

        return {
            "user_id": user_id,
            "date": _today_str(),
            "greeting": _greeting(),
            "weather": None,  # filled by API layer
            "courses_count": len(courses_today),
            "todos_count": len(pending_todos),
            "nearest_exam": nearest_exam,
            "courses_today": courses_today,
            "pending_todos": pending_todos,
        }

    # ── AI Suggestion ───────────────────────────────────────────

    def generate_suggestion(
        self,
        db: Session,
        *,
        user_id: str,
        weather: dict[str, Any] | None = None,
        growth_progress: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate an AI-powered daily suggestion."""
        overview = self.get_overview(db, user_id=user_id)

        # Build context for LLM
        context_parts: list[str] = []

        if weather:
            context_parts.append(
                f"天气: {weather.get('condition', '未知')}, "
                f"{weather.get('temp', '?')}°C, "
                f"{weather.get('location', '未知')}"
            )
            if weather.get("advice"):
                context_parts.append(f"天气建议: {weather['advice']}")

        courses = overview["courses_today"]
        if courses:
            context_parts.append(
                f"今日课程({len(courses)}节): " +
                ", ".join(
                    f"[{c['start']}-{c['end']}节] {c['name']}"
                    for c in courses
                )
            )

        todos = overview["pending_todos"]
        if todos:
            context_parts.append(
                f"待办任务({len(todos)}项): " +
                ", ".join(t["title"] for t in todos)
            )

        if overview["nearest_exam"]:
            e = overview["nearest_exam"]
            context_parts.append(f"最近考试: {e['subject']} ({e['exam_date']})")

        if growth_progress:
            gp = growth_progress
            context_parts.append(
                f"成长规划进度: {gp.get('agent_type', '未知')}方向, "
                f"当前{gp.get('current_phase', '?')}, "
                f"完成率{gp.get('overall_completion', 0) * 100:.0f}%"
            )

        context = "\n".join(context_parts)

        system_prompt = (
            "你是 CampusPal 的 AI 校园生活教练。根据用户今天的课程、待办、天气和成长规划进度，"
            "生成一条温暖、实用的今日建议（<=200字）。\n"
            "规则:\n"
            "- 结合空闲时段给出具体建议\n"
            "- 如果有成长规划任务未完成，温和提醒进度\n"
            "- 天气不好时提醒带伞或注意安全\n"
            "- 语气年轻化，像朋友一样"
        )

        suggestion = ""
        context_summary = {
            "weather": weather,
            "courses_count": overview["courses_count"],
            "todos_count": overview["todos_count"],
            "has_exam": overview["nearest_exam"] is not None,
            "growth_progress": growth_progress,
        }

        if self.llm:
            try:
                suggestion = self.llm.chat(
                    user_message=f"以下是用户今天的情况:\n{context}\n\n请生成今日建议。",
                    system_prompt=system_prompt,
                    temperature=0.8,
                    max_tokens=300,
                )
            except Exception as exc:
                logger.warning("Today suggestion LLM call failed: {}", exc)
                suggestion = "今天也是元气满满的一天！查看下方时间轴，合理安排今天的学习和生活吧~"

        return {
            "user_id": user_id,
            "date": _today_str(),
            "suggestion": suggestion.strip(),
            "context_summary": context_summary,
        }

    # ── Growth Plan Sync ────────────────────────────────────────

    def sync_growth_plan(
        self,
        db: Session,
        *,
        user_id: str,
        growth_session_id: str,
        phase: str,
    ) -> dict[str, Any]:
        """Sync a single phase of a Growth plan into daily Todo items.

        Idempotent: skips phases that were already synced.
        """
        # Check for existing sync (idempotency)
        existing = db.query(PlanTask).filter(
            PlanTask.user_id == user_id,
            PlanTask.growth_session_id == growth_session_id,
            PlanTask.phase_key == phase,
        ).first()

        if existing:
            logger.info(
                "PlanTask sync: phase {} already synced for session {}",
                phase, growth_session_id,
            )
            return {
                "user_id": user_id,
                "growth_session_id": growth_session_id,
                "phase": phase,
                "synced_count": 0,
                "todos": [],
                "message": "该阶段已同步过，无需重复操作",
            }

        # Load growth report
        report = db.query(GrowthReport).filter(
            GrowthReport.session_id == growth_session_id,
        ).first()

        if not report or not report.plan_json:
            raise ValueError(f"No plan found for session {growth_session_id}")

        try:
            plan = json.loads(report.plan_json)
        except (json.JSONDecodeError, TypeError):
            raise ValueError("Failed to parse growth plan JSON")

        # Extract tasks for the requested phase
        action_plan = plan if isinstance(plan, list) else plan.get("action_plan", [])
        phase_tasks: list[dict[str, Any]] = []
        for p in action_plan:
            if isinstance(p, dict) and p.get("phase") == phase:
                phase_tasks = p.get("tasks", [])
                break

        if not phase_tasks:
            raise ValueError(f"No tasks found for phase {phase}")

        # Create Todo + PlanTask for each task
        synced: list[dict[str, Any]] = []
        for idx, task in enumerate(phase_tasks):
            title = task.get("title") or task.get("name") or task.get("task") or ""
            if not title:
                continue

            deadline = task.get("deadline") or task.get("due") or None

            todo = todo_crud.create(db, obj_in={
                "user_id": user_id,
                "title": title,
                "status": "pending",
                "deadline": deadline,
                "source": "ai_plan",
            })

            plan_task = PlanTask(
                user_id=user_id,
                growth_session_id=growth_session_id,
                growth_report_id=report.id,
                todo_id=todo.id,
                phase_key=phase,
                plan_task_index=idx,
            )
            db.add(plan_task)
            db.commit()

            synced.append({
                "todo_id": todo.id,
                "title": todo.title,
                "deadline": todo.deadline,
                "phase": phase,
                "index": idx,
            })

        logger.info(
            "PlanTask sync: {} tasks synced for session {} phase {}",
            len(synced), growth_session_id, phase,
        )

        return {
            "user_id": user_id,
            "growth_session_id": growth_session_id,
            "phase": phase,
            "synced_count": len(synced),
            "todos": synced,
        }

    # ── Progress Tracking ───────────────────────────────────────

    def get_plan_progress(
        self,
        db: Session,
        *,
        user_id: str,
        growth_session_id: str,
    ) -> dict[str, Any]:
        """Query completion progress of a synced growth plan."""
        plan_tasks = db.query(PlanTask).filter(
            PlanTask.user_id == user_id,
            PlanTask.growth_session_id == growth_session_id,
        ).all()

        if not plan_tasks:
            return {
                "user_id": user_id,
                "growth_session_id": growth_session_id,
                "phases": [],
                "overall_completion": 0.0,
            }

        # Group by phase
        phases_map: dict[str, list[dict[str, Any]]] = {}
        for pt in plan_tasks:
            todo = db.query(Todo).filter(Todo.id == pt.todo_id).first()
            todo_info = {
                "todo_id": pt.todo_id,
                "title": todo.title if todo else "(已删除)",
                "status": todo.status if todo else "unknown",
                "plan_task_index": pt.plan_task_index,
            }
            phases_map.setdefault(pt.phase_key, []).append(todo_info)

        phases: list[dict[str, Any]] = []
        total_all = 0
        completed_all = 0
        for pk in sorted(phases_map.keys()):
            items = phases_map[pk]
            completed = sum(1 for t in items if t["status"] in ("done", "archived"))
            phases.append({
                "phase_key": pk,
                "label": PHASE_LABELS.get(pk, pk),
                "total": len(items),
                "completed": completed,
                "todos": items,
            })
            total_all += len(items)
            completed_all += completed

        overall = completed_all / total_all if total_all > 0 else 0.0

        return {
            "user_id": user_id,
            "growth_session_id": growth_session_id,
            "phases": phases,
            "overall_completion": round(overall, 2),
        }

    # ?? Timeline ????????????????????????????????????????????????

    def get_timeline(
        self,
        db,
        *,
        user_id,
        target_date=None,
    ):
        import json
        from datetime import date as date_type
        target = target_date or date_type.today()
        weekday = target.isoweekday()

        events = []

        # Courses
        all_courses = db.query(Course).filter(Course.user_id == user_id).all()
        for c in all_courses:
            try:
                schedule = json.loads(c.schedule_json or "[]")
            except (json.JSONDecodeError, TypeError):
                schedule = []
            for slot in schedule:
                if slot.get("weekday") == weekday:
                    start = slot.get("start", 1)
                    end = slot.get("end", 2)
                    h = 8 + (start - 1)
                    start_str = "%02d:00" % h
                    end_str = "%02d:00" % (8 + end)
                    events.append({
                        "id": c.id,
                        "title": c.name,
                        "time": start_str,
                        "end_time": end_str,
                        "location": c.location or "",
                        "event_type": "course",
                        "color": c.color or "#4A90D9",
                        "source": c.source,
                        "sort_key": start,
                    })

        # Exams
        exams = db.query(Exam).filter(
            Exam.user_id == user_id,
            Exam.exam_date == target,
        ).all()
        for e in exams:
            t = e.start_time or "00:00"
            sk = int(t[:2]) if t[:2].isdigit() else 0
            events.append({
                "id": e.id,
                "title": e.subject,
                "time": t,
                "end_time": e.end_time or "",
                "location": e.location or "",
                "event_type": "exam",
                "color": "#E74C3C",
                "source": e.source,
                "sort_key": sk,
            })

        # Todos
        todos = db.query(Todo).filter(
            Todo.user_id == user_id,
            Todo.status == "pending",
        ).order_by(Todo.created_at.desc()).all()
        for t in todos:
            events.append({
                "id": t.id,
                "title": t.title,
                "time": t.deadline or "",
                "end_time": "",
                "location": "",
                "event_type": "ai_plan" if t.source == "ai_plan" else "todo",
                "color": "#F39C12" if t.source == "ai_plan" else "#8E8E93",
                "source": t.source,
                "sort_key": 99,
            })

        events.sort(key=lambda x: (x["sort_key"], x["time"]))

        return {
            "user_id": user_id,
            "date": target.isoformat(),
            "weekday": weekday,
            "total": len(events),
            "events": events,
        }

    # ?? Calendar ????????????????????????????????????????????????

    def get_calendar(
        self,
        db,
        *,
        user_id,
        year,
        month,
    ):
        import json
        import calendar as cal_mod
        from datetime import date as date_type, timedelta

        today = date_type.today()
        days_in_month = cal_mod.monthrange(year, month)[1]
        first_weekday = cal_mod.monthrange(year, month)[0]  # 0=Mon ? we convert to 1=Mon
        first_weekday = (first_weekday + 6) % 7 + 1  # convert to 1=Mon...7=Sun

        # Pre-build empty day map
        days_map = {}
        for d in range(1, days_in_month + 1):
            dt = date_type(year, month, d)
            days_map[dt] = {
                "date": dt.isoformat(),
                "weekday": dt.isoweekday(),
                "weekday_label": ["", "??", "??", "??", "??", "??", "??", "??"][dt.isoweekday()],
                "is_today": dt == today,
                "events": [],
            }

        # Courses: expand schedule slots to actual dates in this month
        all_courses = db.query(Course).filter(Course.user_id == user_id).all()
        for c in all_courses:
            try:
                schedule = json.loads(c.schedule_json or "[]")
            except (json.JSONDecodeError, TypeError):
                schedule = []
            for slot in schedule:
                wd = slot.get("weekday", 0)
                start = slot.get("start", 1)
                end = slot.get("end", 2)
                weeks_str = slot.get("weeks", "1-16")
                # Compute dates in this month that fall on this weekday
                for d in range(1, days_in_month + 1):
                    dt = date_type(year, month, d)
                    if dt.isoweekday() != wd:
                        continue
                    # Simple week-range parsing
                    h = 8 + (start - 1)
                    start_str = "%02d:00" % h
                    end_str = "%02d:00" % (8 + end)
                    days_map[dt]["events"].append({
                        "id": c.id,
                        "title": c.name,
                        "time": start_str,
                        "end_time": end_str,
                        "location": c.location or "",
                        "event_type": "course",
                        "color": c.color or "#4A90D9",
                        "sort_key": start,
                    })

        # Exams in this month
        month_start = date_type(year, month, 1)
        month_end = date_type(year, month, days_in_month)
        exams = db.query(Exam).filter(
            Exam.user_id == user_id,
            Exam.exam_date >= month_start,
            Exam.exam_date <= month_end,
        ).all()
        for e in exams:
            if e.exam_date in days_map:
                t = e.start_time or "00:00"
                sk = int(t[:2]) if t[:2].isdigit() else 0
                days_map[e.exam_date]["events"].append({
                    "id": e.id,
                    "title": e.subject,
                    "time": t,
                    "end_time": e.end_time or "",
                    "location": e.location or "",
                    "event_type": "exam",
                    "color": "#E74C3C",
                    "sort_key": sk + 10,
                })

        # Pending todos ? attach to today by default
        todos = db.query(Todo).filter(
            Todo.user_id == user_id,
            Todo.status == "pending",
        ).order_by(Todo.created_at.desc()).all()
        for t in todos:
            todo_date = today
            # Try to parse deadline to a date
            if t.deadline:
                for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%m-%d"]:
                    try:
                        parsed = date_type.strptime(t.deadline, fmt) if hasattr(date_type, 'strptime') else None
                        if parsed is None:
                            from datetime import datetime as dt_cls
                            try:
                                parsed = dt_cls.strptime(t.deadline, fmt).date()
                            except:
                                continue
                        if parsed and month_start <= parsed <= month_end:
                            todo_date = parsed
                            break
                    except:
                        continue
            if todo_date in days_map:
                days_map[todo_date]["events"].append({
                    "id": t.id,
                    "title": t.title,
                    "time": t.deadline or "",
                    "end_time": "",
                    "location": "",
                    "event_type": "ai_plan" if t.source == "ai_plan" else "todo",
                    "color": "#F39C12" if t.source == "ai_plan" else "#8E8E93",
                    "sort_key": 99,
                })

        # Sort events within each day
        days_list = []
        for d in range(1, days_in_month + 1):
            dt = date_type(year, month, d)
            day_data = days_map[dt]
            day_data["events"].sort(key=lambda x: (x["sort_key"], x["time"]))
            days_list.append(day_data)

        return {
            "user_id": user_id,
            "year": year,
            "month": month,
            "month_label": "%d?" % month,
            "first_weekday": first_weekday,
            "total_days": days_in_month,
            "days": days_list,
        }

