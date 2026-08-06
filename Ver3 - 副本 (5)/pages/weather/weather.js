const app = getApp();

Page({
  data: { statusBarHeight: 44, city: "青岛", weather: null, advice: "" },
  onLoad() {
    const info = wx.getSystemInfoSync();
    this.setData({ statusBarHeight: info.statusBarHeight });
    this.getWeather();
  },
  async getWeather() {
    try {
      const res = await app.request({ url: "/api/v1/weather?city=" + this.data.city });
      this.setData({ weather: res, advice: res.advice || "" });
    } catch (err) { /* offline */ }
  },
  goBack() { wx.navigateBack(); }
});