const app = getApp();
const { buildProfileList, persistUserField, toApiField } = require("../../utils/profile.js");

Page({
  data: {
    statusBarHeight: 44,
    userId: "",
    userInfo: { name: "", school: "", studentId: "" },
    profileList: [
      { label: "姓名", value: "", field: "name" },
      { label: "年级", value: "", field: "grade" },
      { label: "学院", value: "", field: "college" },
      { label: "专业", value: "", field: "major" },
      { label: "入学年份", value: "", field: "enrollYear" }
    ],
    memoryTotal: 0,
    loading: true,
    loadError: false
  },

  onLoad() {
    const info = wx.getSystemInfoSync();
    const userId = wx.getStorageSync("userId") || app.globalData.userId || "";
    this.setData({ statusBarHeight: info.statusBarHeight, userId });
    this.loadData();
  },

  async loadData() {
    this.setData({ loading: true, loadError: false });
    try {
      const userRes = await app.request({ url: "/api/v1/users/" + this.data.userId });
      let memRes = null;
      try {
        memRes = await app.request({ url: "/api/v1/memory/panel/" + this.data.userId });
      } catch (memoryErr) {
        console.error("加载记忆统计失败:", memoryErr);
      }

      const profileList = buildProfileList(userRes, true);

      const total = (memRes && memRes.total) ? memRes.total : 0;

      this.setData({
        userInfo: { name: userRes.name || "", school: userRes.school || "", studentId: userRes.student_id || "" },
        profileList: profileList,
        memoryTotal: total,
        loading: false
      });
    } catch (err) {
      console.error("加载设置失败:", err);
      this.setData({ loading: false, loadError: true });
      wx.showToast({ title: "加载失败", icon: "none" });
    }
  },

  editField(e) {
    const { field, label } = e.currentTarget.dataset;
    const item = this.data.profileList.find(p => p.field === field);
    const currentValue = item ? item.value : "";

    wx.showModal({
      title: "修改" + label,
      editable: true,
      placeholderText: "请输入" + label,
      content: currentValue,
      success: async (res) => {
        if (!res.confirm || res.content === currentValue) return;
        wx.showLoading({ title: "保存中..." });
        try {
          const updateData = {};
          const apiField = toApiField(field);
          updateData[apiField] = res.content;

          await app.request({
            method: "PUT",
            url: "/api/v1/users/" + this.data.userId,
            data: updateData
          });

          wx.hideLoading();
          wx.showToast({ title: "修改成功", icon: "success" });

          const profileList = this.data.profileList.map(p => {
            if (p.field === field) return { ...p, value: res.content };
            return p;
          });
          this.setData({ profileList });
          persistUserField(app, apiField, res.content);
        } catch (err) {
          wx.hideLoading();
          wx.showToast({ title: "修改失败", icon: "none" });
        }
      }
    });
  },

  goToMemory() { wx.navigateTo({ url: "/pages/memory/memory" }); },
  retryLoad() { this.loadData(); },

  showAbout() {
    wx.showModal({ title: "关于 iCampus", content: "你的校园伙伴\n版本 2.1", showCancel: false });
  },

  logout() {
    wx.showModal({
      title: "确定退出？",
      content: "退出后需要重新登录",
      success: (res) => {
        if (res.confirm) {
          app.clearAuth();
          wx.reLaunch({ url: "/pages/login/login" });
        }
      }
    });
  },

  deleteAccount() {
    wx.showModal({
      title: "注销账号",
      content: "注销后所有数据将被删除，不可恢复",
      confirmColor: "#E74C3C",
      success: (res) => {
        if (res.confirm) {
          wx.navigateTo({ url: "/pages/logout/logout?userId=" + this.data.userId });
        }
      }
    });
  },

  goBack() { wx.navigateBack(); }
});
