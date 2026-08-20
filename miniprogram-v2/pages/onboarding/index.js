const sessionStore = require("../../stores/session-store");
const userService = require("../../services/user-service");
const sandboxService = require("../../services/sandbox-service");
const growthStore = require("../../stores/growth-store");
const { normalizePath, PATH_META } = require("../../normalizers/projection");
const { showError } = require("../../utils/page");

Page({
  data: { step: 1, form: {}, paths: Object.keys(PATH_META).map((type) => normalizePath({ type })), selected: [], submitting: false },
  onLoad() { const user = sessionStore.state.user || {}; this.setData({ form: { nickname: user.nickname || user.name || "", major: user.major || "", grade: user.grade || "", enroll_year: user.enroll_year || "" } }); },
  input(event) { this.setData({ [`form.${event.currentTarget.dataset.key}`]: event.detail.value }); },
  next() { if (!this.data.form.major.trim() || !this.data.form.grade.trim()) { showError(null, "请先填写专业和年级"); return; } this.setData({ step: 2 }); },
  togglePath(event) { const type = event.detail.type; const selected = this.data.selected.slice(); const index = selected.indexOf(type); if (index >= 0) selected.splice(index, 1); else if (selected.length < 2) selected.push(type); else showError(null, "本次先比较两条路径"); this.setData({ selected }); },
  importData() { wx.navigateTo({ url: "/pkg-today/import/index?from=onboarding" }); },
  async finish() {
    if (this.data.submitting) return;
    this.setData({ submitting: true });
    try {
      const user = await userService.update(sessionStore.state.userId, this.data.form);
      sessionStore.updateUser(user);
      if (this.data.selected.length >= 2) {
        const result = await sandboxService.start(sessionStore.state.userId, this.data.selected);
        growthStore.set("sandboxSession", { sessionId: result.session_id, state: result.state || null, phase: result.phase, selected: this.data.selected, finished: result.finished, lastResponse: result });
        wx.redirectTo({ url: `/pkg-growth/sandbox-chat/index?sessionId=${result.session_id}` });
      } else wx.switchTab({ url: "/pages/today/index" });
    } catch (error) { showError(error, "保存失败"); }
    finally { this.setData({ submitting: false }); }
  }
});
