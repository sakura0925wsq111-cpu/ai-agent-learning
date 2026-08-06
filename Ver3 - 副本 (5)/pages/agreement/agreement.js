Page({
  data: { statusBarHeight: 44, type: "user" },

  onLoad(options) {
    const info = wx.getSystemInfoSync();
    this.setData({ statusBarHeight: info.statusBarHeight, type: options.type || "user" });
  },

  goBack() { wx.navigateBack(); }
});