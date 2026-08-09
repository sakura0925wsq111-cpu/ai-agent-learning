const app = getApp();

Page({
  data: {
    userId: ''
  },

  onLoad(options) {
    const userId = options.userId || wx.getStorageSync("userId") || app.globalData.userId || "";
    this.setData({ userId });
    
    // 页面加载后开始注销流程
    this.performLogout();
  },

  async performLogout() {
    const { userId } = this.data;
    
    try {
      // 调用注销 API
      await app.request({
        method: "DELETE",
        url: `/api/v1/users/${userId}`
      });
      
      // 清除本地数据
      app.clearAuth();
      
      // 延迟跳转，让用户看到完成状态
      setTimeout(() => {
        wx.reLaunch({ url: "/pages/login/login" });
      }, 1500);
      
    } catch (err) {
      console.error("注销失败:", err);
      
      wx.showModal({
        title: "注销失败",
        content: err.message || "网络错误，请重试",
        showCancel: false,
        confirmText: "确定",
        success: () => {
          wx.navigateBack();
        }
      });
    }
  }
});
