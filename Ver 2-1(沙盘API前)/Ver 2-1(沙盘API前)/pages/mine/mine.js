// pages/mine/mine.js
const app = getApp();

Page({
  data: {
    statusBarHeight: 44,
    userId: "",
    userInfo: { name: "", school: "" }
  },

  onLoad() {
    const info = wx.getSystemInfoSync();
    const userId = wx.getStorageSync("userId") || app.globalData.userId || "";
    this.setData({ statusBarHeight: info.statusBarHeight, userId });
    if (userId) this.loadUserInfo();
  },

  async loadUserInfo() {
    try {
      const res = await app.request({ url: "/api/v1/users/" + this.data.userId });
      this.setData({
        userInfo: { name: res.name || "", school: res.school || "" }
      });
    } catch (err) { /* ignore */ }
  },

  goBack() { wx.navigateBack(); }
});
