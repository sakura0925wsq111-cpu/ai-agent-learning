App({
  globalData: {
    userInfo: null, token: "", userId: "",
    baseUrl: "http://127.0.0.1:8000",
    mockMode: false
  },

  onLaunch() {
    var token = wx.getStorageSync("token");
    var userId = wx.getStorageSync("userId");
    if (token && userId) {
      this.globalData.token = token;
      this.globalData.userId = userId;
    }
  },

  request: function(options) {
    if (this.globalData.mockMode) return this.mockRequest(options);
    var that = this;
    var url = options.url || "";
    var method = options.method || "GET";
    var data = options.data || {};
    var header = options.header || {};
    return new Promise(function(resolve, reject) {
      wx.request({
        url: that.globalData.baseUrl + url,
        method: method,
        data: data,
        header: Object.assign({ "Content-Type": "application/json", "Authorization": "Bearer " + that.globalData.token }, header),
        success: function(res) {
          if (res.statusCode === 401) {
            that.clearAuth();
            wx.reLaunch({ url: "/pages/login/login" });
            reject(new Error("登录已过期"));
            return;
          }
          if (res.statusCode >= 200 && res.statusCode < 300) {
            var body = res.data;
            if (body && typeof body.code === "number") {
              if (body.code === 0) { resolve(body.data); }
              else { reject(new Error(body.message || "请求失败")); }
            } else { resolve(body); }
          } else {
            var body = res.data;
            reject(new Error((body && body.message) || "请求失败"));
          }
        },
        fail: function(err) {
          wx.showToast({ title: "网络错误", icon: "none" });
          reject(err);
        }
      });
    });
  },

  mockRequest: function(options) {
    return new Promise(function(resolve) {
      setTimeout(function() {
        if (options.url.indexOf("/api/v1/weather") >= 0) {
          resolve({ temp: 25, condition: "多云", location: "青岛", advice: "天气舒适，适合外出活动。" });
        } else { resolve({}); }
      }, 300);
    });
  },

  setAuth: function(token, userId, userInfo) {
    this.globalData.token = token;
    this.globalData.userId = userId;
    this.globalData.userInfo = userInfo;
    wx.setStorageSync("token", token);
    wx.setStorageSync("userId", userId);
    wx.setStorageSync("userInfo", userInfo);
  },

  clearAuth: function() {
    this.globalData.token = "";
    this.globalData.userId = "";
    this.globalData.userInfo = null;
    wx.removeStorageSync("token");
    wx.removeStorageSync("userId");
    wx.removeStorageSync("userInfo");
  }
});