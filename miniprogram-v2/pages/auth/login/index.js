const userService = require("../../../services/user-service");
const sessionStore = require("../../../stores/session-store");
const { showError, getHeroTop } = require("../../../utils/page");

Page({
  data: { studentId: "", password: "", submitting: false, agreed: false, showPassword: false, heroTop: 86 },
  onLoad() { this.setData({ heroTop: getHeroTop(12) }); if (sessionStore.restore().authenticated) wx.redirectTo({ url: "/pages/launch/index" }); },
  input(event) { this.setData({ [event.currentTarget.dataset.key]: event.detail.value }); },
  async submit() {
    if (!this.data.studentId.trim() || !this.data.password) { showError(null, "请输入学号和密码"); return; }
    if (!this.data.agreed) { showError(null, "请先阅读并同意用户协议与隐私政策"); return; }
    if (this.data.submitting) return;
    this.setData({ submitting: true });
    try {
      const result = await userService.login(this.data.studentId.trim(), this.data.password);
      sessionStore.setSession(result);
      const user = result.user || {};
      wx.reLaunch({ url: !user.major || !user.grade ? "/pages/onboarding/index" : "/pages/today/index" });
    } catch (error) { showError(error, "登录失败"); }
    finally { this.setData({ submitting: false }); }
  },
  register() { wx.navigateTo({ url: "/pages/auth/register/index" }); },
  fillDemo() { this.setData({ studentId: "demo2026", password: "DemoPass123!", agreed: true }); },
  toggleAgreement() { this.setData({ agreed: !this.data.agreed }); },
  togglePassword() { this.setData({ showPassword: !this.data.showPassword }); },
  forgot() { wx.showToast({ title: "请联系管理员重置密码", icon: "none" }); },
  agreement() { wx.navigateTo({ url: "/pages/agreement/index" }); }
});
