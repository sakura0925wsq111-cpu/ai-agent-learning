const app = getApp();

Page({
  data: {
    statusBarHeight: 44, sessionId: "", reportTitle: "个人发展规划报告",
    createTime: "", themeColor: "#667EEA", summary: "", sections: [],
    loading: true, error: false
  },

  onLoad(options) {
    const info = wx.getSystemInfoSync();
    this.setData({ statusBarHeight: info.statusBarHeight });
    const { session_id, agent_type } = options;
    this.setData({ sessionId: session_id || "" });
    const colors = { graduate: "#4A90D9", employment: "#52C41A", civil: "#FA8C16", major: "#722ED1", career: "#52C41A" };
    this.setData({ themeColor: colors[agent_type] || "#667EEA" });
    const titles = { graduate: "考研规划报告", employment: "就业指导报告", civil: "考公评估报告", major: "转专业分析报告", career: "就业指导报告" };
    if (titles[agent_type]) this.setData({ reportTitle: titles[agent_type] });
    this.loadReport();
  },

  async loadReport() {
    wx.showLoading({ title: "加载中..." });
    try {
      const res = await app.request({ url: `/api/v1/growth/report/${this.data.sessionId}` });
      const report = res.report || {};
      this.setData({
        createTime: this.formatTime(res.created_at || new Date()),
        summary: report.summary || "",
        sections: this.buildSections(report),
        loading: false
      });
    } catch (err) {
      this.setData({ createTime: this.formatTime(new Date()), loading: false, error: true });
    }
    wx.hideLoading();
  },

  buildSections(report) {
    const sections = [];

    // 现状分析
    if (report.current_status || report.main_problem) {
      sections.push({
        title: "现状分析",
        type: "text",
        content: [report.current_status, report.main_problem].filter(Boolean).join("\n\n")
      });
    }

    // 核心目标
    if (report.goal) {
      sections.push({
        title: "核心目标",
        type: "text",
        content: report.goal
      });
    }

    // 优势
    const advantages = report.advantages || [];
    if (advantages.length > 0) {
      sections.push({
        title: "个人优势",
        type: "list",
        items: advantages.map(a => a.point + (a.detail ? "：" + a.detail : ""))
      });
    }

    // 风险
    const risks = report.risks || [];
    if (risks.length > 0) {
      sections.push({
        title: "风险提示",
        type: "list",
        items: risks.map(r => r.risk + (r.mitigation ? " — " + r.mitigation : ""))
      });
    }

    // 行动计划
    const actionPlan = report.action_plan || [];
    if (actionPlan.length > 0) {
      const events = [];
      actionPlan.forEach((phase, i) => {
        const tasks = (phase.tasks || []).map(t => t.task).join("；");
        events.push({
          time: phase.phase || phase.duration || ("阶段" + (i + 1)),
          description: tasks || phase.detail || ""
        });
      });
      sections.push({
        title: "行动路径",
        type: "timeline",
        events: events
      });
    }

    return sections;
  },

  formatTime(dateStr) {
    const d = new Date(dateStr);
    const now = new Date();
    if (isNaN(d.getTime())) return "";
    const pad = n => String(n).padStart(2, "0");
    if (d.toDateString() === now.toDateString()) {
      return "今天 " + pad(d.getHours()) + ":" + pad(d.getMinutes());
    }
    return (d.getMonth() + 1) + "月" + d.getDate() + "日 " + pad(d.getHours()) + ":" + pad(d.getMinutes());
  },

  async downloadPDF() {
    wx.showToast({ title: "功能开发中", icon: "none" });
  },

  saveToAlbum() { wx.showToast({ title: "功能开发中", icon: "none" }); },
  shareReport() {},
  startNewPlan() { wx.switchTab({ url: "/pages/index/index" }); },
  goBack() { wx.navigateBack(); },
  onShareAppMessage() {
    return { title: this.data.reportTitle, path: "/pages/report/report?session_id=" + this.data.sessionId };
  }
});