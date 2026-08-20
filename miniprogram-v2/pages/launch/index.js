const sessionStore = require("../../stores/session-store");
const { getHeroTop } = require("../../utils/page");

Page({
  data: { heroTop: 86 },
  onLoad() {
    this.setData({ heroTop: getHeroTop(12) });
    if (sessionStore.restore().authenticated) wx.switchTab({ url: "/pages/today/index" });
  },
  start() {
    wx.setStorageSync("ICAMPUS_V2_INTRO_SEEN", true);
    wx.navigateTo({ url: "/pages/auth/login/index" });
  },
  login() { this.start(); }
});
