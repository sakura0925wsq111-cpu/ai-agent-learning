App({
  globalData: {
    userInfo: null,
    token: "",
    userId: "",
    baseUrl: "http://127.0.0.1:8000",
    mockMode: false,
    aiSuggestionFull: null,
    suggestionCache: null
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
    var that = this;
    var url = options.url || "";
    var method = options.method || "GET";
    var data = options.data || {};
    return new Promise(function(resolve, reject) {
      wx.request({
        url: that.globalData.baseUrl + url,
        method: method,
        data: data,
        header: Object.assign({ "Content-Type": "application/json", "Authorization": "Bearer " + that.globalData.token }, options.header || {}),
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
            reject(new Error((res.data && res.data.message) || "请求失败"));
          }
        },
        fail: function(err) { reject(err); }
      });
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
