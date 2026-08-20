const todayService = require("../../services/today-service");
const todoService = require("../../services/todo-service");
const growthService = require("../../services/growth-service");
const sessionStore = require("../../stores/session-store");
const todayStore = require("../../stores/today-store");
const growthStore = require("../../stores/growth-store");
const uiStore = require("../../stores/ui-store");
const { normalizeOverview, normalizeTimeline, normalizeCalendar, todayCompletion, todo } = require("../../normalizers/today");
const { normalizeDashboard } = require("../../normalizers/progress");
const { toDateKey, weekday, monthRange, formatTime } = require("../../utils/date");
const { selectTab, setTabBarHidden, showError, requireSession, getHeroTop } = require("../../utils/page");

function safe(promise, key) {
  return promise.then((value) => ({ key, ok: true, value })).catch((error) => ({ key, ok: false, error }));
}

Page({
  data: {
    loading: true, fatalError: "", partialErrors: [], selectedDate: "", dateLabel: "", overview: { weather: {}, todos: [], courses: [], todosCount: 0 },
    timeline: { events: [] }, calendar: { cells: [] }, todos: [], todayTodos: [], completion: { percent: 0, completed: 0, total: 0 }, dashboard: {},
    nextAction: { title: "正在整理今天", meta: "" }, nextEvent: null, sevenDayCount: 0, weekBars: [], suggestion: "", suggestionLoading: false,
    sheet: "", selectedEvent: {}, editingTodo: {}, submitting: false, confirmTask: null,
    userName: "同学", greeting: "早上好", heroTop: 86, refreshedLabel: ""
  },
  onLoad() { const now = new Date(); const user = sessionStore.state.user || {}; const hour = now.getHours(); this.setData({ selectedDate: toDateKey(now), dateLabel: `${now.getMonth() + 1}月${now.getDate()}日 · ${weekday(now)}`, userName: user.nickname || user.name || "同学", greeting: hour < 11 ? "早上好" : hour < 14 ? "中午好" : hour < 19 ? "下午好" : "晚上好", heroTop: getHeroTop(12) }); },
  onShow() { selectTab(this, 0); if (requireSession()) this.load(false); },
  onHide() { setTabBarHidden(this, false); },
  onPullDownRefresh() { this.load(true).finally(() => wx.stopPullDownRefresh()); },

  async load(force) {
    const session = requireSession(); if (!session) return;
    const now = monthRange(new Date());
    this.setData({ loading: !this.data.overview.date, fatalError: "", partialErrors: [] });
    const calls = [
      safe(todayService.overview(session.userId, uiStore.state.city), "overview"),
      safe(todayService.timeline(session.userId, this.data.selectedDate), "timeline"),
      safe(todayService.calendar(session.userId, now.year, now.month), "calendar"),
      safe(todoService.list(session.userId, "all"), "todos"),
      safe(growthService.dashboard(session.userId), "dashboard")
    ];
    const results = await Promise.all(calls);
    const values = {}; const errors = [];
    results.forEach((item) => { if (item.ok) values[item.key] = item.value; else errors.push({ key: item.key, message: item.error.message }); });
    if (!values.overview && !this.data.overview.date) { this.setData({ loading: false, fatalError: (errors[0] && errors[0].message) || "今天的数据暂时无法加载" }); return; }
    const overview = values.overview ? normalizeOverview(values.overview) : this.data.overview;
    if (overview && overview.weather && !overview.weather.location) {
      overview.weather.location = uiStore.state.city;
    }
    const timeline = values.timeline ? normalizeTimeline(values.timeline) : this.data.timeline;
    const calendar = values.calendar ? normalizeCalendar(values.calendar) : this.data.calendar;
    const todos = values.todos ? (values.todos.todos || []).map(todo) : this.data.todos;
    const dashboard = values.dashboard ? normalizeDashboard(values.dashboard) : this.data.dashboard;
    const completion = todayCompletion(values.todos ? values.todos.todos : todos, overview.date);
    const todayTodos = todos.filter((item) => item.deadline && String(item.deadline).slice(0, 10) === overview.date && !item.cancelled);
    const nextAction = this.pickNext(timeline.events, overview.todos, overview.courses, overview.nearestExam);
    const sevenDayCount = this.countSevenDays(calendar.days, overview.date);
    const weekBars = this.makeWeekBars(calendar.days, overview.date);
    todayStore.set("overview", overview); todayStore.set("timeline", timeline); todayStore.set("calendar", calendar); todayStore.set("todos", todos);
    if (dashboard) growthStore.set("dashboard", dashboard);
    this.setData({ loading: false, overview, timeline, calendar, todos, todayTodos, dashboard, completion, nextAction, nextEvent: timeline.events[0] || null, sevenDayCount, weekBars, partialErrors: errors, refreshedLabel: formatTime(new Date()) });
    if (!this.data.suggestion && uiStore.state.suggestionEnabled) this.loadSuggestion();
  },

  pickNext(events, todos, courses, nearestExam) {
    const event = (events || [])[0];
    if (event) return { eyebrow: "下一关键行动", title: event.title, meta: `${event.timeLabel}${event.location ? ` · ${event.location}` : ""}`, type: event.type };
    const task = (todos || [])[0];
    if (task) return { eyebrow: "下一关键行动", title: task.title, meta: task.deadlineLabel, type: "todo" };
    const course = (courses || [])[0];
    if (course) return { eyebrow: "下一节课程", title: course.title, meta: `${course.periodLabel}${course.location ? ` · ${course.location}` : ""}`, type: "course" };
    if (nearestExam) return { eyebrow: "最近考试", title: nearestExam.title, meta: nearestExam.dateLabel, type: "exam" };
    return { eyebrow: "今天留白", title: "没有必须完成的事项", meta: "可以为长期目标安排一个小行动", type: "empty" };
  },

  countSevenDays(days, dateKey) {
    if (!days || !days.length) return 0;
    const start = new Date(dateKey); const end = new Date(start); end.setDate(end.getDate() + 6);
    return days.filter((day) => { const date = new Date(day.date); return date >= start && date <= end; }).reduce((sum, day) => sum + day.count, 0);
  },

  makeWeekBars(days, dateKey) {
    const source = {};
    (days || []).forEach((day) => { source[day.date] = day; });
    const start = new Date(dateKey);
    const rows = Array.from({ length: 7 }, (_, index) => {
      const date = new Date(start); date.setDate(start.getDate() + index);
      const key = toDateKey(date); const day = source[key] || { count: 0 };
      return { key, dateLabel: `${date.getMonth() + 1}/${date.getDate()}`, label: ["日", "一", "二", "三", "四", "五", "六"][date.getDay()], count: Number(day.count || 0), isToday: index === 0 };
    });
    const max = Math.max(1, ...rows.map((item) => item.count));
    return rows.map((item) => Object.assign({}, item, { height: item.count ? Math.max(18, Math.round(item.count / max * 100)) : 5 }));
  },

  async loadSuggestion() {
    this.setData({ suggestionLoading: true });
    try { const result = await todayService.suggestion(sessionStore.state.userId, uiStore.state.city); this.setData({ suggestion: result.suggestion || "" }); }
    catch (error) { /* suggestions never block the page */ }
    finally { this.setData({ suggestionLoading: false }); }
  },

  async selectDay(event) {
    const day = event.detail; if (!day || !day.date) return;
    this.setData({ selectedDate: day.date, loadingTimeline: true });
    try { const result = await todayService.timeline(sessionStore.state.userId, day.date); this.setData({ timeline: normalizeTimeline(result), loadingTimeline: false }); }
    catch (error) { this.setData({ loadingTimeline: false }); showError(error, "当天轨迹加载失败"); }
  },
  setSheet(sheet, extra) { this.setData(Object.assign({ sheet }, extra || {}), () => setTabBarHidden(this, Boolean(sheet))); },
  selectEvent(event) { this.setSheet("event", { selectedEvent: event.detail }); },
  selectNextEvent() { if (this.data.nextEvent) this.setSheet("event", { selectedEvent: this.data.nextEvent }); },
  openWeather() { this.setSheet("weather"); },
  updateCity(event) { uiStore.setCity(event.detail.city); this.setSheet("", { suggestion: "" }); this.load(true); },
  openAdd() {
    wx.showActionSheet({ itemList: ["新增待办", "新增课程", "新增考试", "导入课表/考试"], success: ({ tapIndex }) => {
      if (tapIndex === 0) this.setSheet("todo", { editingTodo: { deadline: this.data.overview.date || this.data.selectedDate } });
      if (tapIndex === 1) this.setSheet("course");
      if (tapIndex === 2) this.setSheet("exam");
      if (tapIndex === 3) wx.navigateTo({ url: "/pkg-today/import/index" });
    } });
  },
  closeSheet() { this.setSheet("", { editingTodo: {}, selectedEvent: {}, confirmTask: null }); },

  async saveTodo(event) {
    if (!event.detail.title) { showError(null, "请输入任务内容"); return; }
    this.setData({ submitting: true });
    try {
      const payload = Object.assign({ source: "manual" }, event.detail);
      if (this.data.editingTodo && this.data.editingTodo.id) await todoService.update(sessionStore.state.userId, this.data.editingTodo.id, payload);
      else await todoService.create(sessionStore.state.userId, payload);
      this.closeSheet(); todayStore.invalidate(); await this.load(true);
    }
    catch (error) { showError(error, "待办保存失败"); }
    finally { this.setData({ submitting: false }); }
  },
  async saveCourse(event) {
    if (!event.detail.name) { showError(null, "请输入课程名称"); return; }
    const schedule = (event.detail.schedule || [])[0] || {};
    if (!Number.isInteger(schedule.start) || !Number.isInteger(schedule.end) || schedule.start < 1 || schedule.end < schedule.start) { showError(null, "请填写有效的开始和结束节次"); return; }
    this.setData({ submitting: true });
    try { await todayService.createCourse(sessionStore.state.userId, event.detail); this.closeSheet(); await this.load(true); }
    catch (error) { showError(error, "课程保存失败"); }
    finally { this.setData({ submitting: false }); }
  },
  async saveExam(event) {
    if (!event.detail.subject || !event.detail.exam_date) { showError(null, "请填写科目和日期"); return; }
    if (event.detail.start_time && event.detail.end_time && event.detail.end_time <= event.detail.start_time) { showError(null, "结束时间应晚于开始时间"); return; }
    this.setData({ submitting: true });
    try { await todayService.createExam(sessionStore.state.userId, event.detail); this.closeSheet(); await this.load(true); }
    catch (error) { showError(error, "考试保存失败"); }
    finally { this.setData({ submitting: false }); }
  },
  async toggleTodo(event) {
    const task = event.detail; const previous = this.data.todos.slice();
    const optimistic = previous.map((item) => item.id === task.id ? Object.assign({}, item, { done: !item.done, status: item.done ? "pending" : "done" }) : item);
    this.setData({ todos: optimistic });
    try { await todoService.toggle(sessionStore.state.userId, task.id); await this.load(true); }
    catch (error) { this.setData({ todos: previous }); showError(error, "状态更新失败，已恢复"); }
  },
  askRemove(event) { const task = event.detail; this.setSheet("confirm", { confirmTask: task }); },
  async confirmRemove() {
    const task = this.data.confirmTask; if (!task) return;
    this.setData({ submitting: true });
    try { await todoService.remove(sessionStore.state.userId, task.id); this.closeSheet(); await this.load(true); }
    catch (error) { showError(error, task.source === "ai_plan" ? "取消执行失败" : "删除失败"); }
    finally { this.setData({ submitting: false }); }
  },
  openPlan() { if (this.data.dashboard && this.data.dashboard.activePlan) wx.switchTab({ url: "/pages/action/index" }); else wx.switchTab({ url: "/pages/explore/index" }); },
  openCoach() { const coach = (this.data.dashboard && this.data.dashboard.coach) || {}; if (coach.session_id) wx.navigateTo({ url: `/pkg-growth/coach/index?sessionId=${coach.session_id}&agent=${coach.agent || "career"}` }); else wx.switchTab({ url: "/pages/action/index" }); },
  openImport() { wx.navigateTo({ url: "/pkg-today/import/index" }); },
  retry() { this.load(true); }
});
