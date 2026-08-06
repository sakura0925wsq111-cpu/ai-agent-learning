// pages/mine/mine.js
const app = getApp();

Page({
  data: {
    statusBarHeight: 44,
    userId: "",
    userInfo: { 
      name: "", 
      school: "",
      grade: "",
      college: "",      // 新增：学院
      major: "",
      enrollYear: ""
    }
  },

  onLoad() {
    const info = wx.getSystemInfoSync();
    const userId = wx.getStorageSync("userId") || app.globalData.userId || "";
    this.setData({ 
      statusBarHeight: info.statusBarHeight, 
      userId 
    });
    if (userId) this.loadUserInfo();
  },

  async loadUserInfo() {
    try {
      const res = await app.request({ 
        url: "/api/v1/users/" + this.data.userId 
      });
      this.setData({
        userInfo: { 
          name: res.name || "吴同学",
          school: res.school || "青岛大学",
          grade: res.grade || "大二",
          college: res.college || "计算机科学与技术学院",  // 新增
          major: res.major || "计算机科学与技术",
          enrollYear: res.enroll_year || "2022"
        }
      });
    } catch (err) { 
      // 使用默认数据
      this.setData({
        userInfo: {
          name: "吴同学",
          school: "青岛大学",
          grade: "大二",
          college: "计算机科学与技术学院",
          major: "计算机科学与技术",
          enrollYear: "2022"
        }
      });
    }
  },

  // 编辑个人信息
  editInfo(e) {
    const field = e.currentTarget.dataset.field;
    const fieldMap = {
      name: '姓名',
      grade: '年级',
      college: '学院',
      major: '专业',
      enrollYear: '入学年份'
    };
    
    wx.showModal({
      title: '修改' + fieldMap[field],
      editable: true,
      placeholderText: '请输入' + fieldMap[field],
      success: (res) => {
        if (res.confirm && res.content) {
          // 更新本地数据
          const userInfo = this.data.userInfo;
          userInfo[field] = res.content;
          this.setData({ userInfo });
          
          // 调用 API 保存
          this.saveUserInfo(field, res.content);
        }
      }
    });
  },

  // 保存用户信息
  async saveUserInfo(field, value) {
    try {
      const userId = this.data.userId;
      const updateData = {};
      updateData[field] = value;
      
      await app.request({
        method: 'PUT',
        url: '/api/v1/users/' + userId,
        data: updateData
      });
      
      wx.showToast({
        title: '保存成功',
        icon: 'success'
      });
    } catch (err) {
      wx.showToast({
        title: '保存失败',
        icon: 'error'
      });
    }
  },

  // 页面跳转
  goBack() { 
    wx.navigateBack(); 
  },

  goToMemory() {
    wx.navigateTo({ url: '/pages/memory/memory' });
  },

  goToTasks() {
    wx.navigateTo({ url: '/pages/tasks/tasks' });
  },

  goToMessages() {
    wx.navigateTo({ url: '/pages/messages/messages' });
  },

  goToSettings() {
    wx.navigateTo({ url: '/pages/settings/settings' });
  },

  goToHelp() {
    wx.navigateTo({ url: '/pages/help/help' });
  },

  goToAbout() {
    wx.navigateTo({ url: '/pages/about/about' });
  }
});
