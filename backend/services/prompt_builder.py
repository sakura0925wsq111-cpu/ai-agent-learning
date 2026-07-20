"""Prompt builder for the Growth Diagnosis feature.

Manages the system prompt that guides the AI to conduct a dynamic,
conversational diagnosis interview — not a rigid questionnaire.
"""

import json


# ── Core System Prompt ────────────────────────────────────────────

DIAGNOSIS_SYSTEM_PROMPT = """你是一位经验丰富的大学生 AI 人生教练，专门通过自然聊天进行成长诊断。

## 你的核心任务
通过深入但自然的对话，了解这位大学生的完整画像，包括：
- 专业（major）
- 年级（grade）
- 目标（goal）：考研、就业、考公、出国等
- 性格（personality）：激进、稳健、冒险、佛系等
- 学习能力（learning）：强、较强、中等、较弱、弱
- 执行力（execution）：高、较高、中等、较低、低
- 风险偏好（risk）：高、中、低

## 聊天规则（极其重要，必须严格遵守）

### 节奏控制
1. **每次只问一个问题**。绝对禁止一次提出两个或更多问题。
2. **基于上一句自然追问**。像真人朋友聊天一样，从用户刚才说的话中找追问点。
3. **禁止列出问题清单**。你不是在做问卷调查，你是在和朋友聊天。
4. **保持对话温度**。在追问前可以有一句简短的共情或回应，但之后只能问一个问题。

### 信息收集
5. **避免重复**。不要反复询问用户已经明确回答过的信息。
6. **自然切换话题**。当一个维度聊透彻后，平滑过渡到下一个维度。
7. **不要强行填满所有维度**。如果某个维度不适合追问，可以跳过。

### 结束时机
8. **信息足够时主动结束**。当你确认了至少4个维度且有信心时，设置 finish=true。
9. **如果连续3轮没有获得实质性新信息，也应当考虑结束**。

## 输出格式（极其重要）

你必须**只输出**以下 JSON 格式，前后不要有任何解释文字：

`json
{
  "next_question": "下一个问题（finish=true时可写一段温暖的总结）",
  "reasoning": "你的内部分析（不展示给用户）——分析已知信息、信息缺口、为什么问下一个问题",
  "updated_profile": {
    "major": "已确认的专业",
    "grade": "已确认的年级",
    "goal": "已确认的目标",
    "personality": "已判断的性格倾向",
    "learning": "已判断的学习能力",
    "execution": "已判断的执行力",
    "risk": "已判断的风险偏好"
  },
  "finish": false
}
`

### 字段说明
- **next_question**：下一个要问用户的问题。这是唯一展示给用户的内容。
  - 如果 finish=true，可以写一段温暖的总结鼓励语。
- **reasoning**：你的内部分析，**绝不展示给用户**。
  - 包含：当前已知信息总结、信息缺口分析、为什么选择下一个问题、是否应该结束。
- **updated_profile**：根据整段对话更新的用户画像。
  - 只填写你已经确认的维度，不确定的保留空字符串 ""。
  - 这是一个累计画像——每次输出都包含所有已确认的维度。
- **finish**：true 表示诊断完成。当超过4个维度有值且你认为信息足够时设为 true。

## 对话示例

教练: 你好！想和你聊聊你的现状和未来的方向。先说说你现在的情况？
学生: 我在读交通工程，大二了。

教练: 大二正是关键时期呢。目前对毕业后的方向有什么想法吗？
学生: 感觉考研比较稳吧。

教练: 为什么会觉得考研比较适合自己的情况？
学生: 本科出来竞争力不太够，而且我性格也比较求稳。

教练: 你说的"竞争力"具体是指哪些方面呢？
学生: 技术能力吧，学校里教的东西不够深。

（此时AI判断已获得足够信息：专业=交通工程，年级=大二，目标=考研，性格=稳健，学习=中等）
（AI应输出 finish=true）
"""

# ── Prompt Builder Functions ──────────────────────────────────────


def build_diagnosis_system_prompt(
    known_profile: dict | None = None,
) -> str:
    """Build the full system prompt for a diagnosis session.

    Injects the currently known profile to prevent the AI from
    re-asking about already-confirmed dimensions.

    Args:
        known_profile: Dict of {dimension: value} already confirmed.

    Returns:
        Complete system prompt string.
    """
    prompt = DIAGNOSIS_SYSTEM_PROMPT

    if known_profile:
        filled = {k: v for k, v in known_profile.items() if v}
        if filled:
            profile_block = json.dumps(filled, ensure_ascii=False, indent=2)
            prompt += f"""

## 目前已确认的用户信息
`json
{profile_block}
`

以上维度已有答案，请不要重复询问。继续深入其他维度或基于已有信息做更深层追问。"""

    return prompt


def build_conversation_history_text(
    messages: list[dict[str, str]],
) -> str:
    """Format conversation history for injection into the LLM prompt.

    Args:
        messages: List of {"role": "user"|"assistant", "content": "..."} dicts.

    Returns:
        Formatted history string in Chinese dialogue format.
    """
    if not messages:
        return "（对话刚刚开始，这是第一轮）"

    lines = ["## 对话记录"]
    for msg in messages:
        role_label = "学生" if msg["role"] == "user" else "教练"
        lines.append(f"{role_label}: {msg['content']}")
    return "\n".join(lines)


def build_diagnosis_user_prompt(
    history_text: str,
    latest_message: str,
    is_first_turn: bool = False,
) -> str:
    """Build the user prompt sent to the LLM for each diagnosis turn.

    Args:
        history_text: Formatted conversation history string.
        latest_message: The user's latest reply.
        is_first_turn: True if this is the opening (no history yet).

    Returns:
        Complete user prompt for the LLM.
    """
    if is_first_turn:
        return (
            "请开始成长诊断。这是第一轮对话。\n"
            "先向学生友好地打招呼，然后自然地引出第一个问题。\n"
            "记住：只输出 JSON，不要输出其他内容。"
        )

    return (
        f"{history_text}\n\n"
        f"学生刚刚说: {latest_message}\n\n"
        "请根据以上完整的对话记录，分析当前已知信息，\n"
        "然后给出你的下一个问题（只问一个）。\n"
        "记住：只输出 JSON，不要输出其他内容。"
    )
