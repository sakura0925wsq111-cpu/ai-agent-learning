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
    actionPlan: [],
    firstPhaseKey: "phase_1",
    firstPhaseCount: 0,
    planStarted: false,
    syncing: false,
    requestedAction: "",
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
      themeColor: meta.color || "#667EEA",
      requestedAction: options.action || ""
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
      const actionPlan = Array.isArray(report.action_plan) ? report.action_plan : [];
      const firstPhase = actionPlan[0] || {};
      const firstPhaseTasks = Array.isArray(firstPhase.tasks) ? firstPhase.tasks : [];
      this.setData({
        agent,
        reportTitle: meta.title || this.data.reportTitle,
        themeColor: meta.color || this.data.themeColor,
        createTime: this.formatTime(res.created_at || new Date()),
        summary: report.summary || report.current_status || "规划报告已生成，以下是你的详细分析与行动路径。",
        sections: this.buildSections(report),
        actionPlan,
        firstPhaseKey: firstPhase.phase_key || firstPhase.key || "phase_1",
        firstPhaseCount: firstPhaseTasks.length,
        loading: false,
        error: false
      });
      await this.loadPlanProgress();
      if (this.data.requestedAction === "sync" && !this.data.planStarted) {
        this.setData({ requestedAction: "" });
        setTimeout(() => this.startExecution(), 250);
      }
    } catch (err) {
      this.setData({ loading: false, error: true });
    }
  },

  async loadPlanProgress() {
    const userId = wx.getStorageSync("userId") || app.globalData.userId || "";
    if (!userId || !this.data.sessionId) return;
    try {
      const progress = await app.request({
        url: `/api/v1/today/progress?user_id=${userId}&growth_session_id=${this.data.sessionId}`
      });
      this.setData({ planStarted: Boolean(progress && progress.total > 0) });
    } catch (err) {
      console.warn("读取计划执行进度失败:", err);
    }
  },

  startExecution() {
    if (this.data.syncing) return;
    if (!this.data.firstPhaseCount) {
      wx.showToast({ title: "报告中暂无可同步任务", icon: "none" });
      return;
    }
    wx.showModal({
      title: "开始执行第一阶段",
      content: `将${this.data.firstPhaseCount}项任务加入今日任务。稍后仍可修改截止时间。`,
      confirmText: "确认加入",
      cancelText: "再看看",
      success: (result) => {
        if (result.confirm) this.syncFirstPhase();
      }
    });
  },

  async syncFirstPhase() {
    const userId = wx.getStorageSync("userId") || app.globalData.userId || "";
    if (!userId || this.data.syncing) return;
    this.setData({ syncing: true });
    wx.showLoading({ title: "正在加入任务...", mask: true });
    try {
      const result = await app.request({
        method: "POST",
        url: "/api/v1/today/sync-plan",
        data: {
          user_id: userId,
          growth_session_id: this.data.sessionId,
          phase: this.data.firstPhaseKey
        }
      });
      wx.hideLoading();
      this.setData({ planStarted: true, syncing: false });
      wx.showModal({
        title: result.already_synced ? "任务已经加入" : "执行计划已启动",
        content: result.already_synced
          ? "无需重复添加，可以直接查看现有任务。"
          : `已加入${result.synced_count || 0}项任务，完成情况会同步回成长模式。`,
        confirmText: "查看任务",
        cancelText: "留在报告",
        success: (modalResult) => { if (modalResult.confirm) this.viewTasks(); }
      });
    } catch (err) {
      wx.hideLoading();
      this.setData({ syncing: false });
      wx.showToast({ title: "任务加入失败，请重试", icon: "none" });
    }
  },

  viewTasks() {
    wx.navigateTo({ url: "/pages/tasks/tasks?source=ai_plan" });
  },

  continueCoach() {
    wx.navigateTo({
      url: `/pages/chatroom/chatroom?mode=coach&session_id=${this.data.sessionId}&agent=${this.data.agent}`
    });
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
