const growthService = require("../../services/growth-service");
const todayService = require("../../services/today-service");
const sessionStore = require("../../stores/session-store");
const growthStore = require("../../stores/growth-store");
const { normalizeReport } = require("../../normalizers/report");
const { normalizeProgress } = require("../../normalizers/progress");
const { showError, requireSession } = require("../../utils/page");
const { formatTime } = require("../../utils/date");

Page({
  data: { sessionId: "", loading: true, error: "", report: {}, progress: {}, selectedPhase: {}, syncVisible: false, syncing: false, syncedKeys: [], createdLabel: "近期", reportStrength: "报告尚未给出明确优势", reportRisk: "报告尚未给出需要留意项", refreshedLabel: "" },
  onLoad(options) { if (!requireSession()) return; this.setData({ sessionId: options.sessionId || "" }); this.load(); },
  back() { wx.navigateBack(); },
  async load() { this.setData({ loading: true, error: "" }); try { const pair = await Promise.all([growthService.report(this.data.sessionId), todayService.progress(sessionStore.state.userId, this.data.sessionId)]); const report = normalizeReport(pair[0]); const progress = normalizeProgress(pair[1]); const syncedKeys = progress.phases.map((item) => item.key); report.phases = report.phases.map((phase) => Object.assign({}, phase, { synced: syncedKeys.indexOf(phase.key) >= 0 })); this.setData({ loading: false, report, progress, syncedKeys, selectedPhase: report.phases[0] || {}, createdLabel: report.createdAt ? String(report.createdAt).slice(0, 10) : "近期", reportStrength: (report.strengths && report.strengths[0]) || "报告尚未给出明确优势", reportRisk: (report.risks && report.risks[0]) || "报告尚未给出需要留意项", refreshedLabel: formatTime(new Date()) }); growthStore.set("report", report); growthStore.set("progress", progress); } catch (error) { this.setData({ loading: false, error: error.message || "报告加载失败" }); } },
  selectPhase(event) { this.setData({ selectedPhase: event.detail }); },
  openSync(event) { const phase = event.currentTarget.dataset.phase || this.data.selectedPhase; if (phase) this.setData({ selectedPhase: phase, syncVisible: true }); },
  closeSync() { this.setData({ syncVisible: false }); },
  async sync(event) { this.setData({ syncing: true }); try { const result = await todayService.syncPlan({ user_id: sessionStore.state.userId, growth_session_id: this.data.sessionId, phase: event.detail.phase, start_date: event.detail.start_date }); this.setData({ syncVisible: false }); wx.showToast({ title: result.already_synced ? "该阶段已加入" : `已加入 ${result.synced_count} 项`, icon: "success" }); await this.load(); } catch (error) { showError(error, "加入行动失败"); } finally { this.setData({ syncing: false }); } },
  action() { wx.switchTab({ url: "/pages/action/index" }); },
  coach() { wx.navigateTo({ url: `/pkg-growth/coach/index?sessionId=${this.data.sessionId}&agent=${this.data.report.agent}` }); },
  retry() { this.load(); }
});
