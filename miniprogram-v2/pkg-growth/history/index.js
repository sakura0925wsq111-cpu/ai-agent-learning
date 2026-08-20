const growthService = require("../../services/growth-service");
const sessionStore = require("../../stores/session-store");
const { AGENT_LABELS } = require("../../normalizers/report");
const { requireSession } = require("../../utils/page");

Page({
  data: { loading: true, error: "", reports: [], sessions: [], tab: "reports" },
  onLoad() { if (requireSession()) this.load(); },
  back() { wx.navigateBack(); },
  async load() { try { const pair = await Promise.all([growthService.reports(sessionStore.state.userId), growthService.history(sessionStore.state.userId)]); const reports = (pair[0].reports || []).map((item) => Object.assign({}, item, { agentLabel: AGENT_LABELS[item.agent] || "成长", percent: Math.round(Number(item.progress || 0) * 100), dateLabel: item.created_at ? String(item.created_at).slice(0, 10) : "" })); const sessions = (pair[1].sessions || []).map((item) => Object.assign({}, item, { agentLabel: AGENT_LABELS[item.agent] || "成长", dateLabel: item.updated_at ? String(item.updated_at).slice(0, 10) : "" })); this.setData({ loading: false, reports, sessions }); } catch (error) { this.setData({ loading: false, error: error.message || "历史加载失败" }); } },
  tab(event) { this.setData({ tab: event.currentTarget.dataset.tab }); },
  openReport(event) { wx.navigateTo({ url: `/pkg-growth/report/index?sessionId=${event.currentTarget.dataset.id}` }); },
  openSession(event) { const item = event.currentTarget.dataset.item; if (item.finished && item.has_report) this.openReport({ currentTarget: { dataset: { id: item.session_id } } }); else wx.navigateTo({ url: `/pkg-growth/planner-chat/index?sessionId=${item.session_id}&agent=${item.agent}` }); },
  retry() { this.load(); }
});
