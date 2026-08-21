const growthService = require("../../services/growth-service");
const todayService = require("../../services/today-service");
const todoService = require("../../services/todo-service");
const sessionStore = require("../../stores/session-store");
const growthStore = require("../../stores/growth-store");
const { normalizeDashboard, normalizeProgress } = require("../../normalizers/progress");
const { normalizeReport } = require("../../normalizers/report");
const { todo } = require("../../normalizers/today");
const { selectTab, setTabBarHidden, showError, requireSession, getHeroTop } = require("../../utils/page");
const { formatTime } = require("../../utils/date");

function mergePhaseTasks(phase, livePhase) {
  const reportTasks = phase.tasks || [];
  const liveTasks = livePhase && livePhase.tasks ? livePhase.tasks : [];
  const byIndex = {};
  liveTasks.forEach((item) => {
    if (item.planTaskIndex >= 0) byIndex[item.planTaskIndex] = item;
  });
  return reportTasks.map((task, index) => {
    const live = byIndex[index] || liveTasks.find((item) => item.title === task.title);
    const key = live && (live.id || live.key) || task.key || `${phase.key}-${index}`;
    if (!live) return Object.assign({}, task, { key, id: task.id || key, source: "ai_plan", sourceLabel: "成长计划", done: false, cancelled: false });
    return Object.assign({}, task, {
      key,
      id: live.id || key,
      planTaskId: live.planTaskId,
      planTaskIndex: live.planTaskIndex,
      source: live.source || "ai_plan",
      sourceLabel: live.sourceLabel || "成长计划",
      status: live.status,
      done: live.done,
      cancelled: live.cancelled,
      deadline: live.deadline || task.deadline,
      deadlineLabel: live.deadline ? live.deadlineLabel : task.deadlineLabel
    });
  });
}

function buildPhases(report, progress) {
  const progressMap = {};
  (progress.phases || []).forEach((phase) => { progressMap[phase.key] = phase; });
  return (report.phases || []).map((phase) => {
    const live = progressMap[phase.key];
    const synced = Boolean(live);
    const tasks = mergePhaseTasks(phase, live);
    const total = synced ? live.total : tasks.length;
    const completed = synced ? live.completed : 0;
    const cancelled = synced ? live.cancelled : 0;
    const status = !synced ? "unsynced" : (completed + cancelled >= total && total > 0 ? "completed" : "in_progress");
    return Object.assign({}, phase, {
      synced,
      status,
      total,
      completed,
      cancelled,
      tasks
    });
  });
}

