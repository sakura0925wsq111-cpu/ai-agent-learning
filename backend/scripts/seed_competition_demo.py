# -*- coding: utf-8 -*-
"""Seed a clean, repeatable competition demo account.

This script is intentionally application-level: it uses the existing
SQLAlchemy models and TodayService rather than hand-written SQL.  Running it
again removes only the resources owned by the competition demo student and
rebuilds the same presentation-ready state.

Run from the repository root:

    $env:PYTHONPATH = (Resolve-Path backend).Path
    .\venv\Scripts\python.exe backend/scripts/seed_competition_demo.py

The account supports two demo modes:

1. live: log in and run one real AI sandbox/growth generation;
2. fallback: open the pre-completed sandbox and persisted four-phase report
   using the IDs printed at the end of this script.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


# Allow ``python backend/scripts/seed_competition_demo.py`` from the repo root
# without requiring callers to change directory first.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy.orm import Session  # noqa: E402

from core.config import settings  # noqa: E402
from database.session import SessionLocal, init_db  # noqa: E402
from models.growth import GrowthConversation, GrowthReport, GrowthSession  # noqa: E402
from models.memory import Memory  # noqa: E402
from models.today import Course, Exam, ImportPreview, PlanTask  # noqa: E402
from models.todo import Todo  # noqa: E402
from models.user import User  # noqa: E402
from sandbox.state import SandboxPhase, SandboxSession  # noqa: E402
from services.today import TodayService  # noqa: E402
from utils.auth import hash_password  # noqa: E402


# Keep the script aligned with the app's configured demo login while retaining
# the repository defaults for environments that do not load the settings file.
DEMO_STUDENT_ID = settings.demo_student_id or "demo2026"
DEMO_PASSWORD = settings.demo_password or "DemoPass123!"
DEMO_USER_ID = str(uuid.uuid5(uuid.NAMESPACE_URL, "icampus:competition-demo:user"))
SEED_SOURCE = "competition_demo_seed"


def stable_id(kind: str) -> str:
    """Return a stable UUID for resources that are not created by a service."""

    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"icampus:competition-demo:{kind}"))


def delete_demo_resources(db: Session, user_id: str) -> None:
    """Delete all demo-owned records in dependency order."""

    # The order keeps this safe on databases that enforce foreign keys even
    # though the production SQLite setup also has ORM/database cascades.
    for model in (
        PlanTask,
        GrowthConversation,
        GrowthReport,
        GrowthSession,
        Todo,
        Exam,
        Course,
        ImportPreview,
        Memory,
    ):
        db.query(model).filter(model.user_id == user_id).delete(
            synchronize_session=False,
        )
    db.flush()


def seed_user(db: Session) -> User:
    """Create or reset the stable competition login."""

    user = db.query(User).filter(User.student_id == DEMO_STUDENT_ID).first()
    now = datetime.now(timezone.utc)
    if user is None:
        user = User(id=DEMO_USER_ID, student_id=DEMO_STUDENT_ID)
        db.add(user)
        db.flush()

    user.name = "林知远"
    user.nickname = "阿远"
    user.password_hash = hash_password(DEMO_PASSWORD)
    user.school = "青岛理工大学"
    user.college = "信息与控制工程学院"
    user.major = "软件工程"
    user.grade = "大三"
    user.enroll_year = "2023"
    user.updated_at = now
    return user


def add_memory(
    db: Session,
    *,
    user_id: str,
    key: str,
    value: str,
    memory_type: str,
    importance: int,
    confidence: float = 0.96,
    source_note: str,
) -> None:
    """Add one transparent, user-visible memory item."""

    now = datetime.now(timezone.utc)
    db.add(Memory(
        user_id=user_id,
        memory_type=memory_type,
        key=key,
        value=value,
        importance=importance,
        confidence=confidence,
        source=f"{SEED_SOURCE} / {source_note}",
        conflict_history="[]",
        expires_at=None,
        created_at=now,
        updated_at=now,
    ))


def seed_memories(db: Session, user_id: str) -> None:
    """Seed nine explainable memories for the AI-memory screen.

    School, college and enroll year are included because the login endpoint
    syncs those same profile fields on first sign-in.  Seeding them here keeps
    the visible count stable instead of creating extra rows during the demo.
    """

    items = [
        ("学校", "青岛理工大学", "profile", 4, "入学档案·学校字段"),
        ("学院", "信息与控制工程学院", "profile", 4, "入学档案·学院字段"),
        ("专业", "软件工程", "profile", 5, "入学档案·专业字段"),
        ("年级", "大三，计划参加今年秋招", "profile", 4, "入学档案·年级字段"),
        ("入学年份", "2023", "profile", 3, "入学档案·年份字段"),
        ("兴趣", "后端开发、开源项目、城市骑行", "profile", 4, "演示画像·兴趣偏好"),
        ("时间窗口", "工作日 19:00 后可学习；周末可投入半天，每周约 12 小时", "profile", 5, "沙盘对话·时间约束"),
        ("目标", "在秋招前完成一次真实岗位验证，并决定是否把考研作为备选路线", "goal", 5, "规划报告·目标"),
        ("关注路径", "就业规划、考研规划", "goal", 4, "已完成路径沙盘·路径选择"),
    ]
    for key, value, memory_type, importance, source_note in items:
        add_memory(
            db,
            user_id=user_id,
            key=key,
            value=value,
            memory_type=memory_type,
            importance=importance,
            source_note=source_note,
        )


def schedule(weekday: int, start: int, end: int) -> dict[str, Any]:
    return {
        "weekday": weekday,
        "start": start,
        "end": end,
        "weeks": "1-16周",
        "weeks_parsed": {"start": 1, "end": 16, "parity": None},
    }


def seed_courses(db: Session, user_id: str, semester_start: date) -> None:
    courses = [
        {
            "id": stable_id("course-data-structures"),
            "name": "数据结构与算法",
            "teacher": "周老师",
            "location": "图书馆 B203",
            "schedule_json": json.dumps([schedule(4, 1, 2)], ensure_ascii=False),
            "notes": "考试重点：树、图与动态规划",
            "color": "#4A90D9",
        },
        {
            "id": stable_id("course-software-architecture"),
            "name": "软件架构设计",
            "teacher": "陈老师",
            "location": "教学楼 A305",
            "schedule_json": json.dumps([schedule(1, 5, 6)], ensure_ascii=False),
            "notes": "完成一次微服务架构案例复盘",
            "color": "#8B6BD9",
        },
        {
            "id": stable_id("course-english"),
            "name": "大学英语（四）",
            "teacher": "刘老师",
            "location": "外语楼 204",
            "schedule_json": json.dumps([schedule(3, 3, 4)], ensure_ascii=False),
            "notes": "每周提交一篇技术英语摘要",
            "color": "#2E9C78",
        },
    ]
    for item in courses:
        db.add(Course(
            user_id=user_id,
            source="manual",
            semester_start=semester_start,
            **item,
        ))


def seed_exam(db: Session, user_id: str, exam_date: date) -> None:
    db.add(Exam(
        id=stable_id("exam-data-structures"),
        user_id=user_id,
        subject="数据结构与算法期中考试",
        exam_date=exam_date,
        start_time="09:00",
        end_time="11:00",
        location="图书馆 B203",
        notes="优先复习树、图、动态规划；考前完成两套模拟题",
        source="manual",
    ))


def build_report(today: date) -> dict[str, Any]:
    """Build a complete four-phase report that the report UI can normalize."""

    def task(title: str, days: int) -> dict[str, str]:
        return {"title": title, "deadline": (today + timedelta(days=days)).isoformat()}

    return {
        "title": "就业与考研双路径行动路线",
        "summary": "先用两周完成后端岗位验证，再根据真实反馈决定是否加大考研投入；两条路径都保留选择权。",
        "goal": "在秋招前完成一次真实岗位验证，并形成可执行的方向选择依据。",
        "current_status": "软件工程大三，具备 Java/Spring Boot 项目经验，时间主要集中在工作日晚上和周末。",
        "advantages": [
            "有可展示的校园项目，能讲清从开发到部署的完整链路。",
            "调试耐心、执行力稳定，适合用小步验证降低决策压力。",
        ],
        "risks": [
            "同时准备就业和考研容易摊薄每周 12 小时的有效投入。",
            "分布式系统与算法训练仍需要用作品和题目补齐证据。",
        ],
        "action_plan": [
            {
                "phase_key": "phase_1",
                "phase": "第1-2周",
                "title": "建立基线与验证方向",
                "description": "把已有项目整理成可验证的求职材料，并完成一次岗位市场摸底。",
                "tasks": [
                    task("复盘校园二手交易平台，整理一页项目亮点与技术难点", 2),
                    task("完成一次后端岗位 JD 拆解，记录高频技能缺口", 4),
                    task("刷完两组高频算法题并建立错题记录", 6),
                ],
            },
            {
                "phase_key": "phase_2",
                "phase": "第3-4周",
                "title": "形成作品与反馈闭环",
                "description": "用小作品和真实交流检验岗位匹配度。",
                "tasks": [
                    task("为项目补充 Docker 部署说明和架构图", 13),
                    task("完成一次学长或从业者访谈，记录三条一手反馈", 17),
                ],
            },
            {
                "phase_key": "phase_3",
                "phase": "第5-8周",
                "title": "集中投入主路径",
                "description": "根据前两阶段证据，选择就业或考研作为主路径。",
                "tasks": [
                    task("完成三次针对性投递或一轮考研目标院校信息核验", 31),
                    task("针对最大技能缺口完成一个可展示的小专题", 38),
                ],
            },
            {
                "phase_key": "phase_4",
                "phase": "第9-12周",
                "title": "复盘并锁定下一阶段",
                "description": "复盘验证结果，锁定接下来一个学期的投入方向。",
                "tasks": [
                    task("完成一次方向复盘，写下保留、放弃和新增的行动", 59),
                    task("制定下一学期的 12 周执行日历", 66),
                ],
            },
        ],
    }


def seed_growth_report(
    db: Session,
    *,
    user_id: str,
    report: dict[str, Any],
    created_at: datetime,
) -> tuple[GrowthSession, GrowthReport]:
    session_id = stable_id("growth-career-report")
    report_id = stable_id("growth-career-report-row")
    planning_state = {
        "agent_type": "career",
        "user_profile": {
            "major": "软件工程",
            "grade": "大三",
            "interest": "后端开发、开源项目",
            "time_window": "工作日 19:00 后，周末半天",
        },
        "follow_up_answers": {
            "项目经历": "校园二手交易平台，负责 Spring Boot 后端和部署",
            "时间约束": "每周约 12 小时，工作日晚上更稳定",
            "目标": "秋招前完成真实岗位验证",
        },
    }
    state = {
        "planning_state_json": json.dumps(planning_state, ensure_ascii=False),
        "follow_up_round": 5,
        "questions_asked": 5,
        "follow_up_complete": True,
        "analysis": {"direction": "就业优先验证，考研作为保留选项"},
        "identified_problems": ["方向选择缺少真实反馈", "作品表达和算法证据需要补齐"],
        "long_term_goal": report["goal"],
        "action_plan": report["action_plan"],
        "output": report,
        "last_question": "",
        "stage": "report",
        "finished": True,
        "awaiting_trigger": False,
        "turn_analysis": {},
        "knowledge_context": "",
        "knowledge_evidence": {},
    }
    session = GrowthSession(
        id=session_id,
        user_id=user_id,
        agent_type="career",
        status="completed",
        stage="report",
        current_step=5,
        total_steps=5,
        finished=True,
        state_json=json.dumps(state, ensure_ascii=False),
        answers_json=json.dumps(planning_state["follow_up_answers"], ensure_ascii=False),
        report_json=json.dumps(report, ensure_ascii=False),
        progress=100.0,
        created_at=created_at,
        updated_at=created_at,
    )
    db.add(session)
    db.flush()

    growth_report = GrowthReport(
        id=report_id,
        session_id=session_id,
        user_id=user_id,
        agent_type="career",
        report_type="career_report",
        profile_json=json.dumps({"current_status": report["current_status"]}, ensure_ascii=False),
        analysis_json=json.dumps({"summary": report["summary"], "goal": report["goal"]}, ensure_ascii=False),
        advantages_json=json.dumps(report["advantages"], ensure_ascii=False),
        risks_json=json.dumps(report["risks"], ensure_ascii=False),
        recommendations_json=json.dumps(report["action_plan"], ensure_ascii=False),
        plan_json=json.dumps(report["action_plan"], ensure_ascii=False),
        full_report_json=json.dumps(report, ensure_ascii=False),
        created_at=created_at,
    )
    db.add(growth_report)

    conversations = [
        ("assistant", "我们先把你的项目、时间和方向困惑整理清楚，再做路径比较。"),
        ("user", "我做过校园二手交易平台，主要负责 Java 后端和部署。"),
        ("assistant", "你的优势是有完整项目链路，下一步需要补齐可展示的技术证据。"),
        ("user", "工作日晚上更有时间，每周大约能投入 12 小时。"),
        ("assistant", "报告已生成：先用两周验证就业方向，同时保留考研选项。"),
    ]
    for index, (role, content) in enumerate(conversations):
        db.add(GrowthConversation(
            id=stable_id(f"growth-conversation-{index}"),
            session_id=session_id,
            user_id=user_id,
            role=role,
            content=content,
            step=min(index, 5),
            stage="report" if index == len(conversations) - 1 else "questioning",
            created_at=created_at + timedelta(seconds=index),
        ))
    return session, growth_report


def seed_completed_sandbox(db: Session, user_id: str, created_at: datetime) -> str:
    """Persist a completed, restorable sandbox context for fallback demo mode."""

    sandbox_id = stable_id("sandbox-career-graduate")
    path_reports = {
        "career": {
            "path_type": "career",
            "path_label": "就业规划",
            "core_insight": "已有后端项目使就业路径可以先用真实岗位反馈验证。",
            "time_projection": {
                "short_term": "2 周内完成项目复盘、JD 拆解和一次针对性投递。",
                "mid_term": "3 个月内形成可展示作品并完成多轮面试反馈。",
                "long_term": "2-3 年内成长为能独立负责服务模块的后端工程师。",
                "key_milestones": ["项目材料可展示", "完成第一轮投递", "获得真实面试反馈"],
            },
            "strengths": [{"factor": "项目基础", "detail": "有 Java/Spring Boot 完整项目"}],
            "challenges": [{"factor": "证据不足", "detail": "分布式和算法能力需要继续验证"}],
            "best_for": "希望尽快获得真实反馈、重视经济独立的人",
            "deal_breakers": "无法持续投入作品和面试准备的人",
        },
        "graduate": {
            "path_type": "graduate",
            "path_label": "考研规划",
            "core_insight": "考研能延长能力积累窗口，但需要更早确认目标院校和稳定投入。",
            "time_projection": {
                "short_term": "2 周内完成目标院校、专业课和数学基础盘点。",
                "mid_term": "1 年内形成稳定的专业课、英语和数学复习节奏。",
                "long_term": "2-3 年内获得更深的系统与研究训练，再进入技术岗位。",
                "key_milestones": ["完成院校筛选", "完成一轮基础复习", "验证长期投入意愿"],
            },
            "strengths": [{"factor": "学习窗口", "detail": "仍有时间建立系统知识结构"}],
            "challenges": [{"factor": "机会成本", "detail": "需要承担时间和经济投入"}],
            "best_for": "愿意用较长周期换取学历和系统训练的人",
            "deal_breakers": "无法接受一年以上备考周期的人",
        },
    }
    projection = {
        "projections": [
            {**path_reports["career"], "path_label": "就业规划"},
            {**path_reports["graduate"], "path_label": "考研规划"},
        ],
        "comparison_matrix": {
            "dimensions": ["个人匹配度", "成长空间", "时间成本", "风险"],
            "scores": {"career": [9, 8, 4, 5], "graduate": [7, 9, 9, 7]},
        },
        "relationship_analysis": {
            "mutually_exclusive": ["短期主投入时间有限，需要设定主次"],
            "can_be_sequential": ["先做就业验证，再根据反馈决定是否考研"],
            "complementary": ["项目复盘和专业课学习都能提升长期技术基础"],
            "note": "两条路径不必今天一次性定终身，先做低成本验证更适合当前约束。",
        },
        "decision_guide": {
            "questions_to_ask_yourself": ["两周后哪类反馈最能帮助我做决定？", "我能稳定承受多长的备考周期？"],
            "if_you_value_X_then_Y": [
                {"value": "尽快经济独立", "recommendation": "优先就业验证"},
                {"value": "系统学习与学历提升", "recommendation": "加大考研验证"},
            ],
            "possible_hybrid_strategies": ["先完成就业基线验证，再决定是否保留考研为主路径"],
        },
        "key_uncertainties": [
            {"factor": "真实面试反馈", "impact": "决定就业方向的匹配度", "how_to_reduce": "完成一次针对性投递和复盘"},
            {"factor": "长期备考耐受度", "impact": "决定考研投入能否持续", "how_to_reduce": "先做两周固定时段试运行"},
        ],
        "summary": "已完成就业与考研两条路径的对比。当前更适合先用两周完成就业验证，再依据真实反馈调整主路径。",
    }
    session = SandboxSession(
        session_id=sandbox_id,
        user_id=user_id,
        current_phase=SandboxPhase.COMPLETED,
        phase_index=4,
        finished=True,
        discovery_round=3,
        discovery_history=[
            {"q": "你现在最能代表自己能力的一项项目是什么？", "a": "校园二手交易平台，负责 Java/Spring Boot 后端和部署。"},
            {"q": "你每周可以稳定投入多少时间？", "a": "工作日晚上和周末半天，每周约 12 小时。"},
            {"q": "你当前最想解决的方向问题是什么？", "a": "想尽快验证就业，同时不完全放弃考研可能。"},
        ],
        discovery_answers={
            "项目经历": "校园二手交易平台，负责 Java/Spring Boot 后端和部署。",
            "时间约束": "工作日晚上和周末半天，每周约 12 小时。",
            "当前困惑": "想尽快验证就业，同时不完全放弃考研可能。",
        },
        discovery_complete=True,
        user_profile={
            "major": "软件工程",
            "grade": "大三",
            "interest": "后端开发、开源项目、城市骑行",
            "time_window": "工作日 19:00 后，周末半天，每周约 12 小时",
            "core_confusion": "就业与考研之间需要低成本验证",
        },
        questions_asked=5,
        path_selections=["career", "graduate"],
        path_selection_source="competition_demo_seed",
        path_selection_locked=True,
        path_probe_history={
            "career": [{"q": "就业方向希望验证什么？", "a": "后端开发岗位和项目能力是否匹配。"}],
            "graduate": [{"q": "考研方向最担心什么？", "a": "长期投入和机会成本。"}],
        },
        path_probe_done={"career", "graduate"},
        path_reports=path_reports,
        parallel_sim_complete=True,
        projection_result=projection,
        memory_snapshot={"专业": "软件工程", "年级": "大三", "兴趣": "后端开发、开源项目"},
    )
    now = datetime.now(timezone.utc)
    db.add(Memory(
        user_id=user_id,
        memory_type="context",
        key=f"context:sandbox:{sandbox_id}",
        value=json.dumps(session.to_dict(), ensure_ascii=False),
        importance=1,
        confidence=1.0,
        source=f"{SEED_SOURCE} / completed sandbox",
        conflict_history="[]",
        expires_at=now + timedelta(days=365),
        created_at=created_at,
        updated_at=now,
    ))
    return sandbox_id


def seed_demo() -> dict[str, Any]:
    init_db()
    db = SessionLocal()
    try:
        user = seed_user(db)
        delete_demo_resources(db, user.id)
        db.commit()

        today = date.today()
        created_at = datetime.now(timezone.utc)
        semester_start = today - timedelta(days=today.weekday())
        seed_memories(db, user.id)
        seed_courses(db, user.id, semester_start)
        seed_exam(db, user.id, today + timedelta(days=7))
        report_payload = build_report(today)
        growth_session, growth_report = seed_growth_report(
            db,
            user_id=user.id,
            report=report_payload,
            created_at=created_at,
        )
        db.commit()

        # Use the production sync path so PlanTask/Todo linkage and report
        # parsing stay identical to an actual first-phase sync from the UI.
        sync_result = TodayService().sync_growth_plan(
            db,
            user_id=user.id,
            growth_session_id=growth_session.id,
            phase="phase_1",
            start_date=today,
        )
        first_link = db.query(PlanTask).filter(
            PlanTask.user_id == user.id,
            PlanTask.growth_session_id == growth_session.id,
            PlanTask.phase_key == "phase_1",
            PlanTask.plan_task_index == 0,
        ).first()
        if first_link is None:
            raise RuntimeError("phase_1 sync did not create its first PlanTask")
        first_todo = db.query(Todo).filter(Todo.id == first_link.todo_id).one()
        first_todo.status = "done"
        first_todo.updated_at = datetime.now(timezone.utc)

        # Two ordinary tasks keep Today Mode visually rich while the three
        # phase-1 tasks remain traceable to the report.
        db.add_all([
            Todo(
                id=stable_id("todo-mentor-chat"),
                user_id=user.id,
                title="预约一位后端学长，完成 20 分钟职业访谈",
                status="pending",
                deadline=(today + timedelta(days=5)).isoformat(),
                source="manual",
            ),
            Todo(
                id=stable_id("todo-english-summary"),
                user_id=user.id,
                title="整理本周技术英语摘要并提交课程作业",
                status="pending",
                deadline=(today + timedelta(days=3)).isoformat(),
                source="manual",
            ),
        ])
        sandbox_id = seed_completed_sandbox(db, user.id, created_at)
        db.commit()

        pending_count = db.query(Todo).filter(
            Todo.user_id == user.id,
            Todo.status == "pending",
        ).count()
        total_todos = db.query(Todo).filter(Todo.user_id == user.id).count()
        memory_count = db.query(Memory).filter(
            Memory.user_id == user.id,
            Memory.memory_type != "context",
        ).count()
        return {
            "student_id": DEMO_STUDENT_ID,
            "password": DEMO_PASSWORD,
            "user_id": user.id,
            "name": user.name,
            "nickname": user.nickname,
            "sandbox_session_id": sandbox_id,
            "growth_session_id": growth_session.id,
            "growth_report_id": growth_report.id,
            "courses": db.query(Course).filter(Course.user_id == user.id).count(),
            "upcoming_exams": db.query(Exam).filter(Exam.user_id == user.id).count(),
            "todos_total": total_todos,
            "todos_pending": pending_count,
            "visible_memories": memory_count,
            "phase_1_synced": bool(sync_result.get("synced_count")),
            "phase_1_sync_count": sync_result.get("synced_count", 0),
            "completed_tasks": db.query(Todo).filter(
                Todo.user_id == user.id,
                Todo.status.in_(("done", "archived")),
            ).count(),
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset and seed the competition demo account")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the result as one JSON object (useful for automation)",
    )
    args = parser.parse_args()
    result = seed_demo()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print("Competition demo account is ready.")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("Live demo: use the account to run one real AI sandbox/growth generation.")
    print("Fallback demo: open the completed sandbox and report using the printed session IDs.")
    print(f"Database: {settings.database_url}")


if __name__ == "__main__":
    main()
