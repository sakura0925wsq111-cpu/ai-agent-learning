const app = getApp();

Page({
  data: {
    statusBarHeight: 44, sessionId: "", sandboxSessionId: "", isDebug: false,
    summary: "", messageCount: 0, insights: [], recommendation: null,
    directions: [
      { type: "graduate", name: "考研规划", icon: "/images/icon-graduate.png", color: "#4A90D9", bgColor: "#E6F2FF", description: "院校选择、备考规划、复试模拟、资料推荐", matchScore: 0, recommended: false },
      { type: "career", name: "就业指导", icon: "/images/icon-work.png", color: "#52C41A", bgColor: "#E6F9ED", description: "职业测评、简历优化、面试模拟、岗位推荐", matchScore: 0, recommended: false },
      { type: "civil", name: "考公评估", icon: "/images/icon-government.png", color: "#FA8C16", bgColor: "#FFF3E6", description: "岗位匹配、备考规划、真题练习、上岸路径", matchScore: 0, recommended: false },
      { type: "major", name: "转专业分析", icon: "/images/icon-transfer.png", color: "#722ED1", bgColor: "#F0E6FF", description: "转专业条件、成功率、课程差异、风险评估", matchScore: 0, recommended: false }
    ]
  },

  async onLoad(options) {
    const info = wx.getSystemInfoSync(); this.setData({ statusBarHeight: info.statusBarHeight });
    const { session_id, sandbox_session_id, debug } = options;
    this.setData({ sessionId: session_id || "", sandboxSessionId: sandbox_session_id || session_id || "", isDebug: debug === "1" });
    this.loadPaths();
    if (this.data.isDebug) { this.loadMockData(); return; }
    this.loadResult();
  },

  async loadPaths() {
    try {
      const res = await app.request({ url: "/sandbox/paths" });
      if (res.paths && res.paths.length) {
        const icons = { graduate: "/images/icon-graduate.png", employment: "/images/icon-work.png", career: "/images/icon-work.png", civil: "/images/icon-government.png", major: "/images/icon-transfer.png" };
        const colors = { graduate: "#4A90D9", employment: "#52C41A", career: "#52C41A", civil: "#FA8C16", major: "#722ED1" };
        const bgs = { graduate: "#E6F2FF", employment: "#E6F9ED", career: "#E6F9ED", civil: "#FFF3E6", major: "#F0E6FF" };
        this.setData({ directions: res.paths.map(p => ({ type: p.type, name: p.name, icon: icons[p.type] || "/images/icon-graduate.png", color: colors[p.type] || "#4A90D9", bgColor: bgs[p.type] || "#E6F2FF", description: p.description || "", matchScore: 0, recommended: false })) });
      }
    } catch (err) {}
  },

  loadMockData() {
    const d = { summary: "你目前处于职业探索期，对技术方向有较强兴趣，但缺乏明确的执行计划。建议深入调研目标领域，制定阶段性目标。", messageCount: 8,
      insights: [{ label: "当前状态", value: "探索期，需要更多实践验证", color: "#4A90D9" }, { label: "核心优势", value: "逻辑思维强，学习能力突出", color: "#52C41A" }, { label: "主要困惑", value: "方向选择多，难以聚焦", color: "#FA8C16" }, { label: "建议行动", value: "短期实习 + 长期规划并行", color: "#722ED1" }],
      matches: [{ type: "graduate", score: 0.85, recommended: true }, { type: "career", score: 0.72, recommended: false }, { type: "civil", score: 0.45, recommended: false }, { type: "major", score: 0.38, recommended: false }],
      recommendation: { type: "graduate", reason: "你的学术背景扎实，对深入研究有较强兴趣，考研能帮助你进入更高平台" } };
    this.setData({ summary: d.summary, messageCount: d.messageCount, insights: d.insights });
    this.updateDirections(d.matches);
    if (d.recommendation) this.setRecommendation(d.recommendation);
  },

  async loadResult() {
    wx.showLoading({ title: "分析中..." });
    try {
      const data = await app.request({ url: `/sandbox/result/${this.data.sandboxSessionId}` });
      this.setData({ summary: data.summary || "基于你的回答，AI为你生成了个性化的决策分析...", messageCount: data.message_count || 0, insights: data.insights || this.getDefaultInsights() });
      this.updateDirections(data.matches || []);
      if (data.recommendation) this.setRecommendation(data.recommendation);
    } catch (err) { wx.showToast({ title: "加载结果失败", icon: "none" }); }
    wx.hideLoading();
  },

  getDefaultInsights() { return [{ label: "当前状态", value: "待分析", color: "#4A90D9" }, { label: "核心优势", value: "待分析", color: "#52C41A" }, { label: "主要困惑", value: "待分析", color: "#FA8C16" }, { label: "建议行动", value: "待分析", color: "#722ED1" }]; },

  updateDirections(matches) {
    let dirs = this.data.directions.map(d => { const m = matches.find(m => m.type === d.type); return { ...d, matchScore: m ? Math.round(m.score * 100) : Math.floor(Math.random() * 30) + 50, recommended: m ? m.recommended : false }; });
    dirs.sort((a, b) => { if (a.recommended !== b.recommended) return b.recommended - a.recommended; return b.matchScore - a.matchScore; });
    this.setData({ directions: dirs });
  },

  setRecommendation(rec) { const d = this.data.directions.find(d => d.type === rec.type); if (!d) return; this.setData({ recommendation: { ...d, reason: rec.reason || `基于你的背景，${d.name}是最适合你的发展方向` } }); },

  async selectDirection(e) { await this.startAgent(e.currentTarget.dataset.type); },
  startRecommendedAgent() { if (this.data.recommendation) this.startAgent(this.data.recommendation.type); },

  async startAgent(agentType) {
    wx.showLoading({ title: "启动规划中..." });
    try {
      const res = await app.request({ method: "POST", url: "/api/v1/growth/start", data: { agent: agentType, user_id: wx.getStorageSync("userId") || app.globalData.userId || "" } });
      wx.hideLoading();
      wx.navigateTo({ url: `/pages/chatroom/chatroom?mode=agent&agent=${agentType}&session_id=${res.session_id || ""}` });
    } catch (err) { wx.hideLoading(); wx.showToast({ title: "启动失败，请重试", icon: "none" }); }
  },

  async reanalyze() {
    const c = await wx.showModal({ title: "重新分析", content: "当前进度将保存到历史记录，确定要重新开始吗？" });
    if (!c.confirm) return;
    wx.showModal({ title: "想调整什么？", content: "告诉AI你想调整的方向或方面", editable: true, placeholderText: "比如：我更关注就业方向而非考研",
      success: async (ir) => {
        if (!ir.confirm || !ir.content) return;
        wx.showLoading({ title: "处理中..." });
        try {
          await app.request({ method: "POST", url: "/api/v1/growth/correct", data: { session_id: this.data.sandboxSessionId, user_id: wx.getStorageSync("userId") || app.globalData.userId || "", correction: ir.content } });
          wx.hideLoading(); wx.redirectTo({ url: `/pages/chatroom/chatroom?mode=sandbox&session_id=${this.data.sandboxSessionId}&corrected=1` });
        } catch (err) { wx.hideLoading(); wx.showToast({ title: "操作失败", icon: "none" }); }
      }
    });
  },

  goBack() { wx.navigateBack(); }
});