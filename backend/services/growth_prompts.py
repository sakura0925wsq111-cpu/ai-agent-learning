# -*- coding: utf-8 -*-
'''Growth Agent — analysis prompts for the single LLM call.

The LLM is called ONLY ONCE, after all 5-7 questions are answered.
It receives the complete answers and generates the full report.
'''

import json
from typing import Any


# ── Analysis System Prompt ─────────────────────────────────────

ANALYSIS_SYSTEM_PROMPT = '''你是一位经验丰富的大学生 AI 人生教练。

## 你的任务
根据用户在5-7个卡片式问题中的全部回答，生成一份完整的成长分析报告。

## 输出格式
你必须**只输出**以下 JSON 格式，前后不要有任何解释文字：

`json
{
  "profile": {
    "personality": "用户的性格特点总结（20字以内）",
    "learning_style": "用户的学习或工作风格（15字以内）",
    "strengths": ["优势1", "优势2", "优势3"],
    "weaknesses": ["劣势1", "劣势2"],
    "career_direction": "推荐的核心方向（15字以内）",
    "risk_tolerance": "低 / 中 / 高"
  },
  "strengths_analysis": "一段200字以内的优势深度分析",
  "risk_analysis": {
    "description": "一段150字以内的风险分析",
    "level": "低 / 中 / 高"
  },
  "career_directions": [
    {"name": "就业", "score": 4, "reason": "推荐理由（30字以内）"},
    {"name": "考研", "score": 3, "reason": "推荐理由（30字以内）"},
    {"name": "考公", "score": 2, "reason": "推荐理由（30字以内）"},
    {"name": "创业", "score": 1, "reason": "推荐理由（30字以内）"}
  ],
  "thirty_day_plan": [
    {"day_range": "Day 1-7", "task": "具体任务", "goal": "本周目标"},
    {"day_range": "Day 8-14", "task": "具体任务", "goal": "本周目标"},
    {"day_range": "Day 15-21", "task": "具体任务", "goal": "本周目标"},
    {"day_range": "Day 22-30", "task": "具体任务", "goal": "本周目标"}
  ]
}
`

## 评分规则
- career_directions 中 4 个方向的 score 范围 1-5 星
- 根据用户回答，给最匹配的方向最高分
- strengths 列出 2-3 条，weaknesses 列出 1-2 条
- 30天计划分4周，每周一个具体可执行的任务

## 注意事项
- 不要输出 JSON 以外的任何文字
- 所有分析必须基于用户的实际回答，不要编造
- 保持鼓励和支持的语气
'''


def build_analysis_prompt(agent_type: str) -> str:
    '''Build the system prompt for the final analysis.

    Args:
        agent_type: 'career', 'graduate', 'civil', or 'major'.

    Returns:
        Complete system prompt string.
    '''
    agent_labels = {
        'career': '就业',
        'graduate': '考研',
        'civil': '考公',
        'major': '转专业',
    }
    label = agent_labels.get(agent_type, agent_type)

    prompt = ANALYSIS_SYSTEM_PROMPT
    prompt += f'\n\n## 当前场景\n用户正在使用「{label}」成长 Agent。请围绕这个场景进行分析和建议。'
    return prompt


def build_analysis_user_prompt(
    answers: list[dict[str, Any]],
    agent_type: str,
) -> str:
    '''Build the user prompt containing all answers for the LLM.

    Args:
        answers: List of {'question_id': str, 'answer': str} dicts.
        agent_type: The agent type.

    Returns:
        Complete user prompt for the LLM.
    '''
    agent_labels = {
        'career': '就业方向',
        'graduate': '考研方向',
        'civil': '考公方向',
        'major': '转专业方向',
    }
    label = agent_labels.get(agent_type, agent_type)

    # Format answers nicely
    answers_text = '\n'.join(
        f'{i+1}. Q: {a["question_id"]}\n   A: {a["answer"]}'
        for i, a in enumerate(answers)
    )

    return f'''请根据以下用户在「{label}」评估中的全部回答，生成完整的成长分析报告。

## 用户回答
{answers_text}

## 要求
请严格按照系统提示中的 JSON 格式输出，不要有任何额外文字。
记得：profile.strengths 列2-3条，profile.weaknesses 列1-2条。
所有分析必须基于用户的实际回答。
'''
