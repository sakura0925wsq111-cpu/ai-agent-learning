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
    const status = report.current_status || report.main_problem || "";
    if (status) {
      sections.push({ title: "现状分析", type: "text", content: status });
    }

    // 核心目标
    if (report.goal) {
      sections.push({ title: "核心目标", type: "text", content: report.goal });
    }

    // 个人优势 - 防御性取值
    const advantages = report.advantages || [];
    const advItems = advantages.map(a => {
      if (typeof a === "string") return a;
      if (typeof a === "object") {
        const vals = Object.values(a).filter(v => v && typeof v === "string");
        return vals.slice(0, 2).join("：") || JSON.stringify(a);
      }
      return String(a);
    }).filter(v => v);
    if (advItems.length > 0) {
      sections.push({ title: "个人优势", type: "list", items: advItems });
    }

    // 风险提示 - 防御性取值
    const risks = report.risks || [];
    const riskItems = risks.map(r => {
      if (typeof r === "string") return r;
      if (typeof r === "object") {
        const vals = Object.values(r).filter(v => v && typeof v === "string");
        return vals.slice(0, 2).join(" — ") || JSON.stringify(r);
      }
      return String(r);
    }).filter(v => v);
    if (riskItems.length > 0) {
      sections.push({ title: "风险提示", type: "list", items: riskItems });
    }

    // 行动路径 - 防御性取值
    const actionPlan = report.action_plan || [];
    const events = [];
    actionPlan.forEach((phase, i) => {
      if (typeof phase === "string") {
        events.push({ time: "阶段" + (i + 1), description: phase });
      } else if (typeof phase === "object") {
        const name = phase.phase || phase.name || phase.title || ("阶段" + (i + 1));
        const duration = phase.duration || phase.timeline || "";
        const tasks = phase.tasks || [];
        let desc = "";
        if (tasks.length > 0) {
          desc = tasks.map(t => {
            if (typeof t === "string") return t;
            if (typeof t === "object") {
              const tvals = Object.values(t).filter(v => v && typeof v === "string");
              return tvals[1] || tvals[0] || "";
            }
            return String(t);
          }).filter(v => v).join("；");
        }
        if (!desc) {
          const vals = Object.values(phase).filter(v => typeof v === "string" && v.length > 0 && v !== name && v !== duration);
          desc = vals[0] || "";
        }
        events.push({ time: name + (duration ? "（" + duration + "）" : ""), description: desc });
      }
    });
    if (events.length > 0) {
      sections.push({ title: "行动路径", type: "timeline", events: events });
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