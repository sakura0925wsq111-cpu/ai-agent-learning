const app = getApp();

Page({
  data: { statusBarHeight: 44, sessionId: "", reportTitle: "个人发展规划报告", createTime: "", themeColor: "#667EEA", summary: "", sections: [] },

  onLoad(options) {
    const info = wx.getSystemInfoSync(); this.setData({ statusBarHeight: info.statusBarHeight });
    const { session_id, agent_type } = options; this.setData({ sessionId: session_id || "" });
    const colors = { graduate: "#4A90D9", employment: "#52C41A", civil: "#FA8C16", major: "#722ED1" };
    this.setData({ themeColor: colors[agent_type] || "#667EEA" });
    const titles = { graduate: "考研规划报告", employment: "就业指导报告", civil: "考公评估报告", major: "转专业分析报告" };
    if (titles[agent_type]) this.setData({ reportTitle: titles[agent_type] });
    this.loadReport();
  },

  async loadReport() {
    wx.showLoading({ title: "加载中..." });
    try {
      const res = await app.request({ url: `/api/v1/growth/report/${this.data.sessionId}` });
      const report = res.report || {};
      this.setData({ createTime: this.formatTime(res.created_at || new Date()), summary: report.summary || res.summary || "", sections: report.sections || res.sections || this.getDefaultSections() });
    } catch (err) { this.setData({ createTime: this.formatTime(new Date()), summary: "基于你的背景和诉求，AI为你制定了以下发展规划。本报告包含目标分析、行动路径、时间节点等关键内容，建议结合实际情况灵活调整。", sections: this.getDefaultSections() }); }
    wx.hideLoading();
  },

  getDefaultSections() { return [
    { title: "现状分析", type: "text", content: "你目前处于专业学习的关键阶段，具备扎实的理论基础，但缺乏明确的职业方向。建议通过实习、项目实践等方式探索兴趣领域。" },
    { title: "核心目标", type: "list", items: ["短期（1-3个月）：完成技能摸底，确定2-3个候选方向", "中期（3-6个月）：深入调研目标领域，积累相关项目经验", "长期（6-12个月）：明确发展方向，制定详细的执行计划"] },
    { title: "行动路径", type: "timeline", events: [{ time: "第1个月", description: "完成职业测评，梳理个人优势与兴趣" }, { time: "第2-3个月", description: "参与2个以上实践项目，验证方向可行性" }, { time: "第4-6个月", description: "针对性提升技能，准备简历与面试" }, { time: "第7-12个月", description: "投递目标岗位，持续优化执行策略" }] },
    { title: "关键指标", type: "stats", stats: [{ value: "3+", label: "实践项目" }, { value: "85%", label: "目标达成率" }, { value: "2周", label: "迭代周期" }] },
    { title: "风险提示", type: "list", items: ["避免过度规划而忽视执行，建议每月复盘调整", "关注行业动态变化，保持策略灵活性", "建立支持网络，寻求导师或同伴反馈"] }
  ]; },

  formatTime(dateStr) { const d = new Date(dateStr); const now = new Date(); if (d.toDateString() === now.toDateString()) return `今天 ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; return `${d.getMonth() + 1}月${d.getDate()}日 ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; },

  async downloadPDF() {
    const pdfUrl = `${app.globalData.baseUrl}/api/v1/growth/report/${this.data.sessionId}/pdf`;
    wx.showLoading({ title: "下载中..." });
    try { const res = await wx.downloadFile({ url: pdfUrl }); if (res.statusCode === 200) await wx.openDocument({ filePath: res.tempFilePath, fileType: "pdf" }); else throw new Error("下载失败"); } catch (err) { wx.showToast({ title: "PDF生成中，请稍后", icon: "none" }); }
    wx.hideLoading();
  },

  saveToAlbum() { wx.showToast({ title: "功能开发中", icon: "none" }); },
  shareReport() {},
  viewHistory() { wx.navigateTo({ url: "/pages/history/history?type=report" }); },
  startNewPlan() { wx.switchTab({ url: "/pages/index/index" }); },
  goBack() { wx.navigateBack(); },
  onShareAppMessage() { return { title: this.data.reportTitle, path: `/pages/report/report?session_id=${this.data.sessionId}&shared=1` }; }
});
