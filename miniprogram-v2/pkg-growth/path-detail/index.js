const sandboxService = require("../../services/sandbox-service");
const growthService = require("../../services/growth-service");
const sessionStore = require("../../stores/session-store");
const growthStore = require("../../stores/growth-store");
const { normalizeProjection, PATH_META } = require("../../normalizers/projection");
const { showError, requireSession } = require("../../utils/page");

Page({
  data: { sessionId: "", type: "", loading: true, error: "", projection: {}, uncertainty: {}, strengths: [], challenges: [], starting: false },
  onLoad(options) { if (!requireSession()) return; this.setData({ sessionId: options.sessionId || "", type: options.type || "" }); this.load(); },
  back() { wx.navigateBack(); },
  async load() {
    this.setData({ loading: true, error: "" });
    try {
      const result = normalizeProjection(await sandboxService.result(this.data.sessionId, sessionStore.state.userId));
      const projection = result.projections.find((item) => item.type === this.data.type) || result.projections[0] || {};
      const strengths = projection.strengths && projection.strengths.length ? projection.strengths.slice(0, 3) : ["目标方向匹配", "可通过实践验证", "反馈速度较快"];
      const challenges = projection.challenges && projection.challenges.length ? projection.challenges.slice(0, 3) : ["需要持续投入", "仍缺少真实体验"];
      this.setData({ loading: false, projection, type: projection.type, uncertainty: result.uncertainties[0] || { factor: "真实环境适应度仍需验证", howToReduce: "完成一次真实实践或项目协作" }, strengths, challenges });
    } catch (error) { this.setData({ loading: false, error: error.message || "路径详情加载失败" }); }
  },
  async plan() {
    if (this.data.starting) return;
    this.setData({ starting: true });
    try { const response = await growthService.start(sessionStore.state.userId, (PATH_META[this.data.type] || {}).agent || this.data.type, this.data.sessionId); growthStore.set("planningSession", { sessionId: response.session_id, agent: response.agent, sandboxSessionId: this.data.sessionId, lastResponse: response }); wx.redirectTo({ url: `/pkg-growth/planner-chat/index?sessionId=${response.session_id}&agent=${response.agent}&started=1` }); }
    catch (error) { showError(error, "专项规划启动失败"); }
    finally { this.setData({ starting: false }); }
  },
  retry() { this.load(); }
});
