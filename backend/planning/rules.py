# -*- coding: utf-8 -*-
"""Skill matrices and structured rules for planning agents.

方案 B：代码层硬约束 —— 用户技能 vs 目标岗位要求 → 结构化缺口。
方案 C 的前置基础设施，后续可扩展为 JSON/YAML 配置文件。
"""

from __future__ import annotations

from typing import Any

# ── 岗位 → 必备技能 / 加分技能 / 推荐项目 ────────────────────

SKILL_MATRIX: dict[str, dict[str, Any]] = {
    "后端开发": {
        "required": [
            "Java 或 Go 语言基础",
            "SQL 与数据库设计",
            "RESTful API 开发",
            "Redis 缓存",
            "消息队列基础（RabbitMQ 或 Kafka）",
        ],
        "nice_to_have": [
            "Docker 容器化",
            "Kubernetes 基础",
            "系统设计能力",
            "分布式系统概念",
            "Linux 操作",
        ],
        "projects": [
            "API 网关系统",
            "即时通讯系统",
            "秒杀系统设计",
            "博客/论坛后端",
        ],
        "job_titles": [
            "Java 后端开发工程师",
            "Go 后端开发工程师",
            "后端开发实习生",
            "服务端开发工程师",
        ],
    },
    "前端开发": {
        "required": [
            "HTML/CSS/JavaScript",
            "至少一个主流框架（React 或 Vue）",
            "响应式布局",
            "Git 版本控制",
        ],
        "nice_to_have": [
            "TypeScript",
            "前端工程化（Webpack/Vite）",
            "Node.js 基础",
            "小程-序开发",
        ],
        "projects": [
            "个人博客/作品集网站",
            "后台管理系统",
            "移动端 H5 页面",
        ],
        "job_titles": [
            "前端开发工程师",
            "React/Vue 开发工程师",
            "Web 前端实习生",
        ],
    },
    "AI产品经理": {
        "required": [
            "数据分析能力",
            "PRD 文档撰写",
            "用户调研方法",
            "AB 测试设计",
            "竞品分析",
        ],
        "nice_to_have": [
            "Python 基础",
            "机器学习基本概念",
            "Figma/Axure 原型工具",
            "SQL 基础查询",
        ],
        "projects": [
            "竞品分析报告",
            "产品需求文档",
            "用户数据看板",
        ],
        "job_titles": [
            "AI 产品经理",
            "产品经理实习生",
            "产品助理",
        ],
    },
    "数据分析": {
        "required": [
            "Python 数据处理（Pandas/NumPy）",
            "SQL 熟练查询",
            "数据可视化（Matplotlib/ECharts）",
            "统计学基础",
        ],
        "nice_to_have": [
            "机器学习基础",
            "Tableau/Power BI",
            "A/B 测试经验",
            "大数据工具（Spark/Hive）",
        ],
        "projects": [
            "电商用户行为分析",
            "数据看板搭建",
            "Kaggle 竞赛项目",
        ],
        "job_titles": [
            "数据分析师",
            "BI 分析师",
            "数据分析实习生",
        ],
    },
    "测试开发": {
        "required": [
            "至少一门编程语言（Python/Java）",
            "测试理论基础",
            "自动化测试框架（Selenium/Appium）",
            "接口测试工具",
        ],
        "nice_to_have": [
            "性能测试（JMeter）",
            "CI/CD 流程",
            "安全测试基础",
            "测试用例设计方法论",
        ],
        "projects": [
            "搭建自动化测试框架",
            "编写接口测试套件",
            "性能测试报告",
        ],
        "job_titles": [
            "测试开发工程师",
            "自动化测试工程师",
            "质量保障实习生",
        ],
    },
    "运维/DevOps": {
        "required": [
            "Linux 系统管理",
            "Shell 脚本编程",
            "Docker 容器化",
            "CI/CD 流水线搭建",
        ],
        "nice_to_have": [
            "Kubernetes 编排",
            "监控系统（Prometheus/Grafana）",
            "云服务使用（AWS/阿里云/腾讯云）",
            "Nginx 配置",
        ],
        "projects": [
            "搭建多服务 Docker 编排",
            "监控告警系统",
            "自动化部署流水线",
        ],
        "job_titles": [
            "DevOps 工程师",
            "运维开发工程师",
            "SRE 实习生",
        ],
    },
}


