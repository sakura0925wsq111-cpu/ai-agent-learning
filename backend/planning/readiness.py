# -*- coding: utf-8 -*-
"""Deterministic information-readiness gate for growth-planning advice.

Response length and advice readiness are intentionally independent.  A short
turn can collect one useful variable, but personalized advice is only allowed
after the domain-specific minimum below is met.  Unknown or declined answers
are remembered so the agent can move on instead of pressuring the user.
"""

from __future__ import annotations

import re
from typing import Any


UNKNOWN_PATTERNS: tuple[str, ...] = (
    "不知道", "不清楚", "不了解", "没了解", "不确定", "没想好",
    "还没想", "还没考虑", "暂时没有想法", "说不准", "看情况",
    "都行", "都可以", "无所谓", "随便", "再说吧", "都差不多",
)

DECLINED_PATTERNS: tuple[str, ...] = (
    "不想回答", "不方便说", "不愿意说", "先不说", "不便透露",
    "保密", "跳过", "不回答", "不用问了", "别再问", "不再回答",
    "直接规划", "开始规划", "开始分析", "没有其他补充", "没有别的信息",
    "没有补充", "就是这些", "主要情况", "能想到的", "可以了",
)


READINESS_STANDARDS: dict[str, dict[str, Any]] = {
    "graduate": {
        "minimum": 4,
        "required": ("background", "target", "foundation"),
        "dimensions": {
            "background": {
                "label": "专业与年级",
                "profile_keys": ("major", "专业", "grade", "年级", "school", "学校", "学历"),
                "question_terms": ("专业", "年级", "学校背景", "本科背景"),
                "answer_terms": ("大一", "大二", "大三", "大四", "本科", "专科"),
            },
            "motivation": {
                "label": "读研动机与价值排序",
                "profile_keys": ("motivation", "读研动机", "价值排序"),
                "question_terms": ("为什么考研", "读研动机", "更看重", "短期收入", "长期发展"),
                "answer_terms": ("长期发展", "短期收入", "学历门槛", "科研", "深造", "经济独立"),
            },
            "target": {
                "label": "目标方向或岗位",
                "profile_keys": ("target", "goal", "目标", "方向", "目标岗位", "目标院校"),
                "question_terms": ("目标方向", "目标岗位", "哪类岗位", "院校", "研究型", "工程型"),
                "answer_terms": ("算法", "开发", "研究型", "工程型", "跨考", "本专业考研", "院校"),
            },
            "foundation": {
                "label": "学业与备考基础",
                "profile_keys": ("gpa", "绩点", "排名", "数学", "英语", "基础", "skills", "技能"),
                "question_terms": ("数学基础", "英语基础", "当前排名", "绩点", "编程基础", "备考基础"),
                "answer_terms": ("数学", "英语", "六级", "四级", "绩点", "排名", "编程", "基础一般"),
            },
            "constraints": {
                "label": "时间与现实约束",
                "profile_keys": ("time", "时间", "location", "城市", "family", "家庭", "预算", "约束"),
                "question_terms": ("投入多少时间", "时间成本", "家庭", "经济", "风险偏好", "目标城市"),
                "answer_terms": ("小时", "一年", "半年", "家里", "父母", "经济", "尽快工作", "城市"),
            },
        },
    },
    "career": {
        "minimum": 4,
        "required": ("background", "target", "evidence"),
        "dimensions": {
            "background": {
                "label": "专业与求职阶段",
                "profile_keys": ("major", "专业", "grade", "年级", "school", "学校", "学历"),
                "question_terms": ("专业", "年级", "求职阶段", "毕业时间"),
                "answer_terms": ("大一", "大二", "大三", "大四", "应届", "本科", "专科"),
            },
            "target": {
                "label": "目标岗位或工作内容",
                "profile_keys": ("target", "goal", "目标", "岗位", "职业方向"),
                "question_terms": ("职业方向", "目标岗位", "哪类岗位", "工作内容", "想做什么"),
                "answer_terms": ("后端", "前端", "开发", "测试", "产品", "运营", "算法", "岗位"),
            },
            "evidence": {
                "label": "技能、项目或实习证据",
                "profile_keys": ("skills", "技能", "projects", "项目", "internships", "实习", "经历"),
                "question_terms": ("项目经历", "实习经历", "技能基础", "作品", "能证明"),
                "answer_terms": ("项目", "实习", "课程作业", "技能", "证书", "比赛", "作品"),
            },
            "preferences": {
                "label": "城市、行业与工作偏好",
                "profile_keys": ("location", "城市", "industry", "行业", "preferences", "偏好"),
                "question_terms": ("哪个城市", "行业偏好", "企业类型", "工作环境", "团队"),
                "answer_terms": ("杭州", "北京", "上海", "深圳", "互联网", "制造业", "国企", "外企"),
            },
            "constraints": {
                "label": "收入、强度与稳定性约束",
                "profile_keys": ("salary", "薪资", "time", "时间", "values", "价值排序", "约束"),
                "question_terms": ("薪资", "工作强度", "加班", "稳定", "能投入", "更看重"),
                "answer_terms": ("薪资", "成长", "稳定", "加班", "工作强度", "生活平衡", "换工作"),
            },
        },
    },
    "civil": {
        "minimum": 4,
        "required": ("background", "motivation", "target"),
        "dimensions": {
            "background": {
                "label": "专业与报考阶段",
                "profile_keys": ("major", "专业", "grade", "年级", "school", "学校", "学历"),
                "question_terms": ("专业", "年级", "毕业时间", "应届"),
                "answer_terms": ("大一", "大二", "大三", "大四", "应届", "本科", "专科"),
            },
            "motivation": {
                "label": "考公动机与价值排序",
                "profile_keys": ("motivation", "考公动机", "价值排序", "values"),
                "question_terms": ("为什么考公", "考公原因", "更看重", "个人意愿"),
                "answer_terms": ("稳定", "工作生活平衡", "体制", "父母", "个人意愿", "犹豫"),
            },
            "target": {
                "label": "考试、地区与岗位范围",
                "profile_keys": ("target", "目标", "地区", "岗位", "考试类型"),
                "question_terms": ("哪个地区", "目标岗位", "考试类型", "国考", "省考", "岗位范围"),
                "answer_terms": ("国考", "省考", "选调", "事业编", "省会", "老家", "岗位"),
            },
            "foundation": {
                "label": "行测申论基础",
                "profile_keys": ("行测", "申论", "基础", "模考", "分数"),
                "question_terms": ("行测基础", "申论基础", "模考", "数量关系", "资料分析"),
                "answer_terms": ("行测", "申论", "言语", "数量关系", "资料分析", "写作", "模考"),
            },
            "constraints": {
                "label": "备考投入与备选方案",
                "profile_keys": ("time", "时间", "备考周期", "备选方案", "约束"),
                "question_terms": ("备考周期", "投入多少", "备选方案", "没考上", "家庭期待"),
                "answer_terms": ("一年", "半年", "小时", "企业工作", "备选", "父母", "家庭"),
            },
        },
    },
    "major": {
        "minimum": 4,
        "required": ("background", "reason", "target"),
        "dimensions": {
            "background": {
                "label": "当前专业、年级与学校条件",
                "profile_keys": ("major", "专业", "grade", "年级", "school", "学校"),
                "question_terms": ("当前专业", "年级", "学校", "转专业时间"),
                "answer_terms": ("大一", "大二", "大三", "大四", "当前专业"),
            },
            "reason": {
                "label": "转专业原因",
                "profile_keys": ("motivation", "原因", "转专业原因", "兴趣"),
                "question_terms": ("为什么想转", "离开当前专业", "不感兴趣", "转专业原因"),
                "answer_terms": ("没兴趣", "不感兴趣", "喜欢", "就业", "课程", "不适应"),
            },
            "target": {
                "label": "目标专业或替代方向",
                "profile_keys": ("target", "目标", "目标专业", "方向"),
                "question_terms": ("转到什么专业", "目标专业", "替代路径", "想转到"),
                "answer_terms": ("计算机", "金融", "法学", "辅修", "自学", "目标专业"),
            },
            "foundation": {
                "label": "目标专业基础",
                "profile_keys": ("skills", "技能", "基础", "成绩", "数学", "项目"),
                "question_terms": ("目标专业基础", "数学成绩", "编程", "相关课程", "项目实践"),
                "answer_terms": ("数学", "编程", "项目", "课程", "成绩", "基础"),
            },
            "constraints": {
                "label": "政策、时间与家庭约束",
                "profile_keys": ("policy", "政策", "time", "时间", "family", "家庭", "约束"),
                "question_terms": ("转专业要求", "延迟毕业", "家庭", "时间成本", "替代方案"),
                "answer_terms": ("延迟毕业", "父母", "家庭", "辅修", "自学", "成绩要求", "政策"),
            },
        },
    },
}


