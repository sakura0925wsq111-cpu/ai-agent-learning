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
    var userInfo = wx.getStorageSync("userInfo");
    if (token && userId) {
      this.globalData.token = token;
      this.globalData.userId = userId;
      this.globalData.userInfo = userInfo || null;
    }
  },

  request: function(options) {
    var that = this;
    var url = options.url || "";
    var method = options.method || "GET";
    var data = options.data || {};
    return new Promise(function(resolve, reject) {
      var headers = { "Content-Type": "application/json" };
      if (that.globalData.token) {
        headers.Authorization = "Bearer " + that.globalData.token;
      }
      wx.request({
        url: that.globalData.baseUrl + url,
        method: method,
        data: data,
        timeout: options.timeout || 60000,
        header: Object.assign(headers, options.header || {}),
        success: function(res) {
          var errorMessage = res.data && (res.data.message || res.data.detail);
          var isLoginRequest = url === "/api/v1/users/login";
          if (res.statusCode === 401 && !isLoginRequest && options.authRedirect !== false) {
            if (!that._authRedirecting) {
              that._authRedirecting = true;
              that.clearAuth();
              wx.reLaunch({ url: "/pages/login/login" });
            }
            reject(new Error(errorMessage || "登录已过期，请重新登录"));
            return;
          }
          if (res.statusCode >= 200 && res.statusCode < 300) {
            var body = res.data;
            if (body && typeof body.code === "number") {
              if (body.code === 0) { resolve(body.data); }
              else { reject(new Error(body.message || "请求失败")); }
            } else { resolve(body); }
          } else {
            reject(new Error(errorMessage || "请求失败"));
          }
        },
        fail: function(err) { reject(err); }
      });
    });
  },

  setAuth: function(token, userId, userInfo) {
    this._authRedirecting = false;
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
    this.globalData.aiSuggestionFull = null;
    this.globalData.suggestionCache = null;
    wx.removeStorageSync("token");
    wx.removeStorageSync("userId");
    wx.removeStorageSync("userInfo");
  }
});
