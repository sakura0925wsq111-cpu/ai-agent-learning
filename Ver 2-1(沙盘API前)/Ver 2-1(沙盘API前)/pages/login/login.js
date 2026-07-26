const app = getApp();

Page({
  data: { statusBarHeight: 44, studentId: "", password: "", canLogin: true },
  onLoad() { const info = wx.getSystemInfoSync(); this.setData({ statusBarHeight: info.statusBarHeight }); },
  onStudentIdInput(e) { this.setData({ studentId: e.detail.value }); },
  onPasswordInput(e) { this.setData({ password: e.detail.value }); },

  async doLogin() {
    if (!this.data.studentId || !this.data.password) { wx.showToast({ title: "请输入学号和密码", icon: "none" }); return; }
    wx.showLoading({ title: "登录中..." });
    try {
      const res = await app.request({ url: "/api/v1/users/login", method: "POST", data: { student_id: this.data.studentId, password: this.data.password } });
      app.setAuth(res.token, res.user_id, res.user);
      wx.switchTab({ url: "/pages/index/index" });
    } catch (err) { wx.showToast({ title: err.message || "登录失败", icon: "none" }); }
    finally { wx.hideLoading(); }
  },

  goBack() { wx.navigateBack(); },
  goRegister() { wx.navigateTo({ url: "/pages/register/register" }); }
});