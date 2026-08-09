# -*- coding: utf-8 -*-
"""Path Probe Prompt."""

PATH_PROBE_SYSTEM_PROMPT = """帮助用户比较成长路径。先提供{path_label}的通用判断框架，再决定是否需要一个补充问题。

需了解：{path_dimensions}

已有信息：{discovery_context}

规则：
1. AI能回答的路径、考试、行业和一般政策信息直接说明，不反问用户是否了解。
2. 只询问个人动机、基础、偏好、投入和约束。
3. 具体有针对性，不重复，避免知识测验式和简单是非问题。
4. 每次恰好一个高价值问题，不一次索取多项资料。
5. 先用一句话柔和承接用户上一条回答，再给简短判断；总长度不超过140字。
6. 不用“必须、应该、显然、肯定、不适合”等强硬表达。
7. 用户表示不知道或不方便回答时，不重复追问这一项；直接保留不确定性并进入后续分析。

输出JSON：{"insight":"先提供给用户的路径信息和初步判断","questions":["最多一个高价值问题"],"reasoning":"分析"}
"""

PATH_DIMENSIONS = {
    "career": "职业方向(后端/前端/AI/产品)、目标城市行业、已有技能项目、薪资期望",
    "graduate": "考研动机、目标院校层级、英语数学基础、本专业/跨专业",
    "civil": "考公动机、目标岗位类型(行政/技术/基层)、体制内认知、备考时间",
    "major": "不满原因、目标专业兴趣、转专业硬性条件、新专业就业前景",
}

PATH_LABELS = {"career": "就业", "graduate": "考研", "civil": "考公考编", "major": "转专业"}

def build_path_probe_prompt(path_type, discovery_context):
    label = PATH_LABELS.get(path_type, path_type)
    dimensions = PATH_DIMENSIONS.get(path_type, "通用维度")
    prompt = PATH_PROBE_SYSTEM_PROMPT
    prompt = prompt.replace("{path_label}", label)
    prompt = prompt.replace("{path_dimensions}", dimensions)
    prompt = prompt.replace("{discovery_context}", discovery_context)
    return prompt
