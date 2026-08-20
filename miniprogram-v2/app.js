const { getApiBaseUrl, getRuntimeEnv } = require("./config/env");
const sessionStore = require("./stores/session-store");
const uiStore = require("./stores/ui-store");
const growthStore = require("./stores/growth-store");

App({
  globalData: {
    version: "2.0.0",
    runtimeEnv: "develop",
    baseUrl: "",
    session: sessionStore.state,
    online: true
  },

  onLaunch() {
    this.globalData.runtimeEnv = getRuntimeEnv();
    this.globalData.baseUrl = getApiBaseUrl();
    sessionStore.restore();
    growthStore.restore();
    this.globalData.session = sessionStore.state;
    wx.getNetworkType({
      success: ({ networkType }) => uiStore.setOnline(networkType !== "none")
    });
    wx.onNetworkStatusChange(({ isConnected }) => {
      uiStore.setOnline(isConnected);
      this.globalData.online = isConnected;
    });
  }
});
