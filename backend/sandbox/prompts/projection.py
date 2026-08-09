# -*- coding: utf-8 -*-
"""Projection Agent Prompt."""

PROJECTION_SYSTEM_PROMPT = """你是中立的对比分析师。呈现各路径优劣、风险、时间线，不替用户做决定。

原则：不给结论给框架、基于数据、诚实呈现风险、考虑时间线、揭示路径关联。

输出JSON含：projections(path_type/path_label/core_insight/time_projection/strengths/challenges/best_for/deal_breakers), comparison_matrix(dimensions/scores 1-10), decision_guide(questions/if_you_value_X_then_Y/hybrid_strategies), key_uncertainties, summary

projections 必须与输入路径一一对应，并原样返回 career、graduate、civil、major 中对应的 path_type。

所有文本用中文。至少3个if_you_value条件。时间推演要具体。
"""

def build_projection_user_prompt(user_profile, path_reports, discovery_context=""):
    import json
    parts = ["## 用户画像"]
    p = {k: v for k, v in user_profile.items() if v}
    parts.append(json.dumps(p, ensure_ascii=False, indent=2) if p else "（有限）")
    if discovery_context:
        parts.append(discovery_context)
    parts.append("## 各路径报告")
    labels = {"career":"就业规划","graduate":"考研规划","civil":"考公考编规划","major":"转专业规划"}
    for pt, report in path_reports.items():
        parts.append("### " + labels.get(pt, pt) + "（" + pt + "）")
        parts.append(json.dumps(report, ensure_ascii=False, indent=2))
    parts.append("基于以上生成多路径对比分析。只输出JSON。")
    return "\n".join(parts)
