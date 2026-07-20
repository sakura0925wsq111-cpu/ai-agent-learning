# -*- coding: utf-8 -*-
'''Career (就业) Agent — predefined question flow.

Each question is a card with:
- id: unique identifier
- title: the question text
- options: predefined choices
- allow_custom: whether to show an ''Other'' text input
- required: whether an answer is mandatory (always True for core questions)
'''

from typing import Any

CAREER_QUESTIONS: list[dict[str, Any]] = [
    {
        'id': 'career_goal',
        'title': '毕业后你更倾向？',
        'options': ['就业', '考研', '考公', '创业'],
        'allow_custom': True,
        'required': True,
    },
    {
        'id': 'career_value',
        'title': '你最看重？',
        'options': ['薪资', '成长', '稳定', '兴趣'],
        'allow_custom': True,
        'required': True,
    },
    {
        'id': 'career_style',
        'title': '你更喜欢？',
        'options': ['沟通协作', '独立思考', '数据分析', '创意设计'],
        'allow_custom': True,
        'required': True,
    },
    {
        'id': 'career_strength',
        'title': '你最大的优势？',
        'options': ['学习能力', '沟通能力', '执行能力', '逻辑分析'],
        'allow_custom': True,
        'required': True,
    },
    {
        'id': 'career_city',
        'title': '城市偏好？',
        'options': ['一线', '新一线', '家乡附近', '无所谓'],
        'allow_custom': True,
        'required': True,
    },
]

# Supplementary questions — triggered when user answers ''not sure'' too often
CAREER_SUPPLEMENTARY: list[dict[str, Any]] = [
    {
        'id': 'career_no_go',
        'title': '有没有绝对不想做的工作？',
        'options': ['销售', '工地', '倒班', '都可以接受'],
        'allow_custom': True,
        'required': True,
    },
    {
        'id': 'career_priority_conflict',
        'title': '如果薪资和兴趣冲突，你更倾向？',
        'options': ['选薪资', '选兴趣', '看情况折中'],
        'allow_custom': True,
        'required': True,
    },
]

# Ambiguous answers that signal the user doesn't know
AMBIGUOUS_ANSWERS: frozenset[str] = frozenset({
    '不知道', '都可以', '无所谓', '其他', '不确定', '再看看',
})

MAX_SUPPLEMENTARY: int = 2