Page({
  data: { loading: true, error: "", dashboard: null, progress: null, report: null, currentPhase: null, weekCount: 0, weekBars: [], selectedPhase: null, syncedKeys: [], nextTask: null, confirmTask: null, syncVisible: false, syncing: false, submitting: false, heroTop: 86, refreshedLabel: "" },
  onLoad() { this.setData({ heroTop: getHeroTop(12) }); },
  onShow() { selectTab(this, 2); if (requireSession()) this.load(); },
  onHide() { setTabBarHidden(this, false); },
  onPullDownRefresh() { this.load(this.data.selectedPhase && this.data.selectedPhase.key).finally(() => wx.stopPullDownRefresh()); },
  async load(preferredPhaseKey) {
    this.setData({ loading: !this.data.dashboard, error: "" });
    try {
      const dashboard = normalizeDashboard(await growthService.dashboard(sessionStore.state.userId));
      growthStore.set("dashboard", dashboard);
      if (!dashboard.activePlan) { this.setData({ loading: false, dashboard, progress: null, report: null, currentPhase: null }); return; }
      const sessionId = dashboard.activePlan.session_id;
      const pair = await Promise.all([todayService.progress(sessionStore.state.userId, sessionId), growthService.report(sessionId)]);
      const progress = normalizeProgress(pair[0]);
      const report = normalizeReport(pair[1]);
      const phases = buildPhases(report, progress);
      report.phases = phases;
      const currentPhase = phases.find((phase) => phase.key === progress.currentKey) || phases.find((phase) => phase.synced) || phases[0] || null;
      const selectedPhase = phases.find((phase) => phase.key === preferredPhaseKey) || currentPhase;
      const weekCount = this.countWeek(progress.phases);
      const weekBars = this.makeWeekBars(progress.phases);
      const nextTask = (selectedPhase && selectedPhase.tasks || []).find((task) => !task.done && !task.cancelled) || null;
      this.setData({ loading: false, dashboard, progress, report, currentPhase, selectedPhase, syncedKeys: progress.phases.map((phase) => phase.key), weekCount, weekBars, nextTask, refreshedLabel: formatTime(new Date()) });
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
    const chosen = event.detail || {};
    const selectedPhase = (this.data.report.phases || []).find((phase) => phase.key === chosen.key) || chosen;
    const nextTask = (selectedPhase.tasks || []).find((task) => !task.done && !task.cancelled) || null;
    this.setData({ selectedPhase, nextTask });
  },
  openSync() {
    if (this.data.selectedPhase && !this.data.selectedPhase.synced) {
      this.setData({ syncVisible: true }, () => setTabBarHidden(this, true));
    }
  },
  closeSync() {
    this.setData({ syncVisible: false }, () => setTabBarHidden(this, false));
  },
  async sync(event) {
    const phaseKey = event.detail && event.detail.phase;
    if (!phaseKey || !this.data.selectedPhase) return;
    this.setData({ syncing: true });
    try {
      const result = await todayService.syncPlan({
        user_id: sessionStore.state.userId,
        growth_session_id: this.data.dashboard.activePlan.session_id,
        phase: phaseKey,
        start_date: event.detail.start_date
      });
      this.setData({ syncVisible: false }, () => setTabBarHidden(this, false));
      wx.showToast({ title: result.already_synced ? "该阶段已加入" : `已加入 ${result.synced_count} 项`, icon: "success" });
      await this.load(phaseKey);
    } catch (error) {
      showError(error, "加入行动失败");
    } finally {
      this.setData({ syncing: false });
    }
  },
  async toggleTask(event) {
    const task = event.detail;
    if (!this.data.selectedPhase || !this.data.selectedPhase.synced) return;
    const progress = JSON.parse(JSON.stringify(this.data.progress));
    const optimistic = JSON.parse(JSON.stringify(progress));
    optimistic.phases.forEach((phase) => { phase.tasks = phase.tasks.map((item) => item.id === task.id ? Object.assign({}, item, { done: !item.done, status: item.done ? "pending" : "done" }) : item); });
    const selected = optimistic.phases.find((phase) => phase.key === this.data.selectedPhase.key);
    this.setData({ progress: optimistic, selectedPhase: Object.assign({}, this.data.selectedPhase, { tasks: selected.tasks }) });
    try { await todoService.toggle(sessionStore.state.userId, task.id); await this.load(this.data.selectedPhase.key); }
    catch (error) { const previous = progress.phases.find((phase) => phase.key === this.data.selectedPhase.key); this.setData({ progress, selectedPhase: Object.assign({}, this.data.selectedPhase, { tasks: previous.tasks }) }); showError(error, "任务状态更新失败，已恢复"); }
  },
  askRemove(event) { if (this.data.selectedPhase && this.data.selectedPhase.synced) this.setData({ confirmTask: event.detail }, () => setTabBarHidden(this, true)); },
  closeConfirm() { this.setData({ confirmTask: null }, () => setTabBarHidden(this, false)); },
  async confirmRemove() { const task = this.data.confirmTask; if (!task) return; const phaseKey = this.data.selectedPhase && this.data.selectedPhase.key; this.setData({ submitting: true }); try { await todoService.remove(sessionStore.state.userId, task.id); this.closeConfirm(); await this.load(phaseKey); } catch (error) { showError(error, "取消执行失败"); } finally { this.setData({ submitting: false }); } },
  explore() { wx.switchTab({ url: "/pages/explore/index" }); },
  report() { if (this.data.dashboard.activePlan) wx.navigateTo({ url: `/pkg-growth/report/index?sessionId=${this.data.dashboard.activePlan.session_id}` }); },
  coach() { const coach = this.data.dashboard.coach || {}; if (coach.session_id) wx.navigateTo({ url: `/pkg-growth/coach/index?sessionId=${coach.session_id}&agent=${coach.agent}` }); },
  retry() { this.load(); }
});