# ── 技能缺口计算 ──────────────────────────────────────────────

def compute_skill_gaps(
    direction_name: str,
    user_skills: list[str],
) -> dict[str, Any]:
    """对比用户技能与目标方向要求，输出结构化缺口。

    Args:
        direction_name: 目标方向名称，如 "后端开发"、"AI产品经理"
        user_skills: 用户已掌握的技能列表

    Returns:
        {
            "direction": "后端开发",
            "matched": ["Java基础"],
            "missing_required": ["Redis缓存", "消息队列"],
            "missing_nice": ["Docker", "Kubernetes"],
            "suggested_projects": ["API网关系统"],
            "completeness": 0.2  # 必备技能覆盖率
        }
    """
    direction_info = SKILL_MATRIX.get(direction_name)
    if not direction_info:
        return {
            "direction": direction_name,
            "matched": [],
            "missing_required": [],
            "missing_nice": [],
            "suggested_projects": [],
            "completeness": 0.0,
        }

    required = direction_info["required"]
    nice = direction_info["nice_to_have"]
    projects = direction_info["projects"]

    user_lower = {s.lower().strip() for s in user_skills}

    matched_required = [r for r in required if _skill_match(r, user_lower)]
    missing_required = [r for r in required if not _skill_match(r, user_lower)]
    missing_nice = [n for n in nice if not _skill_match(n, user_lower)]

    completeness = len(matched_required) / len(required) if required else 0.0

    return {
        "direction": direction_name,
        "matched": matched_required,
        "missing_required": missing_required,
        "missing_nice": missing_nice,
        "suggested_projects": projects,
        "completeness": round(completeness, 2),
    }


def _skill_match(skill: str, user_skills_lower: set[str]) -> bool:
    """Check if a required skill is present in the user's skills (fuzzy match).

    Matches if the skill keyword appears in any user skill string.
    """
    skill_lower = skill.lower()
    for us in user_skills_lower:
        # Check if skill keyword is a substring of user skill or vice versa
        if skill_lower in us or us in skill_lower:
            return True
    return False


# ── 方向名称模糊匹配 ──────────────────────────────────────────

def find_best_matching_direction(
    direction_name: str,
) -> str | None:
    """Try to find the best matching direction from SKILL_MATRIX.

    Uses substring matching since LLM may output slightly different names.
    """
    direction_lower = direction_name.lower().strip()
    for key in SKILL_MATRIX:
        # Substring match
        if key.lower() in direction_lower or direction_lower in key.lower():
            return key
    return None


# ── 导出 ──────────────────────────────────────────────────────

__all__ = [
    "SKILL_MATRIX",
    "compute_skill_gaps",
    "find_best_matching_direction",
]

# ════════════════════════════════════════════════════════════════
# 考研领域知识
# ════════════════════════════════════════════════════════════════

GRADUATE_EXAM_BASELINE: dict[str, Any] = {
    "required_exams": ["政治", "英语", "数学（数一/数二/数三）", "专业课"],
    "score_factors": {
        "英语": ["四级是否通过", "六级是否通过", "考研英语真题摸底分数"],
        "数学": ["高数成绩", "线代成绩", "概率论成绩", "数一/数二/数三选择"],
        "专业课": ["是否统考408", "是否跨专业", "专业课基础"],
    },
    "tier_map": {
        "冲刺": "985院校或顶尖211的王牌专业",
        "稳妥": "211院校或双一流院校",
        "保底": "省属重点一本院校",
    },
    "prep_phases": [
        "摸底阶段：收集信息、确定目标、制定计划",
        "基础阶段：数学+英语第一轮系统学习",
        "强化阶段：数学强化 + 专业课入门 + 英语真题",
        "冲刺阶段：全科真题模拟 + 政治冲刺 + 查漏补缺",
    ],
}

