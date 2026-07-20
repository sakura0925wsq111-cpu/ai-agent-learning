# -*- coding: utf-8 -*-
'''Civil service (考公) Agent — predefined question flow.'''

from typing import Any

CIVIL_QUESTIONS: list[dict[str, Any]] = [
    {
        'id': 'civil_motivation',
        'title': '为什么想考公？',
        'options': ['稳定', '家庭期望', '不想去企业卷', '对公共服务感兴趣'],
        'allow_custom': True,
        'required': True,
    },
    {
        'id': 'civil_level',
        'title': '目标岗位级别？',
        'options': ['国考', '省考', '市考/区考', '事业单位'],
        'allow_custom': True,
        'required': True,
    },
    {
        'id': 'civil_competition',
        'title': '你对竞争激烈的态度？',
        'options': ['专挑热门岗', '选竞争适中的', '求稳选冷门岗', '都可以'],
        'allow_custom': True,
        'required': True,
    },
    {
        'id': 'civil_preparation',
        'title': '你觉得行测和申论哪个更难？',
        'options': ['行测', '申论', '都难', '都不难'],
        'allow_custom': True,
        'required': True,
    },
    {
        'id': 'civil_plan_b',
        'title': '如果没考上？',
        'options': ['继续考', '找企业工作', '考研', '看情况'],
        'allow_custom': True,
        'required': True,
    },
]

CIVIL_SUPPLEMENTARY: list[dict[str, Any]] = [
    {
        'id': 'civil_study_style',
        'title': '你更喜欢怎么备考？',
        'options': ['报班跟课', '自学刷题', '找学习搭子', '看网课'],
        'allow_custom': True,
        'required': True,
    },
    {
        'id': 'civil_mobility',
        'title': '愿意去外地工作吗？',
        'options': ['只考虑本地', '省内可以', '全国各地都行', '无所谓'],
        'allow_custom': True,
        'required': True,
    },
]

AMBIGUOUS_ANSWERS: frozenset[str] = frozenset({
    '不知道', '都可以', '无所谓', '其他', '不确定', '再看看',
    '看情况',
})

MAX_SUPPLEMENTARY: int = 2
