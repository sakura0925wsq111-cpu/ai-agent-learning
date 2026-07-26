Page({
  data: {
    statusBarHeight: 44
  },

  onLoad() {
    const info = wx.getSystemInfoSync();
    this.setData({ statusBarHeight: info.statusBarHeight });
  },

  goBack() {
    wx.switchTab({ url: '/pages/index/index' });
  },

  goHistory() {
    wx.navigateTo({ url: '/pages/history/history' });
  },

  goTodayMode() {
    wx.switchTab({ url: '/pages/schedule/schedule' });
  },

  goGrowthMode() {
    wx.navigateTo({ url: '/pages/growth/growth' });
  }
});