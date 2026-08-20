const sandboxService = require("../../services/sandbox-service");
const sessionStore = require("../../stores/session-store");
const growthStore = require("../../stores/growth-store");
const { showError, requireSession } = require("../../utils/page");

function parse(value) { if (value && typeof value === "object") return value; try { return JSON.parse(value); } catch (error) { return value; } }
function questionFrom(response) {
  const cards = response.cards || [];
  if (!response.show_cards || !cards.length) return null;
  return { title: response.message || "请选择更符合你的选项", index: response.discovery_round || 1, total: response.max_discovery_rounds || 7, options: cards.map((item) => item.value || item.type || item.label || item.title).filter(Boolean) };
}

Page({
  data: { sessionId: "", phase: "discovery", phaseLabel: "了解你的选择", messages: [], question: null, input: "", sending: false, loading: true, error: "", scrollId: "" },
  onLoad(options) { if (!requireSession()) return; growthStore.restore(); this.setData({ sessionId: options.sessionId || "" }); this.restore(); },
  onUnload() { if (this._stream && this._stream.cancel) this._stream.cancel(); },
  back() { wx.navigateBack(); },
  async restore() {
    const stored = growthStore.state.sandboxSession;
    const cached = stored && stored.sessionId === this.data.sessionId ? stored.lastResponse : null;
    if (cached) { this.applyResponse(cached, true); this.setData({ loading: false }); return; }
    try { const result = await sandboxService.chat(sessionStore.state.userId, this.data.sessionId, ""); this.applyResponse(result, true); this.setData({ loading: false }); }
    catch (error) { this.setData({ loading: false, error: error.message || "无法恢复沙盘" }); }
  },
  applyResponse(response, initial) {
    if (!response) return;
    const labels = { discovery: "了解你的选择", path_probe: "逐条验证路径", parallel_sim: "并行推演", projection: "生成对比", completed: "推演完成" };
    const message = response.report_text || response.message || "请继续。";
    const messages = initial ? [{ id: `a-${Date.now()}`, role: "assistant", content: message }] : this.data.messages;
    const stored = { sessionId: this.data.sessionId || response.session_id, state: response.state || null, phase: response.phase, selected: response.path_selections || [], finished: Boolean(response.finished), lastResponse: response };
    growthStore.set("sandboxSession", stored);
    this.setData({ sessionId: stored.sessionId, phase: response.phase || this.data.phase, phaseLabel: labels[response.phase] || "路径探索", messages, question: questionFrom(response), error: "" });
    if (response.finished) {
      wx.showToast({ title: "对比报告已生成", icon: "success" });
      setTimeout(() => wx.redirectTo({ url: `/pkg-growth/sandbox-result/index?sessionId=${stored.sessionId}` }), 350);
    }
  },
  input(event) { this.setData({ input: event.detail.value }); },
  answer(event) { this.sendValue(event.detail.value); },
  send() { this.sendValue(this.data.input.trim()); },
  async sendValue(value) {
    if (!value || this.data.sending) return;
    const userMessage = { id: `u-${Date.now()}`, role: "user", content: value };
    const assistantId = `a-${Date.now()}`;
    this.setData({ messages: this.data.messages.concat(userMessage, { id: assistantId, role: "assistant", content: "", streaming: true }), input: "", question: null, sending: true, scrollId: assistantId });
    let sawEvent = false; let done = null; let streamed = "";
    const onEvent = ({ event, data }) => {
      sawEvent = true; const payload = parse(data);
      if (event === "token") { streamed += typeof payload === "string" ? payload : (payload.token || payload.message || ""); this.updateAssistant(assistantId, streamed, true); }
      if (event === "done") { done = payload; if (payload && payload.message && !streamed) this.updateAssistant(assistantId, payload.message, true); }
      if (event === "error") this.setData({ error: (payload && payload.message) || "流式响应中断" });
    };
    try {
      this._stream = sandboxService.chatStream(sessionStore.state.userId, this.data.sessionId, value, onEvent);
      await this._stream;
      if (done) { done.session_id = done.session_id || this.data.sessionId; this.updateAssistant(assistantId, done.report_text || done.message || streamed, false); this.applyResponse(done, false); }
      else throw new Error("流式响应未完成");
    } catch (error) {
      if (!sawEvent) {
        try { const result = await sandboxService.chat(sessionStore.state.userId, this.data.sessionId, value); this.updateAssistant(assistantId, result.report_text || result.message || "已收到", false); this.applyResponse(result, false); }
        catch (fallbackError) { this.removeAssistant(assistantId); showError(fallbackError, "消息发送失败，请重试"); }
      } else { this.updateAssistant(assistantId, streamed || "响应中断。你的回答已提交，请退出后恢复会话，不要重复发送。", false); showError(error, "流式连接中断"); }
    } finally { this.setData({ sending: false }); this._stream = null; }
  },
  updateAssistant(id, content, streaming) { this.setData({ messages: this.data.messages.map((item) => item.id === id ? Object.assign({}, item, { content, streaming }) : item), scrollId: id }); },
  removeAssistant(id) { this.setData({ messages: this.data.messages.filter((item) => item.id !== id), sending: false }); },
  retry() { this.restore(); }
});
