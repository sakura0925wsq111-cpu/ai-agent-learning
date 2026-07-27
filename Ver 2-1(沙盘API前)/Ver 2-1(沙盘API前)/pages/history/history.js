const app = getApp();

Page({
  data: { statusBarHeight: 44, userId: "", currentTab: "plan", currentFilter: "全部", planHistory: [], chatHistory: [] },

  onLoad(options) {
    const info = wx.getSystemInfoSync(); const userId = wx.getStorageSync("userId") || app.globalData.userId || "";
    this.setData({ statusBarHeight: info.statusBarHeight, userId, currentTab: options.type === "chat" ? "chat" : "plan" });
    this.loadData();
  },

  async loadData() {
    if (this.data.currentTab === "plan") { await this.loadPlanHistory(); }
    if (this.data.currentTab === "chat") { await this.loadChatHistory(); }
  },

  async loadPlanHistory() {
    wx.showLoading({ title: "加载中..." });
    try {
      const res = await app.request({ url: `/api/v1/growth/history/${this.data.userId}` });
      this.setData({ planHistory: this.formatPlanHistory(res.sessions || []) });
    } catch (err) { this.setData({ planHistory: [] }); }
    wx.hideLoading();
  },

  async loadChatHistory() {
    wx.showLoading({ title: "加载中..." });
    try {
      const res = await app.request({ url: `/api/v1/growth/history/${this.data.userId}` });
      this.setData({ chatHistory: this.formatChatHistory(res.sessions || []) });
    } catch (err) { this.setData({ chatHistory: [] }); }
    wx.hideLoading();
  },

  formatPlanHistory(list) {
    const typeNames = { graduate: "考研规划", employment: "就业指导", civil: "考公评估", major: "转专业分析", career: "就业指导" };
    const colors = { graduate: "#4A90D9", employment: "#52C41A", civil: "#FA8C16", major: "#722ED1", career: "#52C41A" };
    const statusTexts = { completed: "已完成", in_progress: "进行中", abandoned: "已放弃" };
    return list.map(item => ({
      ...item, agent_type: item.agent,
      typeName: typeNames[item.agent] || item.agent,
      color: colors[item.agent] || "#999",
      statusText: statusTexts[item.status] || item.status,
      title: item.title || `${typeNames[item.agent] || "规划"} - ${(item.session_id || "").slice(0, 8)}`,
      summary: item.summary || `${item.message_count || 0} 条消息`
    }));
  },

  formatChatHistory(list) {
    const typeNames = { graduate: "考研规划", employment: "就业指导", civil: "考公评估", major: "转专业分析", career: "就业指导" };
    return list.map(item => ({
      ...item,
      title: item.title || (typeNames[item.agent] || "对话") + "咨询",
      last_message: item.summary || item.last_message || "暂无消息",
      last_message_time: item.updated_at || item.created_at || "",
      message_count: item.message_count || 0
    }));
  },

  switchTab(e) {
    const t = e.currentTarget.dataset.tab;
    if (t === this.data.currentTab) return;
    this.setData({ currentTab: t });
    this.loadData();
  },

  showFilter() {
    wx.showActionSheet({
      itemList: ["全部", "考研规划", "就业指导", "考公评估", "转专业分析"],
      success: (res) => {
        this.setData({ currentFilter: ["全部", "考研规划", "就业指导", "考公评估", "转专业分析"][res.tapIndex] });
      }
    });
  },

  viewPlanDetail(e) {
    const { id, type } = e.currentTarget.dataset;
    wx.navigateTo({ url: `/pages/report/report?session_id=${id}&agent_type=${type}&from=history` });
  },

  viewChatDetail(e) {
    wx.navigateTo({ url: `/pages/chatroom/chatroom?mode=resume&session_id=${e.currentTarget.dataset.id}` });
  },

  goBack() { wx.navigateBack(); }
});
