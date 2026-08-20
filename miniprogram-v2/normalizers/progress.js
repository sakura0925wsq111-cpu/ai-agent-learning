const { todo } = require("./today");

function clampRatio(value) {
  const number = Number(value);
  return Number.isFinite(number) ? Math.min(1, Math.max(0, number)) : 0;
}

function normalizeProgress(raw) {
  raw = raw || {};
  const phases = (raw.phases || []).map((phase, index) => ({
    key: phase.phase_key || `phase_${index + 1}`,
    label: phase.label || `第 ${index + 1} 阶段`,
    total: Number(phase.total || 0),
    completed: Number(phase.completed || 0),
    cancelled: Number(phase.cancelled || 0),
    tasks: (phase.todos || []).map(todo)
  }));
  const ratio = clampRatio(raw.overall_completion);
  const current = raw.current_phase && (raw.current_phase.phase_key || raw.current_phase.key);
  return {
    userId: raw.user_id || "",
    sessionId: raw.growth_session_id || "",
    phases,
    total: Number(raw.total || phases.reduce((sum, item) => sum + item.total, 0)),
    completed: Number(raw.completed || phases.reduce((sum, item) => sum + item.completed, 0)),
    cancelled: Number(raw.cancelled || phases.reduce((sum, item) => sum + item.cancelled, 0)),
    ratio,
    percent: Math.round(ratio * 100),
    currentKey: current || (phases.find((phase) => phase.completed + phase.cancelled < phase.total) || phases[0] || {}).key || ""
  };
}

function normalizeDashboard(raw) {
  raw = raw || {};
  const plan = raw.active_plan || null;
  return {
    userId: raw.user_id || "",
    pageState: raw.page_state || "new",
    reportCount: Number(raw.report_count || 0),
    activeSession: raw.active_session || null,
    latestReport: raw.latest_report || null,
    activePlan: plan ? Object.assign({}, plan, { percent: Math.round(clampRatio(plan.progress) * 100) }) : null,
    coach: raw.coach || { available: false, quick_actions: [] }
  };
}

module.exports = { clampRatio, normalizeProgress, normalizeDashboard };
