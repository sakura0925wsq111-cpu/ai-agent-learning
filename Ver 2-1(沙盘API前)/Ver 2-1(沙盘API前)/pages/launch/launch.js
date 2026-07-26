const app = getApp();

Page({
  data: { isLoggedIn: false, agreed: false },
  onLoad() {
    if (app.globalData.token) { this.setData({ isLoggedIn: true }); setTimeout(() => wx.switchTab({ url: "/pages/index/index" }), 1500); }
  },
  toggleAgree() { this.setData({ agreed: !this.data.agreed }); },
  onGetPhoneNumber(e) {
    if (!this.data.agreed) { wx.showToast({ title: "请先同意用户协议", icon: "none" }); return; }
    if (e.detail.errMsg !== "getPhoneNumber:ok") { wx.showToast({ title: "登录取消", icon: "none" }); return; }
    this.doLogin(e.detail.encryptedData, e.detail.iv);
  },
  async doLogin(encryptedData, iv) {
    wx.showLoading({ title: "登录中..." });
    try {
      const { code } = await wx.login();
      const res = await app.request({ url: "/api/v1/users/login", method: "POST", data: { student_id: "", password: "", wx_code: code, encrypted_data: encryptedData, iv } });
      app.setAuth(res.token, res.user_id, res.user);
      wx.hideLoading(); wx.switchTab({ url: "/pages/index/index" });
    } catch (err) { wx.hideLoading(); wx.showToast({ title: err.message || "登录失败", icon: "none" }); }
  },
  enterApp() { wx.switchTab({ url: "/pages/index/index" }); },
  showAgreement() { wx.navigateTo({ url: "/pages/agreement/agreement?type=user" }); },
  showPrivacy() { wx.navigateTo({ url: "/pages/agreement/agreement?type=privacy" }); }
});
