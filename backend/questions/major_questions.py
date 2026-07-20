# -*- coding: utf-8 -*-
'''Major change (转专业) Agent — predefined question flow.'''

from typing import Any

MAJOR_QUESTIONS: list[dict[str, Any]] = [
    {
        'id': 'major_reason',
        'title': '为什么想转专业？',
        'options': ['不感兴趣', '就业前景差', '学不会', '发现更喜欢的'],
        'allow_custom': True,
        'required': True,
    },
    {
        'id': 'major_target',
        'title': '想转到什么方向？',
        'options': ['计算机/软件', '金融/经管', '医学', '法学'],
        'allow_custom': True,
        'required': True,
    },
    {
        'id': 'major_understanding',
        'title': '对新专业的了解程度？',
        'options': ['很了解', '一般了解', '只是听说不错', '完全不了解'],
        'allow_custom': True,
        'required': True,
    },
    {
        'id': 'major_risk',
        'title': '如果转专业失败？',
        'options': ['继续尝试', '接受现状', '辅修/双学位', '退学重考'],
        'allow_custom': True,
        'required': True,
    },
    {
        'id': 'major_support',
        'title': '家人/学校是否支持？',
        'options': ['全力支持', '不反对', '不太支持', '强烈反对'],
        'allow_custom': True,
        'required': True,
    },
]

MAJOR_SUPPLEMENTARY: list[dict[str, Any]] = [
    {
        'id': 'major_transfer_feasibility',
        'title': '你们学校转专业政策怎么样？',
        'options': ['比较容易', '有难度但可行', '基本不可能', '不了解'],
        'allow_custom': True,
        'required': True,
    },
    {
        'id': 'major_backup',
        'title': '如果转不了，你打算怎么办？',
        'options': ['自学喜欢的', '考研跨考', '找相关实习', '接受现状'],
        'allow_custom': True,
        'required': True,
    },
]

AMBIGUOUS_ANSWERS: frozenset[str] = frozenset({
    '不知道', '都可以', '无所谓', '其他', '不确定', '再看看',
})

MAX_SUPPLEMENTARY: int = 2
