const memoryService = require("../../services/memory-service");
const sessionStore = require("../../stores/session-store");
const { showError, requireSession } = require("../../utils/page");
const LABELS = { all: "全部", profile: "资料", goal: "目标", action: "行动", fact: "事实" };

Page({
  data: { loading: true, error: "", panel: null, memories: [], type: "all", types: Object.keys(LABELS).map((key) => ({ key, label: LABELS[key] })), deleting: null, submitting: false },
  onLoad() { if (requireSession()) this.load(); },
  back() { wx.navigateBack(); },
  async load() { this.setData({ loading: !this.data.panel, error: "" }); try { const panel = await memoryService.panel(sessionStore.state.userId, this.data.type); const memories = (panel.memories || []).map((item) => Object.assign({}, item, { confidenceLabel: `${Math.round(Number(item.confidence || 0) * 100)}%`, sourceLabel: item.source || "来源未记录", typeLabel: LABELS[item.memory_type] || "事实" })); this.setData({ loading: false, panel, memories }); } catch (error) { this.setData({ loading: false, error: error.message || "记忆加载失败" }); } },
  type(event) { this.setData({ type: event.currentTarget.dataset.type }, () => this.load()); },
  edit(event) { const item = event.currentTarget.dataset.item; wx.showModal({ title: `编辑 · ${item.key}`, content: item.value, editable: true, placeholderText: "记忆内容", success: async (result) => { if (!result.confirm || !result.content.trim() || result.content === item.value) return; try { await memoryService.update(sessionStore.state.userId, item.key, result.content.trim(), item.memory_type); wx.showToast({ title: "记忆已更新", icon: "success" }); this.load(); } catch (error) { showError(error, "记忆更新失败"); } } }); },
  askDelete(event) { this.setData({ deleting: event.currentTarget.dataset.item }); },
  closeDelete() { this.setData({ deleting: null }); },
  async remove() { const item = this.data.deleting; if (!item) return; this.setData({ submitting: true }); try { await memoryService.remove(sessionStore.state.userId, item.key); this.closeDelete(); await this.load(); } catch (error) { showError(error, "记忆删除失败"); } finally { this.setData({ submitting: false }); } },
  retry() { this.load(); }
});
