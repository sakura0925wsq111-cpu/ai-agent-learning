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


# ── Week calculation helpers ────────────────────────────────────

import re as _re

_WEEKS_RE = _re.compile(r"^(\d+)-(\d+)周(?:\(([双单])\))?$")


def _parse_weeks(weeks_str: str) -> dict[str, Any]:
    """Parse '3-16周' or '2-8周(双)' into structured form."""
    m = _WEEKS_RE.match((weeks_str or "").strip())
    if not m:
        return {"start": 1, "end": 20, "parity": None}
    parity = None
    if m.group(3) == "单":
        parity = "odd"
    elif m.group(3) == "双":
        parity = "even"
    return {"start": int(m.group(1)), "end": int(m.group(2)), "parity": parity}


def _is_course_active_in_week(weeks_parsed: dict, current_week: int | None) -> bool:
    """Check if a course slot applies to a given academic week.

    If current_week is None or 0 (pre-semester / unknown), skip filtering
    and show all courses matching the weekday.
    """
    if current_week is None or current_week <= 0:
        return True
    if current_week < weeks_parsed["start"]:
        return False
    if current_week > weeks_parsed["end"]:
        return False
    if weeks_parsed["parity"] == "odd" and current_week % 2 == 0:
        return False
    if weeks_parsed["parity"] == "even" and current_week % 2 != 0:
        return False
    return True


def _get_current_week(semester_start: date | None) -> int | None:
    """Current academic week (1-based), or None if semester_start unknown.

    Returns 0 if today is before the semester start date (semester not yet begun).
    """
    if semester_start is None:
        return None
    delta = date.today() - semester_start
    if delta.days < 0:
        return 0  # Semester hasn't started yet
    return delta.days // 7 + 1


