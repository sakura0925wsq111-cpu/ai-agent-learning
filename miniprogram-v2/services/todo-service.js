const { request } = require("./request");
const q = encodeURIComponent;
function list(userId, status) { return request({ url: `/api/v1/todos?user_id=${q(userId)}&status=${q(status || "all")}` }); }
function create(userId, payload) { return request({ method: "POST", url: `/api/v1/todos?user_id=${q(userId)}`, data: payload }); }
function update(userId, id, payload) { return request({ method: "PUT", url: `/api/v1/todos/${q(id)}?user_id=${q(userId)}`, data: payload }); }
function toggle(userId, id) { return request({ method: "POST", url: `/api/v1/todos/${q(id)}/toggle?user_id=${q(userId)}` }); }
function remove(userId, id) { return request({ method: "DELETE", url: `/api/v1/todos/${q(id)}?user_id=${q(userId)}` }); }
module.exports = { list, create, update, toggle, remove };
