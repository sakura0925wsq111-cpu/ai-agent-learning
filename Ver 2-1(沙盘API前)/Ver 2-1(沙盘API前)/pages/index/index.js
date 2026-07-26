const app = getApp();

Page({
  data: {
    statusBarHeight: 44,
    userId: "",
    activeSession: null,
    userInfo: {
      name: "吴同学",
      greeting: "早上好",
      weather: {
        temp: "--",
        condition: "--",
        location: "青岛",
        date: "7月24日 周一"
      }
    },
    todayOverview: [
      { icon: "/images/icon-calendar.png", num: 2, unit: "节", label: "今日课程", bgColor: "#E6F2FF" },
      { icon: "/images/icon-task.png", num: 1, unit: "项", label: "待办任务", bgColor: "#FFF3E6" },
      { icon: "/images/icon-book.png", num: 3, unit: "天后", suffix: "高数考试", label: "", bgColor: "#E6F9ED" },
      { icon: "/images/icon-notice.png", num: 2, unit: "条", label: "校园通知", bgColor: "#F0E6FF" }
    ],
    aiSuggestion: {
      icon: "/images/icon-ai-bulb.png",
      title: "今天有2节课和1项任务",
      content: "建议上午完成高数复习，预留时间练习题目",
      action: "查看详情"
    },
    todoList: [
      { id: 1, title: "完成高数课后练习", time: "今天 14:00截止", done: false },
      { id: 2, title: "阅读《AI导论》第3章", time: "", done: false }
    ]
  },

  async onLoad() {
    const info = wx.getSystemInfoSync();
    const userId = wx.getStorageSync("userId") || app.globalData.userId || "";
    this.setData({ statusBarHeight: info.statusBarHeight, userId });
    this.loadWeather();
    this.loadTodayOverview();
    this.checkActiveSession();
  },

  async checkActiveSession() {
    if (!this.data.userId) return;
    try {
      const res = await app.request({ url: `/api/v1/growth/state/${this.data.userId}` });
      if (res.session_id && !res.finished) {
        this.setData({ activeSession: res });
      }
    } catch (err) { /* 无进行中会话 */ }
  },

  continueSession() {
    const s = this.data.activeSession;
    if (!s || !s.session_id) return;
    wx.navigateTo({ url: `/pages/chatroom/chatroom?mode=agent&session_id=${s.session_id}&agent=${s.agent || "career"}` });
  },

  async loadWeather() {
    try {
      const city = await this.getCityFromLocation();
      const res = await app.request({ url: `/api/v1/weather?city=${encodeURIComponent(city)}` });
      this.setData({
        "userInfo.weather": {
          temp: res.temp,
          condition: res.condition,
          location: res.location,
          date: this.formatDate(new Date())
        }
      });
    } catch (err) {
      this.setData({ "userInfo.weather.date": this.formatDate(new Date()) });
    }
  },

  getCityFromLocation() {
    return new Promise((resolve) => {
      wx.getLocation({ type: "gcj02", success: () => resolve("青岛"), fail: () => resolve("青岛") });
    });
  },

  async loadTodayOverview() {
    try { await app.request({ url: "/api/v1/today/overview" }); } catch (err) {}
  },

  formatDate(date) {
    const month = date.getMonth() + 1;
    const day = date.getDate();
    const weekDays = ["日", "一", "二", "三", "四", "五", "六"];
    return `${month}月${day}日 周${weekDays[date.getDay()]}`;
  },

  goToAI() { wx.navigateTo({ url: '/pages/ai/ai' }); },

  goToSchedule() { wx.switchTab({ url: "/pages/schedule/schedule" }); },
  goToWeather() { wx.navigateTo({ url: "/pages/weather/weather" }); },

  async toggleTodo(e) {
    const id = e.currentTarget.dataset.id;
    const list = this.data.todoList;
    const item = list.find(t => t.id === id);
    if (!item) return;

    // Three-state: pending -> done -> archived (removed)
    if (!item.done) {
      // Mark as done
      this.setData({ todoList: list.map(t => t.id === id ? { ...t, done: true } : t) });
      try {
        await app.request({ method: "POST", url: `/api/v1/todos/${id}/toggle?user_id=${this.data.userId}` });
      } catch (err) { /* offline ok */ }
    } else {
      // Archive (remove from list)
      this.setData({ todoList: list.filter(t => t.id !== id) });
      try {
        await app.request({ method: "POST", url: `/api/v1/todos/${id}/toggle?user_id=${this.data.userId}` });
      } catch (err) { /* offline ok */ }
    }
  }
});