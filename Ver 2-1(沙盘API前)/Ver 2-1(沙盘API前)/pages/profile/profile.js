const app = getApp();

Page({
  data: {
    statusBarHeight: 44, userId: "",
    userInfo: { name: "", school: "", studentId: "" },
    profileList: [
      { label: "年级", value: "" }, { label: "专业", value: "" },
      { label: "学院", value: "" }, { label: "入学年份", value: "" }
    ],
    functionList: [
      { icon: "/images/icon-star.png", name: "我的记忆", bgColor: "#E8F4FD", url: "/pages/memory/memory" },
      { icon: "/images/icon-taskmine.png", name: "我的任务", bgColor: "#FFF2E8", url: "" },
      { icon: "/images/icon-message.png", name: "我的消息", bgColor: "#E6F7E6", url: "/pages/history/history" },
      { icon: "/images/icon-setting.png", name: "设置中心", bgColor: "#F6F0FF", url: "" }
    ],
    aboutList: [{ label: "帮助与反馈" }, { label: "关于 iCampus" }]
  },

  onLoad() {
    const info = wx.getSystemInfoSync();
    this.setData({ statusBarHeight: info.statusBarHeight, userId: wx.getStorageSync("userId") || app.globalData.userId || "" });
    this.loadProfile();
  },

  async loadProfile() {
    if (!this.data.userId) return;
    wx.showLoading({ title: "加载中..." });
    try {
      const res = await app.request({ url: `/api/v1/users/${this.data.userId}` });
      wx.hideLoading();
      const profile = {
        name: res.name || "", school: res.school || "", studentId: res.student_id || res.studentId || ""
      };
      this.setData({
        userInfo: profile,
        profileList: [
          { label: "年级", value: res.grade || "" },
          { label: "专业", value: res.major || "" },
          { label: "学院", value: res.college || "" },
          { label: "入学年份", value: res.enroll_year || "" }
        ]
      });
    } catch (err) {
      wx.hideLoading();
      wx.showToast({ title: "加载失败", icon: "none" });
    }
  },

  editName() {
    wx.showModal({
      title: "修改姓名",
      editable: true,
      placeholderText: "请输入新姓名",
      success: async (res) => {
        if (!res.confirm || !res.content) return;
        wx.showLoading({ title: "保存中..." });
        try {
          await app.request({
            method: "PUT",
            url: `/api/v1/users/${this.data.userId}`,
            data: { name: res.content }
          });
          wx.hideLoading();
          wx.showToast({ title: "修改成功", icon: "success" });
          this.loadProfile();
        } catch (err) {
          wx.hideLoading();
          wx.showToast({ title: "修改失败", icon: "none" });
        }
      }
    });
  },

  navigateTo(e) {
    const url = e.currentTarget.dataset.url;
    if (url) wx.navigateTo({ url });
    else wx.showToast({ title: "功能开发中", icon: "none" });
  },

  showAbout(e) {
    const label = e.currentTarget.dataset.label;
    if (label === "关于 iCampus") {
      wx.showModal({ title: "关于 iCampus", content: "你的校园AI伙伴\n版本 2.1", showCancel: false });
    } else {
      wx.showToast({ title: "功能开发中", icon: "none" });
    }
  },

  logout() {
    wx.showModal({
      title: "退出登录",
      content: "确定要退出登录吗？",
      success: (res) => {
        if (res.confirm) {
          wx.removeStorageSync("token");
          wx.removeStorageSync("userId");
          app.globalData.userId = "";
          app.globalData.token = "";
          wx.reLaunch({ url: "/pages/login/login" });
        }
      }
    });
  }
});