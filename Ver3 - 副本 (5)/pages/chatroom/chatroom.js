var app = getApp();

Page({
  data: {
    statusBarHeight: 44, mode: "sandbox", agent: "career", sessionId: "", userId: "",
    messages: [], inputValue: "", isLoading: false, showQuickActions: true,
    showCards: false, cards: [], scrollToView: "",
    waitingForReady: false, showAnalysisCard: false,
    selectingPaths: false, selectedPaths: [],
    progress: 0, showRetry: false, streamingText: "", isStreaming: false, lastFailedMessage: "",
    quickOptions: ["不知道考研还是就业", "想转专业但不确定方向", "考公和找工作怎么选", "帮我分析一下我的情况"],
    // ========== 新增：Growth 进度条数据 ==========
    growthProgress: null,
    showGrowthProgress: false,
    syncedSessionId: "",
    showProgressDetail: false
    // ========== 新增结束 ==========
  },

  onLoad: function(options) {
    var info = wx.getSystemInfoSync();
    var userId = wx.getStorageSync("userId") || app.globalData.userId || "";
    var mode = options.mode || "sandbox";
    var sessionId = options.session_id || "";
    var agent = options.agent || "career";

    this.setData({
      statusBarHeight: info.statusBarHeight, mode: mode,
      agent: agent, sessionId: sessionId, userId: userId
    });

    // ========== 新增：加载 Growth 进度 ==========
    if (mode === "agent") {
      this.checkGrowthProgress();
    }
    // ========== 新增结束 ==========

    if (mode === "resume") {
      this.loadConversationHistory(sessionId);
      return;
    }

    var agentGreetings = {
      career: "准备好开始规划你的职业道路了吗？",
      employment: "准备好开始规划你的职业道路了吗？",
      graduate: "准备好一起制定你的考研计划了吗？",
      civil: "准备好规划你的考公之路了吗？",
      major: "准备好探索新的专业方向了吗？"
    };
    var welcome;
    if (mode === "sandbox") {
      welcome = "你好呀！我是你的决策教练～\n\n你可以直接告诉我你的困惑，比如：";
      this.setData({ showQuickActions: true });
    } else {
      welcome = agentGreetings[agent] || "准备好开始规划了吗？";
      this.setData({ waitingForReady: true, showQuickActions: false });
    }
    this.addMessage("assistant", welcome);
  },

  // ========== 新增：onShow 刷新进度 ==========
  onShow: function() {
    if (this.data.mode === "agent" && this.data.syncedSessionId) {
      this.loadGrowthProgress(this.data.syncedSessionId);
    }
  },
  // ========== 新增结束 ==========

  async loadConversationHistory(sessionId) {
    wx.showLoading({ title: "加载对话..." });
    try {
      var res = await app.request({ url: "/api/v1/growth/conversation/" + sessionId });
      var messages = [];
      var list = res || [];
      for (var i = 0; i < list.length; i++) {
        var m = list[i];
        messages.push({
          id: "hist-" + i, role: m.role, content: m.content,
          time: m.created_at ? m.created_at.slice(11, 16) : ""
        });
      }
      this.setData({ messages: messages, showQuickActions: false, mode: "qa" });
    } catch (err) {
      this.addMessage("assistant", "无法加载对话记录");
    }
    wx.hideLoading();
  },


  updateLastAssistant: function(text) {
    var msgs = this.data.messages;
    if (msgs.length > 0) {
      msgs[msgs.length - 1].content = text;
      this.setData({ messages: msgs });
    }
  },

  addMessage: function(role, content) {
    var id = Date.now().toString();
    var now = new Date();
    var time = String(now.getHours()).padStart(2, "0") + ":" + String(now.getMinutes()).padStart(2, "0");
    var messages = this.data.messages.concat({ id: id, role: role, content: content, time: time });
    this.setData({ messages: messages, scrollToView: "msg-" + id });
    return id;
  },

  onInput: function(e) { this.setData({ inputValue: e.detail.value }); },

  sendMessage: function() {
    var that = this;
    var content = this.data.inputValue.trim().replace(/\n+$/, '');
    if (!content || this.data.isLoading) return;
    this.addMessage("user", content);
    this.setData({
      inputValue: "", showQuickActions: false, isLoading: true,
      showAnalysisCard: false, progress: 0, showRetry: false, streamingText: "", isStreaming: false,
      lastFailedMessage: content
    });

    // Resume mode switches to agent mode on first message
    if (this.data.mode === "resume") {
      this.setData({ mode: "agent" });
    }

    
// QA mode: simple LLM chat
    if (this.data.mode === "qa") {
      app.request({
        method: "POST", url: "/api/v1/growth/qa",
        data: { session_id: this.data.sessionId, user_id: this.data.userId,
                agent: this.data.agent, message: content }
      }).then(function(res) {
        that.addMessage("assistant", res.message || "收到你的消息");
        that.setData({ isLoading: false });
      }).catch(function() {
        that.addMessage("assistant", "网络异常，请重试");
        that.setData({ isLoading: false, showRetry: true });
      });
      return;
    }

// Agent mode: greeting confirmation
    if (this.data.mode !== "sandbox" && this.data.waitingForReady) {
      this.setData({ waitingForReady: false, showQuickActions: false });
      var agent = this.data.agent || "career";
      app.request({
        method: "POST", url: "/api/v1/growth/start",
        data: { agent: agent, user_id: this.data.userId }
      }).then(function(startRes) {
        var sid = startRes.session_id || "";
        if (sid) that.setData({ sessionId: sid });
        return app.request({
          method: "POST", url: "/api/v1/growth/chat",
          data: { user_id: that.data.userId, agent: agent, message: content, session_id: sid }
        });
      }).then(function(chatRes) {
        that.handleAgentResponse(chatRes);
      }).catch(function() {
        that.addMessage("assistant", "网络异常，请重试");
        that.setData({ isLoading: false, showRetry: true });
      });
      return;
    }

    
// Sandbox mode
    if (this.data.mode === "sandbox") {
      app.request({
        method: "POST", url: "/api/v1/sandbox/chat",
        data: { session_id: this.data.sessionId, user_id: this.data.userId, message: content }
      }).then(function(res) {
        if (!res) { that.setData({ isLoading: false }); return; }
        if (res.session_id && !that.data.sessionId) that.setData({ sessionId: res.session_id });
        if (res.show_cards && res.cards && res.cards.length) {
          that.addMessage("assistant", res.report_text || res.message || "分析完成");
          var isSelecting = res.phase === "path_probe" && !res.finished;
          that.setData({
            showCards: true, cards: res.cards, isLoading: false,
            selectingPaths: isSelecting, selectedPaths: []
          });
        } else {
          that.addMessage("assistant", res.message || "收到你的消息，让我想想...");
          that.setData({ isLoading: false, selectingPaths: false });
        }
      }).catch(function() {
        that.addMessage("assistant", "网络异常，请重试");
        that.setData({ isLoading: false, showRetry: true });
      });
      return;
    }


// Agent mode: continue chat
    var sid = this.data.sessionId;
    var doStart = sid ? Promise.resolve({ session_id: sid }) : app.request({
      method: "POST", url: "/api/v1/growth/start",
      data: { agent: this.data.agent, user_id: this.data.userId }
    });

    doStart.then(function(startRes) {
      sid = startRes.session_id || sid;
      if (sid && !that.data.sessionId) that.setData({ sessionId: sid });
      return app.request({
        method: "POST", url: "/api/v1/growth/chat",
        data: { user_id: that.data.userId, agent: that.data.agent, message: content, session_id: sid }
      });
    }).then(function(chatRes) {
      that.handleAgentResponse(chatRes);
    }).catch(function() {
      that.addMessage("assistant", "网络异常，请重试");
      that.setData({ isLoading: false, showRetry: true });
    });
  },

  handleAgentResponse: function(chatRes) {
    var that = this;
    if (!chatRes) {
      that.addMessage("assistant", "让我想想...");
      that.setData({ isLoading: false });
      return;
    }
    var progress = chatRes.progress || 0;

    if (chatRes.finished && chatRes.report) {
      // Switch to QA mode instead of navigating away
      that.addMessage("assistant", chatRes.message || "报告已生成！你可以继续问我任何问题～");
      that.setData({
        mode: "qa", isLoading: false, progress: 100
      });
    } else if (chatRes.message) {
      that.addMessage("assistant", chatRes.message);
      that.setData({ isLoading: false, progress: progress });
      if (chatRes.stage === "analyzing") {
        that.setData({ showAnalysisCard: true });
      }
    } else {
      that.addMessage("assistant", "让我想想...");
      that.setData({ isLoading: false });
    }
  },

  approveAnalysis: function() {
    var that = this;
    this.setData({ isLoading: true, showAnalysisCard: false });
    app.request({
      method: "POST", url: "/api/v1/growth/approve",
      data: { session_id: this.data.sessionId, user_id: this.data.userId }
    }).then(function(res) {
      that.handleAgentResponse(res);
    }).catch(function() {
      that.addMessage("assistant", "生成报告失败，请重试");
      that.setData({ isLoading: false });
    });
  },

  correctAnalysis: function() {
    var that = this;
    wx.showModal({
      title: "修正方向", editable: true,
      placeholderText: "请输入你的想法，例如：我更想走前端的路线",
      success: function(r) {
        if (!r.confirm || !r.content) return;
        that.setData({ isLoading: true, showAnalysisCard: false });
        app.request({
          method: "POST", url: "/api/v1/growth/correct",
          data: { session_id: that.data.sessionId, user_id: that.data.userId, correction: r.content }
        }).then(function(res) { that.handleAgentResponse(res); })
          .catch(function() {
            that.addMessage("assistant", "网络异常，请重试");
            that.setData({ isLoading: false });
          });
      }
    });
  },

  retryLastMessage: function() {
    this.setData({ showRetry: false });
    this.sendMessage();
  },

  sendQuickMessage: function(e) {
    this.setData({ inputValue: e.currentTarget.dataset.text });
    this.sendMessage();
  },

  startVoice: function() { wx.showToast({ title: "语音功能开发中", icon: "none" }); },

  selectDirection: function(e) {
    var that = this;
    var agentType = e.currentTarget.dataset.type;
    wx.showLoading({ title: "启动规划中..." });
    app.request({
      method: "POST", url: "/api/v1/growth/start",
      data: { agent: agentType, user_id: this.data.userId, sandbox_session_id: this.data.sessionId }
    }).then(function(res) {
      wx.hideLoading();
      var greeting = res.greeting || "准备好开始规划了吗？";
      that.setData({
        mode: "agent", agent: agentType, sessionId: res.session_id || "",
        showCards: false, showQuickActions: false, waitingForReady: true, messages: []
      });
      that.addMessage("assistant", greeting);
      // ========== 新增：切换 agent 后检查进度 ==========
      that.checkGrowthProgress();
      // ========== 新增结束 ==========
    }).catch(function() {
      wx.hideLoading();
      wx.showToast({ title: "启动失败，请重试", icon: "none" });
    });
  },

  togglePathCard: function(e) {
    var type = e.currentTarget.dataset.type;
    var selected = this.data.selectedPaths.slice();
    var idx = selected.indexOf(type);
    if (idx >= 0) { selected.splice(idx, 1); }
    else { selected.push(type); }
    this.setData({ selectedPaths: selected });
  },

  confirmPathSelection: function() {
    var selected = this.data.selectedPaths;
    if (selected.length === 0) {
      wx.showToast({ title: "请至少选择一个方向", icon: "none" });
      return;
    }
    var pathNames = [];
    var nameMap = { career: "就业", graduate: "考研", civil: "考公", major: "转专业" };
    selected.forEach(function(s) { pathNames.push(nameMap[s] || s); });
    this.setData({ inputValue: "开始对比" + pathNames.join("和"), showCards: false, selectingPaths: false, selectedPaths: [] });
    this.sendMessage();
  },

  goBack: function() { wx.navigateBack(); },

  // ========== 新增：Growth 进度条方法 ==========
  
  // 检查并加载 Growth 进度
  async checkGrowthProgress() {
    const syncedMap = wx.getStorageSync('syncedGrowthSessions') || {};
    const agent = this.data.agent;
    
    // 查找当前 agent 对应的已同步 session
    const currentSynced = Object.entries(syncedMap).find(([_, v]) => 
      v.agent === agent && v.syncedAt
    );
    
    if (!currentSynced) {
      this.setData({ showGrowthProgress: false, growthProgress: null });
      return;
    }
    
    const [growthSessionId] = currentSynced;
    this.setData({ syncedSessionId: growthSessionId });
    await this.loadGrowthProgress(growthSessionId);
  },

  // 加载进度数据
  async loadGrowthProgress(growthSessionId) {
    try {
      const res = await app.request({
        url: '/api/v1/today/progress',
        data: {
          user_id: this.data.userId,
          growth_session_id: growthSessionId
        }
      });
      
      if (res && res.percent !== undefined) {
        this.setData({
          growthProgress: {
            agent: this.getAgentName(res.agent || this.data.agent),
            phase: res.phase || '当前阶段',
            phaseName: res.phase_name || res.phase || '第1-2周',
            percent: res.percent,
            done: res.done || 0,
            total: res.total || 0,
            blocks: this.renderProgressBlocks(res.percent),
            phases: res.phases || [] // 阶段明细（可选）
          },
          showGrowthProgress: true
        });
      } else {
        this.setData({ showGrowthProgress: false });
      }
    } catch (err) {
      console.error('加载进度失败', err);
      this.setData({ showGrowthProgress: false });
    }
  },

  // 生成进度块 ████░░░░
  renderProgressBlocks(percent) {
    const total = 10;
    const filled = Math.round(percent / 10);
    return '█'.repeat(filled) + '░'.repeat(total - filled);
  },

  // agent 代码转中文
  getAgentName(agent) {
    const map = {
      career: '就业',
      employment: '就业',
      graduate: '考研',
      civil: '考公',
      major: '转专业'
    };
    return map[agent] || '规划';
  },

  // 切换展开/收起阶段明细
  toggleProgressDetail() {
    this.setData({
      showProgressDetail: !this.data.showProgressDetail
    });
  }

  // ========== 新增结束 ==========
});
