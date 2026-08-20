const { formatDate, toDateKey } = require("../utils/date");

const WEATHER = {
  0: "晴", 1: "少云", 2: "局部多云", 3: "多云", 45: "雾", 48: "冻雾",
  51: "小毛毛雨", 53: "中毛毛雨", 55: "大毛毛雨", 61: "小雨", 63: "中雨",
  65: "大雨", 71: "小雪", 73: "中雪", 75: "大雪", 80: "阵雨", 81: "中阵雨",
  82: "大阵雨", 95: "雷暴", 96: "冰雹雷暴"
};

const SOURCE_LABELS = {
  manual: "手动添加", ai_plan: "成长计划", pdf_import: "课表导入",
  excel_import: "考试导入", course: "课程", exam: "考试"
};

function weather(raw) {
  if (!raw) return { available: false, label: "天气暂不可用" };
  return {
    available: true,
    temp: typeof raw.temp === "number" ? raw.temp : null,
    condition: raw.condition || WEATHER[raw.code] || "天气",
    humidity: raw.humidity,
    icon: raw.icon || "",
    location: raw.location || "",
    advice: raw.advice || ""
  };
}

function course(raw) {
  const start = Number(raw.start || 0);
  const end = Number(raw.end || start || 0);
  return Object.assign({}, raw, {
    title: raw.name || raw.title || "未命名课程",
    periodLabel: start ? `第 ${start}${end && end !== start ? `-${end}` : ""} 节` : "节次待确认",
    sourceLabel: SOURCE_LABELS[raw.source] || "课程"
  });
}

function todo(raw) {
  return Object.assign({}, raw, {
    title: raw.title || raw.description || "未命名任务",
    deadlineLabel: raw.deadline ? formatDate(raw.deadline, false) : "未安排日期",
    sourceLabel: raw.source_label || SOURCE_LABELS[raw.source] || "待办",
    done: raw.status === "done" || raw.status === "archived",
    cancelled: raw.status === "cancelled"
  });
}

function exam(raw) {
  if (!raw) return null;
  return Object.assign({}, raw, {
    title: raw.subject || raw.title || "未命名考试",
    dateLabel: raw.exam_date ? formatDate(raw.exam_date, false) : "日期待确认"
  });
}

function normalizeOverview(raw) {
  raw = raw || {};
  const courses = (raw.courses_today || []).map(course);
  const todos = (raw.pending_todos || []).map(todo);
  return {
    userId: raw.user_id || "",
    date: raw.date || toDateKey(new Date()),
    greeting: raw.greeting || "今天好",
    weather: weather(raw.weather),
    coursesCount: Number.isFinite(raw.courses_count) ? raw.courses_count : courses.length,
    todosCount: Number.isFinite(raw.todos_count) ? raw.todos_count : todos.length,
    nearestExam: exam(raw.nearest_exam),
    courses,
    todos
  };
}

function event(raw) {
  const type = raw.event_type || raw.type || "todo";
  const labels = { course: "课程", exam: "考试", todo: "待办", ai_plan: "成长计划" };
  let timeLabel = raw.time ? `${raw.time}${raw.end_time ? `–${raw.end_time}` : ""}` : "全天";
  if (type === "course") {
    const start = Number(raw.sort_key || 0);
    const endHour = Number(String(raw.end_time || "").slice(0, 2));
    const end = endHour >= 9 ? endHour - 8 : start;
    timeLabel = start ? `第 ${start}${end && end !== start ? `-${end}` : ""} 节` : "节次待确认";
  }
  if (type === "exam" && (!raw.time || raw.time === "00:00")) timeLabel = "时间待定";
  return Object.assign({}, raw, {
    type,
    typeLabel: labels[type] || "事项",
    title: raw.title || "未命名事项",
    timeLabel
  });
}

function normalizeTimeline(raw) {
  raw = raw || {};
  const events = (raw.events || []).map(event);
  return { date: raw.date || "", total: Number.isFinite(raw.total) ? raw.total : events.length, events };
}

function normalizeCalendar(raw) {
  raw = raw || {};
  const leading = Math.max(0, Number(raw.first_weekday || 1) - 1);
  const blanks = Array.from({ length: leading }, (_, index) => ({ key: `blank-${index}`, blank: true }));
  const days = (raw.days || []).map((day) => ({
    key: day.date,
    date: day.date,
    number: Number(String(day.date || "").slice(-2)),
    isToday: Boolean(day.is_today),
    count: (day.events || []).length,
    level: Math.min(3, (day.events || []).length),
    events: (day.events || []).map(event)
  }));
  return { year: raw.year, month: raw.month, label: raw.month_label || `${raw.month || ""}月`, cells: blanks.concat(days), days };
}

function todayCompletion(allTodos, date) {
  const key = date || toDateKey(new Date());
  const due = (allTodos || []).filter((item) => item.deadline && String(item.deadline).slice(0, 10) === key && item.status !== "cancelled");
  if (!due.length) return { available: false, label: "今天暂无截止任务", completed: 0, total: 0, percent: 0 };
  const completed = due.filter((item) => item.status === "done" || item.status === "archived").length;
  return { available: true, label: `${completed}/${due.length} 已完成`, completed, total: due.length, percent: Math.round(completed / due.length * 100) };
}

module.exports = { WEATHER, SOURCE_LABELS, weather, course, todo, exam, event, normalizeOverview, normalizeTimeline, normalizeCalendar, todayCompletion };
