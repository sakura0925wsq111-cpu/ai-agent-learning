const api = require('../../utils/api.js');
const app = getApp();

Page({
  data: {
    statusBarHeight: 44,
    activeSession: null,
    agents: [
      { type: "graduate", name: "考研规划", icon: "/images/icon-postgrad.png", color: "#4A90D9", bgColor: "#E6F2FF" },
      { type: "career", name: "就业指导", icon: "/images/icon-job.png", color: "#52C41A", bgColor: "#E6F9ED" },
      { type: "civil", name: "考公评估", icon: "/images/icon-civil.png", color: "#FA8C16", bgColor: "#FFF3E6" },
      { type: "major", name: "转专业分析", icon: "/images/icon-transfer.png", color: "#722ED1", bgColor: "#F0E6FF" }
    ]
  },
  
  onLoad() {
    const info = wx.getSystemInfoSync();
    this.setData({ statusBarHeight: info.statusBarHeight });
    this.loadAgents();
  },

  onShow() {
    this.loadGrowthState();
  },

  async loadGrowthState() {
    const userId = wx.getStorageSync("userId") || app.globalData.userId || "";
    if (!userId) return;
    try {
      const state = await app.request({ url: `/api/v1/growth/state/${userId}` });
      if (!state || !state.session_id) {
        this.setData({ activeSession: null });
        return;
      }
      const names = {
        graduate: "考研规划",
        career: "就业指导",
        employment: "就业指导",
        civil: "考公评估",
        major: "转专业分析"
      };
      const stageTexts = {
        questioning: "信息收集中",
        awaiting: "等待开始分析",
        analyzing: "待确认分析",
        report: "报告已生成"
      };
      this.setData({
        activeSession: {
          ...state,
          name: names[state.agent] || "成长规划",
          stageText: state.finished || state.has_report ? "报告已生成" : (stageTexts[state.stage] || "进行中"),
          stepText: state.finished || state.has_report ? "可查看完整报告" : `已完成 ${state.current_step || 0}/${state.total_steps || 5} 轮信息采集`
        }
      });
    } catch (err) {
      console.error("加载成长状态失败:", err);
    }
  },
  
  async loadAgents() {
    try {
      const res = await api.getAgents();
      if (res.agents && res.agents.length) {
        const icons = {
          graduate: "/images/icon-postgrad.png",
          career: "/images/icon-job.png",
          civil: "/images/icon-civil.png",
          major: "/images/icon-transfer.png"
        };
        const colors = {
          graduate: "#4A90D9",
          career: "#52C41A",
          civil: "#FA8C16",
          major: "#722ED1"
        };
        const bgs = {
          graduate: "#E6F2FF",
          career: "#E6F9ED",
          civil: "#FFF3E6",
          major: "#F0E6FF"
        };
        this.setData({
          agents: res.agents.map(a => ({
            type: a.type,
            name: a.name || a.label,
            icon: icons[a.type] || "/images/icon-postgrad.png",
            color: colors[a.type] || "#4A90D9",
            bgColor: bgs[a.type] || "#E6F2FF"
          }))
        });
      }
    } catch (err) {
      console.error('加载 agents 失败:', err);
      // 使用默认数据
    }
  },
  
  goBack() { wx.switchTab({ url: "/pages/index/index" }); },

  goHistory() { wx.navigateTo({ url: "/pages/history/history?type=plan" }); },

  continueSession() {
    const session = this.data.activeSession;
    if (!session) return;
    if (session.finished || session.has_report) {
      wx.navigateTo({
        url: `/pages/report/report?session_id=${session.session_id}&agent_type=${session.agent}`
      });
      return;
    }
    wx.navigateTo({
      url: `/pages/chatroom/chatroom?mode=resume&session_id=${session.session_id}&agent=${session.agent}`
    });
  },
  
  goDetail(e) {
    wx.navigateTo({
      url: `/pages/chatroom/chatroom?mode=agent&agent=${e.currentTarget.dataset.type}`
    });
  },

  async goChat() {
    wx.showLoading({ title: "启动中..." });
    try {
      const userId = wx.getStorageSync("userId") || app.globalData.userId || "";
      const res = await api.startSandbox(userId);
      wx.hideLoading();
      wx.navigateTo({
        url: `/pages/chatroom/chatroom?mode=sandbox&session_id=${res.session_id || ""}`
      });
    } catch (err) {
      wx.hideLoading();
      wx.showToast({ title: "启动失败，请重试", icon: "none" });
    }
  }
});
