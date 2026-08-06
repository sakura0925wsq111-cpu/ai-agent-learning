const app = getApp();

Page({
  data: {
    statusBarHeight: 44,
    sessionId: "",
    reportTitle: "个人发展规划报告",
    createTime: "",
    themeColor: "#667EEA",
    summary: "",
    sections: [],
    loading: true,
    error: false,
    // ========== 新增：同步功能数据 ==========
    agent: "",
    phases: [],
    showSyncModal: false,
    syncing: false,
    syncedPhases: []
    // ========== 新增结束 ==========
  },

  onLoad(options) {
    const info = wx.getSystemInfoSync();
    this.setData({ statusBarHeight: info.statusBarHeight });
    const { session_id, agent_type } = options;
    this.setData({
      sessionId: session_id || "",
      agent: agent_type || "career"
    });
    const colors = {
      graduate: "#4A90D9",
      employment: "#52C41A",
      civil: "#FA8C16",
      major: "#722ED1",
      career: "#52C41A"
    };
    this.setData({ themeColor: colors[agent_type] || "#667EEA" });
    const titles = {
      graduate: "考研规划报告",
      employment: "就业指导报告",
      civil: "考公评估报告",
      major: "转专业分析报告",
      career: "就业指导报告"
    };
    if (titles[agent_type]) {
      this.setData({ reportTitle: titles[agent_type] });
    }
    this.loadReport();
    // ========== 新增：加载已同步状态 ==========
    this.loadSyncedState();
    // ========== 新增结束 ==========
  },

  async loadReport() {
    wx.showLoading({ title: "加载中..." });
    try {
      const res = await app.request({
        url: `/api/v1/growth/report/${this.data.sessionId}`
      });
      const report = res.report || {};
      this.setData({
        createTime: this.formatTime(res.created_at || new Date()),
        summary: report.summary || "",
        sections: this.buildSections(report),
        loading: false
      });
      // ========== 新增：解析阶段数据用于同步 ==========
      this.parsePhases(report.action_plan || []);
      // ========== 新增结束 ==========
    } catch (err) {
      this.setData({
        createTime: this.formatTime(new Date()),
        loading: false,
        error: true
      });
    }
    wx.hideLoading();
  },

  // ========== 新增：解析阶段数据 ==========
  parsePhases(actionPlan) {
    const phases = actionPlan.map((phase, index) => {
      const phaseKey = `phase_${index + 1}`;
      let name = "";
      let taskCount = 0;

      if (typeof phase === "string") {
        name = `阶段${index + 1}`;
        taskCount = 1;
      } else if (typeof phase === "object") {
        name = phase.phase || phase.name || phase.title || `阶段${index + 1}`;
        const tasks = phase.tasks || [];
        taskCount = tasks.length || 1;
      }

      return {
        key: phaseKey,
        name: name,
        taskCount: taskCount,
        index: index + 1
      };
    });

    this.setData({ phases: phases });
  },
  // ========== 新增结束 ==========

  // ========== 新增：加载已同步状态 ==========
  loadSyncedState() {
    const syncedMap = wx.getStorageSync("syncedGrowthSessions") || {};
    const sessionSync = syncedMap[this.data.sessionId];
    if (sessionSync && sessionSync.syncedPhases) {
      this.setData({ syncedPhases: sessionSync.syncedPhases });
    }
  },
  // ========== 新增结束 ==========

  buildSections(report) {
    const sections = [];

    const status = report.current_status || report.main_problem || "";
    if (status) {
      sections.push({ title: "现状分析", type: "text", content: status });
    }

    if (report.goal) {
      sections.push({ title: "核心目标", type: "text", content: report.goal });
    }

    const advantages = report.advantages || [];
    const advItems = advantages
      .map((a) => {
        if (typeof a === "string") return a;
        if (typeof a === "object") {
          const vals = Object.values(a).filter(
            (v) => v && typeof v === "string"
          );
          return vals.slice(0, 2).join("：") || JSON.stringify(a);
        }
        return String(a);
      })
      .filter((v) => v);
    if (advItems.length > 0) {
      sections.push({ title: "个人优势", type: "list", items: advItems });
    }

    const risks = report.risks || [];
    const riskItems = risks
      .map((r) => {
        if (typeof r === "string") return r;
        if (typeof r === "object") {
          const vals = Object.values(r).filter(
            (v) => v && typeof v === "string"
          );
          return vals.slice(0, 2).join(" — ") || JSON.stringify(r);
        }
        return String(r);
      })
      .filter((v) => v);
    if (riskItems.length > 0) {
      sections.push({ title: "风险提示", type: "list", items: riskItems });
    }

    const actionPlan = report.action_plan || [];
    const events = [];
    actionPlan.forEach((phase, i) => {
      if (typeof phase === "string") {
        events.push({ time: "阶段" + (i + 1), description: phase });
      } else if (typeof phase === "object") {
        const name =
          phase.phase || phase.name || phase.title || "阶段" + (i + 1);
        const duration = phase.duration || phase.timeline || "";
        const tasks = phase.tasks || [];
        let desc = "";
        if (tasks.length > 0) {
          desc = tasks
            .map((t) => {
              if (typeof t === "string") return t;
              if (typeof t === "object") {
                const tvals = Object.values(t).filter(
                  (v) => v && typeof v === "string"
                );
                return tvals[1] || tvals[0] || "";
              }
              return String(t);
            })
            .filter((v) => v)
            .join("；");
        }
        if (!desc) {
          const vals = Object.values(phase).filter(
            (v) =>
              typeof v === "string" &&
              v.length > 0 &&
              v !== name &&
              v !== duration
          );
          desc = vals[0] || "";
        }
        events.push({
          time: name + (duration ? "（" + duration + "）" : ""),
          description: desc
        });
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
    const pad = (n) => String(n).padStart(2, "0");
    if (d.toDateString() === now.toDateString()) {
      return "今天 " + pad(d.getHours()) + ":" + pad(d.getMinutes());
    }
    return (
      d.getMonth() +
      1 +
      "月" +
      d.getDate() +
      "日 " +
      pad(d.getHours()) +
      ":" +
      pad(d.getMinutes())
    );
  },

  async downloadPDF() {
    wx.showToast({ title: "功能开发中", icon: "none" });
  },

  saveToAlbum() {
    wx.showToast({ title: "功能开发中", icon: "none" });
  },
  shareReport() {},
  startNewPlan() {
    wx.switchTab({ url: "/pages/index/index" });
  },
  goBack() {
    wx.navigateBack();
  },
  onShareAppMessage() {
    return {
      title: this.data.reportTitle,
      path: "/pages/report/report?session_id=" + this.data.sessionId
    };
  },

  // ========== 新增：同步到今日待办功能 ==========

  // 打开同步弹窗
  openSyncModal() {
    this.setData({ showSyncModal: true });
  },

  // 关闭同步弹窗
  closeSyncModal() {
    this.setData({ showSyncModal: false });
  },

  // 选择阶段
  selectPhase(e) {
    const { key } = e.currentTarget.dataset;
    const { syncedPhases } = this.data;

    // 已同步的不能选
    if (syncedPhases.includes(key)) {
      return;
    }

    // 单选逻辑：选中或取消选中
    const selectedPhase = this.data.selectedPhase === key ? "" : key;
    this.setData({ selectedPhase: selectedPhase });
  },

  // 确认同步
  async confirmSync() {
    const { selectedPhase, sessionId, agent, userId } = this.data;

    if (!selectedPhase) {
      wx.showToast({ title: "请选择一个阶段", icon: "none" });
      return;
    }

    this.setData({ syncing: true });

    try {
      const res = await app.request({
        method: "POST",
        url: "/api/v1/today/sync-plan",
        data: {
          user_id: userId || wx.getStorageSync("userId") || "",
          growth_session_id: sessionId,
          phase: selectedPhase
        }
      });

      const syncedCount = res.synced_count || 0;

      // 更新已同步状态
      const newSyncedPhases = [...this.data.syncedPhases, selectedPhase];
      this.setData({
        syncedPhases: newSyncedPhases,
        selectedPhase: "",
        showSyncModal: false,
        syncing: false
      });

      // 写入 storage，供 chatroom 读取
      const syncedMap = wx.getStorageSync("syncedGrowthSessions") || {};
      syncedMap[sessionId] = {
        agent: agent,
        syncedAt: Date.now(),
        syncedPhases: newSyncedPhases,
        lastSyncPhase: selectedPhase
      };
      wx.setStorageSync("syncedGrowthSessions", syncedMap);

      wx.showToast({
        title: `已同步 ${syncedCount} 项任务`,
        icon: "success"
      });
    } catch (err) {
      this.setData({ syncing: false });
      wx.showToast({ title: "同步失败，请重试", icon: "none" });
    }
  }

  // ========== 新增结束 ==========
});
