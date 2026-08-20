const sandboxService = require("../../services/sandbox-service");
const growthService = require("../../services/growth-service");
const sessionStore = require("../../stores/session-store");
const growthStore = require("../../stores/growth-store");
const { normalizePath, PATH_META } = require("../../normalizers/projection");
const { normalizeDashboard } = require("../../normalizers/progress");
const { selectTab, showError, requireSession, getHeroTop } = require("../../utils/page");

Page({
  data: { loading: true, error: "", dashboard: null, displayState: "selecting", paths: [], selected: [], selectedLabels: "", starting: false, sandboxSession: null, heroTop: 86 },
  onLoad() { this.setData({ heroTop: getHeroTop(12) }); },
  onShow() { selectTab(this, 1); if (requireSession()) this.load(); },
  onPullDownRefresh() { this.load(true).finally(() => wx.stopPullDownRefresh()); },
  async load() {
    growthStore.restore();
    this.setData({ loading: !this.data.dashboard, error: "" });
    try {
      const results = await Promise.all([growthService.dashboard(sessionStore.state.userId), sandboxService.paths()]);
      const dashboard = normalizeDashboard(results[0]);
      const paths = ((results[1] && results[1].paths) || Object.keys(PATH_META).map((type) => ({ type }))).map((raw) => {
        const path = normalizePath(raw);
        const meta = PATH_META[path.type];
        return Object.assign({}, path, { label: meta ? meta.label : path.label });
      });
      const sandboxSession = growthStore.state.sandboxSession;
      const selected = this.data.selected.length ? this.data.selected : ["career", "graduate"].filter((type) => paths.some((item) => item.type === type));
      this.setData({ loading: false, dashboard, paths, sandboxSession, displayState: "selecting", selected, selectedLabels: this.labels(paths, selected) });
      growthStore.set("dashboard", dashboard);
    } catch (error) { this.setData({ loading: false, error: error.message || "探索页加载失败" }); }
  },
  togglePath(event) {
    const type = event.detail.type; const selected = this.data.selected.slice(); const index = selected.indexOf(type);
    if (index >= 0) selected.splice(index, 1);
    else if (selected.length < 3) selected.push(type);
    else showError(null, "最多比较三条路径");
    this.setData({ selected, selectedLabels: this.labels(this.data.paths, selected) });
  },
  labels(paths, selected) { return (selected || []).map((type) => { const item = (paths || []).find((path) => path.type === type); return (PATH_META[type] && PATH_META[type].label) || (item && item.label) || type; }).join("、"); },
  beginSelection() { this.setData({ displayState: "selecting" }); },
  cancelSelection() { this.setData({ displayState: this.data.dashboard.pageState, selected: [] }); },
  async startSandbox() {
    if (this.data.selected.length < 2) { showError(null, "请至少选择两条路径"); return; }
    if (this.data.starting) return;
    this.setData({ starting: true });
    try {
      const result = await sandboxService.start(sessionStore.state.userId, this.data.selected);
      const stored = { sessionId: result.session_id, state: result.state || null, phase: result.phase, selected: this.data.selected, finished: result.finished, lastResponse: result };
      growthStore.set("sandboxSession", stored);
      wx.navigateTo({ url: `/pkg-growth/sandbox-chat/index?sessionId=${result.session_id}` });
    } catch (error) { showError(error, "无法开始路径探索"); }
    finally { this.setData({ starting: false }); }
  },
  resumeSandbox() { const session = this.data.sandboxSession; if (session) wx.navigateTo({ url: `/pkg-growth/sandbox-chat/index?sessionId=${session.sessionId}` }); },
  resumePlanning() { const active = this.data.dashboard.activeSession; if (active) wx.navigateTo({ url: `/pkg-growth/planner-chat/index?sessionId=${active.session_id}&agent=${active.agent}` }); },
  openReport() { const report = this.data.dashboard.latestReport; if (report) wx.navigateTo({ url: `/pkg-growth/report/index?sessionId=${report.session_id}` }); },
  openAction() { wx.switchTab({ url: "/pages/action/index" }); },
  history() { wx.navigateTo({ url: "/pkg-growth/history/index" }); },
  retry() { this.load(true); }
});
