const userService = require("../../services/user-service");
const memoryService = require("../../services/memory-service");
const growthService = require("../../services/growth-service");
const sessionStore = require("../../stores/session-store");
const { normalizeDashboard } = require("../../normalizers/progress");
const { normalizeReport } = require("../../normalizers/report");
const { requireSession } = require("../../utils/page");

Page({
  data: { loading: true, error: "", user: {}, initial: "我", memory: { total: 0, max_capacity: 50 }, counts: { profile: 0, goal: 0, action: 0, fact: 0 }, dashboard: {}, report: null, reportDate: "近期", strengths: [], risks: [], nextAction: "继续完成当前阶段任务", nextMeta: "来自行动计划" },
  onLoad() { if (requireSession()) this.load(); },
  back() { wx.navigateBack(); },
  async load() {
    this.setData({ loading: true, error: "" });
    try {
      const uid = sessionStore.state.userId;
      const [user, memory, dashboardRaw] = await Promise.all([userService.get(uid), memoryService.panel(uid), growthService.dashboard(uid)]);
      const dashboard = normalizeDashboard(dashboardRaw);
      let report = null;
      if (dashboard.latestReport && dashboard.latestReport.session_id) report = normalizeReport(await growthService.report(dashboard.latestReport.session_id));
      const counts = memory.type_counts || {};
      const strengths = report && report.strengths && report.strengths.length ? report.strengths.slice(0, 2) : ["表达清晰", "用户观察细致"];
      const risks = report && report.risks && report.risks.length ? report.risks.slice(0, 2) : ["缺少真实岗位体验", "数据分析证据不足"];
      const created = (report && report.createdAt) ? String(report.createdAt).slice(0, 10) : "近期";
      this.setData({ loading: false, user, initial: String(user.nickname || user.name || "我").slice(0, 1), memory, counts: { profile: Number(counts.profile || 0), goal: Number(counts.goal || 0), action: Number(counts.action || 0), fact: Number(counts.fact || 0) }, dashboard, report, reportDate: created, strengths, risks, nextAction: (dashboard.activePlan && dashboard.activePlan.next_action) || "继续完成当前阶段任务", nextMeta: dashboard.activePlan ? `${dashboard.activePlan.phase_label || "当前阶段"} · 来自行动计划` : "先完成一次路径探索" });
    } catch (error) { this.setData({ loading: false, error: error.message || "能力画像加载失败" }); }
  },
  openReport() { if (this.data.report) wx.navigateTo({ url: `/pkg-growth/report/index?sessionId=${this.data.report.sessionId}` }); },
  action() { if (this.data.dashboard.activePlan) wx.switchTab({ url: "/pages/action/index" }); else wx.switchTab({ url: "/pages/explore/index" }); },
  edit() { wx.switchTab({ url: "/pages/passport/index" }); },
  memory() { wx.navigateTo({ url: "/pkg-profile/memory/index" }); },
  retry() { this.load(); }
});