def classify_answer_availability(answer: str) -> str:
    """Return answered, unknown, or declined without treating either as failure."""
    normalized = re.sub(r"\s+", "", str(answer or "")).lower()
    if not normalized:
        return "unknown"
    if any(pattern in normalized for pattern in DECLINED_PATTERNS):
        return "declined"
    if any(pattern in normalized for pattern in UNKNOWN_PATTERNS):
        return "unknown"
    return "answered"


def _looks_like_information_request(text: str) -> bool:
    normalized = re.sub(r"\s+", "", str(text or ""))
    if not normalized or any(
        marker in normalized
        for marker in ("我更", "我想选", "我倾向", "我可以", "我能", "我有", "我目前", "我的")
    ):
        return False
    objective_terms = (
        "薪资", "工资", "区别", "差异", "考试内容", "考什么", "政策",
        "要求", "流程", "前景", "岗位", "有哪些", "多少", "怎么",
    )
    asks = normalized.endswith(("？", "?", "吗")) or any(
        term in normalized for term in ("什么", "多少", "怎么", "哪些")
    )
    return asks and any(term in normalized for term in objective_terms)


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    normalized = str(text or "").lower()
    return any(term.lower() in normalized for term in terms)


def infer_dimension(agent_type: str, question: str, answer: str = "") -> str:
    """Infer the information dimension targeted by a Q&A pair."""
    standard = READINESS_STANDARDS.get(agent_type, READINESS_STANDARDS["career"])
    dimensions = standard["dimensions"]
    for key, spec in dimensions.items():
        if _contains_any(question, spec["question_terms"]):
            return key
    for key, spec in dimensions.items():
        if _contains_any(answer, spec["answer_terms"]):
            return key
    return ""


