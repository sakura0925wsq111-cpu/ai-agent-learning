const app = getApp();

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
    loading: true
  },

  onLoad() {
    const info = wx.getSystemInfoSync();
    const userId = wx.getStorageSync("userId") || app.globalData.userId || "";
    this.setData({ statusBarHeight: info.statusBarHeight, userId });
    this.loadData();
  },

  async loadData() {
    this.setData({ loading: true });
    try {
      const [userRes, memRes] = await Promise.all([
        app.request({ url: "/api/v1/users/" + this.data.userId }),
        app.request({ url: "/api/v1/memory/panel/" + this.data.userId })
      ]);

      const profileList = [
        { label: "姓名", value: userRes.name || "", field: "name" },
        { label: "昵称", value: userRes.nickname || "", field: "nickname" },
        { label: "年级", value: userRes.grade || "", field: "grade" },
        { label: "学院", value: userRes.college || "", field: "college" },
        { label: "专业", value: userRes.major || "", field: "major" },
        { label: "入学年份", value: userRes.enroll_year || "", field: "enrollYear" }
      ];

      const total = (memRes && memRes.total) ? memRes.total : 0;

      this.setData({
        userInfo: { name: userRes.name || "", school: userRes.school || "", studentId: userRes.student_id || "" },
        profileList: profileList,
        memoryTotal: total,
        loading: false
      });
    } catch (err) {
      console.error("加载设置失败:", err);
      this.setData({ loading: false });
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
          const apiField = field === "enrollYear" ? "enroll_year" : field;
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
        } catch (err) {
          wx.hideLoading();
          wx.showToast({ title: "修改失败", icon: "none" });
        }
      }
    });
  },

  goToMemory() { wx.navigateTo({ url: "/pages/memory/memory" }); },

  logout() {
    wx.showModal({
      title: "确定退出？",
      content: "退出后需要重新登录",
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