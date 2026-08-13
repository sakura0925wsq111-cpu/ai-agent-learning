const app = getApp();
const {
  formatDateOnly,
  getAcademicWeek,
  getPickerBounds,
  getStoredSemesterStart,
  saveSemesterStart
} = require("../../utils/semester.js");

Page({
  data: {
    statusBarHeight: 44,
    headerRightPadding: 16,
    userId: "",
    loading: true,
    userInfo: {
      name: "同学",
      greeting: "早上好",
      weather: { temp: "--", condition: "--", icon: "☁️", location: "青岛", date: "" }
    },
    encourageText: "新的一天，元气满满！",
    activeSession: null,
    todayOverview: [
      { key: "courses", icon: "/images/icon-calendar.png", num: 0, unit: "节", label: "今日课程", bgColor: "#E6F2FF", hasData: false, emptyText: "今日无课" },
      { key: "todos", icon: "/images/icon-task.png", num: 0, unit: "项", label: "待办任务", bgColor: "#FFF3E6", hasData: false, emptyText: "暂无待办" },
      { key: "exam", icon: "/images/icon-book.png", num: null, unit: "天后", suffix: "", label: "最近考试", bgColor: "#E6F9ED", hasData: false, emptyText: "最近没有考试", isExam: true }
    ],
    semesterStart: "",
    semesterPickerValue: "",
    semesterStartMin: "",
    semesterStartMax: "",
    semesterOverview: { num: null, unit: "", text: "待设置", label: "当前周次" },
    aiSuggestion: { icon: "/images/icon-ai-bulb.png", title: "", content: "", fullText: "", action: "查看详情", loading: false },
    todoList: [],
    todosLoading: false,
    weatherError: false,
    overviewError: false,
    todosError: false
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
    const bounds = getPickerBounds();
    const userId = wx.getStorageSync("userId") || app.globalData.userId || "";
    const menuRect = wx.getMenuButtonBoundingClientRect ? wx.getMenuButtonBoundingClientRect() : null;
    const headerRightPadding = menuRect && menuRect.left
      ? Math.max(16, info.windowWidth - menuRect.left + 8)
      : 16;
    this.setData({
      statusBarHeight: info.statusBarHeight,
      headerRightPadding,
      userId,
      semesterPickerValue: formatDateOnly(new Date()),
      semesterStartMin: bounds.min,
      semesterStartMax: bounds.max
    });
    this.loadUserGreeting();
    this.refreshSemesterOverview();
    await this.loadAllData();
  },

  async onShow() {
    this.loadUserGreeting();
    this.refreshSemesterOverview();
    if (!this.data.loading) await this.refreshData();
  },
  async onPullDownRefresh() { await this.refreshData(); wx.stopPullDownRefresh(); },

  async loadAllData() {
    this.setData({ loading: true });
    const coreResults = await Promise.allSettled([
      this.loadWeather(), this.loadTodayOverview(), this.loadTodos()
    ]);
    this.logRequestFailures("首页核心数据", coreResults);
    this.setData({ loading: false });
    this.loadSecondaryData();
  },

  async refreshData() {
    const coreResults = await Promise.allSettled([
      this.loadWeather(), this.loadTodayOverview(), this.loadTodos()
    ]);
    this.logRequestFailures("首页刷新", coreResults);
    this.loadSecondaryData();
  },

  async loadSecondaryData() {
    const results = await Promise.allSettled([
      this.loadAISuggestion(), this.checkActiveSession()
    ]);
    this.logRequestFailures("首页次要数据", results);
  },

  logRequestFailures(scope, results) {
    const messages = results
      .filter((item) => item.status === "rejected")
      .map((item) => item.reason && item.reason.errMsg || item.reason && item.reason.message || "请求失败");
    if (messages.length > 0) console.warn(scope + "加载失败:", messages);
  },

  async loadWeather() {
    const city = wx.getStorageSync("weatherCity") || "青岛";
    this.setData({ weatherError: false });
    try {
      const res = await app.request({
        url: "/api/v1/weather?city=" + encodeURIComponent(city),
        authRedirect: false,
        timeout: 10000
      });
      this.setData({
        weatherError: false,
        "userInfo.weather": {
          temp: res.temp ?? "--", condition: res.condition || "--", icon: res.icon || "☁️",
          location: res.location || city, date: this.formatDate(new Date())
        }
      });
    } catch (err) {
      this.setData({ weatherError: true, "userInfo.weather.location": city, "userInfo.weather.date": this.formatDate(new Date()) });
      throw err;
    }
  },

  async loadTodayOverview() {
    this.setData({ overviewError: false });
    try {
      const res = await app.request({
        url: "/api/v1/today/overview?user_id=" + this.data.userId,
        timeout: 10000
      });
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
        this.setData({ todayOverview: overview, encourageText: this.getEncourageText(overview), overviewError: false });
      }
    } catch (err) {
      this.setData({ overviewError: true });
      throw err;
    }
  },

  async loadTodos() {
    this.setData({ todosLoading: true, todosError: false });
    try {
      const res = await app.request({
        url: "/api/v1/todos?user_id=" + this.data.userId + "&status=pending",
        timeout: 10000
      });
      const list = (res && res.todos) ? res.todos.slice(0, 5) : [];
      this.setData({
        todoList: list.map(item => ({
          id: item.id, title: item.title || "", time: item.deadline ? this.formatDeadline(item.deadline) : "",
          done: false, source: item.source || "manual"
        })),
        todosLoading: false,
        todosError: false
      });
    } catch (err) { this.setData({ todosLoading: false, todosError: true }); throw err; }
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
        data: { user_id: this.data.userId, city: this.data.userInfo.weather.location || "" }, timeout: 20000
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
      const res = await app.request({
        url: "/api/v1/growth/state/" + this.data.userId,
        timeout: 10000
      });
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
  retryWeather() { this.loadWeather().catch(err => console.error(err)); },
  retryOverview() { this.loadTodayOverview().catch(err => console.error(err)); },
  retryTodos() { this.loadTodos().catch(err => console.error(err)); },

  refreshSemesterOverview() {
    const semesterStart = getStoredSemesterStart();
    const week = getAcademicWeek(semesterStart);
    let semesterOverview = { num: null, unit: "", text: "待设置", label: "当前周次" };
    if (week === 0) {
      semesterOverview = { ...semesterOverview, text: "未开学" };
    } else if (week !== null) {
      semesterOverview = { ...semesterOverview, num: week, unit: "周", text: "" };
    }
    this.setData({ semesterStart, semesterOverview });
  },

  async onSemesterDateChange(e) {
    const semesterStart = e.detail.value;
    if (!saveSemesterStart(semesterStart)) return;
    this.refreshSemesterOverview();

    try {
      await app.request({
        method: "PUT",
        url: "/api/v1/today/courses/semester-settings?user_id=" + this.data.userId,
        data: { semester_start: semesterStart }
      });
      wx.showToast({ title: "开学日期已同步", icon: "success" });
      await this.loadTodayOverview();
    } catch (err) {
      console.error("同步开学日期失败:", err);
      wx.showToast({ title: "已保存，旧课表同步失败", icon: "none" });
    }
  },

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
      await Promise.allSettled([this.loadTodos(), this.loadTodayOverview()]);
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
        this.loadTodayOverview().catch(err => console.error(err));
      }, 300);
    } catch (err) { wx.showToast({ title: "操作失败", icon: "error" }); this.setData({ todoList: list }); }
  }
});
