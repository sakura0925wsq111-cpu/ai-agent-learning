const app = getApp();

Page({
  data: {
    statusBarHeight: 44,
    agents: [
      { type: "graduate", name: "考研规划", icon: "/images/icon-postgrad.png", color: "#4A90D9", bgColor: "#E6F2FF" },
      { type: "career", name: "就业指导", icon: "/images/icon-job.png", color: "#52C41A", bgColor: "#E6F9ED" },
      { type: "civil", name: "考公评估", icon: "/images/icon-civil.png", color: "#FA8C16", bgColor: "#FFF3E6" },
      { type: "major", name: "转专业分析", icon: "/images/icon-transfer.png", color: "#722ED1", bgColor: "#F0E6FF" }
    ]
  },
  onLoad() { const info = wx.getSystemInfoSync(); this.setData({ statusBarHeight: info.statusBarHeight }); this.loadAgents(); },
  async loadAgents() {
    try {
      const res = await app.request({ url: "/api/v1/growth/agents" });
      if (res.agents && res.agents.length) {
        const icons = { graduate: "/images/icon-postgrad.png", career: "/images/icon-job.png", civil: "/images/icon-civil.png", major: "/images/icon-transfer.png" };
        const colors = { graduate: "#4A90D9", career: "#52C41A", civil: "#FA8C16", major: "#722ED1" };
        const bgs = { graduate: "#E6F2FF", career: "#E6F9ED", civil: "#FFF3E6", major: "#F0E6FF" };
        this.setData({ agents: res.agents.map(a => ({ type: a.type, name: a.name, icon: icons[a.type] || "/images/icon-postgrad.png", color: colors[a.type] || "#4A90D9", bgColor: bgs[a.type] || "#E6F2FF" })) });
      }
    } catch (err) {}
  },
  goBack() { wx.navigateBack(); },
  goDetail(e) { wx.navigateTo({ url: `/pages/chatroom/chatroom?mode=agent&agent=${e.currentTarget.dataset.type}` }); },

  async goChat() {
    wx.showLoading({ title: "启动中..." });
    try {
      const userId = wx.getStorageSync("userId") || app.globalData.userId || "";
      const res = await app.request({
        method: "POST", url: "/sandbox/start",
        data: { user_id: userId }
      });
      wx.hideLoading();
      wx.navigateTo({ url: `/pages/chatroom/chatroom?mode=sandbox&session_id=${res.session_id || ""}` });
    } catch (err) {
      wx.hideLoading();
      wx.showToast({ title: "启动失败，请重试", icon: "none" });
    }
  }
});