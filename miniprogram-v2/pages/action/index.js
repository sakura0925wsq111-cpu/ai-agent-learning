const growthService = require("../../services/growth-service");
const todayService = require("../../services/today-service");
const todoService = require("../../services/todo-service");
const sessionStore = require("../../stores/session-store");
const growthStore = require("../../stores/growth-store");
const { normalizeDashboard, normalizeProgress } = require("../../normalizers/progress");
const { normalizeReport } = require("../../normalizers/report");
const { todo } = require("../../normalizers/today");
const { selectTab, showError, requireSession, getHeroTop } = require("../../utils/page");

Page({
  data: { loading: true, error: "", dashboard: null, progress: null, report: null, currentPhase: null, weekCount: 0, weekBars: [], selectedPhase: null, syncedKeys: [], nextTask: null, confirmTask: null, submitting: false, heroTop: 86 },
  onLoad() { this.setData({ heroTop: getHeroTop(12) }); },
  onShow() { selectTab(this, 2); if (requireSession()) this.load(); },
  onPullDownRefresh() { this.load(true).finally(() => wx.stopPullDownRefresh()); },
  async load() {
    this.setData({ loading: !this.data.dashboard, error: "" });
    try {
      const dashboard = normalizeDashboard(await growthService.dashboard(sessionStore.state.userId));
      growthStore.set("dashboard", dashboard);
      if (!dashboard.activePlan) { this.setData({ loading: false, dashboard, progress: null, report: null, currentPhase: null }); return; }
      const sessionId = dashboard.activePlan.session_id;
      const pair = await Promise.all([todayService.progress(sessionStore.state.userId, sessionId), growthService.report(sessionId)]);
      const progress = normalizeProgress(pair[0]);
      const report = normalizeReport(pair[1]);
      const progressMap = {};
      progress.phases.forEach((phase) => { progressMap[phase.key] = phase; });
      const phases = report.phases.map((phase) => Object.assign({}, phase, progressMap[phase.key] || {}));
      report.phases = phases;
      let currentPhase = phases.find((phase) => phase.key === progress.currentKey) || phases[0] || null;
      if (currentPhase && progressMap[currentPhase.key]) currentPhase.tasks = progressMap[currentPhase.key].tasks;
      const weekCount = this.countWeek(progress.phases);
      const weekBars = this.makeWeekBars(progress.phases);
      const nextTask = progress.phases.reduce((all, phase) => all.concat(phase.tasks || []), []).find((task) => !task.done && !task.cancelled) || null;
      this.setData({ loading: false, dashboard, progress, report, currentPhase, selectedPhase: currentPhase, syncedKeys: progress.phases.map((phase) => phase.key), weekCount, weekBars, nextTask });
      growthStore.set("progress", progress); growthStore.set("report", report);
    } catch (error) { this.setData({ loading: false, error: error.message || "执行状态加载失败" }); }
  },
  countWeek(phases) {
    const start = new Date(); const end = new Date(start); end.setDate(end.getDate() + 6);
    return (phases || []).reduce((all, phase) => all.concat(phase.tasks || []), []).filter((task) => { if (!task.deadline) return false; const date = new Date(task.deadline); return date >= start && date <= end; }).length;
  },
  makeWeekBars(phases) {
    const tasks = (phases || []).reduce((all, phase) => all.concat(phase.tasks || []), []);
    const start = new Date(); start.setHours(0, 0, 0, 0);
    const rows = Array.from({ length: 7 }, (_, index) => {
      const date = new Date(start); date.setDate(start.getDate() + index);
      const end = new Date(date); end.setDate(date.getDate() + 1);
      const dayTasks = tasks.filter((task) => { if (!task.deadline) return false; const due = new Date(task.deadline); return due >= date && due < end; });
      return { key: date.toISOString().slice(0, 10), dateLabel: `${date.getMonth() + 1}/${date.getDate()}`, label: ["日", "一", "二", "三", "四", "五", "六"][date.getDay()], total: dayTasks.length, completed: dayTasks.filter((task) => task.done).length };
    });
    const max = Math.max(1, ...rows.map((item) => item.total));
    return rows.map((item) => Object.assign({}, item, { totalHeight: item.total ? Math.max(16, Math.round(item.total / max * 100)) : 5, doneHeight: item.total ? Math.round(item.completed / item.total * 100) : 0 }));
  },
  selectPhase(event) {
    const chosen = event.detail; const fromProgress = this.data.progress.phases.find((phase) => phase.key === chosen.key);
    this.setData({ selectedPhase: Object.assign({}, chosen, fromProgress || {}, { tasks: fromProgress ? fromProgress.tasks : chosen.tasks }) });
  },
  async toggleTask(event) {
    const task = event.detail; const progress = JSON.parse(JSON.stringify(this.data.progress));
    const optimistic = JSON.parse(JSON.stringify(progress));
    optimistic.phases.forEach((phase) => { phase.tasks = phase.tasks.map((item) => item.id === task.id ? Object.assign({}, item, { done: !item.done, status: item.done ? "pending" : "done" }) : item); });
    const selected = optimistic.phases.find((phase) => phase.key === this.data.selectedPhase.key);
    this.setData({ progress: optimistic, selectedPhase: Object.assign({}, this.data.selectedPhase, { tasks: selected.tasks }) });
    try { await todoService.toggle(sessionStore.state.userId, task.id); await this.load(); }
    catch (error) { const previous = progress.phases.find((phase) => phase.key === this.data.selectedPhase.key); this.setData({ progress, selectedPhase: Object.assign({}, this.data.selectedPhase, { tasks: previous.tasks }) }); showError(error, "任务状态更新失败，已恢复"); }
  },
  askRemove(event) { this.setData({ confirmTask: event.detail }); },
  closeConfirm() { this.setData({ confirmTask: null }); },
  async confirmRemove() { const task = this.data.confirmTask; if (!task) return; this.setData({ submitting: true }); try { await todoService.remove(sessionStore.state.userId, task.id); this.closeConfirm(); await this.load(); } catch (error) { showError(error, "取消执行失败"); } finally { this.setData({ submitting: false }); } },
  explore() { wx.switchTab({ url: "/pages/explore/index" }); },
  report() { if (this.data.dashboard.activePlan) wx.navigateTo({ url: `/pkg-growth/report/index?sessionId=${this.data.dashboard.activePlan.session_id}` }); },
  coach() { const coach = this.data.dashboard.coach || {}; if (coach.session_id) wx.navigateTo({ url: `/pkg-growth/coach/index?sessionId=${coach.session_id}&agent=${coach.agent}` }); },
  retry() { this.load(); }
});
