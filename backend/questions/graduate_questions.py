# -*- coding: utf-8 -*-
'''Graduate school (考研) Agent — predefined question flow.'''

from typing import Any

GRADUATE_QUESTIONS: list[dict[str, Any]] = [
    {
        'id': 'grad_motivation',
        'title': '为什么想考研？',
        'options': ['提升竞争力', '逃避就业', '喜欢学术', '家里期望'],
        'allow_custom': True,
        'required': True,
    },
    {
        'id': 'grad_target',
        'title': '目标院校？',
        'options': ['211/985名校', '本校', '普通一本', '有书读就行'],
        'allow_custom': True,
        'required': True,
    },
    {
        'id': 'grad_discipline',
        'title': '想考什么方向？',
        'options': ['本专业深造', '跨考热门专业', '跨考兴趣专业', '不确定'],
        'allow_custom': True,
        'required': True,
    },
    {
        'id': 'grad_preparation',
        'title': '你觉得自己的准备状态？',
        'options': ['已经规划好了', '大概有方向', '才刚刚开始', '完全没头绪'],
        'allow_custom': True,
        'required': True,
    },
    {
        'id': 'grad_plan_b',
        'title': '如果考研失利？',
        'options': ['二战', '直接就业', '出国', '考公'],
        'allow_custom': True,
        'required': True,
    },
]

GRADUATE_SUPPLEMENTARY: list[dict[str, Any]] = [
    {
        'id': 'grad_time_commit',
        'title': '每天大概能投入多少时间备考？',
        'options': ['2小时以下', '2-4小时', '4-6小时', '6小时以上'],
        'allow_custom': True,
        'required': True,
    },
    {
        'id': 'grad_confidence',
        'title': '对考研的信心程度？',
        'options': ['很有信心', '一般', '不太自信', '很焦虑'],
        'allow_custom': True,
        'required': True,
    },
]

AMBIGUOUS_ANSWERS: frozenset[str] = frozenset({
    '不知道', '都可以', '无所谓', '其他', '不确定', '再看看',
    '不确定', '有书读就行',
})

MAX_SUPPLEMENTARY: int = 2
