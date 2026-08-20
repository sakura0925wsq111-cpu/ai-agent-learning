const growthService = require("../../services/growth-service");
const todoService = require("../../services/todo-service");
const sessionStore = require("../../stores/session-store");
const { AGENT_LABELS } = require("../../normalizers/report");
const { showError, requireSession, getHeroTop } = require("../../utils/page");

Page({
  data: { sessionId: "", agent: "career", agentLabel: "成长", messages: [], input: "", loading: true, error: "", sending: false, scrollId: "", quick: ["汇报进展", "遇到困难", "复盘本周"], suggestedTask: "", confirmTask: false, submitting: false, heroTop: 86 },
  onLoad(options) { if (!requireSession()) return; const agent = options.agent || "career"; this.setData({ sessionId: options.sessionId || "", agent, agentLabel: AGENT_LABELS[agent] || "成长", heroTop: getHeroTop(12) }); this.load(); },
  onUnload() { if (this._stream && this._stream.cancel) this._stream.cancel(); },
  back() { wx.navigateBack(); },
  async load() { try { const conversation = await growthService.conversation(this.data.sessionId); const messages = (conversation || []).filter((item) => item.stage === "qa").map((item, index) => ({ id: item.id || `m-${index}`, role: item.role, content: item.content })); if (!messages.length) messages.push({ id: "welcome", role: "assistant", content: "我会结合你的规划报告、真实任务进度和已保存记忆来回答。你今天想先聊什么？" }); this.setData({ loading: false, messages }); } catch (error) { this.setData({ loading: false, error: error.message || "教练会话加载失败" }); } },
  input(event) { this.setData({ input: event.detail.value }); },
  quick(event) { this.sendValue(event.currentTarget.dataset.value); },
  send() { this.sendValue(this.data.input.trim()); },
  async sendValue(value) {
    if (!value || this.data.sending) return;
    const assistantId = `a-${Date.now()}`;
    this.setData({ messages: this.data.messages.concat({ id: `u-${Date.now()}`, role: "user", content: value }, { id: assistantId, role: "assistant", content: "", streaming: true }), input: "", sending: true, scrollId: assistantId, suggestedTask: "" });
    let sawEvent = false, done = null, text = "";
    try {
      this._stream = growthService.qaStream(sessionStore.state.userId, this.data.agent, this.data.sessionId, value, ({ event, data }) => {
        sawEvent = true;
        if (event === "message" && data && data.token) { text += data.token; this.updateAssistant(assistantId, text, true); }
        if (event === "done") { done = data; if (!text && data.message) text = data.message; }
      });
      await this._stream;
      if (!done) throw new Error("教练响应未完成");
      this.updateAssistant(assistantId, done.message || text, false); this.makeSuggestion(done.message || text);
    } catch (error) {
      if (!sawEvent) { try { const result = await growthService.qa(sessionStore.state.userId, this.data.agent, this.data.sessionId, value); this.updateAssistant(assistantId, result.message, false); this.makeSuggestion(result.message); } catch (fallbackError) { this.setData({ messages: this.data.messages.filter((item) => item.id !== assistantId) }); showError(fallbackError, "教练暂时无法回答"); } }
      else { this.updateAssistant(assistantId, text || "响应中断。问题已提交，请稍后重新进入查看，避免重复发送。", false); showError(error, "流式连接中断"); }
    } finally { this.setData({ sending: false }); this._stream = null; }
  },
  updateAssistant(id, content, streaming) { this.setData({ messages: this.data.messages.map((item) => item.id === id ? Object.assign({}, item, { content, streaming }) : item), scrollId: id }); },
  makeSuggestion(text) { const parts = String(text || "").split(/[。！？\n]/).map((item) => item.trim()).filter(Boolean); const suggestedTask = parts.length ? parts[parts.length - 1].slice(0, 120) : ""; this.setData({ suggestedTask }); },
  askCreate() { this.setData({ confirmTask: true }); },
  dismissSuggestion() { this.setData({ suggestedTask: "" }); },
  closeConfirm() { this.setData({ confirmTask: false }); },
  async createTask() { if (!this.data.suggestedTask) return; this.setData({ submitting: true }); try { await todoService.create(sessionStore.state.userId, { title: this.data.suggestedTask, source: "ai_coach" }); this.setData({ confirmTask: false, suggestedTask: "" }); wx.showToast({ title: "已加入待办", icon: "success" }); } catch (error) { showError(error, "待办创建失败"); } finally { this.setData({ submitting: false }); } },
  retry() { this.load(); }
});
