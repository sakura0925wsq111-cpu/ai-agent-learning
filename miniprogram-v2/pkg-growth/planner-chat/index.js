const growthService = require("../../services/growth-service");
const sessionStore = require("../../stores/session-store");
const growthStore = require("../../stores/growth-store");
const { AGENT_LABELS } = require("../../normalizers/report");
const { showError, requireSession } = require("../../utils/page");

function qcard(response) {
  const question = response && response.next_question;
  if (!question) return null;
  return { id: question.id, title: question.title, options: question.options || [], required: question.required, index: question.index || response.current_step || 1, total: question.total || response.total_steps || 5 };
}

Page({
  data: { sessionId: "", agent: "career", agentLabel: "就业", messages: [], question: null, input: "", loading: true, error: "", sending: false, stage: "questioning", awaitingAnalysis: false, progress: 0, scrollId: "" },
  onLoad(options) { if (!requireSession()) return; this.setData({ sessionId: options.sessionId || "", agent: options.agent || "career", agentLabel: AGENT_LABELS[options.agent] || "成长" }); this.restore(options.started === "1"); },
  onUnload() { if (this._stream && this._stream.cancel) this._stream.cancel(); },
  back() { wx.navigateBack(); },
  async restore(started) {
    try {
      const sessionId = this.data.sessionId;
      if (!sessionId) throw new Error("缺少规划会话");
      const pair = await Promise.all([growthService.conversation(sessionId), growthService.session(sessionId)]);
      const messages = (pair[0] || []).map((item, index) => ({ id: item.id || `m-${index}`, role: item.role, content: item.content }));
      const state = pair[1] || {};
      if (!messages.length && started) {
        const stored = growthStore.state.planningSession;
        const startResponse = stored && stored.lastResponse;
        if (startResponse && startResponse.message) messages.push({ id: "welcome", role: "assistant", content: startResponse.message });
      }
      const last = messages.length ? messages[messages.length - 1] : null;
      const awaitingAnalysis = state.stage === "analyzing" || state.stage === "awaiting";
      let question = !state.finished && !awaitingAnalysis && last && last.role === "assistant" ? { title: last.content, options: [], index: state.current_step || 1, total: state.total_steps || 5 } : null;
      const cachedStart = growthStore.state.planningSession && growthStore.state.planningSession.lastResponse;
      if (started && cachedStart && qcard(cachedStart)) question = qcard(cachedStart);
      this.setData({ loading: false, messages, stage: state.stage || "questioning", awaitingAnalysis, progress: state.finished ? 100 : Math.round((state.current_step || 0) / (state.total_steps || 5) * 100), question });
      if (state.finished) this.openReportSoon();
    } catch (error) { this.setData({ loading: false, error: error.message || "规划会话恢复失败" }); }
  },
  input(event) { this.setData({ input: event.detail.value }); },
  answer(event) { this.sendValue(event.detail.value); },
  send() { this.sendValue(this.data.input.trim()); },
  async sendValue(value) {
    if (!value || this.data.sending) return;
    const userId = `u-${Date.now()}`, assistantId = `a-${Date.now()}`;
    this.setData({ messages: this.data.messages.concat({ id: userId, role: "user", content: value }, { id: assistantId, role: "assistant", content: "", streaming: true }), input: "", question: null, sending: true, scrollId: assistantId });
    let sawEvent = false, done = null, text = "";
    try {
      this._stream = growthService.chatStream(sessionStore.state.userId, this.data.agent, this.data.sessionId, value, ({ event, data }) => {
        sawEvent = true;
        if (event === "message" && data && data.token) { text += data.token; this.updateAssistant(assistantId, text, true); }
        if (event === "done") { done = data; if (!text && data.message) text = data.message; this.updateAssistant(assistantId, text, true); }
        if (event === "error") throw new Error((data && data.message) || "规划响应失败");
      });
      await this._stream;
      if (!done) throw new Error("流式响应未完成");
      this.updateAssistant(assistantId, done.message || text, false);
      const progress = typeof done.progress === "number" ? Math.round(done.progress) : this.data.progress;
      const awaitingAnalysis = done.stage === "analyzing" || done.stage === "awaiting";
      this.setData({ stage: done.stage || this.data.stage, awaitingAnalysis, progress, question: done.finished || awaitingAnalysis ? null : { title: done.message || text, options: [], index: Math.max(1, Math.round(progress / 20)), total: 5 } });
      if (done.finished || done.report) this.openReportSoon();
    } catch (error) {
      if (!sawEvent) {
        try { const result = await growthService.chat(sessionStore.state.userId, this.data.agent, this.data.sessionId, value); this.updateAssistant(assistantId, result.message || "已收到", false); const awaitingAnalysis = result.stage === "analyzing" || result.stage === "awaiting"; this.setData({ question: awaitingAnalysis ? null : qcard(result), stage: result.stage, awaitingAnalysis, progress: Math.round(result.progress || result.current_step / result.total_steps * 100 || 0) }); if (result.finished || result.report) this.openReportSoon(); }
        catch (fallbackError) { this.removeAssistant(assistantId); showError(fallbackError, "回答发送失败"); }
      } else { this.updateAssistant(assistantId, text || "响应中断。回答已提交，请重新进入会话恢复状态。", false); showError(error, "流式连接中断"); }
    } finally { this.setData({ sending: false }); this._stream = null; }
  },
  updateAssistant(id, content, streaming) { this.setData({ messages: this.data.messages.map((item) => item.id === id ? Object.assign({}, item, { content, streaming }) : item), scrollId: id }); },
  removeAssistant(id) { this.setData({ messages: this.data.messages.filter((item) => item.id !== id) }); },
  async approveAnalysis() {
    if (this.data.sending) return;
    this.setData({ sending: true });
    try {
      const result = await growthService.approve(sessionStore.state.userId, this.data.sessionId);
      const id = `a-${Date.now()}`;
      this.setData({ messages: this.data.messages.concat({ id, role: "assistant", content: result.message || "分析已确认，正在生成完整路线。" }), awaitingAnalysis: false, stage: result.stage || "report", scrollId: id });
      if (result.finished || result.report) this.openReportSoon();
    } catch (error) { showError(error, "分析确认失败"); }
    finally { this.setData({ sending: false }); }
  },
  correctAnalysis() { this.setData({ input: "我想补充修正：", awaitingAnalysis: true }); },
  openReportSoon() { wx.showToast({ title: "行动路线已生成", icon: "success" }); setTimeout(() => wx.redirectTo({ url: `/pkg-growth/report/index?sessionId=${this.data.sessionId}` }), 450); },
  retry() { this.restore(false); }
});
