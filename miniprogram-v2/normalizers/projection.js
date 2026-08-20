const PATH_META = {
  career: { label: "就业", kicker: "进入真实行业", description: "用项目、实习与岗位验证，判断能力如何转化为职业机会。", agent: "career" },
  graduate: { label: "考研", kicker: "深化专业能力", description: "从目标院校、研究方向与备考投入评估深造路径。", agent: "graduate" },
  civil: { label: "考公", kicker: "公共服务方向", description: "从岗位偏好、考试准备与长期稳定性理解公共部门选择。", agent: "civil" },
  major: { label: "转专业", kicker: "重选学习轨道", description: "结合兴趣、基础与校内规则评估专业调整的收益和成本。", agent: "major" }
};

function normalizePath(raw) {
  const type = raw.type || raw.path_type || "career";
  return Object.assign({ type }, PATH_META[type] || { label: raw.label || type, kicker: "成长方向", description: "通过真实信息继续探索。", agent: type }, raw, {
    label: (PATH_META[type] && PATH_META[type].label) || raw.label || type
  });
}

function textList(value) {
  if (!Array.isArray(value)) return [];
  return value.map((item) => {
    if (typeof item === "string") return item;
    return item.description || item.text || item.title || item.factor || JSON.stringify(item);
  }).filter(Boolean);
}

function normalizeProjection(raw) {
  const root = (raw && (raw.projection_result || (raw.result && raw.result.projection_result))) || raw || {};
  const projections = (root.projections || []).map((item) => {
    const path = normalizePath({ type: item.path_type, label: item.path_label });
    const timeline = item.time_projection || {};
    return Object.assign({}, item, path, {
      coreInsight: item.core_insight || "暂无核心洞察",
      milestones: [
        { key: "short", label: "3 个月", text: timeline.short_term || "尚未生成" },
        { key: "mid", label: "1 年", text: timeline.mid_term || "尚未生成" },
        { key: "long", label: "2–3 年", text: timeline.long_term || "尚未生成" }
      ],
      keyMilestones: textList(timeline.key_milestones),
      strengths: textList(item.strengths),
      challenges: textList(item.challenges)
    });
  });
  const matrix = root.comparison_matrix || null;
  const dimensions = matrix && Array.isArray(matrix.dimensions) ? matrix.dimensions : [];
  const scoreSeries = [];
  if (matrix && matrix.scores && dimensions.length) {
    Object.keys(matrix.scores).forEach((type) => {
      const values = matrix.scores[type];
      if (!Array.isArray(values) || values.length !== dimensions.length) return;
      const valid = values.map(Number);
      if (valid.every((score) => Number.isFinite(score) && score >= 1 && score <= 10)) {
        scoreSeries.push({ type, label: (PATH_META[type] && PATH_META[type].label) || type, values: valid });
      }
    });
  }
  const relations = root.relationship_analysis || {};
  const guide = root.decision_guide || {};
  return {
    summary: root.summary || "路径推演已完成，请结合具体里程碑和风险做出选择。",
    projections,
    radar: { available: dimensions.length > 0 && scoreSeries.length > 0, dimensions, series: scoreSeries, max: 10 },
    relations: {
      exclusive: textList(relations.mutually_exclusive),
      sequential: textList(relations.can_be_sequential),
      complementary: textList(relations.complementary),
      note: relations.note || ""
    },
    questions: textList(guide.questions_to_ask_yourself),
    values: textList(guide.if_you_value_X_then_Y),
    hybrid: textList(guide.possible_hybrid_strategies),
    uncertainties: (root.key_uncertainties || []).map((item) => ({
      factor: item.factor || "待验证因素", impact: item.impact || "", howToReduce: item.how_to_reduce || ""
    }))
  };
}

module.exports = { PATH_META, normalizePath, normalizeProjection };
