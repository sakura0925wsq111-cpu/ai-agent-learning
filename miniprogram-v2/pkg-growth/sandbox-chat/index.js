const sandboxService = require("../../services/sandbox-service");
const sessionStore = require("../../stores/session-store");
const growthStore = require("../../stores/growth-store");
const { showError, requireSession } = require("../../utils/page");

const PATH_LABELS = { career: "就业规划", graduate: "考研规划", civil: "考公考编规划", major: "转专业规划" };
function parse(value) { if (value && typeof value === "object") return value; try { return JSON.parse(value); } catch (error) { return value; } }
function labelsFor(paths) { return (paths || []).map((type) => PATH_LABELS[type] || type).join(" · "); }
function questionFrom(response) {
  const cards = response.cards || [];
  if (!response.show_cards || !cards.length) return null;
  return { title: response.message || "请选择更符合你的选项", index: response.discovery_round || 1, total: response.max_discovery_rounds || 7, options: cards.map((item) => item.value || item.name || item.label || item.title || item.type).filter(Boolean) };
}
function restoredMessages(response, fallbackMessage) {
  const state = response.state || {};
  const messages = []; let index = 0;
  const push = (role, content) => {
    const text = String(content || "").trim();
    if (!text) return;
    const previous = messages[messages.length - 1];
    if (previous && previous.role === role && previous.content === text) return;
    messages.push({ id: `restore-${role}-${index++}`, role, content: text });
  };
  (state.discovery_history || []).forEach((item) => { push("assistant", item.response); push("user", item.a); });
  if (state.current_phase === "discovery") push("assistant", state.last_discovery_response);
  const paths = state.path_selections || Object.keys(state.path_probe_history || {});
  paths.forEach((type) => (state.path_probe_history || {})[type] && (state.path_probe_history || {})[type].forEach((item) => { push("assistant", item.q); push("user", item.a); }));
  push("assistant", fallbackMessage);
  return messages.length ? messages : [{ id: "restore-welcome", role: "assistant", content: fallbackMessage || "请继续。" }];
}

Page({
  data: { sessionId: "", phase: "discovery", phaseLabel: "了解你的选择", selectedLabels: "", pathSelectionLocked: false, messages: [], question: null, input: "", sending: false, loading: true, error: "", scrollId: "" },
  onLoad(options) { if (!requireSession()) return; growthStore.restore(); this.setData({ sessionId: options.sessionId || "" }); this.restore(); },
  onUnload() { if (this._stream && this._stream.cancel) this._stream.cancel(); },
  back() { wx.navigateBack(); },
  async restore() {
    const stored = growthStore.state.sandboxSession;
    const cached = stored && stored.sessionId === this.data.sessionId ? stored.lastResponse : null;
    if (cached) {
      try {
        if (stored.state) await sandboxService.resume(sessionStore.state.userId, this.data.sessionId, stored.state);
        this.applyResponse(cached, true); this.setData({ loading: false }); return;
      } catch (error) { /* Fall through to a server-side session lookup. */ }
    }
    try { const result = await sandboxService.chat(sessionStore.state.userId, this.data.sessionId, ""); this.applyResponse(result, true); this.setData({ loading: false }); }
    catch (error) { this.setData({ loading: false, error: error.message || "无法恢复沙盘" }); }
  },
  applyResponse(response, initial) {
    if (!response) return;
    const labels = { discovery: "了解你的选择", path_probe: "逐条验证路径", parallel_sim: "并行推演", projection: "生成对比", completed: "推演完成" };
    const message = response.report_text || response.message || "请继续。";
    const messages = initial ? restoredMessages(response, message) : this.data.messages;
    const selected = response.path_selections || (response.state && response.state.path_selections) || [];
    const pathSelectionLocked = Boolean(response.path_selection_locked || (response.state && response.state.path_selection_locked));
    const stored = { sessionId: this.data.sessionId || response.session_id, state: response.state || null, phase: response.phase, selected, pathSelectionLocked, finished: Boolean(response.finished), lastResponse: response };
    growthStore.set("sandboxSession", stored);
    const phaseLabel = response.phase === "discovery" && selected.length ? "已选路径 · 第一轮" : (labels[response.phase] || "路径探索");
    this.setData({ sessionId: stored.sessionId, phase: response.phase || this.data.phase, phaseLabel, selectedLabels: labelsFor(selected), pathSelectionLocked, messages, question: questionFrom(response), error: "" });
    if (response.finished) {
      wx.showToast({ title: "对比报告已生成", icon: "success" });
      setTimeout(() => wx.redirectTo({ url: `/pkg-growth/sandbox-result/index?sessionId=${stored.sessionId}` }), 350);
    }
  },
  input(event) { this.setData({ input: event.detail.value }); },
  changePaths() {
    if (this.data.sending) return;
    wx.showModal({ title: "修改对比路径", content: "修改后会重新开始一轮路径对比，当前沙盘记录仍会保留在历史中。", success: (result) => { if (result.confirm) { growthStore.clearSandbox(); wx.switchTab({ url: "/pages/explore/index" }); } } });
  },
  answer(event) { this.sendValue(event.detail.value); },
  send() { this.sendValue(this.data.input.trim()); },
  async sendValue(value) {
    if (!value || this.data.sending) return;
    const userMessage = { id: `u-${Date.now()}`, role: "user", content: value };
    const assistantId = `a-${Date.now()}`;
    this.setData({ messages: this.data.messages.concat(userMessage, { id: assistantId, role: "assistant", content: "", streaming: true }), input: "", question: null, sending: true, scrollId: assistantId });
    let sawContent = false; let done = null; let streamed = "";
    const onEvent = ({ event, data }) => {
      const payload = parse(data);
      if (event === "token") { sawContent = true; streamed += typeof payload === "string" ? payload : (payload.token || payload.message || ""); this.updateAssistant(assistantId, streamed, true); }
      if (event === "done") { sawContent = true; done = payload; if (payload && payload.message && !streamed) this.updateAssistant(assistantId, payload.message, true); }
      if (event === "error") this.setData({ error: (payload && payload.message) || "流式响应中断" });
    };
    try {
      this._stream = sandboxService.chatStream(sessionStore.state.userId, this.data.sessionId, value, onEvent);
      await this._stream;
      if (done) { done.session_id = done.session_id || this.data.sessionId; this.updateAssistant(assistantId, done.report_text || done.message || streamed, false); this.applyResponse(done, false); }
      else throw new Error("流式响应未完成");
    } catch (error) {
      if (!sawContent) {
        try { const result = await sandboxService.chat(sessionStore.state.userId, this.data.sessionId, value); this.updateAssistant(assistantId, result.report_text || result.message || "已收到", false); this.applyResponse(result, false); }
        catch (fallbackError) { this.removeAssistant(assistantId); showError(fallbackError, "消息发送失败，请重试"); }
      } else { this.updateAssistant(assistantId, streamed || "响应中断。你的回答已提交，请退出后恢复会话，不要重复发送。", false); showError(error, "流式连接中断"); }
    } finally { this.setData({ sending: false }); this._stream = null; }
  },
  updateAssistant(id, content, streaming) { this.setData({ messages: this.data.messages.map((item) => item.id === id ? Object.assign({}, item, { content, streaming }) : item), scrollId: id }); },
  removeAssistant(id) { this.setData({ messages: this.data.messages.filter((item) => item.id !== id), sending: false }); },
  retry() { this.restore(); }
});
