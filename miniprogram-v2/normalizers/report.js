const { cleanText } = require("./text");
const { formatDate } = require("../utils/date");

const AGENT_LABELS = { career: "就业", employment: "就业", graduate: "考研", civil: "考公", major: "转专业" };

function task(item, index) {
  if (typeof item === "string") return { key: `task-${index}`, title: cleanText(item), deadline: "", deadlineLabel: "尚未安排日期", done: false };
  item = item || {};
  const deadline = cleanText(item.deadline || item.due_date || item.date || "");
  return {
    key: item.id || item.key || `task-${index}`,
    title: cleanText(item.title || item.task || item.description || item.action || "待补充任务"),
    deadline,
    deadlineLabel: deadline ? formatDate(deadline, false) : "尚未安排日期",
    done: item.status === "done" || item.status === "archived"
  };
}

function normalizeInsight(item) {
  if (typeof item === "string") return cleanText(item);
  item = item || {};
  return item.point && item.detail
    ? cleanText(`${item.point}：${item.detail}`)
    : cleanText(item.point || item.detail || "");
}

function normalizeInsightList(items) {
  return Array.isArray(items) ? items.map(normalizeInsight).filter(Boolean) : [];
}

function normalizeReport(raw) {
  const wrapper = raw || {};
  const report = wrapper.report || wrapper;
  let actionPlan = report.action_plan || report.plan || report.phases || [];
  if (!Array.isArray(actionPlan) && actionPlan && typeof actionPlan === "object") {
    actionPlan = Object.keys(actionPlan).map((key) => Object.assign({ phase_key: key }, actionPlan[key]));
  }
  const phases = (actionPlan || []).map((phase, index) => {
    phase = typeof phase === "string" ? { title: phase } : (phase || {});
    const tasks = phase.tasks || phase.actions || phase.items || [];
    return {
      key: phase.phase_key || phase.key || `phase_${index + 1}`,
      index: index + 1,
      label: cleanText(phase.phase || phase.label || phase.period || `第 ${index + 1} 阶段`),
      title: cleanText(phase.title || phase.goal || phase.objective || `阶段 ${index + 1}`),
      description: cleanText(phase.description || phase.focus || ""),
      tasks: (Array.isArray(tasks) ? tasks : []).map(task)
    };
  });
  const agent = wrapper.agent || report.agent || report.agent_type || "career";
  return {
    sessionId: wrapper.session_id || report.session_id || "",
    agent,
    agentLabel: AGENT_LABELS[agent] || "成长",
    title: report.title || `${AGENT_LABELS[agent] || "成长"}行动路线`,
    summary: cleanText(report.summary || report.current_status || report.overview || "报告已生成"),
    goal: cleanText(report.goal || report.target || ""),
    strengths: normalizeInsightList(report.strengths || report.advantages),
    risks: normalizeInsightList(report.risks || report.challenges),
    phases,
    createdAt: wrapper.created_at || report.created_at || ""
  };
}

module.exports = { AGENT_LABELS, normalizeInsight, normalizeReport };
