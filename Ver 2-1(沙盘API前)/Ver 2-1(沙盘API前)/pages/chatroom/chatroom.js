var app = getApp();

Page({
  data: {
    statusBarHeight: 44, mode: "sandbox", agent: "career", sessionId: "", userId: "",
    messages: [], inputValue: "", isLoading: false, showQuickActions: true, showCards: false, cards: [], scrollToView: "",
    waitingForReady: false, waitingForTrigger: false, showAnalysisCard: false,
    selectingPaths: false, selectedPaths: [],
    quickOptions: ["转专业", "考研规划", "考公评估", "就业指导"]
  },

  onLoad: function(options) {
    var info = wx.getSystemInfoSync();
    var userId = wx.getStorageSync("userId") || app.globalData.userId || "";
    var mode = options.mode || "sandbox";
    var sessionId = options.session_id || "";
    var agent = options.agent || "career";

    this.setData({
      statusBarHeight: info.statusBarHeight,
      mode: mode,
      agent: agent,
      sessionId: sessionId,
      userId: userId
    });

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
      welcome = "你好呀！我是你的决策教练，聊聊你的困惑，找到更好的选择吧！";
    } else {
      welcome = agentGreetings[agent] || "准备好开始规划了吗？";
      this.setData({ waitingForReady: true, showQuickActions: false });
    }
    this.addMessage("assistant", welcome);
  },

  async loadConversationHistory(sessionId) {
    wx.showLoading({ title: "加载对话..." });
    try {
      var res = await app.request({ url: "/api/v1/growth/conversation/" + sessionId });
      var messages = [];
      var list = res || [];
      for (var i = 0; i < list.length; i++) {
        var m = list[i];
        var id = "hist-" + i;
        messages.push({
          id: id,
          role: m.role,
          content: m.content,
          time: m.created_at ? m.created_at.slice(11, 16) : ""
        });
      }
      this.setData({ messages: messages, scrollToView: "", showQuickActions: false });
    } catch (err) {
      this.addMessage("assistant", "无法加载对话记录");
    }
    wx.hideLoading();
  },

  addMessage: function(role, content) {
    var id = Date.now().toString();
    var messages = this.data.messages.concat({ id: id, role: role, content: content, time: new Date().toLocaleTimeString() });
    this.setData({ messages: messages, scrollToView: "msg-" + id });
    return id;
  },

  onInput: function(e) { this.setData({ inputValue: e.detail.value }); },

  sendMessage: function() {
    var that = this;
    var content = this.data.inputValue.trim();
    if (!content || this.data.isLoading) return;
    this.addMessage("user", content);
    this.setData({ inputValue: "", showQuickActions: false, isLoading: true, showAnalysisCard: false });

    if (this.data.mode === "resume") {
      this.setData({ mode: "agent" });
    }

    // Agent mode: handle greeting confirmation
    if (this.data.mode !== "sandbox" && this.data.waitingForReady) {
      this.setData({ waitingForReady: false, showQuickActions: false, isLoading: true });
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
        that.setData({ isLoading: false });
      });
      return;
    }

    if (this.data.mode === "sandbox") {
      var that = this;
      app.request({
        method: "POST", url: "/sandbox/chat",
        data: { session_id: this.data.sessionId, user_id: this.data.userId, message: content }
      }).then(function(res) {
        if (res.session_id && !that.data.sessionId) that.setData({ sessionId: res.session_id });
        if (res.show_cards && res.cards && res.cards.length) {
          that.addMessage("assistant", res.report_text || res.message);
          var isSelecting = res.phase === "path_probe" && !res.finished;
          that.setData({
            showCards: true, cards: res.cards, showQuickActions: false, isLoading: false,
            selectingPaths: isSelecting, selectedPaths: []
          });
        } else {
          that.addMessage("assistant", res.message || "收到你的消息，让我想想...");
          that.setData({ isLoading: false, selectingPaths: false });
        }
      }).catch(function() {
        that.addMessage("assistant", "网络异常，请重试");
        that.setData({ isLoading: false });
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
      that.setData({ isLoading: false });
    });
  },

  handleAgentResponse: function(chatRes) {
    var that = this;
    if (chatRes.finished && chatRes.report) {
      that.addMessage("assistant", chatRes.message || "报告已生成");
      that.setData({ isLoading: false });
      wx.showToast({ title: "报告已生成", icon: "success" });
      setTimeout(function() {
        wx.navigateTo({ url: "/pages/report/report?session_id=" + (chatRes.session_id || that.data.sessionId) });
      }, 800);
    } else if (chatRes.stage === "analyzing" && chatRes.message) {
      that.addMessage("assistant", chatRes.message);
      that.setData({ isLoading: false, showAnalysisCard: true });
    } else if (chatRes.message) {
      that.addMessage("assistant", chatRes.message);
      that.setData({ isLoading: false, showAnalysisCard: false });
      if (chatRes.stage === "awaiting") {
        that.setData({ waitingForTrigger: true });
      }
    } else {
      that.addMessage("assistant", "让我想想...");
      that.setData({ isLoading: false, showAnalysisCard: false });
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
      title: "修正方向",
      editable: true,
      placeholderText: "请输入你的想法，例如：我更想走前端的路线",
      success: function(r) {
        if (!r.confirm || !r.content) return;
        that.setData({ isLoading: true, showAnalysisCard: false });
        app.request({
          method: "POST", url: "/api/v1/growth/correct",
          data: { session_id: that.data.sessionId, user_id: that.data.userId, correction: r.content }
        }).then(function(res) {
          that.handleAgentResponse(res);
        }).catch(function() {
          that.addMessage("assistant", "网络异常，请重试");
          that.setData({ isLoading: false });
        });
      }
    });
  },

  sendQuickMessage: function(e) {
    this.setData({ inputValue: e.currentTarget.dataset.text });
    this.sendMessage();
  },

  startVoice: function() {
    wx.showToast({ title: "语音功能开发中", icon: "none" });
  },

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
    var msg = "开始对比" + pathNames.join("和");
    this.setData({ inputValue: msg, showCards: false, selectingPaths: false, selectedPaths: [] });
    this.sendMessage();
  },

  goBack: function() { wx.navigateBack(); }
});