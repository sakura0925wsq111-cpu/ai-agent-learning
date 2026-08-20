const { cleanText } = require("./text");

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
    if (typeof item === "string") return cleanText(item);
    if (!item || typeof item !== "object") return "";
    return cleanText(item.description || item.text || item.title || item.factor || "");
  }).filter(Boolean);
}

function normalizeComparisonMatrix(rawMatrix, pathTypes) {
  if (!rawMatrix) return { dimensions: [], series: [], available: false, source: "unavailable" };

  const dimensions = [];
  const scoreMap = {};
  const addDimension = (value) => {
    const label = cleanText(value && typeof value === "object" ? value.dimension || value.label || value.name : value);
    if (label && dimensions.indexOf(label) < 0) dimensions.push(label);
    return label;
  };

  // Accept the canonical {dimensions, scores} shape and the row-oriented
  // shape occasionally returned by older/real model responses:
  // [{"dimension":"时间投入","scores":{"career":7,"graduate":9}}].
  if (Array.isArray(rawMatrix)) {
    rawMatrix.forEach((row) => {
      if (!row || typeof row !== "object") return;
      const label = addDimension(row);
      const scores = row.scores || {};
      if (!label || !scores || typeof scores !== "object") return;
      Object.keys(scores).forEach((type) => {
        if (!scoreMap[type]) scoreMap[type] = {};
        scoreMap[type][label] = scores[type];
      });
    });
  } else if (typeof rawMatrix === "object") {
    const rawDimensions = Array.isArray(rawMatrix.dimensions) ? rawMatrix.dimensions : [];
    rawDimensions.forEach(addDimension);
    const rawScores = rawMatrix.scores && typeof rawMatrix.scores === "object" ? rawMatrix.scores : {};
    Object.keys(rawScores).forEach((type) => { scoreMap[type] = rawScores[type]; });
  }

  if (!dimensions.length) return { dimensions: [], series: [], available: false, source: "unavailable" };
  const series = [];
  const types = pathTypes && pathTypes.length ? pathTypes : Object.keys(scoreMap);
  types.forEach((type) => {
    const rawValues = scoreMap[type];
    const values = Array.isArray(rawValues)
      ? rawValues.slice(0, dimensions.length)
      : dimensions.map((label) => rawValues && typeof rawValues === "object" ? rawValues[label] : undefined);
    if (values.length !== dimensions.length) return;
    const normalized = values.map(Number);
    if (!normalized.every((score) => Number.isFinite(score) && score >= 1 && score <= 10)) return;
    series.push({ type, label: (PATH_META[type] && PATH_META[type].label) || type, values: normalized });
  });

  const declaredSource = rawMatrix && typeof rawMatrix === "object"
    ? String(rawMatrix.source || rawMatrix.score_source || "").toLowerCase()
    : "";
  const allFive = series.length > 0 && series.every((item) => item.values.every((value) => value === 5));
  const unavailable = declaredSource === "fallback" || declaredSource === "default" || allFive;
  return {
    dimensions,
    series: unavailable ? [] : series,
    available: !unavailable && series.length >= 2,
    source: unavailable ? "unavailable" : (declaredSource || "llm")
  };
}

function normalizeProjection(raw) {
  const root = (raw && (raw.projection_result || (raw.result && raw.result.projection_result))) || raw || {};
  const projections = (root.projections || []).map((item) => {
    const path = normalizePath({ type: item.path_type, label: item.path_label });
    const timeline = item.time_projection || {};
    return Object.assign({}, item, path, {
      coreInsight: cleanText(item.core_insight || "暂无核心洞察"),
      milestones: [
        { key: "short", label: "3 个月", text: cleanText(timeline.short_term || "尚未生成") },
        { key: "mid", label: "1 年", text: cleanText(timeline.mid_term || "尚未生成") },
        { key: "long", label: "2–3 年", text: cleanText(timeline.long_term || "尚未生成") }
      ],
      keyMilestones: textList(timeline.key_milestones),
      strengths: textList(item.strengths),
      challenges: textList(item.challenges)
    });
  });
  const matrix = normalizeComparisonMatrix(root.comparison_matrix || null, projections.map((item) => item.type));
  const relations = root.relationship_analysis || {};
  const guide = root.decision_guide || {};
  return {
    summary: cleanText(root.summary || "路径推演已完成，请结合具体里程碑和风险做出选择。"),
    projections,
    radar: { available: matrix.available, dimensions: matrix.dimensions, series: matrix.series, max: 10, source: matrix.source },
    relations: {
      exclusive: textList(relations.mutually_exclusive),
      sequential: textList(relations.can_be_sequential),
      complementary: textList(relations.complementary),
      note: cleanText(relations.note || "")
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
