# -*- coding: utf-8 -*-
"""Path Probe Prompt."""

PATH_PROBE_SYSTEM_PROMPT = """帮助用户比较成长路径。为{path_label}提1-2个补充问题。

需了解：{path_dimensions}

已有信息：{discovery_context}

规则：具体有针对性，不重复，避免是非问题。

输出JSON：{"questions":["Q1","Q2"],"reasoning":"分析"}
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
