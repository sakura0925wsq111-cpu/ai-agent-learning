const app = getApp();

Page({
  data: {
    statusBarHeight: 44,
    city: "青岛",
    cityOptions: ["北京", "上海", "广州", "深圳", "杭州", "南京", "武汉", "成都", "重庆", "西安", "青岛", "济南", "大连", "天津", "长沙", "苏州"],
    weather: null,
    loading: true,
    hasError: false,
    errorMsg: ""
  },
  onLoad() {
    const info = wx.getSystemInfoSync();
    const city = wx.getStorageSync("weatherCity") || "青岛";
    this.setData({ statusBarHeight: info.statusBarHeight, city });
    this.getWeather();
  },
  async getWeather() {
    this.setData({ loading: true, hasError: false, errorMsg: "" });
    try {
      const res = await app.request({ url: "/api/v1/weather?city=" + encodeURIComponent(this.data.city), authRedirect: false });
      this.setData({ weather: res, loading: false });
    } catch (err) {
      this.setData({ weather: null, loading: false, hasError: true, errorMsg: err.message || "天气加载失败" });
    }
  },
  onCityChange(e) {
    const city = this.data.cityOptions[e.detail.value];
    if (!city || city === this.data.city) return;
    wx.setStorageSync("weatherCity", city);
    this.setData({ city }, () => this.getWeather());
  },
  retryWeather() { this.getWeather(); },
  goBack() { wx.navigateBack(); }
});
