const app = getApp();

Page({
  data: {
    statusBarHeight: 44,
    userId: "",
    userInfo: { name: "", school: "", studentId: "" },
    stats: { dayCount: 0 },
    
    // 个人信息列表
    profileList: [
      { label: "姓名", value: "", field: "name" },
      { label: "年级", value: "", field: "grade" },
      { label: "学院", value: "", field: "college" },
      { label: "专业", value: "", field: "major" },
      { label: "入学年份", value: "", field: "enrollYear" }
    ],
    
    // 长期记忆统计
    memoryStats: {
      total: 0,
      types: [
        { name: "画像数量", count: 0, icon: "/images/icon-portrait.png", bgColor: "#E8F4FD" },
        { name: "目标数量", count: 0, icon: "/images/icon-goal.png", bgColor: "#E6F7E6" },
        { name: "事实数量", count: 0, icon: "/images/icon-fact.png", bgColor: "#F0E6FF" }
      ]
    }
  },

  onLoad() {
    const info = wx.getSystemInfoSync();
    this.setData({ 
      statusBarHeight: info.statusBarHeight, 
      userId: wx.getStorageSync("userId") || app.globalData.userId || "" 
    });
    this.loadProfile();
    this.loadMemoryStats();
  },

  async loadProfile() {
    if (!this.data.userId) return;
    wx.showLoading({ title: "加载中..." });
    try {
      const res = await app.request({ url: `/api/v1/users/${this.data.userId}` });
      wx.hideLoading();
      
      const profileData = {
        name: res.name || "吴同学",
        school: res.school || "青岛大学",
        studentId: res.student_id || res.studentId || ""
      };
      
      // 更新个人信息列表
      const profileList = [
        { label: "姓名", value: res.name || "吴同学", field: "name" },
        { label: "年级", value: res.grade || "大二", field: "grade" },
        { label: "学院", value: res.college || "计算机科学与技术学院", field: "college" },
        { label: "专业", value: res.major || "计算机科学与技术", field: "major" },
        { label: "入学年份", value: res.enroll_year || "2022", field: "enrollYear" }
      ];
      
      this.setData({
        userInfo: profileData,
        profileList: profileList,
        stats: { dayCount: res.day_count || 0 }
      });
    } catch (err) {
      wx.hideLoading();
      // 使用默认数据
      this.setData({
        userInfo: { name: "吴同学", school: "青岛大学", studentId: "" },
        profileList: [
          { label: "姓名", value: "吴同学", field: "name" },
          { label: "年级", value: "大二", field: "grade" },
          { label: "学院", value: "计算机科学与技术学院", field: "college" },
          { label: "专业", value: "计算机科学与技术", field: "major" },
          { label: "入学年份", value: "2022", field: "enrollYear" }
        ]
      });
    }
  },

  // 加载长期记忆统计
  async loadMemoryStats() {
    try {
      const userId = this.data.userId;
      const res = await app.request({
        url: `/api/v1/memory/panel/${userId}`
      });
      
      if (res) {
        const tc = res.type_counts || {};
        const profileCount = tc.profile || 0;
        const goalCount = tc.goal || 0;
        const factCount = tc.fact || 0;
        const total = res.total || (profileCount + goalCount + factCount);
        
        this.setData({
          memoryStats: {
            total: total,
            types: [
              { name: "画像数量", count: profileCount, icon: "/images/icon-portrait.png", bgColor: "#E8F4FD" },
              { name: "目标数量", count: goalCount, icon: "/images/icon-goal.png", bgColor: "#E6F7E6" },
              { name: "事实数量", count: factCount, icon: "/images/icon-fact.png", bgColor: "#F0E6FF" }
            ]
          }
        });
      }
    } catch (err) {
      console.error("加载记忆统计失败:", err);
      this.setData({
        memoryStats: {
          total: 0,
          types: [
            { name: "画像数量", count: 0, icon: "/images/icon-portrait.png", bgColor: "#E8F4FD" },
            { name: "目标数量", count: 0, icon: "/images/icon-goal.png", bgColor: "#E6F7E6" },
            { name: "事实数量", count: 0, icon: "/images/icon-fact.png", bgColor: "#F0E6FF" }
          ]
        }
      });
    }
  },

  // 编辑个人信息
  editField(e) {
    const { field, label } = e.currentTarget.dataset;
    const item = this.data.profileList.find(p => p.field === field);
    const currentValue = item ? item.value : "";
    
    wx.showModal({
      title: `修改${label}`,
      editable: true,
      placeholderText: `请输入${label}`,
      content: currentValue,
      success: async (res) => {
        if (!res.confirm) return;
        if (res.content === currentValue) return;
        
        wx.showLoading({ title: "保存中..." });
        try {
          const updateData = {};
          const apiField = field === 'enrollYear' ? 'enroll_year' : field;
          updateData[apiField] = res.content;
          
          await app.request({
            method: "PUT",
            url: `/api/v1/users/${this.data.userId}`,
            data: updateData
          });
          
          wx.hideLoading();
          wx.showToast({ title: "修改成功", icon: "success" });
          
          // 更新本地数据
          const profileList = this.data.profileList.map(p => {
            if (p.field === field) {
              return { ...p, value: res.content };
            }
            return p;
          });
          
          this.setData({ profileList });
          
          // 如果修改的是姓名，同时更新 userInfo
          if (field === 'name') {
            this.setData({
              'userInfo.name': res.content
            });
          }
        } catch (err) {
          wx.hideLoading();
          wx.showToast({ title: "修改失败", icon: "none" });
        }
      }
    });
  },

  // 修改姓名（点击头像区域）
  editProfile() {
    this.editField({ currentTarget: { dataset: { field: 'name', label: '姓名' } } });
  },

  // 跳转长期记忆页
  goToMemory() {
    wx.navigateTo({ url: '/pages/memory/memory' });
  },

  // 关于
  showAbout(e) {
    const type = e.currentTarget.dataset.type;
    if (type === 'about') {
      wx.showModal({ 
        title: "关于 iCampus", 
        content: "你的校园AI伙伴\n版本 2.1", 
        showCancel: false 
      });
    }
  },

  goToSettings() { wx.navigateTo({ url: "/pages/settings/settings" }); },

  // 退出登录
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

  // 注销账号 - 跳转到全屏注销页面
  deleteAccount() {
    wx.showModal({
      title: "注销账号",
      content: "注销后所有数据将被删除，不可恢复",
      confirmColor: "#E74C3C",
      success: (res) => {
        if (res.confirm) {
          // 跳转到注销页面，执行全屏 loading 注销
          wx.navigateTo({
            url: `/pages/logout/logout?userId=${this.data.userId}`
          });
        }
      }
    });
  }
});

