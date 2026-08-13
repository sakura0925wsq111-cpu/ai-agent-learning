const app = getApp();

Page({
  data: { countdown: 3 },
  onLoad() {
    var that = this;
    var timer = setInterval(function() {
      var c = that.data.countdown - 1;
      if (c <= 0) {
        clearInterval(timer);
        var token = wx.getStorageSync("token");
        if (token) {
          wx.switchTab({ url: "/pages/index/index" });
        } else {
          wx.redirectTo({ url: "/pages/login/login" });
        }
      } else {
        that.setData({ countdown: c });
      }
    }, 1000);
  }
});