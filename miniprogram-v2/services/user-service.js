const { request } = require("./request");

function login(studentId, password) {
  return request({ method: "POST", url: "/api/v1/users/login", data: { student_id: studentId, password }, authRedirect: false });
}
function register(payload) { return request({ method: "POST", url: "/api/v1/users", data: payload, authRedirect: false }); }
function get(userId) { return request({ url: `/api/v1/users/${encodeURIComponent(userId)}` }); }
function update(userId, payload) { return request({ method: "PUT", url: `/api/v1/users/${encodeURIComponent(userId)}`, data: payload }); }
function remove(userId) { return request({ method: "DELETE", url: `/api/v1/users/${encodeURIComponent(userId)}` }); }

module.exports = { login, register, get, update, remove };
