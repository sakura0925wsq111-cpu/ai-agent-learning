# -*- coding: utf-8 -*-
'''Question configuration registry.

Import all question sets here. To add a new agent type, simply:
1. Create a new xxx_questions.py file
2. Define XXX_QUESTIONS and XXX_SUPPLEMENTARY lists
3. Register it in the AGENT_QUESTIONS dictionary below
'''

from typing import Any

from .career_questions import CAREER_QUESTIONS, CAREER_SUPPLEMENTARY, AMBIGUOUS_ANSWERS as CAREER_AMBIGUOUS
from .graduate_questions import GRADUATE_QUESTIONS, GRADUATE_SUPPLEMENTARY
from .civil_questions import CIVIL_QUESTIONS, CIVIL_SUPPLEMENTARY
from .major_questions import MAJOR_QUESTIONS, MAJOR_SUPPLEMENTARY

# Agent types -> question configs
AGENT_QUESTIONS: dict[str, dict[str, Any]] = {
    'career': {
        'questions': CAREER_QUESTIONS,
        'supplementary': CAREER_SUPPLEMENTARY,
        'max_supplementary': 2,
    },
    'graduate': {
        'questions': GRADUATE_QUESTIONS,
        'supplementary': GRADUATE_SUPPLEMENTARY,
        'max_supplementary': 2,
    },
    'civil': {
        'questions': CIVIL_QUESTIONS,
        'supplementary': CIVIL_SUPPLEMENTARY,
        'max_supplementary': 2,
    },
    'major': {
        'questions': MAJOR_QUESTIONS,
        'supplementary': MAJOR_SUPPLEMENTARY,
        'max_supplementary': 2,
    },
}

# Universal ambiguous answers
AMBIGUOUS_ANSWERS: frozenset[str] = frozenset({
    '不知道', '都可以', '无所谓', '其他', '不确定', '再看看', '看情况',
})
