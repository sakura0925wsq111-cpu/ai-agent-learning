const app = getApp();

Page({
  data: { statusBarHeight: 44, studentId: "", password: "", canLogin: false, submitting: false, canGoBack: false },
  onLoad() {
    const info = wx.getSystemInfoSync();
    const token = wx.getStorageSync("token");
    const userId = wx.getStorageSync("userId");
    this.setData({ statusBarHeight: info.statusBarHeight, canGoBack: getCurrentPages().length > 1 });
    if (token && userId) wx.switchTab({ url: "/pages/index/index" });
  },
  onStudentIdInput(e) { this.setData({ studentId: e.detail.value }); this.updateCanLogin(); },
  onPasswordInput(e) { this.setData({ password: e.detail.value }); this.updateCanLogin(); },

  updateCanLogin() {
    this.setData({ canLogin: !!(this.data.studentId.trim() && this.data.password) && !this.data.submitting });
  },

  async doLogin() {
    if (!this.data.canLogin || this.data.submitting) { wx.showToast({ title: "请输入学号和密码", icon: "none" }); return; }
    this.setData({ submitting: true, canLogin: false });
    wx.showLoading({ title: "登录中..." });
    try {
      const res = await app.request({ url: "/api/v1/users/login", method: "POST", data: { student_id: this.data.studentId, password: this.data.password } });
      app.setAuth(res.token, res.user_id, res.user);
      wx.switchTab({ url: "/pages/index/index" });
    } catch (err) { wx.showToast({ title: err.message || "登录失败", icon: "none" }); }
    finally { wx.hideLoading(); this.setData({ submitting: false }); this.updateCanLogin(); }
  },

  goBack() { wx.navigateBack(); },
  goRegister() { wx.navigateTo({ url: "/pages/register/register" }); }
});
