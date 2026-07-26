Page({
  data: {
    statusBarHeight: 44
  },

  onLoad() {
    const info = wx.getSystemInfoSync();
    this.setData({
      statusBarHeight: info.statusBarHeight
    });
  },

  // 返回首页
  goBack() {
    wx.switchTab({
      url: '/pages/index/index'
    });
  },

  // 历史记录
  goHistory() {
    wx.navigateTo({
      url: '/pages/history/history'
    });
  },

  // 进入今日模式
  goTodayMode() {
    wx.navigateTo({
      url: '/pages/schedule/schedule'
    });
  },

  // 进入成长模式
  goGrowthMode() {
    wx.navigateTo({
      url: '/pages/growth/growth'
    });
  }
});
