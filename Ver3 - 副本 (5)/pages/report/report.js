const app = getApp();

const REPORT_META = {
  graduate: { title: "考研规划报告", color: "#4A90D9" },
  employment: { title: "就业指导报告", color: "#52C41A" },
  career: { title: "就业指导报告", color: "#52C41A" },
  civil: { title: "考公评估报告", color: "#FA8C16" },
  major: { title: "转专业分析报告", color: "#722ED1" }
};

Page({
  data: {
    statusBarHeight: 44,
    sessionId: "",
    agent: "career",
    reportTitle: "个人发展规划报告",
    createTime: "",
    themeColor: "#667EEA",
    summary: "",
    sections: [],
    loading: true,
    error: false
  },

  onLoad(options) {
    const info = wx.getSystemInfoSync();
    const agent = options.agent_type || "career";
    const meta = REPORT_META[agent] || {};
    this.setData({
      statusBarHeight: info.statusBarHeight,
      sessionId: options.session_id || "",
      agent,
      reportTitle: meta.title || "个人发展规划报告",
      themeColor: meta.color || "#667EEA"
    });
    this.loadReport();
  },

  async loadReport() {
    if (!this.data.sessionId) {
      this.setData({ loading: false, error: true });
      return;
    }
    this.setData({ loading: true, error: false });
    try {
      const res = await app.request({ url: `/api/v1/growth/report/${this.data.sessionId}` });
      const report = res.report || {};
      const agent = res.agent || this.data.agent;
      const meta = REPORT_META[agent] || {};
      this.setData({
        agent,
        reportTitle: meta.title || this.data.reportTitle,
        themeColor: meta.color || this.data.themeColor,
        createTime: this.formatTime(res.created_at || new Date()),
        summary: report.summary || report.current_status || "规划报告已生成，以下是你的详细分析与行动路径。",
        sections: this.buildSections(report),
        loading: false,
        error: false
      });
    } catch (err) {
      this.setData({ loading: false, error: true });
    }
  },

  buildSections(report) {
    const sections = [];
    const status = report.current_status || report.main_problem || "";
    if (status) sections.push({ title: "现状分析", type: "text", content: status });
    if (report.goal) sections.push({ title: "核心目标", type: "text", content: report.goal });

    const advantages = this.toTextItems(report.advantages || [], "：");
    if (advantages.length) sections.push({ title: "个人优势", type: "list", items: advantages });

    const risks = this.toTextItems(report.risks || [], " — ");
    if (risks.length) sections.push({ title: "风险提示", type: "list", items: risks });

    const events = (report.action_plan || []).map((phase, index) => {
      if (typeof phase === "string") {
        return { time: `阶段${index + 1}`, description: phase };
      }
      if (!phase || typeof phase !== "object") return null;
      const name = phase.phase || phase.name || phase.title || `阶段${index + 1}`;
      const duration = phase.duration || phase.timeline || "";
      const tasks = (phase.tasks || []).map((task) => {
        if (typeof task === "string") return task;
        if (!task || typeof task !== "object") return "";
        return task.task || task.title || task.name || Object.values(task).find((value) => typeof value === "string") || "";
      }).filter(Boolean);
      const description = tasks.join("；") || phase.description || phase.detail || phase.expected_outcome || "";
      return { time: name + (duration ? `（${duration}）` : ""), description };
    }).filter(Boolean);
    if (events.length) sections.push({ title: "行动路径", type: "timeline", events });
    return sections;
  },

  toTextItems(items, separator) {
    return items.map((item) => {
      if (typeof item === "string") return item;
      if (!item || typeof item !== "object") return "";
      return Object.values(item).filter((value) => value && typeof value === "string").slice(0, 2).join(separator);
    }).filter(Boolean);
  },

  formatTime(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    const pad = (n) => String(n).padStart(2, "0");
    return `${date.getFullYear()}年${pad(date.getMonth() + 1)}月${pad(date.getDate())}日 ${pad(date.getHours())}:${pad(date.getMinutes())}`;
  },

  viewHistory() {
    wx.navigateTo({ url: "/pages/history/history?type=plan" });
  },

  startNewPlan() {
    wx.switchTab({ url: "/pages/growth/growth" });
  },

  goBack() {
    if (getCurrentPages().length > 1) wx.navigateBack({ delta: 1 });
    else wx.switchTab({ url: "/pages/growth/growth" });
  },

  onShareAppMessage() {
    return {
      title: this.data.reportTitle,
      path: `/pages/report/report?session_id=${this.data.sessionId}&agent_type=${this.data.agent}`
    };
  }
});
