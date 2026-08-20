const { request } = require("./request");
const q = encodeURIComponent;
function panel(userId, type) { return request({ url: `/api/v1/memory/panel/${q(userId)}?memory_type=${q(type || "all")}` }); }
function update(userId, key, value, memoryType) { return request({ method: "PATCH", url: `/api/v1/memory/panel/${q(userId)}/${q(key)}`, data: { value, memory_type: memoryType || "fact" } }); }
function remove(userId, key) { return request({ method: "DELETE", url: `/api/v1/memory/panel/${q(userId)}/${q(key)}` }); }
module.exports = { panel, update, remove };
