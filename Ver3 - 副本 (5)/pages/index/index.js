const app = getApp();

Page({
  data: {
    statusBarHeight: 44,
    userId: "",
    loading: true,
    hasError: false,
    errorMsg: "",
    userInfo: {
      name: "同学",
      greeting: "早上好",
      weather: { temp: "--", condition: "--", location: "青岛", date: "" }
    },
    encourageText: "新的一天，元气满满！",
    activeSession: null,
    todayOverview: [
      { key: "courses", icon: "/images/icon-calendar.png", num: 0, unit: "节", label: "今日课程", bgColor: "#E6F2FF", hasData: false, emptyText: "今日无课" },
      { key: "todos", icon: "/images/icon-task.png", num: 0, unit: "项", label: "待办任务", bgColor: "#FFF3E6", hasData: false, emptyText: "暂无待办" },
      { key: "exam", icon: "/images/icon-book.png", num: null, unit: "天后", suffix: "", label: "最近考试", bgColor: "#E6F9ED", hasData: false, emptyText: "最近没有考试", isExam: true },
      { key: "notice", icon: "/images/icon-notice.png", num: "--", unit: "", label: "校园通知", bgColor: "#F0E6FF", disabled: true }
    ],
    aiSuggestion: { icon: "/images/icon-ai-bulb.png", title: "", content: "", fullText: "", action: "查看详情", loading: false },
    todoList: [],
    todosLoading: false
  },

  getGreeting() {
    const hour = new Date().getHours();
    if (hour < 6) return "夜深了";
    if (hour < 9) return "早上好";
    if (hour < 12) return "上午好";
    if (hour < 14) return "中午好";
    if (hour < 18) return "下午好";
    if (hour < 22) return "晚上好";
    return "夜深了";
  },

  loadUserGreeting() {
    const stored = wx.getStorageSync("userInfo") || app.globalData.userInfo || {};
    const fullName = stored.name || "";
    const surname = fullName ? fullName.charAt(0) : "";
    this.setData({
      "userInfo.name": surname ? surname + "同学" : "同学",
      "userInfo.greeting": this.getGreeting()
    });
  },

  getEncourageText(overview) {
    const hour = new Date().getHours();
    if (hour >= 22 || hour < 6) return "夜深了，早点休息吧";
    const courses = overview.find(item => item.key === "courses")?.num || 0;
    const todos = overview.find(item => item.key === "todos")?.num || 0;
    const exam = overview.find(item => item.key === "exam");
    const examDays = exam?.num;
    const examSubject = exam?.suffix;
    if (examDays !== null && examDays !== undefined && examDays <= 7 && examDays >= 0) {
      return examSubject + "考试还有" + examDays + "天，保持节奏！";
    }
    if (courses > 0 && todos > 0) return "今天有" + courses + "节课和" + todos + "项任务，加油！";
    if (courses > 0 && todos === 0) return "今天有" + courses + "节课，专注听课～";
    if (courses === 0 && todos > 0) return "今天没有课，还有" + todos + "项任务待完成";
    return "今天没有安排，好好休息～";
  },

  async onLoad() {
    const info = wx.getSystemInfoSync();
    const userId = wx.getStorageSync("userId") || app.globalData.userId || "";
    this.setData({ statusBarHeight: info.statusBarHeight, userId });
    this.loadUserGreeting();
    await this.loadAllData();
  },

  async onShow() { if (!this.data.loading) { this.refreshData(); } },
  async onPullDownRefresh() { await this.refreshData(); wx.stopPullDownRefresh(); },
  onRetry() { this.setData({ hasError: false }); this.loadAllData(); },

  async loadAllData() {
    this.setData({ loading: true, hasError: false, errorMsg: "" });
    try {
      await Promise.all([
        this.loadWeather(), this.loadTodayOverview(), this.loadTodos(),
        this.loadAISuggestion(), this.checkActiveSession()
      ]);
    } catch (err) {
      console.error(err);
      this.setData({ hasError: true, errorMsg: err.message || "网络异常，请下拉重试" });
    } finally { this.setData({ loading: false }); }
  },

  async refreshData() {
    try {
      await Promise.all([
        this.loadWeather(), this.loadTodayOverview(), this.loadTodos(),
        this.loadAISuggestion(), this.checkActiveSession()
      ]);
    } catch (err) { console.error(err); }
  },

  async loadWeather() {
    try {
      const res = await app.request({ url: "/api/v1/weather?city=" + encodeURIComponent("青岛") });
      this.setData({ "userInfo.weather": { temp: res.temp || "--", condition: res.condition || "--", location: res.location || "青岛", date: this.formatDate(new Date()) } });
    } catch (err) { this.setData({ "userInfo.weather.date": this.formatDate(new Date()) }); }
  },

  async loadTodayOverview() {
    try {
      const res = await app.request({ url: "/api/v1/today/overview?user_id=" + this.data.userId });
      if (res) {
        const overview = this.data.todayOverview.map((item) => {
          if (item.key === "courses") {
            const count = res.courses_count || 0;
            return { ...item, num: count, hasData: count > 0, emptyText: count === 0 ? "今日无课" : "" };
          }
          if (item.key === "todos") {
            const count = res.todos_count || 0;
            return { ...item, num: count, hasData: count > 0, emptyText: count === 0 ? "暂无待办" : "" };
          }
          if (item.key === "exam") {
            const exam = res.nearest_exam;
            if (exam && exam.exam_date) {
              const examDate = new Date(exam.exam_date);
              const today = new Date(); today.setHours(0, 0, 0, 0);
              const diffDays = Math.ceil((examDate - today) / (1000 * 60 * 60 * 24));
              if (diffDays >= 0 && diffDays <= 14) {
                return { ...item, num: diffDays, suffix: exam.subject || "", hasData: true, emptyText: "" };
              }
            }
            return { ...item, num: null, suffix: "", hasData: false, emptyText: "最近没有考试" };
          }
          return item;
        });
        this.setData({ todayOverview: overview, encourageText: this.getEncourageText(overview) });
      }
    } catch (err) {
      const emptyOverview = this.data.todayOverview.map(item => {
        if (item.key === "courses") return { ...item, num: 0, hasData: false, emptyText: "今日无课" };
        if (item.key === "todos") return { ...item, num: 0, hasData: false, emptyText: "暂无待办" };
        if (item.key === "exam") return { ...item, num: null, suffix: "", hasData: false, emptyText: "最近没有考试" };
        return item;
      });
      this.setData({ todayOverview: emptyOverview, encourageText: "新的一天，从规划开始～" });
      throw err;
    }
  },

  async loadTodos() {
    this.setData({ todosLoading: true });
    try {
      const res = await app.request({ url: "/api/v1/todos?user_id=" + this.data.userId + "&status=pending" });
      const list = (res && res.todos) ? res.todos.slice(0, 5) : [];
      this.setData({
        todoList: list.map(item => ({
          id: item.id, title: item.title || "", time: item.deadline ? this.formatDeadline(item.deadline) : "",
          done: false, source: item.source || "manual"
        })),
        todosLoading: false
      });
    } catch (err) { this.setData({ todosLoading: false }); throw err; }
  },

  async loadAISuggestion() {
    const cache = app.globalData.suggestionCache;
    if (cache && cache.text && (Date.now() - cache.timestamp < 300000)) {
      const displayText = cache.text.length > 60 ? cache.text.substring(0, 58) + "..." : cache.text;
      this.setData({ aiSuggestion: { icon: "/images/icon-ai-bulb.png", title: "AI今日建议", content: displayText, fullText: cache.text, action: "查看详情", loading: false } });
      return;
    }
    this.setData({ "aiSuggestion.loading": true });
    try {
      const res = await app.request({
        method: "POST", url: "/api/v1/today/suggestion",
        data: { user_id: this.data.userId, city: this.data.userInfo.weather.location || "" }, timeout: 15000
      });
      if (res && res.suggestion) {
        const fullText = res.suggestion;
        let displayText = fullText.length > 60 ? fullText.substring(0, 58) + "..." : fullText;
        app.globalData.suggestionCache = { text: fullText, timestamp: Date.now() };
        this.setData({ aiSuggestion: { icon: "/images/icon-ai-bulb.png", title: "AI今日建议", content: displayText, fullText: fullText, action: "查看详情", loading: false } });
      } else {
        this.setData({ aiSuggestion: { icon: "/images/icon-ai-bulb.png", title: "AI今日建议", content: "暂无个性化建议", fullText: "", action: "查看详情", loading: false } });
      }
    } catch (err) {
      this.setData({ aiSuggestion: { icon: "/images/icon-ai-bulb.png", title: "AI今日建议", content: "获取建议失败", fullText: "", action: "查看详情", loading: false } });
      throw err;
    }
  },
  async checkActiveSession() {
    if (!this.data.userId) return;
    try {
      const res = await app.request({ url: "/api/v1/growth/state/" + this.data.userId });
      if (res && res.session_id && !res.finished) { this.setData({ activeSession: res }); }
      else { this.setData({ activeSession: null }); }
    } catch (err) { this.setData({ activeSession: null }); }
  },

  formatDate(date) {
    const weekDays = ["日", "一", "二", "三", "四", "五", "六"];
    return (date.getMonth() + 1) + "月" + date.getDate() + "日 周" + weekDays[date.getDay()];
  },

  formatDeadline(deadlineStr) {
    if (!deadlineStr) return "";
    const d = new Date(deadlineStr), now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const target = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    const diffDays = Math.round((target - today) / 86400000);
    const timeStr = String(d.getHours()).padStart(2, '0') + ":" + String(d.getMinutes()).padStart(2, '0');
    if (diffDays === 0) return "今天 " + timeStr + "截止";
    if (diffDays === 1) return "明天 " + timeStr + "截止";
    if (diffDays > 1) return diffDays + "天后 " + timeStr + "截止";
    return Math.abs(diffDays) + "天前截止";
  },

  onSuggestionTap() {
    if (this.data.aiSuggestion.fullText) app.globalData.aiSuggestionFull = this.data.aiSuggestion.fullText;
    wx.switchTab({ url: "/pages/schedule/schedule" });
  },

  continueSession() {
    const s = this.data.activeSession;
    if (!s || !s.session_id) return;
    wx.navigateTo({ url: "/pages/chatroom/chatroom?mode=agent&session_id=" + s.session_id + "&agent=" + (s.agent || "career") });
  },

  goToAI() { wx.navigateTo({ url: "/pages/ai/ai" }); },
  goToSchedule() { wx.switchTab({ url: "/pages/schedule/schedule" }); },
  goToWeather() { wx.navigateTo({ url: "/pages/weather/weather" }); },
  goToTasks() { wx.navigateTo({ url: "/pages/tasks/tasks" }); },

  onOverviewTap(e) {
    const key = e.currentTarget.dataset.key;
    if (key === "notice") return;
    if (key === "todos") { wx.navigateTo({ url: "/pages/tasks/tasks" }); return; }
    wx.switchTab({ url: "/pages/schedule/schedule" });
  },

  onAddTodo() {
    wx.showModal({
      title: "添加待办", editable: true, placeholderText: "输入待办事项内容", confirmText: "添加",
      success: (res) => { if (res.confirm && res.content && res.content.trim()) this.createTodo(res.content.trim()); }
    });
  },

  async createTodo(title) {
    wx.showLoading({ title: "添加中", mask: true });
    try {
      await app.request({ method: "POST", url: "/api/v1/todos?user_id=" + this.data.userId, data: { title: title, source: "manual" } });
      wx.hideLoading(); wx.showToast({ title: "添加成功", icon: "success" });
      this.loadTodos();
      const overview = this.data.todayOverview.map(item => {
        if (item.key === "todos") { const n = item.num + 1; return { ...item, num: n, hasData: true, emptyText: "" }; }
        return item;
      });
      this.setData({ todayOverview: overview, encourageText: this.getEncourageText(overview) });
    } catch (err) { wx.hideLoading(); wx.showToast({ title: "添加失败", icon: "error" }); }
  },

  async toggleTodo(e) {
    const { id, index } = e.currentTarget.dataset;
    const list = this.data.todoList, item = list[index];
    if (!item || item.done) return;
    this.setData({ todoList: list.map((t, i) => i === index ? { ...t, done: true } : t) });
    try {
      await app.request({ method: "POST", url: "/api/v1/todos/" + id + "/toggle?user_id=" + this.data.userId });
      setTimeout(() => {
        this.setData({ todoList: this.data.todoList.filter(t => t.id !== id) });
        const overview = this.data.todayOverview.map(item => {
          if (item.key === "todos") { const n = Math.max(0, item.num - 1); return { ...item, num: n, hasData: n > 0, emptyText: n === 0 ? "暂无待办" : "" }; }
          return item;
        });
        this.setData({ todayOverview: overview, encourageText: this.getEncourageText(overview) });
      }, 300);
    } catch (err) { wx.showToast({ title: "操作失败", icon: "error" }); this.setData({ todoList: list }); }
  }
});