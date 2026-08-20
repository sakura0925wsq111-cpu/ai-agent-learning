const sandboxService = require("../../services/sandbox-service");
const growthService = require("../../services/growth-service");
const sessionStore = require("../../stores/session-store");
const growthStore = require("../../stores/growth-store");
const { normalizeProjection, PATH_META } = require("../../normalizers/projection");
const { showError, requireSession } = require("../../utils/page");

Page({
  data: { sessionId: "", loading: true, error: "", result: null, selectedType: "", selectedProjection: null, selectedSeries: null, dimensionRows: [], comparisonRows: [], seriesA: {}, seriesB: {}, primaryUncertainty: {}, decisionQuestion: "", starting: false },
  onLoad(options) { if (!requireSession()) return; this.setData({ sessionId: options.sessionId || "" }); this.load(); },
  back() { wx.navigateBack(); },
  async load() { this.setData({ loading: true, error: "" }); try { const raw = await sandboxService.result(this.data.sessionId, sessionStore.state.userId); const result = normalizeProjection(raw); const selectedType = result.projections[0] ? result.projections[0].type : ""; this.applySelection(result, selectedType); this.setData({ loading: false, result }); const stored = growthStore.state.sandboxSession || {}; growthStore.set("sandboxSession", Object.assign({}, stored, { sessionId: this.data.sessionId, finished: true, lastResponse: raw })); } catch (error) { this.setData({ loading: false, error: error.message || "沙盘结果加载失败" }); } },
  applySelection(result, type) {
    const selectedProjection = (result.projections || []).find((item) => item.type === type) || result.projections[0] || null;
    const selectedSeries = (result.radar.series || []).find((item) => item.type === type) || result.radar.series[0] || null;
    const dimensionRows = selectedSeries ? result.radar.dimensions.map((label, index) => ({ label, value: selectedSeries.values[index], width: selectedSeries.values[index] * 10 })) : [];
    const seriesA = result.radar.series[0] || { label: "路径一", values: [] };
    const seriesB = result.radar.series[1] || { label: "路径二", values: [] };
    const comparisonRows = result.radar.dimensions.map((label, index) => ({ label, valueA: seriesA.values[index] || 0, valueB: seriesB.values[index] || 0, widthA: (seriesA.values[index] || 0) * 10, widthB: (seriesB.values[index] || 0) * 10 }));
    this.setData({ selectedType: type, selectedProjection, selectedSeries, dimensionRows, comparisonRows, seriesA, seriesB, primaryUncertainty: result.uncertainties[0] || {}, decisionQuestion: result.questions[0] || "" });
  },
  choose(event) { this.applySelection(this.data.result, event.currentTarget.dataset.type); },
  detail() { if (this.data.selectedType) wx.navigateTo({ url: `/pkg-growth/path-detail/index?sessionId=${this.data.sessionId}&type=${this.data.selectedType}` }); },
  async plan() { const type = this.data.selectedType; if (!type) { showError(null, "请选择一条最终路径"); return; } this.setData({ starting: true }); try { const response = await growthService.start(sessionStore.state.userId, (PATH_META[type] || {}).agent || type, this.data.sessionId); growthStore.set("planningSession", { sessionId: response.session_id, agent: response.agent, sandboxSessionId: this.data.sessionId, lastResponse: response }); wx.redirectTo({ url: `/pkg-growth/planner-chat/index?sessionId=${response.session_id}&agent=${response.agent}&started=1` }); } catch (error) { showError(error, "专项规划启动失败"); } finally { this.setData({ starting: false }); } },
  retry() { this.load(); }
});
