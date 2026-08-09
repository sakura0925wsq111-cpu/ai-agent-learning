const app = getApp();
const { normalizeDateStr } = require("../../utils/date.js");

Page({
  data: {
    statusBarHeight: 44,
    currentYear: 2026,
    currentMonth: 8,
    selectedDate: "",
    today: "",
    calendarView: "month",
    weekStartIndex: 0,
    calendarDays: [],
    calendarEventsMap: {},
    scheduleList: [],
    scheduleLoading: false,
    aiSuggestion: { loading: true, text: "", hasError: false },
    fabOpen: false,
    calendarCollapsed: true
  },

  getUserId() {
    return app.globalData.userId || wx.getStorageSync("userId") || "";
  },

  onLoad() {
    const info = wx.getSystemInfoSync();
    const now = new Date();
    const year = now.getFullYear();
    const month = now.getMonth() + 1;
    const date = now.getDate();
    const dateStr = this.getDateStr(year, month, date);
    this.setData({
      statusBarHeight: info.statusBarHeight,
      currentYear: year, currentMonth: month,
      selectedDate: dateStr, today: dateStr
    });
    this.generateCalendar();
    this.loadCalendarEvents(year, month);
    this.loadScheduleForDate(dateStr);
    this.loadAISuggestion();
  },

  getDateStr(year, month, date) {
    return normalizeDateStr(year, month, date);
  },

  generateCalendar() {
    const { currentYear, currentMonth, selectedDate, today, calendarEventsMap } = this.data;
    const firstDay = new Date(currentYear, currentMonth - 1, 1).getDay();
    const daysInMonth = new Date(currentYear, currentMonth, 0).getDate();
    const daysInPrevMonth = new Date(currentYear, currentMonth - 1, 0).getDate();
    const days = [];
    for (let i = firstDay - 1; i >= 0; i--) {
      const d = daysInPrevMonth - i;
      const fd = this.getDateStr(currentYear, currentMonth - 1, d);
      days.push({ date: d, fullDate: fd, isCurrentMonth: false, isToday: fd === today, isSelected: fd === selectedDate, isWeekend: false, events: calendarEventsMap[fd] || [] });
    }
    for (let i = 1; i <= daysInMonth; i++) {
      const fd = this.getDateStr(currentYear, currentMonth, i);
      const dow = new Date(currentYear, currentMonth - 1, i).getDay();
      days.push({ date: i, fullDate: fd, isCurrentMonth: true, isToday: fd === today, isSelected: fd === selectedDate, isWeekend: dow === 0 || dow === 6, events: calendarEventsMap[fd] || [] });
    }
    const totalRows = Math.ceil(days.length / 7);
    const needRows = totalRows > 5 ? 6 : 5;
    const needFill = needRows * 7 - days.length;
    for (let i = 1; i <= needFill; i++) {
      const fd = this.getDateStr(currentYear, currentMonth + 1, i);
      days.push({ date: i, fullDate: fd, isCurrentMonth: false, isToday: fd === today, isSelected: fd === selectedDate, isWeekend: false, events: [] });
    }
    this.setData({ calendarDays: days });
    this.calcWeekStartIndex();
  },

  calcWeekStartIndex() {
    const idx = this.data.calendarDays.findIndex(d => d.fullDate === this.data.selectedDate);
    if (idx >= 0) this.setData({ weekStartIndex: Math.floor(idx / 7) * 7 });
  },

  async loadCalendarEvents(year, month) {
    try {
      const res = await app.request({
        url: "/api/v1/today/calendar",
        data: { user_id: this.getUserId(), year: year, month: month }
      });
      if (res && res.days) {
        const eventsMap = {};
        res.days.forEach(day => {
          const types = [...new Set((day.events || []).map(e => e.event_type))]; eventsMap[day.date] = types.map(t => ({ type: t }));
        });
        this.setData({ calendarEventsMap: eventsMap }, () => { this.generateCalendar(); });
      }
    } catch (err) { console.error("\u52a0\u8f7d\u65e5\u5386\u5931\u8d25:", err); }
  },

  onDateTap(e) {
    const { date, iscurrentmonth } = e.currentTarget.dataset;
    if (!iscurrentmonth) {
      const d = new Date(date);
      this.setData({ currentYear: d.getFullYear(), currentMonth: d.getMonth() + 1, selectedDate: date }, () => {
        this.generateCalendar();
        this.loadCalendarEvents(this.data.currentYear, this.data.currentMonth);
        this.loadScheduleForDate(date);
      });
      return;
    }
    this.setData({ selectedDate: date }, () => {
      this.calcWeekStartIndex();
      this.loadScheduleForDate(date);
    });
  },

  prevMonth() {
    let { currentYear, currentMonth } = this.data;
    if (currentMonth === 1) { currentYear--; currentMonth = 12; }
    else { currentMonth--; }
    this.setData({ currentYear, currentMonth, calendarView: "month" }, () => {
      this.generateCalendar();
      this.loadCalendarEvents(currentYear, currentMonth);
    });
  },

  nextMonth() {
    let { currentYear, currentMonth } = this.data;
    if (currentMonth === 12) { currentYear++; currentMonth = 1; }
    else { currentMonth++; }
    this.setData({ currentYear, currentMonth, calendarView: "month" }, () => {
      this.generateCalendar();
      this.loadCalendarEvents(currentYear, currentMonth);
    });
  },

  prevWeek() {
    const { weekStartIndex, calendarDays } = this.data;
    const newIdx = Math.max(0, weekStartIndex - 7);
    const newDate = calendarDays[newIdx] && calendarDays[newIdx].fullDate || this.data.selectedDate;
    this.setData({ weekStartIndex: newIdx, selectedDate: newDate, calendarView: "week" }, () => {
      this.loadScheduleForDate(newDate);
    });
  },

  nextWeek() {
    const { weekStartIndex, calendarDays } = this.data;
    const newIdx = Math.min(calendarDays.length - 7, weekStartIndex + 7);
    const newDate = calendarDays[newIdx] && calendarDays[newIdx].fullDate || this.data.selectedDate;
    this.setData({ weekStartIndex: newIdx, selectedDate: newDate, calendarView: "week" }, () => {
      this.loadScheduleForDate(newDate);
    });
  },

  onGoToday() {
    const now = new Date();
    const year = now.getFullYear();
    const month = now.getMonth() + 1;
    const ts = this.data.today;
    this.setData({
      selectedDate: ts,
      currentYear: year,
      currentMonth: month,
      calendarView: "month"
    }, () => {
      this.loadCalendarEvents(year, month);
      this.loadScheduleForDate(ts);
    });
  },

  onToggleView() {
    const v = this.data.calendarView === "month" ? "week" : "month";
    this.setData({ calendarView: v }, () => { this.calcWeekStartIndex(); });
  },

  async loadScheduleForDate(dateStr) {
    this.setData({ scheduleLoading: true });
    try {
      const res = await app.request({
        url: "/api/v1/today/timeline",
        data: { user_id: this.getUserId(), date: dateStr }
      });
      let events = [];
      if (res && res.events) { events = res.events.map(e => this.mapEvent(e)); }
      events = this.sortEvents(events);
      events = this.calcEventStatus(events);
      this.setData({ scheduleList: events, scheduleLoading: false });
    } catch (err) {
      console.error("\u52a0\u8f7d\u65e5\u7a0b\u5931\u8d25:", err);
      this.setData({ scheduleList: [], scheduleLoading: false });
    }
  },

  mapEvent(e) {
    const time = this.normalizeEventTime(e.time || (e.start ? e.start + ":00" : ""));
    return {
      id: e.id, title: e.title || e.name || e.subject || "",
      time: time,
      endTime: e.end_time || "",
      location: e.location || "",
      eventType: e.event_type || "todo",
      source: e.source || "manual",
      status: e.status || "pending",
      sortKey: e.sort_key || 99
    };
  },

  normalizeEventTime(value) {
    if (!value) return "";
    if (/^\d{2}:\d{2}/.test(value)) return value.substring(0, 5);
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return "";
    return String(parsed.getHours()).padStart(2, "0") + ":" + String(parsed.getMinutes()).padStart(2, "0");
  },

  sortEvents(events) {
    return events.sort((a, b) => (a.sortKey || 99) - (b.sortKey || 99) || (a.time || "").localeCompare(b.time || ""));
  },

  calcEventStatus(events) {
    const now = new Date();
    const selected = this.data.selectedDate.split("-").map(Number);
    const eventDay = new Date(selected[0], selected[1] - 1, selected[2]);
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    return events.map(e => {
      if (!e.time) return { ...e, statusLabel: "", isActive: false };
      const [h, m] = e.time.split(":").map(Number);
      const start = new Date(eventDay.getFullYear(), eventDay.getMonth(), eventDay.getDate(), h || 0, m || 0);
      if (eventDay < today) return { ...e, statusLabel: "已结束", isActive: false };
      if (eventDay > today) return { ...e, statusLabel: "未开始", isActive: false };
      if (e.endTime) {
        const [eh, em] = e.endTime.split(":").map(Number);
        const end = new Date(now.getFullYear(), now.getMonth(), now.getDate(), eh || 0, em || 0);
        if (now >= start && now < end) return { ...e, statusLabel: "进行中", isActive: true };
        if (now < start) return { ...e, statusLabel: "未开始", isActive: false };
        return { ...e, statusLabel: "已结束", isActive: false };
      }
      if (now < start) return { ...e, statusLabel: "未开始", isActive: false };
      return { ...e, statusLabel: "", isActive: false };
    });
  },

  toggleFab() { this.setData({ fabOpen: !this.data.fabOpen }); },
  closeFab() { this.setData({ fabOpen: false }); },

  toggleCalendar() { this.setData({ calendarCollapsed: !this.data.calendarCollapsed }); },

  onImportSchedule() {
    this.closeFab();
    wx.navigateTo({ url: "/pages/import/import" });
  },

  onAddCourse() {
    this.closeFab();
    wx.showModal({
      title: "添加课程",
      editable: true,
      placeholderText: "课程名称",
      confirmText: "下一步",
      success: (res) => {
        if (!res.confirm || !res.content || !res.content.trim()) return;
        const name = res.content.trim();
        wx.showModal({
          title: "上课地点",
          editable: true,
          placeholderText: "例如：教三楼301",
          confirmText: "下一步",
          success: (res2) => {
            const location = (res2.confirm && res2.content) ? res2.content.trim() : "";
            wx.showModal({
              title: "星期几？",
              editable: true,
              placeholderText: "1=周一, 2=周二... 7=周日",
              confirmText: "下一步",
              success: (res3) => {
                const wd = parseInt(res3.content);
                if (isNaN(wd) || wd < 1 || wd > 7) {
                  wx.showToast({ title: "请输入1-7", icon: "none" });
                  return;
                }
                wx.showModal({
                  title: "节次范围",
                  editable: true,
                  placeholderText: "例如：1-2",
                  confirmText: "添加",
                  success: (res4) => {
                    const range = (res4.confirm && res4.content) ? res4.content.trim() : "1-2";
                    const parts = range.split("-");
                    const start = parseInt(parts[0]) || 1;
                    const end = parseInt(parts[1]) || start;
                    this.createCourse(name, location, wd, { start: start, end: end });
                  }
                });
              }
            });
          }
        });
      }
    });
  },

  async createCourse(name, location, weekday, slot) {
    wx.showLoading({ title: "添加中...", mask: true });
    try {
      const userId = this.getUserId();
      await app.request({
        method: "POST",
        url: "/api/v1/today/courses?user_id=" + userId,
        data: {
          name: name, teacher: "", location: location,
          schedule: [{ weekday: weekday, start: slot.start, end: slot.end, weeks: "1-16" }],
          notes: "", color: "#4A90D9", source: "manual"
        }
      });
      wx.hideLoading();
      wx.showToast({ title: "课程已添加", icon: "success" });
      this.loadCalendarEvents(this.data.currentYear, this.data.currentMonth);
      this.loadScheduleForDate(this.data.selectedDate);
    } catch (err) {
      wx.hideLoading();
      wx.showToast({ title: "添加失败", icon: "error" });
    }
  },

  onAddExam() {
    this.closeFab();
    wx.showModal({
      title: "添加考试",
      editable: true,
      placeholderText: "考试科目名称",
      confirmText: "下一步",
      success: (res) => {
        if (!res.confirm || !res.content || !res.content.trim()) return;
        this.showExamDetailForm(res.content.trim());
      }
    });
  },

  showExamDetailForm(subject) {
    wx.showModal({
      title: "考试日期",
      editable: true,
      placeholderText: "例如：2026-08-15",
      confirmText: "下一步",
      success: (res1) => {
        const examDate = (res1.confirm && res1.content) ? res1.content.trim() : this.data.selectedDate;
        wx.showModal({
          title: "考试时间",
          editable: true,
          placeholderText: "例如：10:00",
          confirmText: "下一步",
          success: (res2) => {
            const startTime = (res2.confirm && res2.content) ? res2.content.trim() : "10:00";
            wx.showModal({
              title: "考试地点",
              editable: true,
              placeholderText: "例如：主教学楼A101",
              confirmText: "添加",
              success: (res3) => {
                const location = (res3.confirm && res3.content) ? res3.content.trim() : "";
                this.createExam(subject, examDate, startTime, location);
              }
            });
          }
        });
      }
    });
  },

  async createExam(subject, examDate, startTime, location) {
    wx.showLoading({ title: "添加中...", mask: true });
    try {
      const userId = this.getUserId();
      await app.request({
        method: "POST",
        url: "/api/v1/today/exams?user_id=" + userId,
        data: {
          subject: subject, exam_date: examDate,
          start_time: startTime, end_time: "", location: location,
          notes: "", source: "manual"
        }
      });
      wx.hideLoading();
      wx.showToast({ title: "考试已添加", icon: "success" });
      this.loadCalendarEvents(this.data.currentYear, this.data.currentMonth);
      this.loadScheduleForDate(this.data.selectedDate);
    } catch (err) {
      wx.hideLoading();
      wx.showToast({ title: "添加失败", icon: "error" });
    }
  },

  onAddTodo() {
    this.closeFab();
    wx.showModal({
      title: "添加待办",
      editable: true,
      placeholderText: "输入待办事项内容",
      confirmText: "添加",
      success: (res) => {
        if (!res.confirm || !res.content || !res.content.trim()) return;
        this.createTodo(res.content.trim());
      }
    });
  },

  async createTodo(title) {
    wx.showLoading({ title: "添加中...", mask: true });
    try {
      const userId = this.getUserId();
      await app.request({
        method: "POST",
        url: "/api/v1/todos?user_id=" + userId,
        data: { title: title, source: "manual" }
      });
      wx.hideLoading();
      wx.showToast({ title: "待办已添加", icon: "success" });
      this.loadScheduleForDate(this.data.selectedDate);
    } catch (err) {
      wx.hideLoading();
      wx.showToast({ title: "添加失败", icon: "error" });
    }
  },

  async loadAISuggestion() {
    const cache = app.globalData.suggestionCache;
    if (cache && cache.text && (Date.now() - cache.timestamp < 300000)) {
      this.setData({ aiSuggestion: { loading: false, text: cache.text, hasError: false } });
      return;
    }
    this.setData({ "aiSuggestion.loading": true });
    try {
      const res = await app.request({
        method: "POST",
        url: "/api/v1/today/suggestion",
        data: { user_id: this.getUserId(), city: "青岛" }
      });
      const text = (res && res.suggestion) ? res.suggestion : "";
      app.globalData.suggestionCache = { text: text, timestamp: Date.now() };
      this.setData({
        aiSuggestion: { loading: false, text: text, hasError: false }
      });
    } catch (err) {
      this.setData({ aiSuggestion: { loading: false, text: "", hasError: true } });
    }
  },

  onShow() {
    if (this._hasShown && this.data.selectedDate) {
      this.loadCalendarEvents(this.data.currentYear, this.data.currentMonth);
      this.loadScheduleForDate(this.data.selectedDate);
    }
    this._hasShown = true;
  },

  onFabTap() { this.toggleFab(); },
  goBack() { wx.switchTab({ url: "/pages/index/index" }); }
});