def _profile_coverage(agent_type: str, profile: dict[str, Any]) -> set[str]:
    standard = READINESS_STANDARDS.get(agent_type, READINESS_STANDARDS["career"])
    covered: set[str] = set()
    for dimension, spec in standard["dimensions"].items():
        for key, value in profile.items():
            if value in (None, "", [], {}):
                continue
            normalized_key = str(key).lower()
            if any(profile_key.lower() in normalized_key for profile_key in spec["profile_keys"]):
                covered.add(dimension)
                break

    raw_input = str(profile.get("raw_input", ""))
    if raw_input:
        for dimension, spec in standard["dimensions"].items():
            if _contains_any(raw_input, spec["answer_terms"]):
                covered.add(dimension)
    return covered


def evaluate_advice_readiness(
    agent_type: str,
    *,
    user_profile: dict[str, Any] | None = None,
    follow_up_history: list[dict[str, str]] | None = None,
    unavailable_dimensions: dict[str, str] | None = None,
    questions_asked: int = 0,
    max_questions: int = 5,
    current_question: str = "",
    current_dimension: str = "",
    current_answer: str = "",
) -> dict[str, Any]:
    """Evaluate whether personalized, general, or conditional advice is safe."""
    standard = READINESS_STANDARDS.get(agent_type, READINESS_STANDARDS["career"])
    dimensions = standard["dimensions"]
    covered = _profile_coverage(agent_type, user_profile or {})
    unavailable = dict(unavailable_dimensions or {})

    for entry in follow_up_history or []:
        answer = str(entry.get("a", ""))
        dimension = str(entry.get("dimension", "")) or infer_dimension(
            agent_type, str(entry.get("q", "")), answer
        )
        availability = str(entry.get("availability", "")) or classify_answer_availability(answer)
        if not dimension:
            continue
        if availability == "answered":
            covered.add(dimension)
            unavailable.pop(dimension, None)
        elif availability in ("unknown", "declined"):
            unavailable[dimension] = availability

    current_availability = classify_answer_availability(current_answer) if current_answer else "not_applicable"
    if current_answer and _looks_like_information_request(current_answer):
        current_availability = "not_answered"
    resolved_current_dimension = current_dimension or infer_dimension(
        agent_type, current_question, current_answer
    )
    if current_answer and resolved_current_dimension:
        if current_availability == "answered":
            covered.add(resolved_current_dimension)
            unavailable.pop(resolved_current_dimension, None)
        elif current_availability in ("unknown", "declined"):
            unavailable[resolved_current_dimension] = current_availability

    covered &= set(dimensions)
    unavailable = {
        key: value for key, value in unavailable.items()
        if key in dimensions and key not in covered
    }
    missing = [key for key in dimensions if key not in covered]
    required_missing = [key for key in standard["required"] if key not in covered]
    personalized = len(covered) >= standard["minimum"] and not required_missing

    askable_missing = [key for key in missing if key not in unavailable]
    priority = [key for key in required_missing if key in askable_missing]
    priority.extend(key for key in askable_missing if key not in priority)
    can_ask = bool(priority) and questions_asked < max_questions and not personalized

    if personalized:
        advice_level = "personalized"
    elif can_ask:
        advice_level = "general_only"
    else:
        # The cap was reached or the remaining variables are unavailable.  The
        # workflow may proceed, but only with explicit assumptions/scenarios.
        advice_level = "conditional"

    labels = {key: spec["label"] for key, spec in dimensions.items()}
    next_dimension = priority[0] if can_ask else ""
    return {
        "ready": advice_level != "general_only",
        "ready_for_personalized_advice": personalized,
        "advice_level": advice_level,
        "covered_dimensions": [key for key in dimensions if key in covered],
        "covered_labels": [labels[key] for key in dimensions if key in covered],
        "missing_dimensions": missing,
        "missing_labels": [labels[key] for key in missing],
        "required_missing": required_missing,
        "unavailable_dimensions": unavailable,
        "askable_missing": askable_missing,
        "next_dimension": next_dimension,
        "next_dimension_label": labels.get(next_dimension, ""),
        "current_dimension": resolved_current_dimension,
        "current_availability": current_availability,
        "minimum_required": standard["minimum"],
        "covered_count": len(covered),
        "questions_asked": questions_asked,
        "max_questions": max_questions,
        "can_ask": can_ask,
    }