def _get_week_for_date(semester_start: date | None, target: date) -> int | None:
    """Academic week for a specific date, or None if unknown.

    Returns 0 if target date is before semester start.
    """
    if semester_start is None:
        return None
    delta = target - semester_start
    if delta.days < 0:
        return 0  # Before semester
    return delta.days // 7 + 1


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

        # Courses today: filter by weekday AND week range
        all_courses = db.query(Course).filter(Course.user_id == user_id).all()
        courses_today: list[dict[str, Any]] = []
        for c in all_courses:
            try:
                schedule = json.loads(c.schedule_json or "[]")
            except (json.JSONDecodeError, TypeError):
                schedule = []
            for slot in schedule:
                if slot.get("weekday") != weekday:
                    continue
                # Week-range filter
                weeks_parsed = slot.get("weeks_parsed")
                if weeks_parsed is None:
                    weeks_parsed = _parse_weeks(slot.get("weeks", ""))
                current_week = _get_current_week(c.semester_start)
                if current_week is not None and not _is_course_active_in_week(weeks_parsed, current_week):
                    continue

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
                f"湿度 {weather.get('humidity', '?')}%"
            )

        # Courses context
        courses = overview.get("courses_today", [])
        if courses:
            course_lines = []
            for c in courses:
                loc = f"({c.get('location', '')})" if c.get("location") else ""
                course_lines.append(
                    f"  {c.get('start', '?')}-{c.get('end', '?')}节 "
                    f"{c['name']}{loc}"
                )
            context_parts.append(
                f"今日课程({len(courses)}门):\n" + "\n".join(course_lines)
            )
        else:
            context_parts.append("今日无课程")

        # Todos context
        todos = overview.get("pending_todos", [])
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
            "你是 CampusPal 的 AI 今日助手。"
            "请根据用户今天的课程、待办、考试、天气和成长规划进度，"
            "给出具体、可执行且不过度安排的建议。"
            "优先指出最值得完成的一件事，并帮助用户留出休息时间。"
            "\n\n"
            "☀️ 天气：只依据提供的信息建议出行与穿着，不要猜测。"
            "\n"
            "⏳ 空闲：结合真实空闲时段安排任务，不要制造时间。"
            "\n"
            "📋 计划：最多突出三个优先事项，避免堆砌任务。"
            "\n\n"
            "重要规则："
            "如果今日无课，绝对不要编造课程时间；"
            "如果无待办，不要提作业或任务；"
            "不要使用markdown标题或加粗；"
            "语气年轻化像朋友；"
            "总长不超过200字"
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
                "Plan phase already synced: {} / {}",
                growth_session_id, phase,
            )
            return {
                "user_id": user_id,
                "growth_session_id": growth_session_id,
                "phase": phase,
                "synced_count": 0,
                "todos": [],
            }

        # Load the growth report for this session
        report = db.query(GrowthReport).filter(
            GrowthReport.user_id == user_id,
            GrowthReport.session_id == growth_session_id,
        ).order_by(GrowthReport.created_at.desc()).first()

        if not report:
            raise ValueError(f"Growth report not found: {growth_session_id}")

        try:
            plan_data = json.loads(report.content_json or "{}")
        except (json.JSONDecodeError, TypeError):
            plan_data = {}

        phase_data = plan_data.get("phases", {}).get(phase, {})
        tasks = phase_data.get("tasks", [])
        if not tasks:
            logger.warning("No tasks found in phase {}", phase)
            return {
                "user_id": user_id,
                "growth_session_id": growth_session_id,
                "phase": phase,
                "synced_count": 0,
                "todos": [],
            }

        # Create PlanTask + Todo records
        synced = []
        for task in tasks:
            plan_task = PlanTask(
                user_id=user_id,
                growth_session_id=growth_session_id,
                phase_key=phase,
                phase_label=PHASE_LABELS.get(phase, phase),
                description=task.get("title", task.get("description", "")),
                deadline=task.get("deadline"),
                status="pending",
            )
            db.add(plan_task)
            db.flush()  # get plan_task.id

            todo = Todo(
                user_id=user_id,
                title=task.get("title", task.get("description", "")),
                source="ai_plan",
                status="pending",
                deadline=task.get("deadline"),
                plan_task_id=plan_task.id,
            )
            db.add(todo)
            synced.append({
                "plan_task_id": plan_task.id,
                "todo_id": todo.id,
                "title": todo.title,
            })

        db.commit()
        logger.info(
            "Synced {} tasks from {} / {}", len(synced), growth_session_id, phase
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

        phases: dict[str, dict[str, Any]] = {}
        for pt in plan_tasks:
            ph = phases.setdefault(pt.phase_key, {
                "phase_key": pt.phase_key,
                "label": pt.phase_label,
                "total": 0,
                "completed": 0,
                "todos": [],
            })
            ph["total"] += 1
            if pt.status == "completed":
                ph["completed"] += 1
            ph["todos"].append({
                "id": pt.id,
                "description": pt.description,
                "deadline": pt.deadline,
                "status": pt.status,
            })

        phases_list = list(phases.values())
        total_tasks = sum(p["total"] for p in phases_list)
        completed = sum(p["completed"] for p in phases_list)
        overall = completed / total_tasks if total_tasks > 0 else 0.0

        return {
            "user_id": user_id,
            "growth_session_id": growth_session_id,
            "phases": phases_list,
            "overall_completion": round(overall, 2),
        }

    # ── Timeline ────────────────────────────────────────────────

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

        # Courses — filtered by weekday AND week range
        all_courses = db.query(Course).filter(Course.user_id == user_id).all()
        for c in all_courses:
            try:
                schedule = json.loads(c.schedule_json or "[]")
            except (json.JSONDecodeError, TypeError):
                schedule = []
            for slot in schedule:
                if slot.get("weekday") != weekday:
                    continue
                # Week-range filter
                weeks_parsed = slot.get("weeks_parsed")
                if weeks_parsed is None:
                    weeks_parsed = _parse_weeks(slot.get("weeks", ""))
                week_num = _get_week_for_date(c.semester_start, target)
                if week_num is not None and not _is_course_active_in_week(weeks_parsed, week_num):
                    continue

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
            time_value = ""
            if t.deadline:
                try:
                    deadline = datetime.fromisoformat(t.deadline.replace("Z", "+00:00"))
                    if deadline.date() != target:
                        continue
                    time_value = deadline.strftime("%H:%M")
                except (TypeError, ValueError):
                    continue
            elif target != date_type.today():
                continue
            events.append({
                "id": t.id,
                "title": t.title,
                "time": time_value,
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

    # ── Calendar ────────────────────────────────────────────────

    def get_calendar(
        self,
        db,
        *,
        user_id,
        year,
        month,
    ):
        import calendar as cal_mod
        from datetime import date as date_type
        today = date_type.today()
        days_in_month = cal_mod.monthrange(year, month)[1]
        first_weekday = cal_mod.monthrange(year, month)[0]  # 0=Mon → we convert to 1=Mon
        first_weekday = (first_weekday + 6) % 7 + 1  # convert to 1=Mon...7=Sun

        # Build day map
        days_map = {}
        for d in range(1, days_in_month + 1):
            dt = date_type(year, month, d)
            days_map[dt] = {
                "date": dt.isoformat(),
                "weekday": dt.isoweekday(),
                "weekday_label": ["", "一", "二", "三", "四", "五", "六", "日"][dt.isoweekday()],
                "is_today": dt == today,
                "events": [],
            }

        # Courses: expand schedule slots to actual dates, with week-range filtering
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
                # Pre-parse weeks once per slot
                weeks_parsed = slot.get("weeks_parsed")
                if weeks_parsed is None:
                    weeks_parsed = _parse_weeks(slot.get("weeks", ""))
                # Compute dates in this month that fall on this weekday
                for d in range(1, days_in_month + 1):
                    dt = date_type(year, month, d)
                    if dt.isoweekday() != wd:
                        continue
                    # Week-range filtering
                    if c.semester_start is not None:
                        week_num = _get_week_for_date(c.semester_start, dt)
                        if week_num is not None and not _is_course_active_in_week(weeks_parsed, week_num):
                            continue
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

        # Pending todos → attach to today by default
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
                        from datetime import datetime as dt_cls
                        parsed = dt_cls.strptime(t.deadline, fmt).date()
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
            "month_label": "%d月" % month,
            "first_weekday": first_weekday,
            "total_days": days_in_month,
            "days": days_list,
        }
