var app = getApp();

Page({
  data: {
    statusBarHeight: 44, mode: "sandbox", agent: "career", sessionId: "", userId: "",
    messages: [], inputValue: "", isLoading: false, showQuickActions: true, showCards: false, cards: [], scrollToView: "",
    waitingForReady: false, waitingForTrigger: false,
    selectingPaths: false, selectedPaths: [],
    quickOptions: ["转专业", "考研规划", "考公评估", "就业指导"]
  },

  onLoad: function(options) {
    var info = wx.getSystemInfoSync();
    this.setData({
      statusBarHeight: info.statusBarHeight,
      mode: options.mode || "sandbox",
      agent: options.agent || "career",
      sessionId: options.session_id || "",
      userId: wx.getStorageSync("userId") || app.globalData.userId || ""
    });
    var agentGreetings = {
      career: "准备好开始规划你的职业道路了吗？",
      employment: "准备好开始规划你的职业道路了吗？",
      graduate: "准备好一起制定你的考研计划了吗？",
      civil: "准备好规划你的考公之路了吗？",
      major: "准备好探索新的专业方向了吗？"
    };
    var welcome;
    if (this.data.mode === "sandbox") {
      welcome = "你好呀！我是你的决策教练，聊聊你的困惑，找到更好的选择吧！";
    } else {
      welcome = agentGreetings[this.data.agent] || "准备好开始规划了吗？";
      this.setData({ waitingForReady: true, showQuickActions: false });
    }
    this.addMessage("assistant", welcome);
  },

  addMessage: function(role, content) {
    var id = Date.now().toString();
    var messages = this.data.messages.concat({ id: id, role: role, content: content, time: new Date().toLocaleTimeString() });
    this.setData({ messages: messages, scrollToView: "msg-" + id });
    return id;
  },

  appendLastMessage: function(content) {
    var messages = this.data.messages;
    if (messages.length === 0) return;
    var last = messages[messages.length - 1];
    last.content += content;
    this.setData({ messages: messages });
  },

  onInput: function(e) { this.setData({ inputValue: e.detail.value }); },

  sendMessage: function() {
    var that = this;
    var content = this.data.inputValue.trim();
    if (!content || this.data.isLoading) return;
    this.addMessage("user", content);
    this.setData({ inputValue: "", showQuickActions: false, isLoading: true });

    // Agent mode: handle greeting confirmation ("准备好了")
    if (this.data.mode !== "sandbox" && this.data.waitingForReady) {
      this.setData({ waitingForReady: false, showQuickActions: false, isLoading: true });
      var that = this;
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
        that.addMessage("assistant", chatRes.message || "让我深入了解你的情况...");
        that.setData({ isLoading: false });
      }).catch(function() {
        that.addMessage("assistant", "网络异常，请重试");
        that.setData({ isLoading: false });
      });
      return;
    }

    var isSandbox = this.data.mode === "sandbox";

    if (isSandbox) {
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

    // Agent 模式：先启动会话再发消息
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
      that.addMessage("assistant", chatRes.message || "收到你的消息，让我分析一下...");
      that.setData({ isLoading: false });
    }).catch(function() {
      that.addMessage("assistant", "网络异常，请重试");
      that.setData({ isLoading: false });
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
      data: {
        agent: agentType,
        user_id: this.data.userId,
        sandbox_session_id: this.data.sessionId
      }
    }).then(function(res) {
      wx.hideLoading();
      var greeting = res.greeting || "准备好开始规划了吗？";
      that.setData({
        mode: "agent",
        agent: agentType,
        sessionId: res.session_id || "",
        showCards: false,
        showQuickActions: false,
        waitingForReady: true,
        messages: []
      });
      that.addMessage("assistant", greeting);
    }).catch(function() {
      wx.hideLoading();
      wx.showToast({ title: "启动失败，请重试", icon: "none" });
    });
  },

  // Path selection for sandbox
  togglePathCard: function(e) {
    var type = e.currentTarget.dataset.type;
    var selected = this.data.selectedPaths.slice();
    var idx = selected.indexOf(type);
    if (idx >= 0) {
      selected.splice(idx, 1);
    } else {
      selected.push(type);
    }
    this.setData({ selectedPaths: selected });
  },

  confirmPathSelection: function() {
    var that = this;
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