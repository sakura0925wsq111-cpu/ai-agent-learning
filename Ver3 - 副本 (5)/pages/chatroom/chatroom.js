const app = getApp();

const AGENT_NAMES = {
  career: "就业指导",
  employment: "就业指导",
  graduate: "考研规划",
  civil: "考公评估",
  major: "转专业分析"
};

Page({
  data: {
    statusBarHeight: 44,
    mode: "sandbox",
    coachMode: false,
    agent: "career",
    agentName: "决策教练",
    sessionId: "",
    sourceSandboxSessionId: "",
    sessionStage: "questioning",
    userId: "",
    messages: [],
    inputValue: "",
    inputPlaceholder: "有什么想聊的吗？",
    isLoading: false,
    loadingText: "正在思考...",
    showQuickActions: true,
    showCards: false,
    cards: [],
    scrollToView: "",
    showAnalysisCard: false,
    reportReady: false,
    selectingPaths: false,
    selectedPaths: [],
    progress: 0,
    showRetry: false,
    retryKind: "",
    lastFailedMessage: "",
    pendingPrompt: "",
    reportNavigating: false,
    quickOptions: [
      "不知道考研还是就业",
      "想转专业但不确定方向",
      "考公和找工作怎么选",
      "帮我分析一下我的情况"
    ]
  },

  onLoad(options) {
    const info = wx.getSystemInfoSync();
    const userId = wx.getStorageSync("userId") || app.globalData.userId || "";
    const mode = options.mode || "sandbox";
    const sessionId = options.session_id || "";
    const sourceSandboxSessionId = options.sandbox_session_id || "";
    const agent = options.agent || "career";
    const coachMode = mode === "coach";
    let pendingPrompt = options.prompt || "";
    try { pendingPrompt = decodeURIComponent(pendingPrompt); } catch (err) {}

    this.setData({
      statusBarHeight: info.statusBarHeight,
      mode,
      coachMode,
      agent,
      agentName: coachMode ? "成长教练" : (mode === "sandbox" ? "决策教练" : (AGENT_NAMES[agent] || "成长规划")),
      sessionId,
      sourceSandboxSessionId,
      userId,
      pendingPrompt,
      showQuickActions: mode === "sandbox" || coachMode,
      quickOptions: coachMode
        ? ["汇报最近进展", "复盘本周执行", "计划有点太满", "我想调整当前安排"]
        : this.data.quickOptions
    });

    if (sessionId && mode !== "sandbox") {
      this.restoreSession(sessionId);
      return;
    }

    if (mode === "sandbox") {
      this.addMessage("assistant", "你好，我是你的决策教练。你可以直接告诉我现在最纠结的选择，我会陪你梳理不同路径。");
      return;
    }

    this.startAgentSession(agent, sourceSandboxSessionId);
  },

  async startAgentSession(agent, sandboxSessionId) {
    const inheritedSandboxId = sandboxSessionId || this.data.sourceSandboxSessionId;
    this.setData({
      isLoading: true,
      showRetry: false,
      retryKind: "",
      showQuickActions: false,
      agent,
      agentName: AGENT_NAMES[agent] || "成长规划",
      sourceSandboxSessionId: inheritedSandboxId || ""
    });
    try {
      const data = { agent, user_id: this.data.userId };
      if (inheritedSandboxId) data.sandbox_session_id = inheritedSandboxId;
      const res = await app.request({ method: "POST", url: "/api/v1/growth/start", data });
      this.setData({
        mode: "agent",
        sessionId: res.session_id || "",
        sessionStage: res.stage || "questioning",
        isLoading: false,
        progress: res.progress || 0
      });
      this.addMessage("assistant", res.message || "先和我说说你目前的情况，以及最想解决的问题吧。");
    } catch (err) {
      this.addMessage("assistant", "成长规划暂时没有启动成功，请检查网络后重试。");
      this.setData({ isLoading: false, showRetry: true, retryKind: "start" });
    }
  },

  async restoreSession(sessionId) {
    wx.showLoading({ title: "恢复规划中..." });
    this.setData({ isLoading: true, showRetry: false });
    try {
      const [history, state] = await Promise.all([
        app.request({ url: "/api/v1/growth/conversation/" + sessionId }),
        app.request({ url: "/api/v1/growth/session/" + sessionId })
      ]);
      const messages = (history || []).map((item, index) => ({
        id: item.id || `hist-${index}`,
        role: item.role,
        content: item.content,
        time: this.formatMessageTime(item.created_at)
      }));
      const finished = Boolean(state.finished || state.has_report);
      const stage = state.stage || "questioning";
      const agent = state.agent || this.data.agent;
      const coachMode = this.data.coachMode && finished;
      this.setData({
        messages,
        mode: coachMode ? "coach" : (finished ? "qa" : "agent"),
        agent,
        agentName: coachMode ? "成长教练" : (AGENT_NAMES[agent] || "成长规划"),
        sessionStage: stage,
        reportReady: finished,
        showAnalysisCard: stage === "analyzing" && !finished,
        inputPlaceholder: coachMode ? "说说最近的进展或困难" : (finished ? "继续追问报告内容" : "输入你的回答"),
        showQuickActions: coachMode,
        inputValue: coachMode ? this.data.pendingPrompt : "",
        isLoading: false,
        progress: finished ? 100 : (stage === "analyzing" ? 40 : 0),
        scrollToView: messages.length ? "msg-" + messages[messages.length - 1].id : ""
      });
      if (!messages.length) {
        this.addMessage("assistant", finished ? "报告已经生成，可以查看报告或继续咨询。" : "规划已恢复，请继续告诉我你的情况。");
      }
    } catch (err) {
      this.addMessage("assistant", "没有恢复成功，请稍后重试或返回历史记录重新进入。");
      this.setData({ isLoading: false, showRetry: true, retryKind: "restore" });
    } finally {
      wx.hideLoading();
    }
  },

  formatMessageTime(value) {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    const pad = (n) => String(n).padStart(2, "0");
    return pad(date.getHours()) + ":" + pad(date.getMinutes());
  },

  addMessage(role, content) {
    if (!content) return "";
    const id = Date.now().toString() + Math.floor(Math.random() * 1000);
    const now = new Date();
    const pad = (n) => String(n).padStart(2, "0");
    const time = pad(now.getHours()) + ":" + pad(now.getMinutes());
    const messages = this.data.messages.concat({ id, role, content, time });
    this.setData({ messages, scrollToView: "msg-" + id });
    return id;
  },

  onInput(e) {
    this.setData({ inputValue: e.detail.value });
  },

  sendMessage() {
    const content = this.data.inputValue.trim().replace(/\n+$/, "");
    if (!content || this.data.isLoading) return;

    this.addMessage("user", content);
    this.setData({
      inputValue: "",
      showQuickActions: false,
      isLoading: true,
      showAnalysisCard: false,
      showRetry: false,
      retryKind: "send",
      lastFailedMessage: content,
      loadingText: this.data.mode === "sandbox"
        ? "正在生成路径分析，请稍候..."
        : (this.data.mode === "coach" ? "正在结合计划和进度复盘..." : "正在整理你的信息...")
    });

    if (this.data.mode === "qa" || this.data.mode === "coach") {
      this.sendQa(content);
    } else if (this.data.mode === "sandbox") {
      this.sendSandbox(content);
    } else {
      this.sendAgent(content);
    }
  },

  async sendQa(content) {
    try {
      const res = await app.request({
        method: "POST",
        url: "/api/v1/growth/qa",
        data: {
          session_id: this.data.sessionId,
          user_id: this.data.userId,
          agent: this.data.agent,
          message: content
        }
      });
      this.addMessage("assistant", res.message || "我已经收到你的问题，请换一种方式再描述一下。" );
      this.setData({ isLoading: false });
    } catch (err) {
      this.handleSendFailure("回答生成失败，请点击重试。");
    }
  },

  async sendAgent(content) {
    try {
      const res = await app.request({
        method: "POST",
        url: "/api/v1/growth/chat",
        data: {
          user_id: this.data.userId,
          agent: this.data.agent,
          message: content,
          session_id: this.data.sessionId || undefined
        }
      });
      if (res.session_id && !this.data.sessionId) this.setData({ sessionId: res.session_id });
      this.handleAgentResponse(res);
    } catch (err) {
      this.handleSendFailure("消息发送失败，请点击重试。");
    }
  },

  async sendSandbox(content) {
    try {
      const res = await app.request({
        method: "POST",
        url: "/api/v1/sandbox/chat",
        data: { session_id: this.data.sessionId, user_id: this.data.userId, message: content },
        timeout: 45000
      });
      if (!res) {
        this.setData({ isLoading: false });
        return;
      }
      if (res.session_id && !this.data.sessionId) this.setData({ sessionId: res.session_id });
      if (res.finished) {
        const sandboxSessionId = res.session_id || this.data.sessionId;
        this.setData({ isLoading: false, showCards: false, selectingPaths: false });
        wx.showToast({ title: "对比报告已生成", icon: "success", duration: 900 });
        setTimeout(() => {
          wx.redirectTo({
            url: "/pages/sandbox-result/sandbox-result?session_id=" + encodeURIComponent(sandboxSessionId) + "&sandbox_session_id=" + encodeURIComponent(sandboxSessionId)
          });
        }, 250);
        return;
      }
      this.addMessage("assistant", res.report_text || res.message || "我已经收到，正在继续梳理。" );
      this.setData({
        showCards: Boolean(res.show_cards && res.cards && res.cards.length),
        cards: (res.cards || []).map(item => ({
          ...item,
          icon: item.icon && item.icon.startsWith("/") ? item.icon : `/images/${item.icon || "icon-postgrad"}.png`
        })),
        selectingPaths: res.phase === "path_probe" && !res.finished,
        selectedPaths: [],
        isLoading: false
      });
    } catch (err) {
      this.handleSendFailure("消息发送失败，请点击重试。");
    }
  },

  handleAgentResponse(res) {
    if (!res) {
      this.handleSendFailure("没有收到有效回复，请点击重试。");
      return;
    }
    const stage = res.stage || "questioning";
    if (res.finished || res.report) {
      this.addMessage("assistant", "完整规划报告已生成。你可以先查看报告，也可以在这里继续追问细节。" );
      this.setData({
        mode: "qa",
        sessionStage: "report",
        reportReady: true,
        showAnalysisCard: false,
        inputPlaceholder: "继续追问报告内容",
        isLoading: false,
        progress: 100
      });
      if (!this.data.reportNavigating) {
        this.setData({ reportNavigating: true });
        wx.showToast({ title: "规划报告已生成", icon: "success", duration: 900 });
        setTimeout(() => {
          wx.navigateTo({
            url: `/pages/report/report?session_id=${this.data.sessionId}&agent_type=${this.data.agent}`,
            complete: () => this.setData({ reportNavigating: false })
          });
        }, 300);
      }
      return;
    }
    this.addMessage("assistant", res.message || "请继续补充你的情况。" );
    this.setData({
      sessionStage: stage,
      showAnalysisCard: stage === "analyzing",
      isLoading: false,
      progress: res.progress || (stage === "analyzing" ? 40 : 0)
    });
  },

  handleSendFailure(message) {
    this.addMessage("assistant", message);
    this.setData({ isLoading: false, showRetry: true, retryKind: "send" });
  },

  async approveAnalysis() {
    if (this.data.isLoading) return;
    this.setData({ isLoading: true, showAnalysisCard: false, showRetry: false });
    try {
      const res = await app.request({
        method: "POST",
        url: "/api/v1/growth/approve",
        data: { session_id: this.data.sessionId, user_id: this.data.userId }
      });
      this.handleAgentResponse(res);
    } catch (err) {
      this.addMessage("assistant", "报告生成失败，请重试。");
      this.setData({ isLoading: false, showAnalysisCard: true });
    }
  },

  correctAnalysis() {
    wx.showModal({
      title: "修正分析方向",
      editable: true,
      placeholderText: "例如：我更想走前端方向，请重新评估",
      success: async (result) => {
        const correction = (result.content || "").trim();
        if (!result.confirm) return;
        if (!correction) {
          wx.showToast({ title: "请填写修正内容", icon: "none" });
          return;
        }
        this.addMessage("user", "修正方向：" + correction);
        this.setData({ isLoading: true, showAnalysisCard: false });
        try {
          const res = await app.request({
            method: "POST",
            url: "/api/v1/growth/correct",
            data: { session_id: this.data.sessionId, user_id: this.data.userId, correction }
          });
          this.handleAgentResponse(res);
        } catch (err) {
          this.addMessage("assistant", "方向修正失败，请稍后重试。");
          this.setData({ isLoading: false, showAnalysisCard: true });
        }
      }
    });
  },

  retryLastMessage() {
    const kind = this.data.retryKind;
    this.setData({ showRetry: false });
    if (kind === "start") {
      this.startAgentSession(this.data.agent, this.data.sourceSandboxSessionId);
      return;
    }
    if (kind === "restore") {
      this.restoreSession(this.data.sessionId);
      return;
    }
    const message = this.data.lastFailedMessage;
    if (message) {
      this.setData({ isLoading: true, showAnalysisCard: false });
      if (this.data.mode === "qa" || this.data.mode === "coach") this.sendQa(message);
      else if (this.data.mode === "sandbox") this.sendSandbox(message);
      else this.sendAgent(message);
    }
  },

  sendQuickMessage(e) {
    this.setData({ inputValue: e.currentTarget.dataset.text }, () => this.sendMessage());
  },

  async selectDirection(e) {
    const agentType = e.currentTarget.dataset.type;
    const sandboxSessionId = this.data.sessionId;
    this.setData({ messages: [], showCards: false, selectingPaths: false });
    await this.startAgentSession(agentType, sandboxSessionId);
  },

  togglePathCard(e) {
    const type = e.currentTarget.dataset.type;
    const selected = this.data.selectedPaths.slice();
    const index = selected.indexOf(type);
    if (index >= 0) selected.splice(index, 1);
    else selected.push(type);
    this.setData({ selectedPaths: selected });
  },

  confirmPathSelection() {
    const selected = this.data.selectedPaths;
    if (!selected.length) {
      wx.showToast({ title: "请至少选择一个方向", icon: "none" });
      return;
    }
    const names = { career: "就业", graduate: "考研", civil: "考公", major: "转专业" };
    const content = "开始对比" + selected.map((item) => names[item] || item).join("和");
    this.setData({ inputValue: content, showCards: false, selectingPaths: false, selectedPaths: [] }, () => this.sendMessage());
  },

  viewReport() {
    if (!this.data.sessionId) return;
    wx.navigateTo({
      url: `/pages/report/report?session_id=${this.data.sessionId}&agent_type=${this.data.agent}`
    });
  },

  goHistory() {
    wx.navigateTo({ url: this.data.coachMode ? "/pages/history/history?type=plan" : "/pages/history/history?type=chat" });
  },

  goBack() {
    if (getCurrentPages().length > 1) wx.navigateBack({ delta: 1 });
    else wx.switchTab({ url: "/pages/growth/growth" });
  }
});
