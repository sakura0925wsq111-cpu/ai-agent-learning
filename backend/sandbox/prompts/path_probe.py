# -*- coding: utf-8 -*-
"""Path Probe Prompt — path-specific follow-up questions for the DecisionSandbox.

After the discovery phase has built a general user profile, this module
generates 1-2 targeted questions per selected path to fill gaps that the
planning agent may need for its analysis.
"""

PATH_PROBE_SYSTEM_PROMPT = """你是一位跨领域的成长顾问，正在帮助用户比较不同的成长路径。

## 你的任务
用户已经完成了一轮通用画像评估。现在你需要为目标路径 {path_label} 提出 1-2 个补充问题，
收集该路径特有的信息，以便后续的规划分析更加精准。

## 路径专属信息维度
{path_dimensions}

## 已有信息
{discovery_context}

## 规则
1. 问题要具体、有针对性，弥补通用画像中对该路径的盲区
2. 避免重复询问用户已经回答过的信息
3. 每个问题要有区分度：如果第一个问了"为什么选这条路径"，第二个就问"这条路你最担心什么"
4. 问题要开放，避免"是/否"类封闭式问题
5. 如果用户对该路径完全不了解（比如只是"听说过"），第一个问题可以温和地问"你了解这条路吗？"

## 输出格式
你必须**只输出**以下 JSON 格式，前后不要有任何解释文字：

`json
{
  "questions": [
    "第一个补充问题...",
    "第二个补充问题..."
  ],
  "reasoning": "为什么需要这两个问题（不展示给用户）"
}
`

如果只有一个问题就够了，questions 数组可以只包含一个元素。
"""

# ── Path dimension mappings ─────────────────────────────────────

PATH_DIMENSIONS: dict[str, str] = {
    "career": (
        "- 职业方向偏好（后端/前端/AI/产品等）\n"
        "- 目标城市和行业\n"
        "- 已有的技能和项目经验\n"
        "- 对薪资和工作强度的期望"
    ),
    "graduate": (
        "- 考研动机（学历提升/逃避就业/学术兴趣）\n"
        "- 目标院校层级期望\n"
        "- 英语和数学基础\n"
        "- 本专业深造还是跨专业"
    ),
    "civil": (
        "- 考公考编动机（稳定/家庭期望/价值观）\n"
        "- 目标岗位类型（行政/技术/基层）\n"
        "- 体制内工作的了解和预期\n"
        "- 备考时间预估"
    ),
    "major": (
        "- 对现有专业的不满原因\n"
        "- 目标专业的兴趣来源\n"
        "- 转专业的硬性条件了解程度\n"
        "- 对新专业的就业前景认知"
    ),
}

PATH_LABELS: dict[str, str] = {
    "career": "就业",
    "graduate": "考研",
    "civil": "考公考编",
    "major": "转专业",
}


def build_path_probe_prompt(
    path_type: str,
    discovery_context: str,
) -> str:
    """Build the path probe system prompt for a specific path.

    Args:
        path_type: One of 'career', 'graduate', 'civil', 'major'.
        discovery_context: Formatted discovery history string.

    Returns:
        Complete system prompt string.
    """
    label = PATH_LABELS.get(path_type, path_type)
    dimensions = PATH_DIMENSIONS.get(path_type, "通用维度")

    return PATH_PROBE_SYSTEM_PROMPT.format(
        path_label=label,
        path_dimensions=dimensions,
        discovery_context=discovery_context,
    )
