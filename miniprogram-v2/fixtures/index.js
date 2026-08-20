const today = {
  normal: { date: "2026-08-13", greeting: "下午好", weather: { temp: 28, code: 2, humidity: 68, location: "青岛" }, courses_count: 2, todos_count: 1, courses_today: [{ id: "c1", name: "数据结构", start: 1, end: 2, location: "教学楼 A201" }], pending_todos: [{ id: "t1", title: "整理项目复盘", deadline: "2026-08-13T20:00:00", status: "pending" }] },
  empty: { date: "2026-08-13", greeting: "下午好", weather: null, courses_count: 0, todos_count: 0, courses_today: [], pending_todos: [] },
  weatherFailure: { date: "2026-08-13", greeting: "下午好", weather: null, courses_count: 1, todos_count: 0, courses_today: [{ id: "c1", name: "数据结构", start: 1, end: 2 }], pending_todos: [] },
  partialFailure: { overview: { status: "success" }, timeline: { status: "error", message: "时间轨迹暂不可用" } }
};

const dashboard = {
  new: { page_state: "new", report_count: 0, coach: { available: false } },
  planning: { page_state: "planning", active_session: { session_id: "g1", agent: "career", current_step: 2, total_steps: 5 } },
  reportReady: { page_state: "report_ready", latest_report: { session_id: "g1", title: "就业指导报告", progress: 0 } },
  executing: { page_state: "executing", active_plan: { session_id: "g1", phase_key: "phase_1", completed: 1, total: 4, progress: 0.25 } }
};

const progress = {
  unsynced: { phases: [], overall_completion: 0 },
  partial: { phases: [{ phase_key: "phase_1", label: "第1-2周", total: 2, completed: 1, cancelled: 0, todos: [] }], total: 2, completed: 1, overall_completion: 0.5 },
  completed: { phases: [{ phase_key: "phase_1", label: "第1-2周", total: 2, completed: 2, cancelled: 0, todos: [] }], total: 2, completed: 2, overall_completion: 1 },
  cancelled: { phases: [{ phase_key: "phase_1", label: "第1-2周", total: 2, completed: 0, cancelled: 1, todos: [] }], total: 2, completed: 0, cancelled: 1, overall_completion: 0 }
};

const memory = {
  empty: { total: 0, max_capacity: 50, type_counts: {}, memories: [] },
  full: { total: 50, max_capacity: 50, type_counts: { profile: 8, goal: 12, action: 15, fact: 15 }, memories: [] },
  specialKey: { total: 1, max_capacity: 50, type_counts: { fact: 1 }, memories: [{ key: "偏好/地点&方向", value: "沿海城市", memory_type: "fact", confidence: 0.8, importance: 5, source: "手动设置" }] }
};

module.exports = { today, dashboard, progress, memory };
