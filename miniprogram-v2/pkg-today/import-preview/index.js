const todayService = require("../../services/today-service");
const { showError, requireSession } = require("../../utils/page");

function present(item, type, index) {
  if (type === "course") { const slot = (item.schedule || [])[0] || {}; return Object.assign({}, item, { index, checked: true, title: item.name || "未命名课程", meta: `周${["", "一", "二", "三", "四", "五", "六", "日"][slot.weekday] || "?"} · 第 ${slot.start || "?"}-${slot.end || "?"} 节 · ${item.location || "地点待确认"}` }); }
  return Object.assign({}, item, { index, checked: true, title: item.subject || "未命名考试", meta: `${item.exam_date || "日期待确认"} ${item.start_time || ""} · ${item.location || "地点待确认"}` });
}

Page({
  data: { importId: "", from: "", loading: true, error: "", type: "course", items: [], selectedCount: 0, confirming: false },
  onLoad(options) { if (!requireSession()) return; this.setData({ importId: options.importId || "", from: options.from || "" }); this.load(); },
  back() { wx.navigateBack(); },
  async load() { try { const result = await todayService.preview(this.data.importId); const items = (result.items || []).map((item, index) => present(item, result.import_type, index)); this.setData({ loading: false, type: result.import_type, items, selectedCount: items.length }); } catch (error) { this.setData({ loading: false, error: error.message || "预览加载失败" }); } },
  toggle(event) { const index = Number(event.currentTarget.dataset.index); const items = this.data.items.map((item) => item.index === index ? Object.assign({}, item, { checked: !item.checked }) : item); this.setData({ items, selectedCount: items.filter((item) => item.checked).length }); },
  all() { const check = this.data.selectedCount !== this.data.items.length; const items = this.data.items.map((item) => Object.assign({}, item, { checked: check })); this.setData({ items, selectedCount: check ? items.length : 0 }); },
  async confirm() { if (!this.data.selectedCount) { showError(null, "请至少选择一项"); return; } this.setData({ confirming: true }); try { const selected = this.data.items.filter((item) => item.checked).map((item) => item.index); const result = await todayService.confirmImport(this.data.importId, selected); wx.showToast({ title: `已导入 ${result.saved_count} 项`, icon: "success" }); if (this.data.from === "onboarding") setTimeout(() => wx.navigateBack({ delta: 2 }), 500); else setTimeout(() => wx.switchTab({ url: "/pages/today/index" }), 500); } catch (error) { showError(error, "确认导入失败"); } finally { this.setData({ confirming: false }); } },
  retry() { this.load(); }
});
