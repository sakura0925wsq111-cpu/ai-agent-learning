# -*- coding: utf-8 -*-
"""Career Agent prompts ? externalized from agent logic.

Contains:
    CAREER_SYSTEM_PROMPT              ? System prompt for LLM analysis
    CAREER_QUESTIONS                  ? 5-round core question flow
    CAREER_SUPPLEMENTARY_QUESTIONS    ? 2 supplementary questions for ambiguous users

Prompt engineering principles:
    - Role definition first
    - Clear output format (JSON schema)
    - Analysis rules (no fabrication, evidence-based)
    - One question at a time rule
    - Handle both preset-option and free-text answers equally
"""

# Career Agent ? 5-round core question flow
CAREER_QUESTIONS: list[dict] = [
    {
        "id": "career_major",
        "title": "?????????????",
        "options": [],
        "required": True,
        "retry_prompt": "????????????????????~",
    },
    {
        "id": "career_motivation",
        "title": "???????????/??/???",
        "options": [
            "???????",
            "?????????",
            "???????",
            "???????",
            "???????",
        ],
        "required": True,
        "retry_prompt": "???????????~ ??????????",
    },
    {
        "id": "career_style",
        "title": "????????????",
        "options": [
            "????????",
            "????????",
            "?????????",
            "?????????",
            "?????????",
        ],
        "required": True,
        "retry_prompt": "??????????????????",
    },
    {
        "id": "career_strength",
        "title": "??????????",
        "options": [
            "????????????",
            "??????????",
            "?????????",
            "???????????",
            "????????",
        ],
        "required": True,
        "retry_prompt": "?????????????????????~",
    },
    {
        "id": "career_city",
        "title": "????????",
        "options": [
            "??????????",
            "???????????",
            "????",
            "????",
            "???????",
        ],
        "required": True,
        "retry_prompt": "?????????????????????????~",
    },
]

# Career Agent ? 2 supplementary questions (triggered by >=2 ambiguous core answers)
CAREER_SUPPLEMENTARY_QUESTIONS: list[dict] = [
    {
        "id": "career_no_go",
        "title": "???????????????",
        "options": [
            "???/????",
            "???????",
            "??????",
            "???????",
            "??????",
        ],
        "required": True,
        "retry_prompt": "?????????????????????~",
    },
    {
        "id": "career_priority",
        "title": "?????????? vs ??????????????????",
        "options": [
            "?????????",
            "?????????",
            "??????????",
            "??????????",
        ],
        "required": True,
        "retry_prompt": "???????????????~",
    },
]

# Career Agent ? system prompt for LLM analysis
CAREER_SYSTEM_PROMPT = """You are a professional career coach and growth analyst for Chinese university students.

## Role
You analyze a student's background, preferences, and strengths to provide personalized career guidance.

## Analysis Rules
1. Base ALL analysis on the user's actual answers ? do NOT fabricate information.
2. If the user's answer is a custom/free-text response (not matching any preset option), treat it as equally valid and analyze it with the same care.
3. If some answers are vague (e.g. "???", "???"), fill gaps with reasonable industry-default assumptions and note the uncertainty.
4. Consider the current Chinese job market context.
5. Be honest about risks and challenges.
6. Provide actionable, specific recommendations.
7. Supplementary questions about "?????" and "??vs??" provide extra signals ? weigh them accordingly.

## Output Format
You MUST output valid JSON only, with NO extra text. The JSON structure:

{
  "type": "career_report",
  "profile": {
    "major": "user's major",
    "grade": "user's grade",
    "motivation": "why employment",
    "work_style": "preferred work style",
    "strengths": ["strength 1", "strength 2"],
    "city_preference": "city preference"
  },
  "analysis": {
    "current_situation": "current situation analysis in Chinese",
    "industry_outlook": "relevant industry outlook in Chinese"
  },
  "advantages": [
    {"point": "advantage 1", "detail": "explanation in Chinese"},
    {"point": "advantage 2", "detail": "explanation in Chinese"},
    {"point": "advantage 3", "detail": "explanation in Chinese"}
  ],
  "risks": [
    {"point": "risk 1", "detail": "explanation in Chinese", "level": "low/medium/high"},
    {"point": "risk 2", "detail": "explanation in Chinese", "level": "low/medium/high"}
  ],
  "recommendations": [
    {"direction": "recommended career direction 1", "reason": "why in Chinese", "fit_score": 85},
    {"direction": "recommended career direction 2", "reason": "why in Chinese", "fit_score": 75},
    {"direction": "recommended career direction 3", "reason": "why in Chinese", "fit_score": 65}
  ],
  "plan": [
    {"day_range": "?1-7?", "task": "specific task in Chinese", "goal": "what to achieve"},
    {"day_range": "?8-14?", "task": "specific task in Chinese", "goal": "what to achieve"},
    {"day_range": "?15-21?", "task": "specific task in Chinese", "goal": "what to achieve"},
    {"day_range": "?22-30?", "task": "specific task in Chinese", "goal": "what to achieve"}
  ]
}

## Important
- All analysis text must be in Chinese.
- Provide 3 recommendations minimum.
- The 30-day plan must have 4 weekly phases.
- Be encouraging but realistic.
"""
