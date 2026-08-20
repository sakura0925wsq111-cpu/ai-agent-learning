const { request } = require("./request");
const { upload } = require("./upload");

const q = encodeURIComponent;
function overview(userId, city) { return request({ url: `/api/v1/today/overview?user_id=${q(userId)}&city=${q(city || "北京")}` }); }
function timeline(userId, date) { return request({ url: `/api/v1/today/timeline?user_id=${q(userId)}${date ? `&date=${q(date)}` : ""}` }); }
function calendar(userId, year, month) { return request({ url: `/api/v1/today/calendar?user_id=${q(userId)}&year=${year}&month=${month}` }); }
function suggestion(userId, city) { return request({ method: "POST", url: "/api/v1/today/suggestion", data: { user_id: userId, city: city || "北京" } }); }
function courses(userId) { return request({ url: `/api/v1/today/courses?user_id=${q(userId)}` }); }
function createCourse(userId, payload) { return request({ method: "POST", url: `/api/v1/today/courses?user_id=${q(userId)}`, data: payload }); }
function updateCourse(userId, id, payload) { return request({ method: "PUT", url: `/api/v1/today/courses/${q(id)}?user_id=${q(userId)}`, data: payload }); }
function deleteCourse(userId, id) { return request({ method: "DELETE", url: `/api/v1/today/courses/${q(id)}?user_id=${q(userId)}` }); }
function exams(userId) { return request({ url: `/api/v1/today/exams?user_id=${q(userId)}` }); }
function createExam(userId, payload) { return request({ method: "POST", url: `/api/v1/today/exams?user_id=${q(userId)}`, data: payload }); }
function updateExam(userId, id, payload) { return request({ method: "PUT", url: `/api/v1/today/exams/${q(id)}?user_id=${q(userId)}`, data: payload }); }
function deleteExam(userId, id) { return request({ method: "DELETE", url: `/api/v1/today/exams/${q(id)}?user_id=${q(userId)}` }); }
function syncPlan(payload) { return request({ method: "POST", url: "/api/v1/today/sync-plan", data: payload }); }
function progress(userId, sessionId) { return request({ url: `/api/v1/today/progress?user_id=${q(userId)}&growth_session_id=${q(sessionId)}` }); }
function importFile(userId, filePath, type, onProgress, fileName) {
  const excel = type === "exam" && /\.(xlsx|xls)$/i.test(fileName || filePath);
  const url = excel
    ? `/api/v1/today/import/excel?user_id=${q(userId)}`
    : `/api/v1/today/import?user_id=${q(userId)}&import_type=${q(type)}`;
  return upload({ url, filePath, onProgress });
}
function preview(importId) { return request({ url: `/api/v1/today/import/preview?import_id=${q(importId)}` }); }
function confirmImport(importId, selectedIndexes) { return request({ method: "POST", url: "/api/v1/today/import/confirm", data: { import_id: importId, selected_indexes: selectedIndexes } }); }

module.exports = { overview, timeline, calendar, suggestion, courses, createCourse, updateCourse, deleteCourse, exams, createExam, updateExam, deleteExam, syncPlan, progress, importFile, preview, confirmImport };
