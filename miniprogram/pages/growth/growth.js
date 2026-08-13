const api = require("../../utils/api.js");
const app = getApp();

const AGENT_META = {
  graduate: { name: "考研规划", short: "研", icon: "/images/icon-postgrad.png", className: "agent-blue", desc: "院校选择与备考路径" },
  career: { name: "就业指导", short: "职", icon: "/images/icon-job.png", className: "agent-green", desc: "职业定位与求职准备" },
  employment: { name: "就业指导", short: "职", icon: "/images/icon-job.png", className: "agent-green", desc: "职业定位与求职准备" },
  civil: { name: "考公评估", short: "公", icon: "/images/icon-civil.png", className: "agent-orange", desc: "岗位匹配与备考评估" },
  major: { name: "转专业分析", short: "转", icon: "/images/icon-transfer.png", className: "agent-purple", desc: "条件差异与风险分析" }
};

const COACH_PROMPTS = {
  check_in: "我想汇报一下最近的执行进展",
  blocked: "我最近执行计划时遇到了一些困难",
  weekly_review: "请结合我的实际任务完成情况，帮我复盘本周"
};

Page({
  data: {
    statusBarHeight: 44,
    userId: "",
    pageState: "new",
    dashboardLoading: true,
    activeSession: null,
    activePlan: null,
    latestReport: null,
    reportCount: 0,
    coachSummary: "",
    agents: Object.keys(AGENT_META)
      .filter((key) => key !== "employment")
      .map((key) => ({ type: key, ...AGENT_META[key] }))
  },

  onLoad() {
    const info = wx.getSystemInfoSync();
    const userId = wx.getStorageSync("userId") || app.globalData.userId || "";
    this.setData({ statusBarHeight: info.statusBarHeight, userId });
    this.loadAgents();
  },

  onShow() {
    this.loadDashboard();
  },

  async loadDashboard() {
    const userId = this.data.userId || wx.getStorageSync("userId") || app.globalData.userId || "";
    if (!userId) {
      this.setData({ dashboardLoading: false, pageState: "new" });
      return;
    }
    this.setData({ dashboardLoading: true });
    try {
      const data = await app.request({ url: `/api/v1/growth/dashboard/${userId}` });
      const activeSession = data.active_session ? this.formatActiveSession(data.active_session) : null;
      const activePlan = data.active_plan ? {
        ...data.active_plan,
        percent: Math.max(0, Math.min(100, Math.round((data.active_plan.progress || 0) * 100)))
      } : null;
      const latestReport = data.latest_report ? {
        ...data.latest_report,
        displayTime: this.formatDate(data.latest_report.created_at)
      } : null;
      this.setData({
        pageState: data.page_state || "new",
        activeSession,
        activePlan,
        latestReport,
        reportCount: data.report_count || 0,
        coachSummary: (data.coach && data.coach.last_summary) || "",
        dashboardLoading: false
      });
    } catch (err) {
      console.error("加载成长首页失败:", err);
      await this.loadLegacyState();
    }
  },

  async loadLegacyState() {
    try {
      const state = await app.request({ url: `/api/v1/growth/state/${this.data.userId}` });
      if (!state || !state.session_id) {
        this.setData({ pageState: "new", activeSession: null, dashboardLoading: false });
        return;
      }
      if (state.finished || state.has_report) {
        const meta = AGENT_META[state.agent] || AGENT_META.career;
        this.setData({
          pageState: "report_ready",
          activeSession: null,
          latestReport: {
            session_id: state.session_id,
            agent: state.agent,
            title: `${meta.name}报告`,
            summary: "完整规划报告已生成",
            displayTime: this.formatDate(state.updated_at || state.created_at)
          },
          reportCount: 1,
          dashboardLoading: false
        });
      } else {
        this.setData({
          pageState: "planning",
          activeSession: this.formatActiveSession(state),
          dashboardLoading: false
        });
      }
    } catch (err) {
      this.setData({ dashboardLoading: false, pageState: "new" });
      wx.showToast({ title: "成长状态加载失败", icon: "none" });
    }
  },

  formatActiveSession(state) {
    const meta = AGENT_META[state.agent] || AGENT_META.career;
    const stageTexts = {
      questioning: "信息收集中",
      awaiting: "等待开始分析",
      analyzing: "待确认分析",
      report: "报告生成中"
    };
    return {
      ...state,
      name: meta.name,
      stageText: stageTexts[state.stage] || "规划进行中",
      stepText: `已完成 ${state.current_step || 0}/${state.total_steps || 5} 轮信息采集`
    };
  },

  async loadAgents() {
    try {
      const res = await api.getAgents();
      if (!res.agents || !res.agents.length) return;
      const agents = res.agents
        .filter((item) => item.type !== "employment")
        .map((item) => ({
          type: item.type,
          ...(AGENT_META[item.type] || AGENT_META.career),
          name: item.name || item.label || (AGENT_META[item.type] || AGENT_META.career).name
        }));
      this.setData({ agents });
    } catch (err) {
      console.error("加载专项能力失败:", err);
    }
  },

  formatDate(value) {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    return `${date.getMonth() + 1}月${date.getDate()}日`;
  },

  goBack() { wx.switchTab({ url: "/pages/index/index" }); },

  goReportCenter() { wx.navigateTo({ url: "/pages/history/history?type=plan" }); },

  continueSession() {
    const session = this.data.activeSession;
    if (!session) return;
    wx.navigateTo({
      url: `/pages/chatroom/chatroom?mode=resume&session_id=${session.session_id}&agent=${session.agent}`
    });
  },

  viewLatestReport() {
    const report = this.data.latestReport;
    if (!report) return;
    wx.navigateTo({
      url: `/pages/report/report?session_id=${report.session_id}&agent_type=${report.agent}`
    });
  },

  startExecution() {
    const report = this.data.latestReport;
    if (!report) return;
    wx.navigateTo({
      url: `/pages/report/report?session_id=${report.session_id}&agent_type=${report.agent}&action=sync`
    });
  },

  goCoach(e) {
    const report = this.data.latestReport;
    if (!report) {
      this.goChat();
      return;
    }
    const intent = e && e.currentTarget ? e.currentTarget.dataset.intent : "";
    const prompt = COACH_PROMPTS[intent] || "我想继续聊聊目前的成长计划";
    wx.navigateTo({
      url: `/pages/chatroom/chatroom?mode=coach&session_id=${report.session_id}&agent=${report.agent}&prompt=${encodeURIComponent(prompt)}`
    });
  },

  goDetail(e) {
    wx.navigateTo({
      url: `/pages/chatroom/chatroom?mode=agent&agent=${e.currentTarget.dataset.type}`
    });
  },

  async goChat() {
    if (this.data.dashboardLoading) return;
    wx.showLoading({ title: "启动中...", mask: true });
    try {
      const res = await api.startSandbox(this.data.userId);
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
