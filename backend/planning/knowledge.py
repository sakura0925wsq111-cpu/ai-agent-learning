# -*- coding: utf-8 -*-
"""Curated, source-aware domain knowledge for growth conversations.

This is deliberately conservative: stable concepts are provided directly,
while volatile figures are described as variables unless a future external
provider supplies dated evidence.
"""

from __future__ import annotations

from typing import Any


_COMMON = {
    "salary": (
        "薪资不能只由学历推断，还会受到专业、岗位、城市、企业类型、实习项目和个人能力影响。"
        "没有带地区、岗位和时间范围的可靠来源时，不应给出精确薪资数字。"
    ),
    "comparison": (
        "比较两条路径时，应同时看岗位准入范围、短期机会成本、能力积累方式和三到五年的发展空间，"
        "不能只比较第一份工作的起薪。"
    ),
    "policy": (
        "学校、专业和地区政策可能每年变化。可以先解释通用规则；涉及具体院校、岗位或年份时，"
        "应提示以当年官方公告为准。"
    ),
}

_DOMAIN_KNOWLEDGE: dict[str, dict[str, str]] = {
    "graduate": {
        "path_overview": (
            "考研方向通常可从本专业深化、相近专业交叉、跨专业转换三类考虑。"
            "判断重点是目标岗位的学历门槛、当前学业基础、读研动机和时间成本。"
        ),
        "comparison": (
            "研究型、算法和部分高门槛研发岗位通常更重视研究生阶段的专业训练；"
            "偏工程实践的岗位也高度看重项目、实习和解决实际问题的能力。读研并不自动等于更高收入。"
        ),
        "exam": (
            "硕士研究生初试通常包括思想政治理论、外语和业务课；是否考数学、考哪一类数学、"
            "专业课是统考还是自命题，取决于具体专业和招生单位。"
        ),
        "timeline": (
            "备考一般经历目标确认与摸底、基础学习、强化训练、真题与冲刺几个阶段。"
            "合理周期取决于当前基础、跨考幅度和每日稳定投入，而不是一个适用于所有人的固定月份数。"
        ),
        "policy": _COMMON["policy"],
        "salary": _COMMON["salary"],
    },
    "career": {
        "path_overview": (
            "就业方向应从岗位族、行业场景和能力证据三个层面选择：先明确想解决哪类问题，"
            "再用课程、项目和实习证明匹配度。"
        ),
        "comparison": _COMMON["comparison"],
        "salary": _COMMON["salary"],
        "timeline": (
            "求职准备通常包括方向定位、能力补缺、项目与简历、实习或校招投递、面试复盘。"
            "越接近招聘窗口，越应优先建设可展示的能力证据。"
        ),
        "policy": _COMMON["policy"],
    },
    "civil": {
        "path_overview": (
            "考公考编需要同时比较岗位资格、地区竞争、考试能力、备考机会成本和备选路径，"
            "不能只把“稳定”作为唯一判断依据。"
        ),
        "exam": (
            "公务员笔试通常围绕行政职业能力测验和申论；事业单位、教师、医疗等招聘的科目和资格要求"
            "差异较大，需要结合具体公告判断。"
        ),
        "timeline": (
            "备考通常包括模块摸底、基础训练、真题强化和全真模拟。周期应由目标考试时间、"
            "当前正确率和每日可投入时间倒推。"
        ),
        "policy": _COMMON["policy"],
        "salary": _COMMON["salary"],
        "comparison": _COMMON["comparison"],
    },
    "major": {
        "path_overview": (
            "改变专业方向不只有正式转专业，还可比较辅修、双学位、自学加实践、毕业后跨专业深造等路径。"
            "应同时评估兴趣证据、先修能力、校内政策和毕业时间成本。"
        ),
        "policy": (
            "转专业通常涉及成绩或排名、名额、申请窗口、笔试面试和课程补修，但各校差异很大。"
            "具体决定前必须核对本校当学年的教务公告。"
        ),
        "comparison": _COMMON["comparison"],
        "salary": _COMMON["salary"],
        "timeline": (
            "时间成本不仅是申请周期，还包括先修课程、学分转换、补修压力和是否影响毕业。"
        ),
    },
}


def get_knowledge_context(agent_type: str, topics: list[str] | None = None) -> dict[str, Any]:
    """Return curated knowledge plus provenance metadata for prompt grounding."""
    domain = _DOMAIN_KNOWLEDGE.get(agent_type, {})
    selected_topics = topics or ["path_overview"]
    facts: list[str] = []
    used_topics: list[str] = []
    for topic in selected_topics:
        fact = domain.get(topic) or _COMMON.get(topic)
        if fact and fact not in facts:
            facts.append(fact)
            used_topics.append(topic)

    if not facts and domain.get("path_overview"):
        facts.append(domain["path_overview"])
        used_topics.append("path_overview")

    return {
        "text": "\n".join(f"- {fact}" for fact in facts),
        "topics": used_topics,
        "source": "curated_internal_baseline",
        "updated_at": "2026-08-09",
        "volatile_data_verified": False,
    }
