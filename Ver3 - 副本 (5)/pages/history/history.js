const app = getApp();

const TYPE_NAMES = {
  graduate: "考研规划",
  employment: "就业指导",
  career: "就业指导",
  civil: "考公评估",
  major: "转专业分析"
};

const TYPE_COLORS = {
  graduate: "#4A90D9",
  employment: "#52C41A",
  career: "#52C41A",
  civil: "#FA8C16",
  major: "#722ED1"
};

Page({
  data: {
    statusBarHeight: 44,
    userId: "",
    currentTab: "plan",
    currentFilter: "全部",
    rawSessions: [],
    rawReports: [],
    planHistory: [],
    chatHistory: [],
    loading: true,
    error: false
  },

  onLoad(options) {
    const info = wx.getSystemInfoSync();
    const userId = wx.getStorageSync("userId") || app.globalData.userId || "";
    this.setData({
      statusBarHeight: info.statusBarHeight,
      userId,
      currentTab: options.type === "chat" ? "chat" : "plan"
    });
    this.loadData();
  },

  async loadData() {
    this.setData({ loading: true, error: false });
    try {
      const [history, reports] = await Promise.all([
        app.request({ url: `/api/v1/growth/history/${this.data.userId}` }),
        app.request({ url: `/api/v1/growth/reports?user_id=${this.data.userId}` })
      ]);
      this.setData({
        rawSessions: history.sessions || [],
        rawReports: reports.reports || [],
        loading: false
      });
      this.applyFilter();
    } catch (err) {
      this.setData({ rawSessions: [], rawReports: [], planHistory: [], chatHistory: [], loading: false, error: true });
    }
  },

  applyFilter() {
    const filter = this.data.currentFilter;
    const sessions = this.data.rawSessions.filter((item) => {
      return filter === "全部" || TYPE_NAMES[item.agent] === filter;
    });
    const reports = this.data.rawReports.filter((item) => {
      return filter === "全部" || TYPE_NAMES[item.agent] === filter;
    });
    const plans = reports.map((item) => ({
      ...item,
      agent_type: item.agent,
      typeName: TYPE_NAMES[item.agent] || "成长规划",
      color: TYPE_COLORS[item.agent] || "#667085",
      status: item.is_executing ? "in_progress" : "completed",
      statusText: item.is_executing ? `执行中 ${Math.round((item.progress || 0) * 100)}%` : "已生成",
      title: item.title || TYPE_NAMES[item.agent] || "成长规划",
      summary: item.summary || "已生成完整报告",
      displayTime: this.formatTime(item.created_at)
    }));
    const chats = sessions.map((item) => ({
      ...item,
      title: (TYPE_NAMES[item.agent] || "成长规划") + "咨询",
      last_message: item.finished ? "报告已生成，可继续咨询" : this.getStageText(item.stage),
      displayTime: this.formatTime(item.updated_at || item.created_at),
      message_count: item.message_count || 0
    }));
    this.setData({ planHistory: plans, chatHistory: chats });
  },

  getStageText(stage) {
    const texts = {
      questioning: "信息收集中，点击继续",
      awaiting: "信息已收集，等待开始分析",
      analyzing: "初步分析已完成，等待确认",
      report: "报告已生成"
    };
    return texts[stage] || "规划进行中，点击继续";
  },

  formatTime(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    const pad = (n) => String(n).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
  },

  switchTab(e) {
    const tab = e.currentTarget.dataset.tab;
    if (tab !== this.data.currentTab) this.setData({ currentTab: tab });
  },

  showFilter() {
    const options = ["全部", "考研规划", "就业指导", "考公评估", "转专业分析"];
    wx.showActionSheet({
      itemList: options,
      success: (res) => this.setData({ currentFilter: options[res.tapIndex] }, () => this.applyFilter())
    });
  },

  viewPlanDetail(e) {
    const { id, type } = e.currentTarget.dataset;
    wx.navigateTo({ url: `/pages/report/report?session_id=${id}&agent_type=${type}&from=history` });
  },

  viewChatDetail(e) {
    const { id, agent } = e.currentTarget.dataset;
    wx.navigateTo({ url: `/pages/chatroom/chatroom?mode=resume&session_id=${id}&agent=${agent}` });
  },

  startGrowth() {
    wx.switchTab({ url: "/pages/growth/growth" });
  },

  goBack() {
    if (getCurrentPages().length > 1) wx.navigateBack({ delta: 1 });
    else wx.switchTab({ url: "/pages/growth/growth" });
  }
});