# ════════════════════════════════════════════════════════════════
# 考公考编领域知识
# ════════════════════════════════════════════════════════════════

CIVIL_EXAM_BASELINE: dict[str, Any] = {
    "exam_modules": {
        "行测": ["言语理解与表达", "数量关系", "判断推理", "资料分析", "常识判断"],
        "申论": ["归纳概括", "综合分析", "提出对策", "应用文写作", "大作文"],
        "公基": ["政治理论", "法律基础", "经济常识", "公文写作", "管理知识", "历史人文"],
    },
    "job_categories": {
        "行政编": ["国考（中央部委）", "省考（省市县乡）", "选调生"],
        "事业编": ["事业单位联考", "教师编制", "医疗卫生编制", "科研院所"],
        "其他": ["国企招聘（烟草/电网/银行）", "三支一扶", "大学生村官", "军队文职"],
    },
    "major_advantage_scores": {
        "法学": 10,
        "汉语言文学": 9,
        "计算机": 9,
        "会计/财务管理": 9,
        "经济学": 8,
        "统计学": 7,
        "公共管理": 7,
        "其他": 5,
    },
    "prep_phases": [
        "摸底阶段：各模块自测、确定主攻方向",
        "基础阶段：行测各模块分项突破 + 申论入门",
        "强化阶段：真题套卷 + 申论系统训练",
        "冲刺阶段：全真模拟 + 时政热点 + 面试准备",
    ],
}

# ════════════════════════════════════════════════════════════════
# 转专业领域知识
# ════════════════════════════════════════════════════════════════

MAJOR_TRANSFER_BASELINE: dict[str, Any] = {
    "common_target_majors": {
        "计算机科学": {
            "pre_reqs": ["数学基础（高数/线代）", "至少一门编程语言", "逻辑思维能力"],
            "difficulty": "高",
            "competition": "高",
            "suggested_prep": ["自学数据结构", "完成一个小项目", "LeetCode入门"],
        },
        "电子信息": {
            "pre_reqs": ["数学基础", "物理基础", "电路基础"],
            "difficulty": "高",
            "competition": "中",
            "suggested_prep": ["自学C语言", "了解电路原理", "学习信号处理入门"],
        },
        "金融学": {
            "pre_reqs": ["数学基础（微积分/线代）", "英语阅读能力", "逻辑分析能力"],
            "difficulty": "中",
            "competition": "高",
            "suggested_prep": ["阅读经济学入门书籍", "学习基础会计", "关注财经新闻"],
        },
        "法学": {
            "pre_reqs": ["阅读与写作能力", "逻辑思维", "记忆力"],
            "difficulty": "中",
            "competition": "中",
            "suggested_prep": ["阅读法律入门书籍", "了解司法考试要求", "旁听法学课程"],
        },
        "英语/翻译": {
            "pre_reqs": ["英语基础（四级≥550或六级≥500）", "语感", "文化知识"],
            "difficulty": "中",
            "competition": "低",
            "suggested_prep": ["背专四/专八词汇", "练习翻译", "考雅思/托福"],
        },
    },
    "alternative_paths": {
        "辅修": "不需转专业，利用课余修读第二专业课程，获得辅修证书",
        "双学位": "需申请，修读时间更长学分更多，获得双学位证书",
        "自学+实践": "不申请任何证书，通过Coursera/B站/项目自学 + 实习积累经验",
        "考研换专业": "本科毕业时考研跨考目标专业",
    },
    "policy_checkpoints": [
        "本校转专业政策（成绩要求、名额限制、申请时间窗口）",
        "目标专业的转入门槛（是否要求特定课程成绩、是否设笔试面试）",
        "课程衔接（补修课程数量、是否影响正常毕业）",
        "学费和学制变化",
    ],
}

# ── 导出更新 ──────────────────────────────────────────────────

__all__ = [
    "SKILL_MATRIX",
    "compute_skill_gaps",
    "find_best_matching_direction",
    "GRADUATE_EXAM_BASELINE",
    "CIVIL_EXAM_BASELINE",
    "MAJOR_TRANSFER_BASELINE",
]
