Page({
  data: {
    statusBarHeight: 44,
    weather: {
      temp: 25,
      condition: '多云',
      icon: '/images/weather-cloudy.png',
      advice: '天气舒适，适合外出活动，记得补充水分，保持良好状态。'
    }
  },

  onLoad() {
    const info = wx.getSystemInfoSync();
    this.setData({
      statusBarHeight: info.statusBarHeight
    });
  },

  goBack() {
    wx.navigateBack();
  }
});
