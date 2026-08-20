const sessionStore = require("../../stores/session-store");
const uiStore = require("../../stores/ui-store");
const userService = require("../../services/user-service");
const { showError, requireSession } = require("../../utils/page");

Page({
  data: { city: "北京", apiBase: "", reduceMotion: false, suggestionEnabled: true, confirm: "", submitting: false },
  onLoad() { if (!requireSession()) return; this.setData({ city: uiStore.state.city, apiBase: wx.getStorageSync("ICAMPUS_V2_API_BASE_URL") || "", reduceMotion: uiStore.state.reduceMotion, suggestionEnabled: uiStore.state.suggestionEnabled }); },
  back() { wx.navigateBack(); },
  input(event) { this.setData({ [event.currentTarget.dataset.key]: event.detail.value }); },
  toggle(event) { const key = event.currentTarget.dataset.key; this.setData({ [key]: event.detail.value }); uiStore.setPreference(key, event.detail.value); },
  saveCity() { uiStore.setCity(this.data.city); wx.showToast({ title: "城市已保存", icon: "success" }); },
  saveApi() { const value = String(this.data.apiBase || "").trim().replace(/\/$/, ""); if (value) wx.setStorageSync("ICAMPUS_V2_API_BASE_URL", value); else wx.removeStorageSync("ICAMPUS_V2_API_BASE_URL"); getApp().globalData.baseUrl = value || require("../../config/env").getApiBaseUrl(); wx.showToast({ title: "调试地址已更新", icon: "success" }); },
  agreement() { wx.navigateTo({ url: "/pages/agreement/index" }); },
  askLogout() { this.setData({ confirm: "logout" }); },
  askDelete() { this.setData({ confirm: "delete" }); },
  closeConfirm() { this.setData({ confirm: "" }); },
  async confirmAction() {
    if (this.data.confirm === "logout") { sessionStore.clear(); wx.reLaunch({ url: "/pages/auth/login/index" }); return; }
    if (this.data.confirm === "delete") {
      this.setData({ submitting: true });
      try { await userService.remove(sessionStore.state.userId); sessionStore.clear(); wx.reLaunch({ url: "/pages/auth/login/index" }); }
      catch (error) { showError(error, "账户删除失败"); }
      finally { this.setData({ submitting: false, confirm: "" }); }
    }
  }
});
