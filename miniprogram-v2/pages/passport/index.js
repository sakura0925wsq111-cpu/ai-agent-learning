const userService = require("../../services/user-service");
const memoryService = require("../../services/memory-service");
const growthService = require("../../services/growth-service");
const sessionStore = require("../../stores/session-store");
const { normalizeDashboard } = require("../../normalizers/progress");
const { AGENT_LABELS } = require("../../normalizers/report");
const { selectTab, showError, requireSession, getHeroTop } = require("../../utils/page");

Page({
  data: { loading: true, error: "", partial: false, user: {}, avatarInitial: "我", memory: { total: 0, max_capacity: 50, type_counts: {} }, memoryStats: { profile: 0, goal: 0, action: 0, fact: 0 }, reports: [], recentReports: [], dashboard: {}, editing: false, submitting: false, heroTop: 86 },
  onLoad() { this.setData({ heroTop: getHeroTop(12) }); },
  onShow() { selectTab(this, 3); if (requireSession()) this.load(); },
  onPullDownRefresh() { this.load().finally(() => wx.stopPullDownRefresh()); },
  async load() {
    this.setData({ loading: !this.data.user, error: "" });
    const uid = sessionStore.state.userId;
    const results = await Promise.all([
      userService.get(uid).then((value) => ({ ok: true, value })).catch((error) => ({ ok: false, error })),
      memoryService.panel(uid).then((value) => ({ ok: true, value })).catch((error) => ({ ok: false, error })),
      growthService.reports(uid).then((value) => ({ ok: true, value })).catch((error) => ({ ok: false, error })),
      growthService.dashboard(uid).then((value) => ({ ok: true, value })).catch((error) => ({ ok: false, error }))
    ]);
    if (!results[0].ok && !this.data.user) { this.setData({ loading: false, error: results[0].error.message || "资料加载失败" }); return; }
    const user = results[0].ok ? results[0].value : this.data.user;
    const memory = results[1].ok ? results[1].value : this.data.memory;
    const reports = results[2].ok ? (results[2].value.reports || []).map((item) => Object.assign({}, item, { agentLabel: AGENT_LABELS[item.agent] || "成长", percent: Math.round(Number(item.progress || 0) * 100) })) : this.data.reports;
    const dashboard = results[3].ok ? normalizeDashboard(results[3].value) : this.data.dashboard;
    sessionStore.updateUser(user);
    const avatarInitial = String(user.nickname || user.name || "我").slice(0, 1);
    const counts = (memory && memory.type_counts) || {};
    this.setData({ loading: false, user, avatarInitial, memory, memoryStats: { profile: Number(counts.profile || 0), goal: Number(counts.goal || 0), action: Number(counts.action || 0), fact: Number(counts.fact || 0) }, reports, recentReports: reports.slice(0, 2), dashboard, partial: results.some((item) => !item.ok) });
  },
  edit() { this.setData({ editing: true }); },
  closeEdit() { this.setData({ editing: false }); },
  async saveProfile(event) { this.setData({ submitting: true }); try { const user = await userService.update(sessionStore.state.userId, event.detail); sessionStore.updateUser(user); this.setData({ user, avatarInitial: String(user.nickname || user.name || "我").slice(0, 1), editing: false }); wx.showToast({ title: "资料已更新", icon: "success" }); } catch (error) { showError(error, "资料保存失败"); } finally { this.setData({ submitting: false }); } },
  memory() { wx.navigateTo({ url: "/pkg-profile/memory/index" }); },
  history() { wx.navigateTo({ url: "/pkg-growth/history/index" }); },
  settings() { wx.navigateTo({ url: "/pages/settings/index" }); },
  openReport(event) { wx.navigateTo({ url: `/pkg-growth/report/index?sessionId=${event.currentTarget.dataset.id}` }); },
  explore() { wx.switchTab({ url: "/pages/explore/index" }); },
  openActionOrExplore() { if (this.data.dashboard && this.data.dashboard.activePlan) wx.switchTab({ url: "/pages/action/index" }); else this.explore(); },
  capability() { wx.navigateTo({ url: "/pkg-profile/capability/index" }); },
  retry() { this.load(); }
});
